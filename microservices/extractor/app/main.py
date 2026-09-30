import pymupdf
import pymupdf4llm
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

app = FastAPI(title="PDF Extractor", version="0.1.0")


class ExtractionResponse(BaseModel):
    content: str
    page_count: int


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "extractor"}


@app.post("/extract", response_model=ExtractionResponse)
async def extract(request: Request) -> ExtractionResponse:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Content-Type must be application/pdf")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="PDF body must not be empty")
    if not body.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Body must start with %PDF")
    try:
        document = pymupdf.open(stream=body, filetype="pdf")
    except pymupdf.FileDataError as exc:
        raise HTTPException(status_code=400, detail="Invalid PDF document") from exc
    with document:
        if document.needs_pass:
            raise HTTPException(
                status_code=400, detail="Password-protected PDFs are not supported"
            )
        page_count = document.page_count
        content = pymupdf4llm.to_markdown(
            document, use_ocr=False, write_images=False, embed_images=False
        )
    return ExtractionResponse(content=content, page_count=page_count)
