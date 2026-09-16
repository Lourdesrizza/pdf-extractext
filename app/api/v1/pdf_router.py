import logging
from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, status
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from app.api.dependencies import get_document_service
from app.application.services.document_service import DocumentService
from app.core.exceptions import ValidationException
from app.domain.entities.document import Document as DomainDocument
from app.domain.exceptions.domain_exceptions import DocumentNotFoundError
from app.infrastructure.database.schemas.document_schema import (
    DocumentResponse,
    DocumentUpdate,
)
from app.services.pdf_service import PDFService

router = APIRouter()
logger = logging.getLogger(__name__)


async def _read_pdf_body(request: Request) -> bytes:
    """Lee el body por chunks y rechaza el exceso antes de acumularlo.

    ``Request.stream()`` expone los eventos ASGI directamente: a diferencia del
    parser multipart, no crea archivos spooled ni temporales.
    """
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > PDFService.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="El archivo no puede superar los 5MB",
        )

    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > PDFService.MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="El archivo no puede superar los 5MB",
            )
        content.extend(chunk)
    return bytes(content)


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


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_pdf(
    request: Request,
    filename: str | None = Header(default=None, alias="X-Filename"),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Procesa un PDF recibido como body binario, sin archivos temporales."""
    media_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if media_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El Content-Type debe ser application/pdf",
        )

    content = await _read_pdf_body(request)
    try:
        document = await document_service.upload_pdf(filename or "", content)
    except ValidationException as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=error.message
        ) from error
    except PyMongoError as error:
        logger.error("Error de MongoDB al persistir documento: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible",
        ) from error
    return _to_response(document)


# --- Endpoints CRUD de documentos ---


@router.get(
    "/documents",
    response_model=List[DocumentResponse],
    status_code=status.HTTP_200_OK,
)
async def get_all_documents(
    document_service: DocumentService = Depends(get_document_service),
) -> List[DocumentResponse]:
    """Obtiene todos los documentos almacenados.

    Args:
        document_service: Servicio de documentos inyectado.

    Returns:
        Lista de documentos.
    """
    try:
        documents = await document_service.get_all_documents()
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
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Busca un documento por su ID.

    Args:
        document_id: ID del documento a buscar.
        document_service: Servicio de documentos inyectado.

    Returns:
        Documento encontrado.

    Raises:
        HTTPException: Si el documento no existe.
    """
    try:
        document = await document_service.get_document_by_id(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return _to_response(document)


@router.get(
    "/documents/checksum/{checksum}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
async def get_document_by_checksum(
    checksum: str = Path(..., description="Hash SHA256 del contenido"),
    *,
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Busca un documento por su checksum.

    Args:
        checksum: Hash SHA256 del contenido del archivo.
        document_service: Servicio de documentos inyectado.

    Returns:
        Documento encontrado.

    Raises:
        HTTPException: Si el documento no existe.
    """
    try:
        document = await document_service.get_document_by_checksum(checksum)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
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
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Actualiza el nombre de un documento existente (solo filename es mutable).

    Args:
        document_update: Datos a actualizar del documento.
        document_id: ID del documento a actualizar.
        document_service: Servicio de documentos inyectado.

    Returns:
        Documento actualizado.

    Raises:
        HTTPException: Si el documento no existe o no se proporciona filename.
    """
    try:
        updated = await document_service.update_document_filename(
            document_id, document_update.filename
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except ValidationException as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error.message,
        ) from error
    return _to_response(updated)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    document_id: str = Path(..., description="ID del documento en MongoDB"),
    *,
    document_service: DocumentService = Depends(get_document_service),
) -> None:
    """Elimina un documento por su ID.

    Args:
        document_id: ID del documento a eliminar.
        document_service: Servicio de documentos inyectado.

    Raises:
        HTTPException: Si el documento no existe.
    """
    try:
        await document_service.delete_document(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
