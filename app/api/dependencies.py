"""Dependencias de inyección para FastAPI."""

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.application.services.user_service import UserService
from app.application.services.document_service import DocumentService
from app.domain.repositories.user_repository import UserRepository
from app.domain.repositories.document_repository import DocumentRepository
from app.infrastructure.database.connection import get_database_session
from app.infrastructure.repositories.mongo_user_repository import MongoUserRepository
from app.infrastructure.repositories.mongo_document_repository import (
    MongoDocumentRepository,
)


async def get_user_repository(
    database: AsyncIOMotorDatabase = Depends(get_database_session),
) -> UserRepository:
    """Provee el repositorio de usuarios con MongoDB.

    Args:
        database: Sesión de base de datos MongoDB de Motor.

    Returns:
        Instancia de MongoUserRepository.
    """
    return MongoUserRepository(database)


async def get_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
) -> UserService:
    """Provee el servicio de usuarios.

    Args:
        user_repository: Repositorio de usuarios inyectado.

    Returns:
        Instancia de UserService configurada.
    """
    return UserService(user_repository)


async def get_document_repository(
    database: AsyncIOMotorDatabase = Depends(get_database_session),
) -> DocumentRepository:
    """Provee el repositorio de documentos con MongoDB.

    Args:
        database: Sesión de base de datos MongoDB de Motor.

    Returns:
        Instancia de MongoDocumentRepository.
    """
    return MongoDocumentRepository(database)


async def get_document_service(
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> DocumentService:
    """Provee el caso de uso de subida con el repositorio configurado."""
    return DocumentService(document_repository)
