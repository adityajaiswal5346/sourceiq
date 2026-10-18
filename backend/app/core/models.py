"""
DocuMind — Document Models
============================
Pydantic models representing documents and chunks at each pipeline stage.

Design decision: a single ChunkMetadata model carries context through the
entire pipeline — from parsing through chunking, embedding, indexing,
retrieval, and citation generation. Adding a field here automatically
propagates it to every downstream stage.

Every chunk carries its full heading path so the LLM receives:
  "Production Deployment > Configuring TLS > Certificate rotation"
rather than an orphaned block of text.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocumentFormat(str, Enum):
    """Supported source document formats."""

    PDF = "pdf"
    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"


class DocumentSource(str, Enum):
    """Where the document came from — for audit and display."""

    LOCAL = "local"
    S3 = "s3"
    CONFLUENCE = "confluence"
    URL = "url"


class ParsedDocument(BaseModel):
    """
    Output of the parsing stage.
    Raw text + metadata extracted from the source document.
    Input to the chunking stage.
    """

    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    format: DocumentFormat
    source: DocumentSource = DocumentSource.LOCAL
    source_path: str = Field(description="Original file path or URL")
    text: str = Field(description="Full extracted text")
    page_count: int = Field(default=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    parsed_at: datetime = Field(default_factory=datetime.utcnow)


class ChunkMetadata(BaseModel):
    """
    Metadata attached to every chunk — persisted in Pinecone and Postgres.

    heading_path is the key field: it carries the full H1 > H2 > H3
    hierarchy from the source document so context is never lost.

    Example:
        heading_path = "Production Deployment > TLS Configuration > Certificate Rotation"
        source_file  = "kubernetes-production-guide.md"
        page         = 47
    """

    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doc_id: str
    source_file: str
    source_path: str
    format: DocumentFormat
    heading_path: str = Field(
        default="",
        description="Full heading hierarchy: H1 > H2 > H3. Empty for documents with no headings.",
    )
    page: int = Field(default=0, description="Source page number (0 if not applicable)")
    chunk_index: int = Field(description="Position of this chunk within the document")
    char_count: int
    token_count: int = Field(default=0, description="Approximate token count via tiktoken")


class DocumentChunk(BaseModel):
    """
    A single chunk ready for embedding and indexing.
    Text + metadata together — this is what flows into the embedding stage.
    """

    text: str
    metadata: ChunkMetadata

    @property
    def chunk_id(self) -> str:
        return self.metadata.chunk_id

    def citation_string(self) -> str:
        """
        Human-readable citation for use in Claude prompts and UI display.
        Format: 'filename > heading_path (page N)'
        """
        parts = [self.metadata.source_file]
        if self.metadata.heading_path:
            parts.append(self.metadata.heading_path)
        if self.metadata.page > 0:
            parts.append(f"page {self.metadata.page}")
        return " > ".join(parts)


class IndexedChunk(BaseModel):
    """
    A chunk that has been embedded and upserted into Pinecone.
    Returned by the ingestion pipeline to update the document registry.
    """

    chunk_id: str
    doc_id: str
    vector_id: str = Field(description="ID used in Pinecone — same as chunk_id")
    token_count: int
    indexed_at: datetime = Field(default_factory=datetime.utcnow)


class RetrievedChunk(BaseModel):
    """
    A chunk returned from Pinecone hybrid search.
    Carries all metadata needed for citation and reranking.
    """

    chunk_id: str
    text: str
    source_file: str
    heading_path: str
    page: int
    doc_id: str
    citation: str = Field(description="Pre-formatted citation string from metadata")
    score: float = Field(description="Pinecone retrieval score")
    chunk_index: int = Field(default=0)


class RankedChunk(BaseModel):
    """
    A chunk after Cohere cross-encoder reranking.
    Carries both the original retrieval score and the rerank score.
    The rerank score is what determines final ordering and citation order.
    """

    chunk_id: str
    text: str
    source_file: str
    heading_path: str
    page: int
    doc_id: str
    citation: str
    retrieval_score: float = Field(description="Original Pinecone bi-encoder score")
    rerank_score: float = Field(description="Cohere cross-encoder relevance score")
    confidence_score: float = Field(description="Normalised confidence [0, 1]")
    chunk_index: int = Field(default=0)


class Citation(BaseModel):
    """
    A single source citation included in a QueryResponse.
    Shown in the UI alongside the answer text.
    """

    source_file: str
    heading_path: str
    page: int
    citation: str = Field(description="Full formatted citation string")
    confidence: float = Field(description="Reranker confidence for this specific chunk")


class QueryResponse(BaseModel):
    """
    The complete response returned by POST /api/query.
    This is what the frontend receives and renders.
    """

    answer: str
    citations: list[Citation]
    confidence_score: float = Field(description="Overall answer confidence [0, 1]")
    confidence_label: str = Field(description="high | medium | low")
    chunks_used: int = Field(description="Number of chunks passed to Claude")
    namespace: str
    response_ms: int = Field(description="Total query pipeline latency")

    # Present when confidence is low — shown as a warning in the UI
    insufficient_context: bool = Field(default=False)
    warning_message: str = Field(default="")


class QueryRequest(BaseModel):
    """
    Request body for POST /api/query.
    Validated by FastAPI before the pipeline runs.
    """

    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="The user's natural language question",
    )
    namespace: str = Field(
        default="default",
        max_length=100,
        description="Document collection to search",
        pattern=r"^[a-z0-9\-]+$",  # lowercase alphanumeric and hyphens only
    )
    alpha: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Hybrid search weighting. 0=keyword only, 1=semantic only.",
    )
