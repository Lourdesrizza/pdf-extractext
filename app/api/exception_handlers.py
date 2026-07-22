"""Manejadores globales de excepciones — RFC 9457 (Problem Details).

Devuelve respuestas con ``Content-Type: application/problem+json`` y los
campos obligatorios exigidos por el estándar: ``type``, ``title``,
``status`` y ``detail``.
"""
import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import ServerSelectionTimeoutError

from app.api.problem_json import ProblemDetail, build_problem
from app.core.exceptions import DomainException, NotFoundException, ValidationException

logger = logging.getLogger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json; charset=utf-8"


def _problem_response(problem: ProblemDetail) -> JSONResponse:
    """Construye una ``JSONResponse`` con ``application/problem+json``."""
    return JSONResponse(
        status_code=problem.status,
        content=problem.to_dict(),
        media_type=PROBLEM_CONTENT_TYPE,
    )


def domain_exception_handler(request: Request, exception: DomainException) -> JSONResponse:
    """Maneja excepciones del dominio (4xx)."""
    status_code = _domain_status(exception)
    detail = getattr(exception, "field", None) or exception.message
    return _problem_response(
        build_problem(
            type_="https://pdf-extactext.local/errors/domain-error",
            title="Domain Error",
            status=status_code,
            detail=detail,
            instance=str(request.url),
        )
    )


def request_validation_exception_handler(
    request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    """Maneja errores de validación de Pydantic/FastAPI (422)."""
    return _problem_response(
        build_problem(
            type_="https://pdf-extactext.local/errors/validation-error",
            title="Validation Error",
            status=422,
            detail="Se encontraron errores de validacion en la peticion.",
            instance=str(request.url),
            extensions={"errors": exception.errors()},
        )
    )


def mongo_server_selection_timeout_handler(
    request: Request,
    exception: ServerSelectionTimeoutError,
) -> JSONResponse:
    """Maneja errores de conexion contra MongoDB (503)."""
    logger.error("Base de datos no disponible: %s", exception)
    return _problem_response(
        build_problem(
            type_="https://pdf-extactext.local/errors/database-unavailable",
            title="Database Unavailable",
            status=503,
            detail="Base de datos no disponible",
            instance=str(request.url),
        )
    )


def generic_exception_handler(request: Request, exception: Exception) -> JSONResponse:
    """Captura cualquier excepción no controlada y responde 500."""
    logger.exception("Error interno no controlado: %s", exception)
    return _problem_response(
        build_problem(
            type_="https://pdf-extactext.local/errors/internal",
            title="Internal Server Error",
            status=500,
            detail="Ocurrio un error interno inesperado.",
            instance=str(request.url),
        )
    )


def http_exception_handler(request: Request, exception: HTTPException) -> JSONResponse:
    """Convierte HTTPException en un problem+json RFC 9457."""
    detail = exception.detail if isinstance(exception.detail, str) else "Error"
    return _problem_response(
        build_problem(
            type_=f"https://pdf-extactext.local/errors/http-{exception.status_code}",
            title=HTTP_STATUSES.get(exception.status_code, "HTTP Error"),
            status=exception.status_code,
            detail=detail,
            instance=str(request.url),
        )
    )


def _domain_status(exception: DomainException) -> int:
    """Mapea subtipos de DomainException a un código HTTP adecuado."""
    if isinstance(exception, NotFoundException):
        return 404
    if isinstance(exception, ValidationException):
        return 400
    return 400


HTTP_STATUSES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}
