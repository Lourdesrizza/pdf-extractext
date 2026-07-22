"""Endpoint de salud (health check) para orquestadores y balanceadores.

Implementación del Issue #24: responde 200 OK si MongoDB responde al ping,
o 503 si la base de datos no está disponible.
"""
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from app.infrastructure.database.connection import get_client
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Health check de la API y MongoDB",
    status_code=status.HTTP_200_OK,
)
async def health() -> JSONResponse:
    """Verifica la conectividad con MongoDB.

    Returns:
        JSONResponse con ``{"status": "ok", "db": "connected"}`` y HTTP 200
        si MongoDB responde, o ``{"status": "degraded", "db": "disconnected"}``
        con HTTP 503 si no es posible conectar.
    """
    ok = await _ping_mongo()
    if ok:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "db": "connected"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "degraded", "db": "disconnected"},
    )


async def _ping_mongo() -> bool:
    """Ejecuta el comando ``ping`` contra MongoDB con un timeout corto.

    Returns:
        ``True`` si la base responde, ``False`` en caso contrario.
    """
    try:
        client = get_client()
        result = await client.admin.command("ping")
        return bool(result.get("ok", 0))
    except (ServerSelectionTimeoutError, PyMongoError, Exception):
        return False
