"""Servicio de extracción y validación de archivos PDF.

Procesa archivos PDF completamente en memoria usando ``io.BytesIO``;
no persiste archivos temporales en disco (Issue #23).
"""
import hashlib
import io
import logging

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFService:
    """Servicio encargado de validaciones y extracción de texto PDF."""

    MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

    @staticmethod
    def get_checksum(content: bytes) -> str:
        """Genera un hash SHA-256 para identificar archivos duplicados."""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def has_valid_pdf_signature(content: bytes) -> bool:
        """Valida que el contenido tenga la firma binaria de un PDF."""
        return content[:5] == b"%PDF-"

    @classmethod
    def validate_pdf_content(cls, content: bytes) -> None:
        """Aplica las reglas de validación sobre el archivo PDF recibido.

        Args:
            content: Bytes del archivo PDF.

        Raises:
            ValueError: Si el contenido es vacío, excede el tamaño máximo o
                no posee la firma mágica de PDF.
        """
        if not content:
            raise ValueError("El archivo no puede estar vacio")

        if len(content) > cls.MAX_FILE_SIZE_BYTES:
            raise ValueError("El archivo no puede superar los 5MB")

        if not cls.has_valid_pdf_signature(content):
            raise ValueError("El contenido del archivo debe ser un PDF valido")

    @staticmethod
    def extract_text(content: bytes) -> str:
        """Extrae el texto plano del PDF completamente en memoria.

        No escribe archivos temporales: usa ``io.BytesIO`` como buffer.

        Args:
            content: Bytes del archivo PDF.

        Returns:
            Texto extraído (sin espacios laterales). Si la extracción
            falla retorna una cadena vacía.
        """
        if not content:
            return ""

        buffer = io.BytesIO(content)
        try:
            with fitz.open(stream=buffer.getbuffer(), filetype="pdf") as doc:
                pages_text = [page.get_text() for page in doc]
            return "\n".join(pages_text).strip()
        except (RuntimeError, ValueError, Exception) as error:
            logger.warning("No se pudo extraer texto del PDF: %s", error)
            return ""
