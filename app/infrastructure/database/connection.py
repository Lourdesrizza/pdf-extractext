"""Configuración de conexión a base de datos MongoDB."""

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from app.core.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.database_url)
    return _client


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
