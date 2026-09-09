import hashlib
from datetime import datetime
from unittest.mock import AsyncMock

import fitz
import pytest
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from app.application.services.document_service import DocumentService
from app.core.exceptions import ValidationException
from app.domain.entities.document import Document
from app.domain.repositories.document_repository import DocumentRepository


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
    repository.find_by_checksum.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [PyMongoError, ServerSelectionTimeoutError, RuntimeError, ValueError])
async def test_persistence_error_is_propagated(error_type):
    repository = AsyncMock(spec=DocumentRepository)
    failure = error_type("fallo simulado")
    repository.create.side_effect = failure

    with pytest.raises(error_type) as error:
        await DocumentService(repository).upload_pdf("test.pdf", pdf_bytes())

    assert error.value is failure
    repository.create.assert_awaited_once()
    repository.find_by_checksum.assert_not_called()


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

    with pytest.raises(ValidationException) as error:
        await DocumentService(repository).upload_pdf(filename, content)

    assert error.value.message == message
    repository.create.assert_not_called()
    repository.find_by_checksum.assert_not_called()
