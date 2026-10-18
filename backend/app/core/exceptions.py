"""
DocuMind — Custom Exceptions
==============================
Domain-specific exceptions allow precise error handling at each
pipeline stage without leaking internal details to callers.

Each exception maps to a specific pipeline failure mode so the
ingestion CLI and API can surface clear, actionable error messages.
"""


class DocuMindError(Exception):
    """Base exception for all DocuMind errors."""


# ── Parsing ───────────────────────────────────────────────────────────────


class ParseError(DocuMindError):
    """Raised when a document cannot be parsed (corrupt, unsupported format)."""


class UnsupportedFormatError(ParseError):
    """Raised when a file extension has no registered parser."""


# ── Chunking ──────────────────────────────────────────────────────────────


class ChunkError(DocuMindError):
    """Raised when chunking produces zero chunks from a non-empty document."""


# ── Embedding ─────────────────────────────────────────────────────────────


class EmbeddingError(DocuMindError):
    """Raised when the Voyage AI embedding call fails."""


class EmbeddingDimensionError(EmbeddingError):
    """Raised when returned embedding dimensions don't match config."""


# ── Indexing ──────────────────────────────────────────────────────────────


class IndexError(DocuMindError):
    """Raised when Pinecone upsert fails after retries."""


# ── Database ──────────────────────────────────────────────────────────────


class DatabaseError(DocuMindError):
    """Raised when a Postgres operation fails."""


# ── Retrieval ─────────────────────────────────────────────────────────────


class RetrievalError(DocuMindError):
    """Raised when hybrid search or reranking fails."""


class InsufficientContextError(DocuMindError):
    """
    Raised when retrieved chunks do not meet the minimum confidence
    threshold to generate a reliable answer.
    Not an error condition — surfaced as a user-facing message.
    """
