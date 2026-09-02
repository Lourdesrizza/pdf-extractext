from datetime import datetime

from app.domain.entities.document import Document


def _document() -> Document:
    return Document(
        id="507f1f77bcf86cd799439011",
        filename="informe.pdf",
        checksum="a" * 64,
        extracted_text="Texto extraído",
        created_at=datetime(2026, 1, 1),
    )


def test_get_all_documents_returns_repository_documents(client, mock_document_repo):
    mock_document_repo.find_all.return_value = [_document()]

    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    assert response.json()[0]["filename"] == "informe.pdf"


def test_get_document_by_id_returns_document(client, mock_document_repo):
    document = _document()
    mock_document_repo.find_by_id.return_value = document

    response = client.get(f"/api/v1/documents/{document.id}")

    assert response.status_code == 200
    assert response.json()["checksum"] == document.checksum


def test_get_document_by_id_returns_problem_when_not_found(client):
    response = client.get("/api/v1/documents/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "Documento con ID 'missing' no encontrado"


def test_get_document_by_checksum_returns_document(client, mock_document_repo):
    document = _document()
    mock_document_repo.find_by_checksum.return_value = document

    response = client.get(f"/api/v1/documents/checksum/{document.checksum}")

    assert response.status_code == 200
    assert response.json()["id"] == document.id


def test_update_document_updates_filename(client, mock_document_repo):
    document = _document()
    mock_document_repo.find_by_id.return_value = document
    mock_document_repo.update.side_effect = lambda updated: updated

    response = client.patch(
        f"/api/v1/documents/{document.id}", json={"filename": " nuevo.pdf "}
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "nuevo.pdf"
    mock_document_repo.update.assert_awaited_once_with(document)


def test_delete_document_delegates_to_repository(client, mock_document_repo):
    document = _document()
    mock_document_repo.find_by_id.return_value = document

    response = client.delete(f"/api/v1/documents/{document.id}")

    assert response.status_code == 204
    mock_document_repo.delete.assert_awaited_once_with(document.id)
