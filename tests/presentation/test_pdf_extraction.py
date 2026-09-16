import fitz
from unittest.mock import Mock

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
