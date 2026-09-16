"""Endpoint sin estado para medir la extracción de PDFs."""

from fastapi import APIRouter, HTTPException, Request, status

from app.services.pdf_service import PDFService

router = APIRouter()


@router.post("/extract", status_code=status.HTTP_200_OK)
async def extract_pdf(request: Request) -> dict[str, str]:
    """Extrae texto desde un PDF binario sin persistirlo."""
    media_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if media_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El Content-Type debe ser application/pdf",
        )

    content = await request.body()
    try:
        PDFService.validate_pdf_content(content)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    text = PDFService.extract_text(content)
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo extraer texto del PDF",
        )
    return {"text": text}
