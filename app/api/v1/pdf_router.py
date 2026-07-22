import io
import logging
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from app.api.dependencies import get_document_repository
from app.domain.entities.document import Document as DomainDocument
from app.domain.repositories.document_repository import DocumentRepository
from app.infrastructure.database.schemas.document_schema import (
    DocumentResponse,
    DocumentUpdate,
)
from app.services.pdf_service import PDFService

router = APIRouter()
logger = logging.getLogger(__name__)


def _to_response(document: DomainDocument) -> DocumentResponse:
    """Convierte una entidad de dominio a un schema de respuesta de API.

    Args:
        document: Entidad Document del dominio.

    Returns:
        Schema DocumentResponse con los datos del documento.

    Raises:
        ValueError: Si el documento no tiene ID asignado.
    """
    if not document.id:
        raise ValueError("El documento debe tener un ID para convertirse a respuesta")
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        checksum=document.checksum,
        extracted_text=document.extracted_text,
        created_at=document.created_at,
    )


# --- Endpoints de subida de documentos ---


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Endpoint para subir y procesar un archivo PDF.

    Procesa el archivo completamente en memoria con ``io.BytesIO``;
    no persiste archivos temporales en disco (Issue #23).

    Args:
        file: Archivo PDF recibido como UploadFile.

    Returns:
        JSON con el nombre del archivo, checksum y texto extraído.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")

    content = await file.read()
    buffer = io.BytesIO(content)

    try:
        PDFService.validate_pdf_content(buffer.getvalue())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    checksum = PDFService.get_checksum(buffer.getvalue())
    text = PDFService.extract_text(buffer.getvalue())

    if not text:
        raise HTTPException(
            status_code=400, detail="El PDF no contiene texto extraíble"
        )

    return {
        "filename": file.filename,
        "checksum": checksum,
        "extracted_text_preview": text[:100] + "...",
        "message": "Texto extraído correctamente",
    }


# --- Endpoints CRUD de documentos ---


@router.get(
    "/documents",
    response_model=List[DocumentResponse],
    status_code=status.HTTP_200_OK,
)
async def get_all_documents(
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> List[DocumentResponse]:
    """Obtiene todos los documentos almacenados.

    Args:
        document_repository: Repositorio de documentos inyectado.

    Returns:
        Lista de documentos.
    """
    try:
        documents = await document_repository.find_all()
    except (ServerSelectionTimeoutError, PyMongoError) as error:
        logger.error("Error de conexion a MongoDB al obtener documentos: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible",
        ) from error

    return [_to_response(doc) for doc in documents]


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
async def get_document_by_id(
    document_id: str = Path(..., description="ID del documento en MongoDB"),
    *,
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> DocumentResponse:
    """Busca un documento por su ID.

    Args:
        document_id: ID del documento a buscar.
        document_repository: Repositorio de documentos inyectado.

    Returns:
        Documento encontrado.

    Raises:
        HTTPException: Si el documento no existe.
    """
    document = await document_repository.find_by_id(document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento con ID '{document_id}' no encontrado",
        )
    return _to_response(document)


@router.get(
    "/documents/checksum/{checksum}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
async def get_document_by_checksum(
    checksum: str = Path(..., description="Hash SHA256 del contenido"),
    *,
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> DocumentResponse:
    """Busca un documento por su checksum.

    Args:
        checksum: Hash SHA256 del contenido del archivo.
        document_repository: Repositorio de documentos inyectado.

    Returns:
        Documento encontrado.

    Raises:
        HTTPException: Si el documento no existe.
    """
    document = await document_repository.find_by_checksum(checksum)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento con checksum '{checksum}' no encontrado",
        )
    return _to_response(document)


@router.patch(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
async def update_document(
    document_update: DocumentUpdate,
    document_id: str = Path(..., description="ID del documento en MongoDB"),
    *,
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> DocumentResponse:
    """Actualiza el nombre de un documento existente (solo filename es mutable).

    Args:
        document_update: Datos a actualizar del documento.
        document_id: ID del documento a actualizar.
        document_repository: Repositorio de documentos inyectado.

    Returns:
        Documento actualizado.

    Raises:
        HTTPException: Si el documento no existe o no se proporciona filename.
    """
    document = await document_repository.find_by_id(document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento con ID '{document_id}' no encontrado",
        )

    if document_update.filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se debe proporcionar 'filename' para actualizar",
        )

    document.update_filename(document_update.filename)
    updated = await document_repository.update(document)
    return _to_response(updated)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    document_id: str = Path(..., description="ID del documento en MongoDB"),
    *,
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> None:
    """Elimina un documento por su ID.

    Args:
        document_id: ID del documento a eliminar.
        document_repository: Repositorio de documentos inyectado.

    Raises:
        HTTPException: Si el documento no existe.
    """
    document = await document_repository.find_by_id(document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento con ID '{document_id}' no encontrado",
        )

    await document_repository.delete(document_id)
