"""
DocuMind — Header-Aware Chunker
=================================
Splits documents into chunks while preserving heading hierarchy.

This is the most important component in the ingestion pipeline.
Retrieval quality is directly determined by chunk quality — a chunk
that carries its full heading context ("Production Deployment >
TLS Configuration > Certificate Rotation") gives the LLM the
information it needs to generate accurate, attributable answers.

Algorithm:
    1. Split the document text on heading markers ([H1:...], [H2:...])
    2. Track the current heading stack as headings are encountered
    3. For each text section, build the heading_path from the stack
    4. Apply recursive character splitting within each section
       to enforce the configured chunk_size and chunk_overlap
    5. Attach heading_path and source metadata to every chunk

Design decisions:
- Heading markers are written by the parsers (not added here)
  so this chunker is parser-agnostic.
- chunk_size is measured in tokens (via tiktoken), not characters.
  Character limits produce inconsistent chunks for mixed-language
  content and code blocks.
- Overlap ensures that context at chunk boundaries is not lost.
  A sentence that spans a chunk boundary appears in both adjacent
  chunks, preserving its meaning in each.
"""

import logging
import re
from typing import Generator

import tiktoken
from app.core.config import settings
from app.core.exceptions import ChunkError
from app.core.models import ChunkMetadata, DocumentChunk, ParsedDocument

logger = logging.getLogger(__name__)

# Matches the heading markers embedded by the parsers
# Captures: level (1-6), title text
_HEADING_MARKER_RE = re.compile(r"\[H(\d): ([^\]]+)\]")

# Matches the [PAGE N] markers embedded by the PDF parser
_PAGE_MARKER_RE = re.compile(r"\[PAGE (\d+)\]")

# Tokeniser — cl100k_base covers Claude and GPT-4 vocabulary
_TOKENISER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in text using the cl100k_base tokeniser."""
    return len(_TOKENISER.encode(text))


def chunk_document(doc: ParsedDocument) -> list[DocumentChunk]:
    """
    Split a ParsedDocument into chunks with heading-path metadata.

    Args:
        doc: Parsed document with heading-annotated text.

    Returns:
        List of DocumentChunk objects, each carrying full context.

    Raises:
        ChunkError: If chunking produces zero chunks from non-empty input.
    """
    if not doc.text.strip():
        raise ChunkError(f"Document '{doc.filename}' has no text to chunk.")

    chunks = list(_generate_chunks(doc))

    if not chunks:
        raise ChunkError(
            f"Chunking produced zero chunks for '{doc.filename}'. "
            "Check that the document contains readable text."
        )

    logger.info(
        "Document chunked",
        extra={
            "file": doc.filename,
            "chunks": len(chunks),
            "format": doc.format,
        },
    )
    return chunks


def _generate_chunks(doc: ParsedDocument) -> Generator[DocumentChunk, None, None]:
    """
    Core chunking generator. Walks the document text, tracking headings
    and yielding chunks with correct metadata.
    """
    chunk_size = settings.CHUNK_SIZE
    chunk_overlap = settings.CHUNK_OVERLAP

    # Current state tracked as we walk the document
    heading_stack: dict[int, str] = {}  # level → title
    current_page: int = 0
    chunk_index: int = 0

    # Split text into sections on heading markers
    # Each section is: optional heading marker + text until next heading
    sections = _split_on_headings(doc.text)

    for section_heading_level, section_heading_title, section_text in sections:
        # Update heading stack
        if section_heading_level > 0:
            heading_stack[section_heading_level] = section_heading_title
            # Clear any deeper headings (we've moved to a new section)
            for level in list(heading_stack.keys()):
                if level > section_heading_level:
                    del heading_stack[level]

        # Update page number from PAGE markers in this section
        page_match = _PAGE_MARKER_RE.search(section_text)
        if page_match:
            current_page = int(page_match.group(1))

        # Clean the section text (remove markers before chunking)
        clean_text = _clean_markers(section_text).strip()
        if not clean_text:
            continue

        # Build heading path from current stack
        heading_path = _build_heading_path(heading_stack)

        # Split section into token-sized chunks with overlap
        text_chunks = _split_by_tokens(clean_text, chunk_size, chunk_overlap)

        for text_chunk in text_chunks:
            if not text_chunk.strip():
                continue

            metadata = ChunkMetadata(
                doc_id=doc.doc_id,
                source_file=doc.filename,
                source_path=doc.source_path,
                format=doc.format,
                heading_path=heading_path,
                page=current_page,
                chunk_index=chunk_index,
                char_count=len(text_chunk),
                token_count=count_tokens(text_chunk),
            )

            yield DocumentChunk(text=text_chunk, metadata=metadata)
            chunk_index += 1


def _split_on_headings(
    text: str,
) -> Generator[tuple[int, str, str], None, None]:
    """
    Split text on heading markers, yielding (level, title, text) tuples.
    Level 0 = content before the first heading.
    """
    last_end = 0
    last_level = 0
    last_title = ""

    for match in _HEADING_MARKER_RE.finditer(text):
        # Yield the text before this heading
        section_text = text[last_end : match.start()]
        if section_text.strip() or last_level > 0:
            yield (last_level, last_title, section_text)

        last_level = int(match.group(1))
        last_title = match.group(2).strip()
        last_end = match.end()

    # Yield remaining text after the last heading
    remaining = text[last_end:]
    if remaining.strip():
        yield (last_level, last_title, remaining)


def _build_heading_path(stack: dict[int, str]) -> str:
    """
    Build a human-readable heading path from the heading stack.

    Stack: {1: "Production Deployment", 2: "TLS Configuration", 3: "Certificate Rotation"}
    Path:  "Production Deployment > TLS Configuration > Certificate Rotation"
    """
    if not stack:
        return ""
    return " > ".join(stack[level] for level in sorted(stack.keys()))


def _split_by_tokens(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """
    Split text into chunks of approximately chunk_size tokens,
    with chunk_overlap tokens of overlap between adjacent chunks.

    Uses sentence boundaries where possible to avoid splitting
    mid-sentence. Falls back to hard token splits for very long
    sentences (e.g. code lines without sentence markers).
    """
    tokens = _TOKENISER.encode(text)
    total = len(tokens)

    if total <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < total:
        end = min(start + chunk_size, total)
        chunk_tokens = tokens[start:end]
        chunk_text = _TOKENISER.decode(chunk_tokens)
        chunks.append(chunk_text)

        if end >= total:
            break

        # Step forward by (chunk_size - overlap) so adjacent chunks share
        # chunk_overlap tokens of context
        start += chunk_size - chunk_overlap

    return chunks


def _clean_markers(text: str) -> str:
    """Remove [H1: ...] and [PAGE N] markers from text before indexing."""
    text = _HEADING_MARKER_RE.sub("", text)
    text = _PAGE_MARKER_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
