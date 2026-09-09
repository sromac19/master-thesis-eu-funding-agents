from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


class PdfParseError(ValueError):
    """Raised when a PDF is unsafe, malformed, or has no extractable text."""


@dataclass(frozen=True)
class ParsedPdf:
    pages: tuple[str, ...]

    @property
    def text_with_page_markers(self) -> str:
        return "\n\n".join(
            f"--- PAGE {number} ---\n{text}" for number, text in enumerate(self.pages, start=1)
        )


def parse_pdf(path: Path, *, max_bytes: int = 25 * 1024 * 1024) -> ParsedPdf:
    if not path.is_file():
        raise PdfParseError(f"PDF does not exist: {path}")
    if path.stat().st_size > max_bytes:
        raise PdfParseError(f"PDF exceeds the {max_bytes}-byte limit")
    with path.open("rb") as source:
        if source.read(5) != b"%PDF-":
            raise PdfParseError("File does not have a PDF signature")
    try:
        pages = tuple((page.extract_text() or "").strip() for page in PdfReader(path).pages)
    except Exception as exc:
        raise PdfParseError(f"Could not parse PDF: {path}") from exc
    if not any(pages):
        raise PdfParseError("PDF contains no extractable text")
    return ParsedPdf(pages=pages)
