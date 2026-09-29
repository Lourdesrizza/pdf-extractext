"""Servicio de extracción y validación de archivos PDF.

Procesa archivos PDF completamente en memoria;
no persiste archivos temporales en disco (Issue #23).
"""
import hashlib
import logging

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFService:
    """Servicio encargado de validaciones y extracción de texto PDF."""

    MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
    MAX_EXTRACTION_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MiB

    @staticmethod
    def get_checksum(content: bytes) -> str:
        """Genera un hash SHA-256 para identificar archivos duplicados."""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def has_valid_pdf_signature(content: bytes | memoryview) -> bool:
        """Valida que el contenido tenga la firma binaria de un PDF."""
        return content[:5] == b"%PDF-"

    @classmethod
    def validate_pdf_content(
        cls,
        content: bytes | memoryview,
        max_file_size_bytes: int | None = None,
    ) -> None:
        """Aplica las reglas de validación sobre el archivo PDF recibido.

        Args:
            content: Bytes del archivo PDF.
            max_file_size_bytes: Límite opcional específico del endpoint. Si no
                se indica, se conserva el límite general de 5 MiB.

        Raises:
            ValueError: Si el contenido es vacío, excede el tamaño máximo o
                no posee la firma mágica de PDF.
        """
        if not content:
            raise ValueError("El archivo no puede estar vacio")

        max_size = (
            cls.MAX_FILE_SIZE_BYTES
            if max_file_size_bytes is None
            else max_file_size_bytes
        )
        if len(content) > max_size:
            max_size_mb = max_size // (1024 * 1024)
            raise ValueError(f"El archivo no puede superar los {max_size_mb}MB")

        if not cls.has_valid_pdf_signature(content):
            raise ValueError("El contenido del archivo debe ser un PDF valido")

    @staticmethod
    def extract_text(content: bytes) -> str:
        """Extrae el texto plano del PDF completamente en memoria.

        No escribe archivos temporales: pasa los bytes directamente a PyMuPDF.

        Args:
            content: Bytes del archivo PDF.

        Returns:
            Texto extraído (sin espacios laterales). Si la extracción
            falla retorna una cadena vacía.
        """
        if not content:
            return ""

        try:
            with fitz.open(stream=content, filetype="pdf") as doc:
                pages_text = [page.get_text() for page in doc]
            return "\n".join(pages_text).strip()
        except (RuntimeError, ValueError, Exception) as error:
            logger.warning("No se pudo extraer texto del PDF: %s", error)
            return ""
