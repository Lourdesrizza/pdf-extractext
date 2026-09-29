import asyncio
import hashlib
import importlib
from contextlib import asynccontextmanager
from multiprocessing.shared_memory import SharedMemory
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fitz
import pytest

from app.services.parallel_pdf_extractor import ParallelPDFExtractor
from app.services.pdf_service import PDFService


def _pdf(label: str) -> bytes:
    with fitz.open() as document:
        for index in range(7):
            page = document.new_page()
            page.insert_text((50, 50), f"{label} - página {index}: texto único")
        return document.tobytes()


@pytest.mark.asyncio
async def test_real_processes_preserve_text_order_isolation_and_release_memory(monkeypatch):
    extractor = ParallelPDFExtractor(workers=2, min_pages=2)
    await extractor.start()
    pool = extractor._pool
    name = extractor._memory.name
    documents = [_pdf("Primero"), _pdf("Segundo")]
    expected = [PDFService.extract_text(content) for content in documents]
    try:
        async def receive_and_extract(content):
            async with extractor.receive_buffer() as target:
                target[:len(content)] = content
                return await extractor.extract_received(len(content))

        assert await asyncio.gather(
            *(receive_and_extract(content) for content in documents)
        ) == expected
        for _ in range(2):
            actual = await asyncio.gather(
                *(extractor.extract_text(content) for content in documents)
            )
            assert actual == expected
            assert [hashlib.sha256(text.encode()).hexdigest() for text in actual] == [
                hashlib.sha256(text.encode()).hexdigest() for text in expected
            ]
            assert extractor._pool is pool
        interrupted = asyncio.create_task(receive_and_extract(documents[0]))
        await asyncio.sleep(0)
        interrupted.cancel()
        replacement = asyncio.create_task(receive_and_extract(documents[1]))
        with pytest.raises(asyncio.CancelledError):
            await interrupted
        assert await replacement == expected[1]

        # Si el executor falla tras enviar una tarea, se espera a los lectores
        # y se conserva la salida mediante la extracción secuencial.
        original_submit = pool.submit
        submissions = 0

        def fail_second_submit(*args, **kwargs):
            nonlocal submissions
            submissions += 1
            if submissions == 2:
                raise RuntimeError("executor unavailable")
            return original_submit(*args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(pool, "submit", fail_second_submit)
            assert await extractor.extract_text(documents[0]) == expected[0]
        assert await extractor.extract_text(documents[1]) == expected[1]
        assert await extractor.extract_text(b"%PDF-corrupto") == ""
        assert await receive_and_extract(b"%PDF-corrupto") == ""
        with pytest.raises(ValueError, match="20MB"):
            await extractor.extract_text(b"0" * (20 * 1024 * 1024 + 1))
    finally:
        await extractor.close()
    assert extractor._pool is None
    assert extractor._memory is None
    with pytest.raises(FileNotFoundError):
        SharedMemory(name=name)


@pytest.mark.parametrize("workers", [0, 9])
def test_worker_count_is_bounded(workers):
    with pytest.raises(ValueError, match="entre 1 y 8"):
        ParallelPDFExtractor(workers=workers)


@pytest.mark.asyncio
async def test_startup_failure_releases_shared_buffer(monkeypatch):
    module = importlib.import_module("app.services.parallel_pdf_extractor")
    extractor = ParallelPDFExtractor(workers=2)
    names = []

    def allocate(**kwargs):
        memory = SharedMemory(**kwargs)
        names.append(memory.name)
        return memory

    def fail_executor(**kwargs):
        raise RuntimeError("cannot start executor")

    monkeypatch.setattr(module, "SharedMemory", allocate)
    monkeypatch.setattr(module, "ProcessPoolExecutor", fail_executor)
    with pytest.raises(RuntimeError, match="cannot start executor"):
        await extractor.start()
    assert extractor._memory is None
    with pytest.raises(FileNotFoundError):
        SharedMemory(name=names[0])


@pytest.mark.asyncio
async def test_application_lifespan_closes_extractor_on_failure(monkeypatch):
    module = importlib.import_module("app.main")
    extractor = SimpleNamespace(start=AsyncMock(), close=AsyncMock())
    app = SimpleNamespace(state=SimpleNamespace())

    @asynccontextmanager
    async def database_lifespan(app):
        yield

    monkeypatch.setattr(module, "database_lifespan", database_lifespan)
    monkeypatch.setattr(module, "ParallelPDFExtractor", lambda: extractor)
    with pytest.raises(RuntimeError, match="request failed"):
        async with module.application_lifespan(app):
            assert app.state.pdf_extractor is extractor
            raise RuntimeError("request failed")
    extractor.start.assert_awaited_once()
    extractor.close.assert_awaited_once()
    assert not hasattr(app.state, "pdf_extractor")
