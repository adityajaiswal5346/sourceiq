"""
DocuMind — Parser Registry
===========================
Dispatches files to format-specific parsers by extension.
"""

from collections.abc import Callable
from pathlib import Path

from app.core.exceptions import UnsupportedFormatError
from app.core.models import ParsedDocument

from ingestion.parsers.html import parse_html
from ingestion.parsers.markdown import parse_markdown
from ingestion.parsers.pdf import parse_pdf

ParserFn = Callable[[Path], ParsedDocument]

_PARSERS: dict[str, ParserFn] = {
    ".md": parse_markdown,
    ".mdx": parse_markdown,
    ".pdf": parse_pdf,
    ".html": parse_html,
    ".htm": parse_html,
}


def parse_document(path: Path) -> ParsedDocument:
    """Parse a document using the parser registered for its file extension."""
    ext = path.suffix.lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        supported = ", ".join(sorted(_PARSERS))
        raise UnsupportedFormatError(
            f"Unsupported file extension '{ext}' for '{path.name}'. " f"Supported: {supported}"
        )
    return parser(path)


def is_supported(path: Path) -> bool:
    """Return True if the file extension has a registered parser."""
    return path.suffix.lower() in _PARSERS


def supported_extensions() -> list[str]:
    """Return sorted list of supported file extensions (e.g. '.md')."""
    return sorted(_PARSERS.keys())
