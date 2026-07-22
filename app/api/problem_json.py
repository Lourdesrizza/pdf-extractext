"""Implementación del estándar RFC 9457 — Problem Details for HTTP APIs.

Define ``ProblemDetail`` con los campos obligatorios (``type``, ``title``,
``status``, ``detail``) y campos opcionales (``instance`` + extensiones).
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProblemDetail:
    """Representación de un problem+json según RFC 9457."""

    type: str
    title: str
    status: int
    detail: str
    instance: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializa a un dict válido para JSONResponse."""
        payload: dict[str, Any] = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }
        if self.instance is not None:
            payload["instance"] = self.instance
        if self.extensions:
            payload.update(self.extensions)
        return payload


def build_problem(
    type_: str,
    title: str,
    status: int,
    detail: str,
    instance: str | None = None,
    extensions: dict[str, Any] | None = None,
) -> ProblemDetail:
    """Construye un ProblemDetail validando los campos obligatorios.

    Args:
        type_: URI de referencia del problema.
        title: Resumen del tipo de error.
        status: Código HTTP.
        detail: Descripción específica.
        instance: URI de la ocurrencia.
        extensions: Campos adicionales definidos por la API.

    Returns:
        ProblemDetail listo para serializar.
    """
    if not all([type_, title, status, detail]):
        raise ValueError(
            "RFC 9457: type, title, status y detail son obligatorios"
        )
    return ProblemDetail(
        type=type_,
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        extensions=extensions or {},
    )
