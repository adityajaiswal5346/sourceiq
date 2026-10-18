"""
DocuMind — HTML Parser
========================
Parses HTML documents — primarily Confluence exports and
web-scraped engineering documentation.

Design decisions:
- BeautifulSoup with lxml backend for fast, robust parsing.
- Navigation, sidebars, footers, and scripts are removed before
  extraction — they add noise that degrades retrieval quality.
- Heading hierarchy is extracted using the same [H1: ...] marker
  convention as the Markdown parser so the header-aware chunker
  uses a single code path for both formats.
- Table content is extracted as structured plain text so tabular
  data (e.g. API parameter tables) remains queryable.
"""

import logging
import re
from pathlib import Path

from app.core.exceptions import ParseError
from app.core.models import DocumentFormat, ParsedDocument
from bs4 import BeautifulSoup, NavigableString, Tag

logger = logging.getLogger(__name__)

# HTML elements to remove entirely before text extraction
# These contain navigation and UI chrome, not document content
_NOISE_TAGS = {
    "nav",
    "header",
    "footer",
    "aside",
    "script",
    "style",
    "noscript",
    "iframe",
    "button",
    "form",
}


def parse_html(path: Path) -> ParsedDocument:
    """
    Parse an HTML file, extracting clean text with heading annotations.

    Args:
        path: Path to the .html or .htm file.

    Returns:
        ParsedDocument with heading-annotated plain text.

    Raises:
        ParseError: If the file cannot be read or produces no content.
    """
    if not path.exists():
        raise ParseError(f"File not found: {path}")

    logger.info("Parsing HTML", extra={"file": path.name})

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            raw = path.read_text(encoding="latin-1")
        except Exception as exc:
            raise ParseError(f"Cannot decode '{path.name}': {exc}") from exc

    soup = BeautifulSoup(raw, "lxml")

    # Remove noise elements in place
    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()

    # Extract the main content container if present
    # Confluence uses <main>, <article>, or div.wiki-content
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"wiki-content|page-content|main-content"))
        or soup.body
        or soup
    )

    if main is None:
        raise ParseError(f"No content container found in '{path.name}'.")

    text = _extract_text(main)

    if not text.strip():
        raise ParseError(f"HTML file '{path.name}' produced no extractable text.")

    logger.info(
        "HTML parsed",
        extra={"file": path.name, "chars": len(text)},
    )

    return ParsedDocument(
        filename=path.name,
        format=DocumentFormat.HTML,
        source_path=str(path),
        text=text,
        page_count=0,
    )


def _extract_text(element: Tag) -> str:
    """
    Recursively extract text from an HTML element, preserving structure.
    Headings get the [H1: ...] annotation; tables are flattened to text.
    """
    parts: list[str] = []

    for child in element.children:
        if isinstance(child, NavigableString):
            stripped = str(child).strip()
            if stripped:
                parts.append(stripped)
            continue

        tag_name = child.name.lower() if child.name else ""

        # Headings — annotate with marker for header-aware chunker
        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_name[1])
            title = child.get_text(separator=" ", strip=True)
            clean = re.sub(r"\s+", " ", title).strip()
            parts.append(f"\n[H{level}: {clean}]\n{clean}")

        # Tables — flatten to pipe-delimited text
        elif tag_name == "table":
            parts.append(_table_to_text(child))

        # Code blocks — preserve intact with a marker
        elif tag_name in ("pre", "code"):
            code = child.get_text()
            parts.append(f"\n```\n{code}\n```\n")

        # Block elements — add spacing
        elif tag_name in ("p", "div", "section", "blockquote", "li"):
            inner = _extract_text(child).strip()
            if inner:
                parts.append(f"\n{inner}")

        # Everything else — recurse
        else:
            parts.append(_extract_text(child))

    return " ".join(parts)


def _table_to_text(table: Tag) -> str:
    """
    Convert an HTML table to readable pipe-delimited text.
    Preserves the information in tables without raw HTML tags.
    """
    rows: list[str] = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(" | ".join(cells))
    return "\n" + "\n".join(rows) + "\n"
