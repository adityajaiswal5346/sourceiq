"""
DocuMind — PDF Parser
======================
Extracts text and page metadata from PDF documents using pypdf.

Design decisions:
- Page numbers are preserved on every extracted block so citations
  can reference exact pages — "AWS Well-Architected Framework, page 47".
- Each page is returned as a separate text block to preserve page
  boundaries before chunking.
- Encrypted PDFs raise ParseError with a clear message rather than
  silently returning empty text.
- Minimum text length threshold filters scanned/image-only PDFs
  that produce no extractable text.
"""

import logging
from pathlib import Path

import pypdf
from app.core.exceptions import ParseError
from app.core.models import DocumentFormat, ParsedDocument

logger = logging.getLogger(__name__)

# PDFs with less than this many characters per page are likely
# scanned images — flag rather than silently index empty content
_MIN_CHARS_PER_PAGE = 50


def parse_pdf(path: Path) -> ParsedDocument:
    """
    Extract text from a PDF file, preserving page structure.

    Each page's text is extracted separately and joined with a
    page-break marker so the chunker can optionally respect page
    boundaries when splitting.

    Args:
        path: Absolute or relative path to the PDF file.

    Returns:
        ParsedDocument with full text and page_count populated.

    Raises:
        ParseError: If the file is encrypted, corrupt, or produces
                    no extractable text (likely a scanned PDF).
    """
    if not path.exists():
        raise ParseError(f"File not found: {path}")

    logger.info("Parsing PDF", extra={"file": path.name})

    try:
        reader = pypdf.PdfReader(str(path))
    except pypdf.errors.PdfReadError as exc:
        raise ParseError(f"Cannot read PDF '{path.name}': {exc}") from exc

    if reader.is_encrypted:
        raise ParseError(
            f"PDF '{path.name}' is encrypted. "
            "Decrypt it before ingestion or export an unencrypted copy."
        )

    page_count = len(reader.pages)
    page_texts: list[str] = []
    empty_pages: list[int] = []

    for i, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        text = raw.strip()

        if len(text) < _MIN_CHARS_PER_PAGE:
            empty_pages.append(i)
            # Include a placeholder so page numbers stay aligned
            page_texts.append(f"[PAGE {i} — no extractable text]")
        else:
            # Prepend page marker — the chunker uses this to track page numbers
            page_texts.append(f"[PAGE {i}]\n{text}")

    if empty_pages:
        logger.warning(
            "Low text on pages — may be scanned or image-only",
            extra={"file": path.name, "pages": empty_pages},
        )

    full_text = "\n\n".join(page_texts)

    if not full_text.strip().replace("[PAGE", "").strip():
        raise ParseError(
            f"PDF '{path.name}' produced no extractable text. "
            "It may be a scanned document. OCR support is not yet implemented."
        )

    logger.info(
        "PDF parsed",
        extra={"file": path.name, "pages": page_count, "chars": len(full_text)},
    )

    return ParsedDocument(
        filename=path.name,
        format=DocumentFormat.PDF,
        source_path=str(path),
        text=full_text,
        page_count=page_count,
    )
