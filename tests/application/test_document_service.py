import hashlib
from dataclasses import replace
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import fitz
import pytest
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from app.application.services.document_service import DocumentService
from app.core.exceptions import ValidationException
from app.domain.entities.document import Document
from app.domain.repositories.document_repository import DocumentRepository
from app.domain.exceptions.domain_exceptions import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
)
from app.services.pdf_service import PDFService


def pdf_bytes(text="Texto del documento"):
    with fitz.open() as pdf:
        page = pdf.new_page()
        if text:
            page.insert_text((50, 50), text)
        return pdf.tobytes()


@pytest.mark.asyncio
async def test_upload_persists_once_and_returns_repository_document():
    content = pdf_bytes()
    repository = AsyncMock(spec=DocumentRepository)
    repository.find_by_checksum.return_value = None
    persisted = Document(
        id="507f1f77bcf86cd799439011",
        filename="informe.pdf",
        checksum=hashlib.sha256(content).hexdigest(),
        extracted_text="Texto del documento",
        created_at=datetime(2026, 1, 1),
    )
    repository.create.return_value = persisted

    result = await DocumentService(repository).upload_pdf("informe.pdf", content)

    repository.create.assert_awaited_once()
    submitted = repository.create.await_args.args[0]
    assert isinstance(submitted, Document)
    assert submitted.id is None
    assert submitted.filename == persisted.filename
    assert submitted.checksum == persisted.checksum
    assert submitted.extracted_text == persisted.extracted_text
    assert result is persisted
    repository.find_by_checksum.assert_awaited_once_with(persisted.checksum)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [PyMongoError, ServerSelectionTimeoutError, RuntimeError, ValueError])
async def test_persistence_error_is_propagated(error_type):
    repository = AsyncMock(spec=DocumentRepository)
    repository.find_by_checksum.return_value = None
    failure = error_type("fallo simulado")
    repository.create.side_effect = failure

    with pytest.raises(error_type) as error:
        await DocumentService(repository).upload_pdf("test.pdf", pdf_bytes())

    assert error.value is failure
    repository.create.assert_awaited_once()
    repository.find_by_checksum.assert_awaited_once()


@pytest.mark.asyncio
async def test_filename_over_255_characters_is_not_persisted():
    repository = AsyncMock(spec=DocumentRepository)
    filename = "a" * 252 + ".pdf"

    with pytest.raises(ValidationException) as error:
        await DocumentService(repository).upload_pdf(filename, pdf_bytes())

    assert error.value.field == "filename"
    assert error.value.message == "El nombre del archivo no puede superar los 255 caracteres"
    repository.create.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("", b"%PDF-", "El archivo debe ser un PDF"),
        ("archivo.txt", b"texto", "El archivo debe ser un PDF"),
        ("vacio.pdf", b"", "El archivo no puede estar vacio"),
        ("grande.pdf", b"0" * (5 * 1024 * 1024 + 1), "El archivo no puede superar los 5MB"),
        ("falso.pdf", b"texto", "El contenido del archivo debe ser un PDF valido"),
        ("corrupto.pdf", b"%PDF-1.7\ncorrupto", "El PDF no contiene texto extraíble"),
        ("sin-texto.pdf", pdf_bytes(""), "El PDF no contiene texto extraíble"),
    ],
    ids=["missing-name", "extension", "empty", "size", "signature", "corrupt", "no-text"],
)
async def test_rejected_pdf_is_not_persisted(filename, content, message):
    repository = AsyncMock(spec=DocumentRepository)
    repository.find_by_checksum.return_value = None

    with pytest.raises(ValidationException) as error:
        await DocumentService(repository).upload_pdf(filename, content)

    assert error.value.message == message
    repository.create.assert_not_called()
    if filename in ("corrupto.pdf", "sin-texto.pdf"):
        repository.find_by_checksum.assert_awaited_once_with(hashlib.sha256(content).hexdigest())
    else:
        repository.find_by_checksum.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_is_rejected_before_extraction(monkeypatch):
    content = pdf_bytes()
    repository = AsyncMock(spec=DocumentRepository)
    repository.find_by_checksum.return_value = Document(filename="otro-nombre.pdf")
    extract = Mock(side_effect=AssertionError("No debe extraer un duplicado"))
    monkeypatch.setattr(PDFService, "extract_text", extract)

    with pytest.raises(DocumentAlreadyExistsError):
        await DocumentService(repository).upload_pdf("nuevo-nombre.pdf", content)

    repository.find_by_checksum.assert_awaited_once_with(hashlib.sha256(content).hexdigest())
    extract.assert_not_called()
    repository.create.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_error_prevents_extraction_and_creation(monkeypatch):
    repository = AsyncMock(spec=DocumentRepository)
    repository.find_by_checksum.side_effect = PyMongoError("fallo de consulta")
    extract = Mock()
    monkeypatch.setattr(PDFService, "extract_text", extract)
    with pytest.raises(PyMongoError):
        await DocumentService(repository).upload_pdf("test.pdf", pdf_bytes())
    extract.assert_not_called()
    repository.create.assert_not_called()


@pytest.mark.asyncio
async def test_same_filename_different_contents_are_allowed_but_same_bytes_are_rejected():
    stored = {}
    repository = AsyncMock(spec=DocumentRepository)
    repository.find_by_checksum.side_effect = stored.get

    def save(document):
        persisted = replace(document, id=str(len(stored) + 1))
        stored[document.checksum] = persisted
        return persisted

    repository.create.side_effect = save
    service = DocumentService(repository)
    first_content = pdf_bytes("Primer contenido")
    first = await service.upload_pdf("informe.pdf", first_content)
    second = await service.upload_pdf("informe.pdf", pdf_bytes("Segundo contenido"))
    with pytest.raises(DocumentAlreadyExistsError):
        await service.upload_pdf("renombrado.pdf", first_content)

    assert first.checksum != second.checksum
    assert first.id != second.id
    assert repository.create.await_count == 2
    assert len(stored) == 2


@pytest.mark.asyncio
async def test_list_documents_returns_repository_documents():
    repository = AsyncMock(spec=DocumentRepository)
    documents = [Document(id="1", filename="uno.pdf"), Document(id="2", filename="dos.pdf")]
    repository.find_all.return_value = documents

    result = await DocumentService(repository).get_all_documents()

    assert result == documents
    repository.find_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_document_by_id_returns_existing_document():
    repository = AsyncMock(spec=DocumentRepository)
    document = Document(id="document-id", filename="informe.pdf")
    repository.find_by_id.return_value = document

    result = await DocumentService(repository).get_document_by_id(document.id)

    assert result is document
    repository.find_by_id.assert_awaited_once_with(document.id)


@pytest.mark.asyncio
async def test_get_document_by_id_raises_when_document_does_not_exist():
    repository = AsyncMock(spec=DocumentRepository)
    repository.find_by_id.return_value = None

    with pytest.raises(DocumentNotFoundError) as error:
        await DocumentService(repository).get_document_by_id("missing")

    assert str(error.value) == "Documento con ID 'missing' no encontrado"
    repository.find_by_id.assert_awaited_once_with("missing")


@pytest.mark.asyncio
async def test_get_document_by_checksum_returns_existing_document():
    repository = AsyncMock(spec=DocumentRepository)
    checksum = "a" * 64
    document = Document(id="document-id", filename="informe.pdf", checksum=checksum)
    repository.find_by_checksum.return_value = document

    result = await DocumentService(repository).get_document_by_checksum(checksum)

    assert result is document
    repository.find_by_checksum.assert_awaited_once_with(checksum)


@pytest.mark.asyncio
async def test_get_document_by_checksum_raises_when_document_does_not_exist():
    repository = AsyncMock(spec=DocumentRepository)
    checksum = "missing-checksum"
    repository.find_by_checksum.return_value = None

    with pytest.raises(DocumentNotFoundError) as error:
        await DocumentService(repository).get_document_by_checksum(checksum)

    assert str(error.value) == f"Documento con checksum '{checksum}' no encontrado"
    repository.find_by_checksum.assert_awaited_once_with(checksum)


@pytest.mark.asyncio
async def test_update_document_filename_persists_existing_document():
    repository = AsyncMock(spec=DocumentRepository)
    document = Document(id="document-id", filename="original.pdf")
    repository.find_by_id.return_value = document
    repository.update.side_effect = lambda updated: updated

    result = await DocumentService(repository).update_document_filename(
        document.id, " actualizado.pdf "
    )

    assert result is document
    assert result.filename == "actualizado.pdf"
    repository.find_by_id.assert_awaited_once_with(document.id)
    repository.update.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_update_document_filename_raises_when_document_does_not_exist():
    repository = AsyncMock(spec=DocumentRepository)
    repository.find_by_id.return_value = None

    with pytest.raises(DocumentNotFoundError):
        await DocumentService(repository).update_document_filename("missing", "nuevo.pdf")

    repository.find_by_id.assert_awaited_once_with("missing")
    repository.update.assert_not_called()


@pytest.mark.asyncio
async def test_update_document_filename_requires_a_filename():
    repository = AsyncMock(spec=DocumentRepository)
    repository.find_by_id.return_value = Document(id="document-id", filename="informe.pdf")

    with pytest.raises(ValidationException) as error:
        await DocumentService(repository).update_document_filename("document-id", None)

    assert error.value.message == "Se debe proporcionar 'filename' para actualizar"
    repository.find_by_id.assert_awaited_once_with("document-id")
    repository.update.assert_not_called()


@pytest.mark.asyncio
async def test_delete_document_removes_existing_document():
    repository = AsyncMock(spec=DocumentRepository)
    document = Document(id="document-id", filename="informe.pdf")
    repository.find_by_id.return_value = document

    await DocumentService(repository).delete_document(document.id)

    repository.find_by_id.assert_awaited_once_with(document.id)
    repository.delete.assert_awaited_once_with(document.id)


@pytest.mark.asyncio
async def test_delete_document_raises_when_document_does_not_exist():
    repository = AsyncMock(spec=DocumentRepository)
    repository.find_by_id.return_value = None

    with pytest.raises(DocumentNotFoundError):
        await DocumentService(repository).delete_document("missing")

    repository.find_by_id.assert_awaited_once_with("missing")
    repository.delete.assert_not_called()
