from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from pymongo.errors import ServerSelectionTimeoutError

# Tus imports originales
from app.api.exception_handlers import (
    domain_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    mongo_server_selection_timeout_handler,
    request_validation_exception_handler,
)
from app.api.v1.health_router import router as health_router
from app.api.v1.user_routes import router as user_router
from app.api.v1.pdf_router import router as pdf_router
from app.core.config import settings
from app.core.exceptions import DomainException

# 1. Creamos una única app, y le apagamos el docs por defecto para usar el tuyo
app = FastAPI(
    title="PDF Extractor API",
    version="1.0.0",
    debug=settings.DEBUG,
    docs_url=None,
)

app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(
    ServerSelectionTimeoutError,
    mongo_server_selection_timeout_handler,
)
app.add_exception_handler(
    RequestValidationError,
    request_validation_exception_handler,
)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# 2. Le decimos exactamente dónde está la carpeta static
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 3. Creamos la ruta de la interfaz aesthetic
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_css_url="/static/custom.css",
    )

# 4. Tu ruta raíz original
@app.get("/")
def root():
    return {
        "message": "Bienvenida a la API de Extracción de PDF",
        "status": "Online",
        "db_name": settings.DB_NAME,
    }

# 5. Routers de la API (siempre al final)
app.include_router(health_router, tags=["health"])
app.include_router(user_router, prefix="/api/v1", tags=["users"])
app.include_router(pdf_router, prefix="/api/v1", tags=["Documentos"])
