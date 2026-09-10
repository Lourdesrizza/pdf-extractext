"""Implementación MongoDB del repositorio de documentos."""

from typing import List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.domain.entities.document import Document
from app.domain.exceptions.domain_exceptions import DocumentAlreadyExistsError
from app.domain.repositories.document_repository import DocumentRepository
from app.infrastructure.database.schemas.document_schema import (
    DocumentCreate,
    DocumentInDB,
)


class MongoDocumentRepository(DocumentRepository):
    """Repositorio de documentos usando MongoDB con Motor."""

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        """Inicializa el repositorio con la colección de documentos.

        Args:
            database: Instancia de base de datos MongoDB de Motor.
        """
        self._collection = database.documents

    async def find_by_id(self, document_id: str) -> Optional[Document]:
        """Busca un documento por su ID.

        Args:
            document_id: ID del documento como string.

        Returns:
            Entidad Document si existe, None si no se encuentra.
        """
        try:
            document = await self._collection.find_one({"_id": ObjectId(document_id)})
        except InvalidId:
            return None

        if document:
            return self._to_entity(DocumentInDB.model_validate(document))
        return None

    async def find_by_checksum(self, checksum: str) -> Optional[Document]:
        """Busca un documento por su checksum.

        Args:
            checksum: Hash SHA256 del contenido.

        Returns:
            Entidad Document si existe, None si no se encuentra.
        """
        document = await self._collection.find_one({"checksum": checksum})
        if document:
            return self._to_entity(DocumentInDB.model_validate(document))
        return None

    async def find_all(self) -> List[Document]:
        """Obtiene todos los documentos.

        Returns:
            Lista de entidades Document.
        """
        documents = []
        cursor = self._collection.find()
        async for document in cursor:
            documents.append(self._to_entity(DocumentInDB.model_validate(document)))
        return documents

    async def create(self, document: Document) -> Document:
        """Crea un nuevo documento.

        Args:
            document: Entidad Document a crear.

        Returns:
            Entidad Document creada con ID asignado.
        """
        document_create = DocumentCreate(
            filename=document.filename,
            checksum=document.checksum,
            extracted_text=document.extracted_text,
        )

        document_in_db = DocumentInDB(**document_create.model_dump())
        db_document = document_in_db.model_dump(by_alias=True, exclude={"id"})

        try:
            result = await self._collection.insert_one(db_document)
        except DuplicateKeyError as error:
            raise DocumentAlreadyExistsError("El documento ya existe") from error
        document_in_db.id = str(result.inserted_id)

        return self._to_entity(document_in_db)

    async def update(self, document: Document) -> Document:
        """Actualiza un documento existente (solo filename es mutable).

        Args:
            document: Entidad Document con datos actualizados.

        Returns:
            Entidad Document actualizada.

        Raises:
            ValueError: Si el documento no tiene ID.
        """
        if not document.id:
            raise ValueError("El documento debe tener un ID para actualizarse")

        update_data = {"filename": document.filename}

        await self._collection.update_one(
            {"_id": ObjectId(document.id)}, {"$set": update_data}
        )

        return document

    async def delete(self, document_id: str) -> None:
        """Elimina un documento por su ID.

        Args:
            document_id: ID del documento a eliminar.
        """
        await self._collection.delete_one({"_id": ObjectId(document_id)})

    def _to_entity(self, document_in_db: DocumentInDB) -> Document:
        """Convierte schema Pydantic a entidad de dominio.

        Args:
            document_in_db: Schema DocumentInDB.

        Returns:
            Entidad Document del dominio.
        """
        return Document(
            id=document_in_db.id,
            filename=document_in_db.filename,
            checksum=document_in_db.checksum,
            extracted_text=document_in_db.extracted_text,
            created_at=document_in_db.created_at,
        )
