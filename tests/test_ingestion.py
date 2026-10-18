"""
DocuMind — Day 1 Unit Tests
=============================
Tests for the ingestion pipeline — parsers, chunker, and models.
No API calls, no Pinecone, no Postgres required.
All external dependencies are mocked or bypassed.

Run from repo root:
    export PYTHONPATH=.:backend
    pytest tests/test_ingestion.py -v
"""

from pathlib import Path

import pytest

# ── Parser tests ───────────────────────────────────────────────────────────


class TestMarkdownParser:
    """Tests for the Markdown parser — heading annotation is the key behaviour."""

    def test_parses_basic_markdown(self, tmp_path: Path):
        from ingestion.parsers.markdown import parse_markdown

        md = tmp_path / "guide.md"
        md.write_text("# Introduction\n\nThis is a guide.\n\n## Installation\n\nRun pip install.")
        doc = parse_markdown(md)
        assert doc.filename == "guide.md"
        assert "Introduction" in doc.text
        assert "Installation" in doc.text

    def test_annotates_headings_with_markers(self, tmp_path: Path):
        from ingestion.parsers.markdown import parse_markdown

        md = tmp_path / "guide.md"
        md.write_text("# Getting Started\n\n## Prerequisites\n\nYou need Python.")
        doc = parse_markdown(md)
        # Markers must be present for the header-aware chunker
        assert "[H1: Getting Started]" in doc.text
        assert "[H2: Prerequisites]" in doc.text

    def test_strips_front_matter(self, tmp_path: Path):
        from ingestion.parsers.markdown import parse_markdown

        md = tmp_path / "guide.md"
        md.write_text("---\ntitle: My Doc\ndate: 2024-01-01\n---\n\n# Content\n\nBody text.")
        doc = parse_markdown(md)
        assert "title: My Doc" not in doc.text
        assert "Content" in doc.text

    def test_raises_on_empty_file(self, tmp_path: Path):
        from app.core.exceptions import ParseError

        from ingestion.parsers.markdown import parse_markdown

        md = tmp_path / "empty.md"
        md.write_text("")
        with pytest.raises(ParseError, match="empty"):
            parse_markdown(md)

    def test_raises_on_missing_file(self, tmp_path: Path):
        from app.core.exceptions import ParseError

        from ingestion.parsers.markdown import parse_markdown

        with pytest.raises(ParseError, match="not found"):
            parse_markdown(tmp_path / "nonexistent.md")


class TestParserRegistry:
    """Tests for the parser dispatch registry."""

    def test_dispatches_md_to_markdown_parser(self, tmp_path: Path):
        from ingestion.parsers import parse_document

        md = tmp_path / "readme.md"
        md.write_text("# Title\n\nContent here.")
        doc = parse_document(md)
        assert doc.format.value == "markdown"

    def test_raises_on_unsupported_extension(self, tmp_path: Path):
        from app.core.exceptions import UnsupportedFormatError

        from ingestion.parsers import parse_document

        f = tmp_path / "data.xlsx"
        f.write_text("fake")
        with pytest.raises(UnsupportedFormatError):
            parse_document(f)

    def test_is_supported_returns_true_for_md(self, tmp_path: Path):
        from ingestion.parsers import is_supported

        assert is_supported(Path("guide.md")) is True
        assert is_supported(Path("report.pdf")) is True
        assert is_supported(Path("data.csv")) is False


# ── Chunker tests ──────────────────────────────────────────────────────────


class TestHeaderAwareChunker:
    """Tests for the header-aware chunker — the core Day 1 component."""

    def _make_doc(self, text: str, filename: str = "test.md"):
        """Create a minimal ParsedDocument for testing."""
        from app.core.models import DocumentFormat, ParsedDocument

        return ParsedDocument(
            filename=filename,
            format=DocumentFormat.MARKDOWN,
            source_path=f"/tmp/{filename}",
            text=text,
        )

    def test_produces_chunks_from_simple_text(self):
        from ingestion.chunkers.header_aware import chunk_document

        doc = self._make_doc("Some content here.\n" * 10)
        chunks = chunk_document(doc)
        assert len(chunks) >= 1

    def test_chunks_carry_heading_path(self):
        from ingestion.chunkers.header_aware import chunk_document

        text = (
            "[H1: Production Deployment]\n# Production Deployment\n\n"
            "[H2: TLS Configuration]\n## TLS Configuration\n\n"
            "Configure TLS termination at the load balancer.\n" * 5
        )
        doc = self._make_doc(text)
        chunks = chunk_document(doc)
        paths = [c.metadata.heading_path for c in chunks]
        # At least one chunk should carry the full path
        assert any("Production Deployment" in p for p in paths)
        assert any("TLS Configuration" in p for p in paths)

    def test_heading_path_preserves_hierarchy(self):
        from ingestion.chunkers.header_aware import _build_heading_path

        stack = {1: "Getting Started", 2: "Installation", 3: "macOS"}
        path = _build_heading_path(stack)
        assert path == "Getting Started > Installation > macOS"

    def test_empty_path_for_no_headings(self):
        from ingestion.chunkers.header_aware import _build_heading_path

        assert _build_heading_path({}) == ""

    def test_raises_on_empty_document(self):
        from app.core.exceptions import ChunkError

        from ingestion.chunkers.header_aware import chunk_document

        doc = self._make_doc("   \n\n   ")
        with pytest.raises(ChunkError):
            chunk_document(doc)

    def test_each_chunk_has_unique_id(self):
        from ingestion.chunkers.header_aware import chunk_document

        doc = self._make_doc("Text content.\n" * 50)
        chunks = chunk_document(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Duplicate chunk IDs found"

    def test_chunk_index_is_sequential(self):
        from ingestion.chunkers.header_aware import chunk_document

        doc = self._make_doc("Content.\n" * 50)
        chunks = chunk_document(doc)
        indices = [c.metadata.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_citation_string_format(self):
        from ingestion.chunkers.header_aware import chunk_document

        text = "[H1: Deployment]\n# Deployment\n\n" + "Content.\n" * 10
        doc = self._make_doc(text, "production-guide.md")
        chunks = chunk_document(doc)
        citation = chunks[0].citation_string()
        assert "production-guide.md" in citation


# ── Token counter ──────────────────────────────────────────────────────────


class TestTokenCounter:
    def test_counts_tokens(self):
        from ingestion.chunkers.header_aware import count_tokens

        # "Hello world" is 2 tokens in cl100k_base
        count = count_tokens("Hello world")
        assert count >= 2
        assert isinstance(count, int)

    def test_empty_string_is_zero(self):
        from ingestion.chunkers.header_aware import count_tokens

        assert count_tokens("") == 0


# ── Model tests ────────────────────────────────────────────────────────────


class TestModels:
    def test_parsed_document_generates_uuid(self):
        from app.core.models import DocumentFormat, ParsedDocument

        doc = ParsedDocument(
            filename="test.md",
            format=DocumentFormat.MARKDOWN,
            source_path="/tmp/test.md",
            text="content",
        )
        assert len(doc.doc_id) == 36  # UUID format
        assert "-" in doc.doc_id

    def test_chunk_metadata_generates_uuid(self):
        from app.core.models import ChunkMetadata, DocumentFormat

        meta = ChunkMetadata(
            doc_id="test-id",
            source_file="guide.md",
            source_path="/tmp/guide.md",
            format=DocumentFormat.MARKDOWN,
            chunk_index=0,
            char_count=100,
        )
        assert len(meta.chunk_id) == 36
