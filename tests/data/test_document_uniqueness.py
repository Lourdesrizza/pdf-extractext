from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.domain.entities.document import Document
from app.domain.exceptions.domain_exceptions import DocumentAlreadyExistsError
from app.infrastructure.database import connection
from app.infrastructure.repositories.mongo_document_repository import MongoDocumentRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [PyMongoError, ValueError])
async def test_repository_preserves_other_errors(failure_type):
    database = MagicMock()
    failure = failure_type("informacion interna")
    database.documents.insert_one = AsyncMock(side_effect=failure)
    repository = MongoDocumentRepository(database)
    with pytest.raises(failure_type) as error:
        await repository.create(Document(filename="test.pdf", checksum="a" * 64, extracted_text="Texto"))
    database.documents.insert_one.assert_awaited_once()
    assert error.value is failure


@pytest.mark.asyncio
async def test_repository_translates_checksum_duplicate_key():
    database = MagicMock()
    failure = DuplicateKeyError(
        "informacion interna", 11000, {"keyPattern": {"checksum": 1}}
    )
    database.documents.insert_one = AsyncMock(side_effect=failure)
    with pytest.raises(DocumentAlreadyExistsError) as error:
        await MongoDocumentRepository(database).create(
            Document(filename="test.pdf", checksum="a" * 64, extracted_text="Texto")
        )
    assert error.value.message == "El documento ya existe"
    assert error.value.__cause__ is failure
    database.documents.insert_one.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "details",
    [
        {"keyPattern": {"filename": 1}},
        {"keyPattern": {"_id": 1}},
        {"keyPattern": {"checksum": 1, "filename": 1}},
        None,
        {},
        {"errmsg": "index: uq_documents_checksum dup key"},
    ],
    ids=["other-field", "id", "compound", "missing", "empty", "message-only"],
)
async def test_repository_preserves_unconfirmed_duplicate_key(details):
    database = MagicMock()
    failure = DuplicateKeyError("uq_documents_checksum", 11000, details)
    database.documents.insert_one = AsyncMock(side_effect=failure)
    with pytest.raises(DuplicateKeyError) as error:
        await MongoDocumentRepository(database).create(
            Document(filename="test.pdf", checksum="a" * 64, extracted_text="Texto")
        )
    assert error.value is failure
    database.documents.insert_one.assert_awaited_once()


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
