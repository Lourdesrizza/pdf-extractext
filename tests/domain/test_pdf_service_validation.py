import hashlib

import pytest

from app.services.pdf_service import PDFService


def test_checksum_matches_sha256() -> None:
    content = b"contenido de prueba"

    assert PDFService.get_checksum(content) == hashlib.sha256(content).hexdigest()


def test_valid_pdf_signature_is_accepted() -> None:
    assert PDFService.has_valid_pdf_signature(b"%PDF-1.7\n") is True


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "El archivo no puede estar vacio"),
        (b"texto sin formato PDF", "El contenido del archivo debe ser un PDF valido"),
        (b"%PDF-" + b"0" * (5 * 1024 * 1024), "El archivo no puede superar los 5MB"),
    ],
    ids=["empty", "invalid-signature", "too-large"],
)
def test_validate_pdf_content_rejects_invalid_content(
    content: bytes, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        PDFService.validate_pdf_content(content)
