"""Endpoint sin estado para medir la extracción de PDFs."""

import logging
import hashlib
from time import perf_counter_ns, process_time_ns

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.services.pdf_service import PDFService

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


async def _read_extract_body(
    request: Request, target: memoryview | None = None,
) -> bytes | memoryview:
    """Lee el PDF por fragmentos y limita el cuerpo a 20 MiB."""
    max_size = PDFService.MAX_EXTRACTION_FILE_SIZE_BYTES
    content_length = request.headers.get("content-length")
    if content_length is not None:
        declared_length = content_length.strip()
        # Solo interpretamos dígitos ASCII. Encabezados inválidos se ignoran:
        # el límite real sobre los fragmentos siempre se aplica más abajo.
        if declared_length and declared_length.isascii() and declared_length.isdecimal():
            if len(declared_length) > len(str(max_size)):
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="El archivo no puede superar los 20MB",
                )
            if int(declared_length) > max_size:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="El archivo no puede superar los 20MB",
                )

    chunks: list[bytes] = []
    total_size = 0
    started_at = perf_counter_ns()
    cpu_started_at = process_time_ns()
    processing_ns = 0
    chunk_count = 0
    async for chunk in request.stream():
        chunk_started_at = perf_counter_ns()
        total_size += len(chunk)
        if total_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="El archivo no puede superar los 20MB",
            )
        if target is None:
            chunks.append(chunk)
        else:
            target[total_size - len(chunk):total_size] = chunk
        chunk_count += 1
        processing_ns += perf_counter_ns() - chunk_started_at
    joined_at = perf_counter_ns()
    body = b"".join(chunks) if target is None else target[:total_size]
    finished_at = perf_counter_ns()
    logger.info(
        "read_profile chunks=%d receive_wait_ms=%.2f python_ms=%.2f join_ms=%.2f cpu_ms=%.2f",
        chunk_count,
        (joined_at - started_at - processing_ns) / 1_000_000,
        processing_ns / 1_000_000,
        (finished_at - joined_at) / 1_000_000,
        (process_time_ns() - cpu_started_at) / 1_000_000,
    )
    return body


@router.post("/extract", status_code=status.HTTP_200_OK)
async def extract_pdf(request: Request) -> JSONResponse:
    """Extrae texto desde un PDF binario sin persistirlo."""
    media_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if media_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El Content-Type debe ser application/pdf",
        )

    started_at = perf_counter_ns()
    extractor = request.app.state.pdf_extractor
    async with extractor.receive_buffer() as target:
        content = None
        try:
            content = await _read_extract_body(request, target)
            content_size = len(content)
            body_read_at = perf_counter_ns()
            try:
                PDFService.validate_pdf_content(
                    content,
                    max_file_size_bytes=PDFService.MAX_EXTRACTION_FILE_SIZE_BYTES,
                )
            except ValueError as error:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(error),
                ) from error
            validated_at = perf_counter_ns()
            text = (
                await extractor.extract_received(content_size)
                if target is not None
                else await extractor.extract_text(content)
            )
        finally:
            if isinstance(content, memoryview):
                content.release()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo extraer texto del PDF",
        )
    extracted_at = perf_counter_ns()
    response = JSONResponse(content={"text": text})
    text_checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    prepared_at = perf_counter_ns()
    logger.info(
        "extract_profile bytes=%d body_ms=%.2f validation_ms=%.2f "
        "extraction_ms=%.2f response_ms=%.2f total_ms=%.2f chars=%d sha256=%s",
        content_size,
        (body_read_at - started_at) / 1_000_000,
        (validated_at - body_read_at) / 1_000_000,
        (extracted_at - validated_at) / 1_000_000,
        (prepared_at - extracted_at) / 1_000_000,
        (prepared_at - started_at) / 1_000_000,
        len(text),
        text_checksum,
    )
    return response
