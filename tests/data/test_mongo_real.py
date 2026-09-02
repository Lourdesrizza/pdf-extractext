import os

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient


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
    db = client[TEST_DB_NAME]
    collection = db["documents"]
    
    # Limpiamos antes por si quedó algún archivo fantasma
    await collection.delete_many({})
    
    # Le pasamos la colección real al test
    yield collection 
    
    # Limpiamos todo al terminar
    await collection.delete_many({})
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
    """Test Real: Simula el intento de guardar el mismo PDF dos veces."""
    documento = {
        "filename": "tp_repetido.pdf",
        "checksum": "hash_duplicado_999",
        "content": "Este texto ya existe."
    }
    
    # 1. Guardamos el documento por primera vez
    await db_collection.insert_one(documento)
    
    # 2. Llega el mismo documento de nuevo. La lógica debería buscar el checksum primero.
    documento_existente = await db_collection.find_one({"checksum": "hash_duplicado_999"})
    
    # Verificamos que la base de datos nos avisa que ya lo tiene
    assert documento_existente is not None
    assert documento_existente["filename"] == "tp_repetido.pdf"
