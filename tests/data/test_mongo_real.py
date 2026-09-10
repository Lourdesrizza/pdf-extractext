import os
import asyncio
from uuid import uuid4

import fitz
import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from app.application.services.document_service import DocumentService
from app.domain.entities.document import Document
from app.domain.exceptions.domain_exceptions import DocumentAlreadyExistsError
from app.infrastructure.database.connection import ensure_document_indexes
from app.infrastructure.repositories.mongo_document_repository import MongoDocumentRepository


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_MONGO_TESTS") != "1",
        reason="Requiere MongoDB real. Ejecutar con RUN_MONGO_TESTS=1.",
    ),
]

# Tu código corre en la compu y se conecta al MongoDB que está adentro de Docker usando localhost
MONGO_URL = "mongodb://localhost:27017"
TEST_DB_NAME = "test_pdf_extractor_db"

@pytest_asyncio.fixture
async def db_collection():
    """
    Se conecta a la base de datos de prueba.
    Limpia todo antes y después de cada test para no dejar basura.
    """
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[f"{TEST_DB_NAME}_{uuid4().hex}"]
    collection = db["documents"]
    
    try:
        yield collection
    finally:
        await client.drop_database(db.name)
        client.close()

@pytest.mark.asyncio
async def test_mongo_real_insert_and_find(db_collection):
    """Test Real: Guarda un documento en Docker y verifica que exista."""
    nuevo_documento = {
        "filename": "tp_sistemas.pdf",
        "checksum": "hash_real_123",
        "content": "Texto extraído directo desde la base de datos real."
    }
    
    # 1. Insertamos en el MongoDB de verdad
    resultado = await db_collection.insert_one(nuevo_documento)
    assert resultado.inserted_id is not None
    
    # 2. Lo buscamos para confirmar que se guardó
    documento_guardado = await db_collection.find_one({"checksum": "hash_real_123"})
    assert documento_guardado is not None
    assert documento_guardado["filename"] == "tp_sistemas.pdf"

@pytest.mark.asyncio
async def test_mongo_real_delete(db_collection):
    """Test Real: Guarda un documento y luego lo borra definitivamente."""
    # Insertamos algo temporal
    await db_collection.insert_one({"checksum": "hash_para_borrar", "file": "basura.pdf"})
    
    # Lo borramos
    borrado = await db_collection.delete_one({"checksum": "hash_para_borrar"})
    assert borrado.deleted_count == 1
    
    # Confirmamos que ya no existe en Docker
    no_existe = await db_collection.find_one({"checksum": "hash_para_borrar"})
    assert no_existe is None
    
@pytest.mark.asyncio
async def test_mongo_real_duplicate_pdf_prevention(db_collection):
    """El indice rechaza otro _id con el mismo checksum."""
    await ensure_document_indexes(db_collection.database)
    documento = {
        "_id": ObjectId(),
        "filename": "tp_repetido.pdf",
        "checksum": "hash_duplicado_999",
        "content": "Este texto ya existe."
    }
    
    # 1. Guardamos el documento por primera vez
    await db_collection.insert_one(documento)
    
    with pytest.raises(DuplicateKeyError):
        await db_collection.insert_one({**documento, "_id": ObjectId()})
    assert await db_collection.count_documents({"checksum": documento["checksum"]}) == 1


@pytest.mark.asyncio
async def test_concurrent_index_initialization_is_idempotent(db_collection):
    await asyncio.gather(*[
        ensure_document_indexes(db_collection.database) for _ in range(3)
    ])
    await ensure_document_indexes(db_collection.database)
    indexes = await db_collection.index_information()
    assert indexes["uq_documents_checksum"]["key"] == [("checksum", 1)]
    assert indexes["uq_documents_checksum"]["unique"] is True


@pytest.mark.asyncio
async def test_existing_duplicates_prevent_unique_index_without_data_changes(db_collection):
    await db_collection.insert_many([{"checksum": "a" * 64}, {"checksum": "a" * 64}])
    with pytest.raises(RuntimeError, match="duplicados"):
        await ensure_document_indexes(db_collection.database)
    assert await db_collection.count_documents({}) == 2


@pytest.mark.asyncio
async def test_concurrent_uploads_persist_only_once(db_collection):
    await ensure_document_indexes(db_collection.database)
    barrier = asyncio.Barrier(2)

    class ConcurrentRepository(MongoDocumentRepository):
        async def find_by_checksum(self, checksum):
            result = await super().find_by_checksum(checksum)
            await asyncio.wait_for(barrier.wait(), timeout=10)
            return result

    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 50), "Texto concurrente")
        content = pdf.tobytes()
    results = await asyncio.gather(*[
        DocumentService(ConcurrentRepository(db_collection.database)).upload_pdf(name, content)
        for name in ("uno.pdf", "dos.pdf")
    ], return_exceptions=True)
    assert sum(isinstance(result, Document) for result in results) == 1
    assert sum(isinstance(result, DocumentAlreadyExistsError) for result in results) == 1
    assert await db_collection.count_documents({}) == 1
