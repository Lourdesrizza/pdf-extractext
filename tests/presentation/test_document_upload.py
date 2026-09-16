import hashlib
import tempfile
from datetime import datetime

from app.domain.entities.document import Document
from app.api.v1 import pdf_router
from app.services.pdf_service import PDFService

import pytest
import fitz 
from starlette.requests import Request



def _post_pdf(client, content, filename="test.pdf", content_type="application/pdf"):
    return client.post(
        "/api/v1/upload",
        content=content,
        headers={"content-type": content_type, "x-filename": filename},
    )


def test_upload_pdf_body_persists_document_and_preserves_filename(
    client, mock_document_repo
):
    text = "PDF recibido como body HTTP"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 50), text)
        pdf_bytes = pdf.tobytes()
    persisted = Document(
        id="507f1f77bcf86cd799439011",
        filename="informe-final.pdf",
        checksum=hashlib.sha256(pdf_bytes).hexdigest(),
        extracted_text=text,
        created_at=datetime(2026, 1, 1),
    )
    mock_document_repo.create.return_value = persisted

    response = client.post(
        "/api/v1/upload",
        content=pdf_bytes,
        headers={
            "content-type": "application/pdf",
            "x-filename": persisted.filename,
        },
    )

    assert response.status_code == 201
    assert response.json()["filename"] == persisted.filename
    mock_document_repo.create.assert_awaited_once()


def test_upload_pdf(client, mock_document_repo):
    """Test: Subida de PDF real con texto."""
    text = "\n".join(["Probando la API"] * 12)
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 50), text)
        pdf_bytes = doc.write()
    persisted = Document(
        id="507f1f77bcf86cd799439011",
        filename="test.pdf",
        checksum=hashlib.sha256(pdf_bytes).hexdigest(),
        extracted_text=text,
        created_at=datetime(2026, 1, 1),
    )
    mock_document_repo.create.return_value = persisted
    
    response = _post_pdf(client, pdf_bytes, "test.pdf")
    
    assert response.status_code == 201
    assert response.json() == {
        "id": persisted.id,
        "filename": persisted.filename,
        "checksum": persisted.checksum,
        "extracted_text": text,
        "created_at": "2026-01-01T00:00:00",
    }
    mock_document_repo.create.assert_awaited_once()
    submitted = mock_document_repo.create.await_args.args[0]
    assert submitted.id is None
    assert submitted.filename == persisted.filename
    assert submitted.checksum == persisted.checksum
    assert submitted.extracted_text == text
    mock_document_repo.find_by_checksum.assert_awaited_once_with(persisted.checksum)

def test_upload_filename_over_255_characters_returns_400(client, mock_document_repo):
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 50), "Texto del documento")
        content = pdf.tobytes()
    filename = "a" * 252 + ".pdf"
    mock_document_repo.create.return_value = Document(
        id="507f1f77bcf86cd799439011", filename=filename,
        checksum=hashlib.sha256(content).hexdigest(), extracted_text="Texto del documento",
    )

    response = _post_pdf(client, content, filename)

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 400
    assert response.json()["detail"] == "El nombre del archivo no puede superar los 255 caracteres"
    mock_document_repo.create.assert_not_called()


def test_upload_invalid_format(client, mock_document_repo):
    """Test: Rechazo de archivos TXT."""
    file_content = b"esto es texto"
    response = _post_pdf(client, file_content, "test.txt", "text/plain")
    
    assert response.status_code == 415
    assert response.json()["detail"] == "El Content-Type debe ser application/pdf"
    mock_document_repo.create.assert_not_called()
    
def test_upload_file_too_large(client, mock_document_repo):
    """Test: Simula el rechazo de un archivo que supera el límite de 5MB."""
    # Creamos un archivo falso pesado
    large_content = b"0" * (6 * 1024 * 1024) # 6 MB de ceros
    response = _post_pdf(client, large_content, "pesado.pdf")
    
    assert response.status_code == 413
    mock_document_repo.create.assert_not_called()

def test_api_health_check(client):
    """Test: Verifica que el servidor de FastAPI esté vivo y respondiendo."""
    response = client.get("/") # O la ruta de health que tengan
    assert response.status_code in [200, 404] # Al menos sabemos que el server responde
    
def test_upload_image_instead_of_pdf(client, mock_document_repo):
    """Test: Verifica qué pasa si el usuario intenta subir una imagen (PNG)."""
    # Simulamos el encabezado de un archivo de imagen real
    fake_image_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."
    response = _post_pdf(client, fake_image_content, "foto_amarillo.png", "image/png")
    
    assert response.status_code == 415
    assert response.json()["detail"] == "El Content-Type debe ser application/pdf"
    mock_document_repo.create.assert_not_called()
    
def test_upload_empty_file_0_bytes(client, mock_document_repo):
    """Test: Verifica que la API rechace un PDF que pesa 0 bytes."""
    # Le mandamos b"" (bytes vacíos)
    response = _post_pdf(client, b"", "vacio.pdf")
    
    # Debe tirar error de validación o Bad Request
    assert response.status_code == 400
    mock_document_repo.create.assert_not_called()


@pytest.mark.parametrize("kind", ["signature", "corrupt", "no-text"])
def test_upload_rejected_content_returns_problem_without_persisting(client, mock_document_repo, kind):
    if kind == "no-text":
        with fitz.open() as pdf:
            pdf.new_page()
            content = pdf.tobytes()
    else:
        content = b"texto" if kind == "signature" else b"%PDF-1.7\ncorrupto"

    response = _post_pdf(client, content, "test.pdf")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 400
    assert response.json()["detail"] == (
        "El contenido del archivo debe ser un PDF valido"
        if kind == "signature" else "El PDF no contiene texto extraíble"
    )
    mock_document_repo.create.assert_not_called()
    if kind == "signature":
        mock_document_repo.find_by_checksum.assert_not_called()
    else:
        mock_document_repo.find_by_checksum.assert_awaited_once_with(hashlib.sha256(content).hexdigest())


@pytest.mark.parametrize("race", [False, True], ids=["existing", "concurrent-insert"])
def test_duplicate_upload_returns_global_conflict(client, mock_document_repo, race):
    from app.domain.exceptions.domain_exceptions import DocumentAlreadyExistsError

    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 50), "Texto duplicado")
        content = pdf.tobytes()
    if race:
        mock_document_repo.create.side_effect = DocumentAlreadyExistsError("dato interno")
    else:
        mock_document_repo.find_by_checksum.return_value = Document(filename="original.pdf")
    response = _post_pdf(client, content, "renombrado.pdf")
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["status"] == 409
    assert payload["title"] == "Conflict"
    assert payload["type"] == "https://pdf-extactext.local/errors/document-already-exists"
    assert payload["detail"] == "El documento ya existe"
    assert "dato interno" not in response.text
    mock_document_repo.find_by_checksum.assert_awaited_once_with(hashlib.sha256(content).hexdigest())
    if race:
        mock_document_repo.create.assert_awaited_once()
    else:
        mock_document_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_upload_body_reader_stops_when_limit_is_exceeded():
    chunks = [b"%PDF-", b"0" * PDFService.MAX_FILE_SIZE_BYTES, b"not-read"]
    receive_calls = 0

    async def receive():
        nonlocal receive_calls
        receive_calls += 1
        body = chunks.pop(0)
        return {
            "type": "http.request",
            "body": body,
            "more_body": bool(chunks),
        }

    request = Request({"type": "http", "headers": []}, receive)

    with pytest.raises(Exception) as error:
        await pdf_router._read_pdf_body(request)

    assert getattr(error.value, "status_code", None) == 413
    assert receive_calls == 2
    assert chunks == [b"not-read"]


def test_normal_upload_does_not_invoke_temporary_file_apis(
    client, mock_document_repo, monkeypatch
):
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 50), "Procesado enteramente en memoria")
        content = pdf.tobytes()
    persisted = Document(
        id="507f1f77bcf86cd799439011",
        filename="memoria.pdf",
        checksum=hashlib.sha256(content).hexdigest(),
        extracted_text="Procesado enteramente en memoria",
    )
    mock_document_repo.create.return_value = persisted

    def fail_if_called(*args, **kwargs):
        raise AssertionError("El flujo de upload no debe crear archivos temporales")

    monkeypatch.setattr(tempfile, "SpooledTemporaryFile", fail_if_called)
    monkeypatch.setattr(tempfile, "TemporaryFile", fail_if_called)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", fail_if_called)

    response = _post_pdf(client, content, persisted.filename)

    assert response.status_code == 201
    mock_document_repo.create.assert_awaited_once()
