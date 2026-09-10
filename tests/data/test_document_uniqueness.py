from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.domain.entities.document import Document
from app.domain.exceptions.domain_exceptions import DocumentAlreadyExistsError
from app.infrastructure.database import connection
from app.infrastructure.repositories.mongo_document_repository import MongoDocumentRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [DuplicateKeyError, PyMongoError, ValueError])
async def test_repository_translates_only_duplicate_key(failure_type):
    database = MagicMock()
    failure = failure_type("informacion interna")
    database.documents.insert_one = AsyncMock(side_effect=failure)
    repository = MongoDocumentRepository(database)
    expected = DocumentAlreadyExistsError if failure_type is DuplicateKeyError else failure_type
    with pytest.raises(expected) as error:
        await repository.create(Document(filename="test.pdf", checksum="a" * 64, extracted_text="Texto"))
    database.documents.insert_one.assert_awaited_once()
    if failure_type is DuplicateKeyError:
        assert error.value.message == "El documento ya existe"
    else:
        assert error.value is failure


@pytest.mark.asyncio
async def test_index_initialization_creates_and_verifies_exact_definition():
    database = MagicMock()
    database.documents.create_index = AsyncMock()
    database.documents.index_information = AsyncMock(return_value={
        "uq_documents_checksum": {"key": [("checksum", 1)], "unique": True}
    })
    await connection.ensure_document_indexes(database)
    database.documents.create_index.assert_awaited_once_with(
        [("checksum", 1)], unique=True, name="uq_documents_checksum"
    )
    database.documents.index_information.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("definition", [None, {"key": [("checksum", 1)]}, {"key": [("filename", 1)], "unique": True}, {"key": [("checksum", 1)], "unique": True, "sparse": True}, {"key": [("checksum", 1)], "unique": True, "partialFilterExpression": {"checksum": {"$exists": True}}}])
async def test_invalid_index_definition_blocks_initialization(definition):
    database = MagicMock()
    database.documents.create_index = AsyncMock()
    database.documents.index_information = AsyncMock(return_value={
        "uq_documents_checksum": definition
    } if definition else {})
    with pytest.raises(RuntimeError, match="indice"):
        await connection.ensure_document_indexes(database)


@pytest.mark.asyncio
async def test_existing_duplicates_block_initialization_without_deletion():
    database = MagicMock()
    database.documents.create_index = AsyncMock(side_effect=DuplicateKeyError("duplicados"))
    with pytest.raises(RuntimeError, match="duplicados"):
        await connection.ensure_document_indexes(database)
    database.documents.delete_many.assert_not_called()
    database.documents.drop.assert_not_called()
