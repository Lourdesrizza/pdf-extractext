import fitz
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError


def test_get_all_documents_returns_503_when_mongo_is_unavailable(
    client,
    mock_document_repo,
):
    mock_document_repo.find_all.side_effect = ServerSelectionTimeoutError(
        "timeout simulado"
    )

    response = client.get("/api/v1/documents")

    assert response.status_code == 503
    assert response.json()["detail"] == "Base de datos no disponible"


@pytest.mark.parametrize(
    ("error_type", "expected_status", "detail"),
    [
        (ServerSelectionTimeoutError, 503, "Base de datos no disponible"),
        (PyMongoError, 503, "Base de datos no disponible"),
        (RuntimeError, 500, "Ocurrio un error interno inesperado."),
        (ValueError, 500, "Ocurrio un error interno inesperado."),
    ],
)
def test_upload_persistence_errors_return_problem(
    client, mock_document_repo, error_type, expected_status, detail
):
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 50), "Texto para guardar")
        content = pdf.tobytes()
    mock_document_repo.create.side_effect = error_type("fallo simulado")

    # Inspeccionamos la respuesta 500 en vez de relanzar la excepción del servidor.
    with TestClient(client.app, raise_server_exceptions=False) as error_client:
        response = error_client.post(
            "/api/v1/upload",
            content=content,
            headers={
                "content-type": "application/pdf",
                "x-filename": "test.pdf",
            },
        )

    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == expected_status
    assert response.json()["detail"] == detail
    mock_document_repo.create.assert_awaited_once()
    mock_document_repo.find_by_checksum.assert_awaited_once()


def test_upload_lookup_error_returns_503_without_creation(client, mock_document_repo):
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 50), "Texto")
        content = pdf.tobytes()
    mock_document_repo.find_by_checksum.side_effect = PyMongoError("dato interno")
    response = client.post(
        "/api/v1/upload",
        content=content,
        headers={
            "content-type": "application/pdf",
            "x-filename": "test.pdf",
        },
    )
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "Base de datos no disponible"
    assert "dato interno" not in response.text
    mock_document_repo.create.assert_not_called()
