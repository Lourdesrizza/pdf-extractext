"""Caso de uso de extracción y persistencia de documentos PDF."""

from app.core.exceptions import ValidationException
from app.domain.entities.document import Document
from app.domain.exceptions.domain_exceptions import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
)
from app.domain.repositories.document_repository import DocumentRepository
from app.services.pdf_service import PDFService


class DocumentService:
    """Coordina el procesamiento en memoria y el guardado del documento."""

    def __init__(self, document_repository: DocumentRepository) -> None:
        self._repository = document_repository

    async def get_all_documents(self) -> list[Document]:
        """Obtiene todos los documentos almacenados."""
        return await self._repository.find_all()

    async def get_document_by_id(self, document_id: str) -> Document:
        """Busca un documento por su identificador."""
        document = await self._repository.find_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(
                f"Documento con ID '{document_id}' no encontrado"
            )
        return document

    async def get_document_by_checksum(self, checksum: str) -> Document:
        """Busca un documento por el checksum de su contenido."""
        document = await self._repository.find_by_checksum(checksum)
        if document is None:
            raise DocumentNotFoundError(
                f"Documento con checksum '{checksum}' no encontrado"
            )
        return document

    async def update_document_filename(
        self, document_id: str, filename: str | None
    ) -> Document:
        """Actualiza el nombre de un documento existente."""
        document = await self.get_document_by_id(document_id)
        if filename is None:
            raise ValidationException(
                "filename", "Se debe proporcionar 'filename' para actualizar"
            )
        document.update_filename(filename)
        return await self._repository.update(document)

    async def delete_document(self, document_id: str) -> None:
        """Elimina un documento existente."""
        await self.get_document_by_id(document_id)
        await self._repository.delete(document_id)

    async def upload_pdf(self, filename: str, content: bytes) -> Document:
        """Devuelve el documento persistido con el ID asignado por el repositorio."""
        if not filename or not filename.lower().endswith(".pdf"):
            raise ValidationException("filename", "El archivo debe ser un PDF")
        if len(filename) > 255:
            raise ValidationException(
                "filename", "El nombre del archivo no puede superar los 255 caracteres"
            )

        try:
            PDFService.validate_pdf_content(content)
        except ValueError as error:
            raise ValidationException("content", str(error)) from error

        checksum = PDFService.get_checksum(content)
        if await self._repository.find_by_checksum(checksum) is not None:
            raise DocumentAlreadyExistsError("El documento ya existe")

        text = PDFService.extract_text(content)
        if not text:
            raise ValidationException("content", "El PDF no contiene texto extraíble")

        document = Document(
            filename=filename, checksum=checksum, extracted_text=text
        )
        return await self._repository.create(document)
