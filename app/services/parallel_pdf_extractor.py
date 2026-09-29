"""Extracción por procesos, con un buffer compartido y uso de memoria acotado."""

import asyncio
import atexit
import logging
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from multiprocessing.shared_memory import SharedMemory
from time import perf_counter

import fitz

from app.services.pdf_service import PDFService

logger = logging.getLogger("uvicorn.error")
_worker_memory: SharedMemory | None = None


def _initialize_worker(name: str, barrier) -> None:
    global _worker_memory
    _worker_memory = SharedMemory(name=name)
    atexit.register(_worker_memory.close)
    # Inicializa el motor con un documento efímero genérico, sin leer ni
    # conservar documentos de usuarios o resultados de extracción.
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((50, 50), "PDF extraction worker ready")
        page.get_text()
    barrier.wait(timeout=60)


def _ready() -> bool:
    return _worker_memory is not None


def _extract_pages(size: int, start: int, end: int, step: int) -> tuple[list[str], float]:
    if _worker_memory is None:
        raise RuntimeError("El trabajador no fue inicializado")
    started = perf_counter()
    view = _worker_memory.buf[:size]
    try:
        with fitz.open(stream=view, filetype="pdf") as document:
            pages = [document[index].get_text() for index in range(start, end, step)]
        return pages, (perf_counter() - started) * 1000
    finally:
        view.release()


class ParallelPDFExtractor:
    """Un solo PDF en vuelo por instancia; las demás peticiones esperan el buffer."""

    def __init__(self, workers: int | None = None, min_pages: int = 128) -> None:
        self.workers = workers if workers is not None else min(8, os.cpu_count() or 1)
        if not 1 <= self.workers <= 8:
            raise ValueError("La cantidad de trabajadores debe estar entre 1 y 8")
        if min_pages < 1:
            raise ValueError("min_pages debe ser positivo")
        self.min_pages = min_pages
        self._memory: SharedMemory | None = None
        self._pool: ProcessPoolExecutor | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        await asyncio.to_thread(self._start)

    def _start(self) -> None:
        if self._pool is not None:
            return
        started = perf_counter()
        # Crear el segmento antes de los procesos comparte también su tracker.
        self._memory = SharedMemory(
            create=True, size=PDFService.MAX_EXTRACTION_FILE_SIZE_BYTES
        )
        try:
            self._memory.buf[:] = b"\0" * self._memory.size
            # El forkserver carga PyMuPDF sin abrir documentos ni heredar el
            # cliente Mongo/threads de la API. Sus hijos comparten esas páginas
            # de memoria; en Windows se conserva el arranque mediante spawn.
            method = "spawn"
            if "forkserver" in multiprocessing.get_all_start_methods():
                multiprocessing.set_forkserver_preload([__name__])
                method = "forkserver"
            context = multiprocessing.get_context(method)
            self._pool = ProcessPoolExecutor(
                max_workers=self.workers,
                mp_context=context,
                initializer=_initialize_worker,
                initargs=(self._memory.name, context.Barrier(self.workers)),
            )
            futures = [self._pool.submit(_ready) for _ in range(self.workers)]
            for future in futures:
                future.result(timeout=90)
            logger.info(
                "parallel_startup workers=%d method=%s duration_ms=%.2f",
                self.workers, method, (perf_counter() - started) * 1000,
            )
        except BaseException:
            self._close()
            raise

    async def close(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._close)

    def _close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None
        if self._memory is not None:
            self._memory.close()
            self._memory.unlink()
            self._memory = None

    async def extract_text(self, content: bytes) -> str:
        if self._pool is None or self._memory is None:
            return PDFService.extract_text(content)
        if len(content) > PDFService.MAX_EXTRACTION_FILE_SIZE_BYTES:
            raise ValueError("El archivo no puede superar los 20MB")
        try:
            with fitz.open(stream=content, filetype="pdf") as document:
                page_count = len(document)
        except Exception:
            return PDFService.extract_text(content)
        if page_count < self.min_pages:
            return PDFService.extract_text(content)

        async with self._lock:
            started = perf_counter()
            self._memory.buf[:len(content)] = content
            return await self._extract_shared(
                len(content), page_count, (perf_counter() - started) * 1000
            )

    @asynccontextmanager
    async def receive_buffer(self):
        """Reserva el buffer hasta finalizar la lectura y la extracción."""
        if self._memory is None or self._pool is None:
            yield None
            return
        async with self._lock:
            view = self._memory.buf[:]
            try:
                yield view
            finally:
                view.release()

    async def extract_received(self, size: int) -> str:
        """Extrae el cuerpo recibido; requiere mantener receive_buffer abierto."""
        if not 0 <= size <= PDFService.MAX_EXTRACTION_FILE_SIZE_BYTES:
            raise ValueError("El archivo no puede superar los 20MB")
        view = self._memory.buf[:size]
        try:
            try:
                with fitz.open(stream=view, filetype="pdf") as document:
                    page_count = len(document)
            except Exception:
                return PDFService.extract_text(bytes(view))
            if page_count < self.min_pages:
                return PDFService.extract_text(bytes(view))
            return await self._extract_shared(size, page_count, 0.0)
        finally:
            view.release()

    async def _extract_shared(self, size: int, page_count: int, copy_ms: float) -> str:
        copied = perf_counter()
        loop = asyncio.get_running_loop()
        futures = []
        submission_failed = False
        for index in range(self.workers):
            try:
                futures.append(loop.run_in_executor(
                    self._pool, _extract_pages, size,
                    index, page_count, self.workers,
                ))
            except Exception:
                submission_failed = True
                break
        # No reutilizar el buffer mientras queden procesos leyendo, incluso
        # si el cliente cancela o falla una de las tareas.
        pending = asyncio.gather(*futures, return_exceptions=True)
        cancelled = False
        while True:
            try:
                results = await asyncio.shield(pending)
                break
            except asyncio.CancelledError:
                cancelled = True
        if cancelled:
            raise asyncio.CancelledError
        finished = perf_counter()
        page_results = [
            result for result in results if not isinstance(result, BaseException)
        ]
        if submission_failed or len(page_results) != len(results):
            logger.warning("Fallo de extracción paralela; se usa extracción secuencial")
            return PDFService.extract_text(bytes(self._memory.buf[:size]))
        ordered_pages = [""] * page_count
        for index, (pages, _) in enumerate(page_results):
            ordered_pages[index::self.workers] = pages
        text = "\n".join(ordered_pages).strip()
        logger.info(
            "parallel_profile workers=%d pages=%d copy_ms=%.2f "
            "dispatch_gather_ms=%.2f worker_max_ms=%.2f join_ms=%.2f worker_ms=%s",
            self.workers, page_count, copy_ms,
            (finished - copied) * 1000, max(elapsed for _, elapsed in page_results),
            (perf_counter() - finished) * 1000,
            [round(elapsed, 2) for _, elapsed in page_results],
        )
        return text
