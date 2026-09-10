import hashlib
from datetime import datetime

from app.domain.entities.document import Document

import pytest
import fitz 



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
    
    files = {"file": ("test.pdf", pdf_bytes, "application/pdf")}
    # Usamos 'client' (el nombre del parámetro)
    response = client.post("/api/v1/upload", files=files)
    
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

    response = client.post(
        "/api/v1/upload", files={"file": (filename, content, "application/pdf")}
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 400
    assert response.json()["detail"] == "El nombre del archivo no puede superar los 255 caracteres"
    mock_document_repo.create.assert_not_called()


def test_upload_invalid_format(client, mock_document_repo):
    """Test: Rechazo de archivos TXT."""
    file_content = b"esto es texto"
    files = {"file": ("test.txt", file_content, "text/plain")}
    
    response = client.post("/api/v1/upload", files=files)
    
    assert response.status_code == 400
    assert response.json()["detail"] == "El archivo debe ser un PDF"
    mock_document_repo.create.assert_not_called()
    
def test_upload_file_too_large(client, mock_document_repo):
    """Test: Simula el rechazo de un archivo que supera el límite de 5MB."""
    # Creamos un archivo falso pesado
    large_content = b"0" * (6 * 1024 * 1024) # 6 MB de ceros
    files = {"file": ("pesado.pdf", large_content, "application/pdf")}
    
    response = client.post("/api/v1/upload", files=files)
    
    # Dependiendo de cómo lo configuraste, FastAPI podría cortar la conexión 
    # o devolver un 413 (Payload Too Large) o 400.
    assert response.status_code == 400
    mock_document_repo.create.assert_not_called()

def test_api_health_check(client):
    """Test: Verifica que el servidor de FastAPI esté vivo y respondiendo."""
    response = client.get("/") # O la ruta de health que tengan
    assert response.status_code in [200, 404] # Al menos sabemos que el server responde
    
def test_upload_image_instead_of_pdf(client, mock_document_repo):
    """Test: Verifica qué pasa si el usuario intenta subir una imagen (PNG)."""
    # Simulamos el encabezado de un archivo de imagen real
    fake_image_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."
    files = {"file": ("foto_amarillo.png", fake_image_content, "image/png")}
    
    response = client.post("/api/v1/upload", files=files)
    
    # La API debería rebotarlo por el formato
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"] # Asegura que el mensaje avise que debe ser PDF
    mock_document_repo.create.assert_not_called()
    
def test_upload_empty_file_0_bytes(client, mock_document_repo):
    """Test: Verifica que la API rechace un PDF que pesa 0 bytes."""
    # Le mandamos b"" (bytes vacíos)
    files = {"file": ("vacio.pdf", b"", "application/pdf")}
    response = client.post("/api/v1/upload", files=files)
    
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

    response = client.post(
        "/api/v1/upload", files={"file": ("test.pdf", content, "application/pdf")}
    )

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
    response = client.post(
        "/api/v1/upload", files={"file": ("renombrado.pdf", content, "application/pdf")}
    )
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
