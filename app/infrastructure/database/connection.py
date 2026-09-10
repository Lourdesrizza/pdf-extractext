"""Configuración de conexión a base de datos MongoDB."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError, ServerSelectionTimeoutError

from app.core.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.database_url)
    return _client


async def ensure_document_indexes(database: AsyncIOMotorDatabase) -> None:
    """Garantiza el indice unico antes de habilitar peticiones."""
    try:
        await database.documents.create_index(
            [("checksum", 1)], unique=True, name="uq_documents_checksum"
        )
    except DuplicateKeyError as error:
        raise RuntimeError(
            "No se pudo crear el indice uq_documents_checksum: existen valores "
            "duplicados de checksum. Revisar los datos antes de iniciar; "
            "no se modificaron documentos automaticamente."
        ) from error

    indexes = await database.documents.index_information()
    index = indexes.get("uq_documents_checksum", {})
    if (
        index.get("key") != [("checksum", 1)]
        or index.get("unique") is not True
        or index.get("sparse", False)
        or "partialFilterExpression" in index
    ):
        raise RuntimeError("El indice uq_documents_checksum no tiene la configuracion esperada")


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Inicializa MongoDB una vez por proceso y libera el cliente al finalizar."""
    global _client
    client = get_client()
    try:
        database = client[settings.DB_NAME]
        try:
            await database.command("ping")
            await ensure_document_indexes(database)
        except PyMongoError as error:
            raise RuntimeError(
                "No se pudo inicializar MongoDB y garantizar uq_documents_checksum; "
                "se cancela el inicio de la aplicacion."
            ) from error
        yield
    finally:
        client.close()
        _client = None


async def get_database_session() -> AsyncIOMotorDatabase:
    try:
        database = get_client()[settings.DB_NAME]
        await database.command("ping")
        yield database
    except (ServerSelectionTimeoutError, PyMongoError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible",
        ) from error
