"""
DocuMind — Markdown Parser
============================
Parses Markdown documents while preserving heading structure.

This is the most important parser for engineering documentation:
Kubernetes docs, Stripe API docs, internal runbooks, and architecture
decision records are almost exclusively Markdown.

Design decisions:
- Heading hierarchy is extracted and attached to every text section
  as metadata. This is what enables header-aware chunking downstream.
- Code blocks are preserved intact — splitting inside a code example
  produces nonsensical chunks and breaks citation accuracy.
- Front matter (YAML/TOML between --- delimiters) is stripped —
  it contains metadata not useful for retrieval.
- The parser returns a ParsedDocument whose text contains embedded
  heading markers that the header-aware chunker reads to assign
  the correct heading_path to each chunk.
"""

import logging
import re
from pathlib import Path

from app.core.exceptions import ParseError
from app.core.models import DocumentFormat, ParsedDocument

logger = logging.getLogger(__name__)

# Matches YAML or TOML front matter at the start of the file
_FRONT_MATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)

# Matches ATX-style headings: # H1, ## H2, ### H3
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def parse_markdown(path: Path) -> ParsedDocument:
    """
    Parse a Markdown file preserving heading structure.

    The returned text embeds heading markers in the format:
        [H1: Introduction]
        [H2: Installation]
        [H3: Prerequisites]
    These markers are read by the header-aware chunker to assign
    the correct heading_path to each chunk.

    Args:
        path: Path to the .md or .mdx file.

    Returns:
        ParsedDocument with heading-annotated text.

    Raises:
        ParseError: If the file cannot be read or is empty.
    """
    if not path.exists():
        raise ParseError(f"File not found: {path}")

    logger.info("Parsing Markdown", extra={"file": path.name})

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Try latin-1 fallback for files with encoding issues
        try:
            raw = path.read_text(encoding="latin-1")
            logger.warning("Fell back to latin-1 encoding", extra={"file": path.name})
        except Exception as exc:
            raise ParseError(f"Cannot decode '{path.name}': {exc}") from exc

    if not raw.strip():
        raise ParseError(f"Markdown file '{path.name}' is empty.")

    # Strip front matter — YAML/TOML metadata block at top of file
    text = _FRONT_MATTER_RE.sub("", raw).strip()

    # Annotate headings with markers the chunker can parse
    text = _annotate_headings(text)

    logger.info(
        "Markdown parsed",
        extra={"file": path.name, "chars": len(text)},
    )

    return ParsedDocument(
        filename=path.name,
        format=DocumentFormat.MARKDOWN,
        source_path=str(path),
        text=text,
        page_count=0,  # Markdown has no page concept
    )


def _annotate_headings(text: str) -> str:
    """
    Replace ATX headings with annotated markers.

    Input:  ## Installation
    Output: [H2: Installation]\n## Installation

    The original heading is preserved for human readability;
    the marker is what the chunker reads programmatically.
    This dual representation means the text still reads naturally
    while carrying machine-parseable structure.
    """

    def replace_heading(match: re.Match) -> str:
        hashes = match.group(1)
        level = len(hashes)
        title = match.group(2).strip()
        # Remove any inline markdown from heading (bold, code, links)
        clean_title = re.sub(r"[`*\[\]()]", "", title).strip()
        return f"[H{level}: {clean_title}]\n{match.group(0)}"

    return _HEADING_RE.sub(replace_heading, text)
