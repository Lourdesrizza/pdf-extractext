import fitz
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from unittest.mock import Mock

from app.api.v1.extraction_router import _read_extract_body
from app.services.pdf_service import PDFService


def _pdf_bytes(text: str = "Texto para extraer") -> bytes:
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 50), text)
        return pdf.tobytes()


def test_extract_valid_pdf_returns_extracted_text(client):
    response = client.post(
        "/extract",
        content=_pdf_bytes("Contenido real del PDF"),
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 200
    assert "Contenido real del PDF" in response.json()["text"]


def test_extract_invalid_pdf_is_rejected(client):
    response = client.post(
        "/extract",
        content=b"%PDF-1.7\ncontenido-corrupto",
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "No se pudo extraer texto del PDF"


def test_extract_rejects_non_pdf_content_type(client):
    response = client.post(
        "/extract",
        content=_pdf_bytes(),
        headers={"content-type": "application/octet-stream"},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "El Content-Type debe ser application/pdf"


def test_extract_rejects_empty_body(client):
    response = client.post(
        "/extract",
        content=b"",
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "El archivo no puede estar vacio"


def test_extract_delegates_to_existing_pdf_service(client, monkeypatch):
    content = _pdf_bytes()
    extract_text = Mock(return_value="Texto extraído por el servicio")
    monkeypatch.setattr(PDFService, "extract_text", extract_text)

    response = client.post(
        "/extract",
        content=content,
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Texto extraído por el servicio"}
    extract_text.assert_called_once_with(content)


def test_extract_accepts_pdf_larger_than_upload_limit(client, monkeypatch):
    content = b"%PDF-1.7\n" + b"0" * (17 * 1024 * 1024)
    extract_text = Mock(return_value="Texto del PDF grande")
    monkeypatch.setattr(PDFService, "extract_text", extract_text)

    response = client.post(
        "/extract",
        content=content,
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Texto del PDF grande"}
    extract_text.assert_called_once_with(content)


def test_extract_returns_413_when_streamed_body_exceeds_20_mib(client, monkeypatch):
    content = b"%PDF-1.7\n" + b"0" * (20 * 1024 * 1024)
    extract_text = Mock(return_value="No debería extraer")
    monkeypatch.setattr(PDFService, "extract_text", extract_text)

    response = client.post(
        "/extract",
        content=content,
        headers={"content-type": "application/pdf", "content-length": "1"},
    )

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 413
    extract_text.assert_not_called()


def test_extract_returns_413_when_declared_body_exceeds_20_mib(client, monkeypatch):
    extract_text = Mock(return_value="No debería extraer")
    monkeypatch.setattr(PDFService, "extract_text", extract_text)

    response = client.post(
        "/extract",
        content=_pdf_bytes(),
        headers={
            "content-type": "application/pdf",
            "content-length": str(20 * 1024 * 1024 + 1),
        },
    )

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    extract_text.assert_not_called()


def test_extract_ignores_invalid_content_length_and_still_checks_body(client, monkeypatch):
    content = _pdf_bytes()
    extract_text = Mock(return_value="Texto extraído")
    monkeypatch.setattr(PDFService, "extract_text", extract_text)

    response = client.post(
        "/extract",
        content=content,
        headers={"content-type": "application/pdf", "content-length": "invalid"},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Texto extraído"}
    extract_text.assert_called_once_with(content)


def test_extract_accepts_stream_without_content_length(client, monkeypatch):
    content = _pdf_bytes()
    extract_text = Mock(return_value="Texto extraído")
    monkeypatch.setattr(PDFService, "extract_text", extract_text)

    response = client.post(
        "/extract",
        content=iter([content[:3], content[3:8], content[8:]]),
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Texto extraído"}
    extract_text.assert_called_once_with(content)


def test_extract_does_not_use_document_repository(client, mock_document_repo):
    response = client.post(
        "/extract",
        content=_pdf_bytes(),
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 200
    mock_document_repo.find_by_checksum.assert_not_called()
    mock_document_repo.create.assert_not_called()
    mock_document_repo.update.assert_not_called()
    mock_document_repo.delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("declared", [None, "invalid", "1"])
async def test_direct_receive_checks_limit_before_writing(monkeypatch, declared):
    monkeypatch.setattr(PDFService, "MAX_EXTRACTION_FILE_SIZE_BYTES", 8)
    chunks = iter([b"%PDF-", b"1234"])

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    headers = [] if declared is None else [(b"content-length", declared.encode())]
    request = Request({"type": "http", "headers": headers}, receive)
    storage = bytearray(8)
    with memoryview(storage) as target:
        with pytest.raises(HTTPException) as error:
            await _read_extract_body(request, target)
    assert error.value.status_code == 413
    assert storage == b"%PDF-\0\0\0"


@pytest.mark.asyncio
async def test_direct_receive_preserves_fragment_order():
    chunks = iter([b"%PD", b"F-", b"123"])

    async def receive():
        chunk = next(chunks)
        return {"type": "http.request", "body": chunk, "more_body": chunk != b"123"}

    request = Request({"type": "http", "headers": []}, receive)
    storage = bytearray(8)
    with memoryview(storage) as target:
        content = await _read_extract_body(request, target)
        try:
            assert content == b"%PDF-123"
            PDFService.validate_pdf_content(content)
        finally:
            content.release()
