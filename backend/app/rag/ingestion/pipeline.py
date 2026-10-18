"""
DocuMind — Ingestion Pipeline
================================
Orchestrates the full ingestion flow for a single document:
    parse → chunk → embed → index → register

This is the only file that knows the full pipeline sequence.
Each stage is implemented in its own module — this file only
wires them together and handles status tracking.

Design decision: each stage updates the document registry independently
so failures are recoverable. If embedding succeeds but indexing fails,
we know exactly where to resume rather than restarting from parsing.

Usage (from ingest.py CLI):
    result = await ingest_document(path, namespace="kubernetes-docs")
"""

import logging
import time
from pathlib import Path

from app.core.exceptions import (
    ChunkError,
    EmbeddingError,
    IndexError,
    ParseError,
)
from app.core.models import ParsedDocument
from app.db.registry import IngestionStatus, register_document, update_status
from app.rag.ingestion.embedder import embed_chunks
from app.rag.ingestion.indexer import upsert_chunks
from ingestion.chunkers.header_aware import chunk_document
from ingestion.parsers import parse_document

logger = logging.getLogger(__name__)


class IngestionResult:
    """Value object returned on successful ingestion."""

    __slots__ = (
        "doc_id",
        "filename",
        "chunk_count",
        "token_count",
        "duration_ms",
        "namespace",
    )

    def __init__(
        self,
        doc_id: str,
        filename: str,
        chunk_count: int,
        token_count: int,
        duration_ms: int,
        namespace: str,
    ) -> None:
        self.doc_id = doc_id
        self.filename = filename
        self.chunk_count = chunk_count
        self.token_count = token_count
        self.duration_ms = duration_ms
        self.namespace = namespace

    def __repr__(self) -> str:
        return (
            f"IngestionResult(file={self.filename!r}, "
            f"chunks={self.chunk_count}, "
            f"tokens={self.token_count}, "
            f"ms={self.duration_ms})"
        )


async def ingest_document(
    path: Path,
    namespace: str = "default",
) -> IngestionResult:
    """
    Run the full ingestion pipeline for a single document.

    Stages:
        1. Parse    — extract text and structure from source file
        2. Chunk    — split into token-sized chunks with heading context
        3. Embed    — generate Voyage AI dense vectors (batched)
        4. Index    — upsert vectors + metadata into Pinecone
        5. Register — update document registry in Postgres

    Args:
        path:      Path to the source document file.
        namespace: Pinecone namespace — use collection name for scoping.
                   Allows collection-scoped search at query time.

    Returns:
        IngestionResult with chunk count, token count, and duration.

    Raises:
        ParseError:     Document cannot be parsed.
        ChunkError:     Chunking produces no output.
        EmbeddingError: Voyage AI call fails after retries.
        IndexError:     Pinecone upsert fails after retries.
    """
    start_ms = int(time.perf_counter() * 1000)

    # ── Stage 1: Parse ──────────────────────────────────────────────
    logger.info("Stage 1/4 — Parsing", extra={"file": path.name})
    try:
        doc: ParsedDocument = parse_document(path)
    except ParseError as exc:
        logger.error("Parse failed", extra={"file": path.name, "error": str(exc)})
        raise

    # Register document in Postgres immediately after parsing
    # so downstream stages can update status even if they fail
    await register_document(
        doc_id=doc.doc_id,
        filename=doc.filename,
        source_path=doc.source_path,
        format=doc.format.value,
        namespace=namespace,
    )
    await update_status(doc.doc_id, IngestionStatus.CHUNKING)

    # ── Stage 2: Chunk ──────────────────────────────────────────────
    logger.info("Stage 2/4 — Chunking", extra={"file": path.name})
    try:
        chunks = chunk_document(doc)
    except ChunkError as exc:
        await update_status(doc.doc_id, IngestionStatus.FAILED, error=str(exc))
        raise

    await update_status(doc.doc_id, IngestionStatus.EMBEDDING)
    logger.info(
        "Chunking complete",
        extra={"file": path.name, "chunks": len(chunks)},
    )

    # ── Stage 3: Embed ──────────────────────────────────────────────
    logger.info("Stage 3/4 — Embedding", extra={"chunks": len(chunks)})
    try:
        embeddings = embed_chunks(chunks)
    except EmbeddingError as exc:
        await update_status(doc.doc_id, IngestionStatus.FAILED, error=str(exc))
        raise

    await update_status(doc.doc_id, IngestionStatus.INDEXING)

    # ── Stage 4: Index ──────────────────────────────────────────────
    logger.info("Stage 4/4 — Indexing into Pinecone", extra={"namespace": namespace})
    try:
        upsert_chunks(chunks, embeddings, namespace=namespace)
    except IndexError as exc:
        await update_status(doc.doc_id, IngestionStatus.FAILED, error=str(exc))
        raise

    # ── Complete ─────────────────────────────────────────────────────
    total_tokens = sum(c.metadata.token_count for c in chunks)
    duration_ms = int(time.perf_counter() * 1000) - start_ms

    await update_status(
        doc.doc_id,
        IngestionStatus.COMPLETE,
        chunk_count=len(chunks),
    )

    result = IngestionResult(
        doc_id=doc.doc_id,
        filename=doc.filename,
        chunk_count=len(chunks),
        token_count=total_tokens,
        duration_ms=duration_ms,
        namespace=namespace,
    )

    logger.info(
        "Ingestion complete",
        extra={
            "file": path.name,
            "chunks": result.chunk_count,
            "tokens": result.token_count,
            "duration": f"{duration_ms}ms",
        },
    )
    return result
