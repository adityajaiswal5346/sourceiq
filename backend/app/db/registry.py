"""
DocuMind — Document Registry (Neon Postgres)
==============================================
Tracks the state of every document through the ingestion pipeline.
Provides idempotency: re-ingesting a document updates its record
rather than creating a duplicate.

Schema is in database/migrations/001_initial.sql.

Tables:
    documents     — one row per source document
    ingestion_jobs — audit log of every ingestion run
"""

import logging
from enum import Enum
from typing import Optional

import asyncpg

from app.core.config import settings
from app.core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class IngestionStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETE = "complete"
    FAILED = "failed"


# ── Connection ─────────────────────────────────────────────────────────────


async def get_connection() -> asyncpg.Connection:
    """Open a single Postgres connection. Caller must close it."""
    try:
        return await asyncpg.connect(settings.DATABASE_URL)
    except Exception as exc:
        raise DatabaseError(f"Cannot connect to Postgres: {exc}") from exc


# ── Document registry ──────────────────────────────────────────────────────


async def register_document(
    doc_id: str,
    filename: str,
    source_path: str,
    format: str,
    namespace: str = "default",
) -> None:
    """
    Insert or update a document record.
    ON CONFLICT upserts so re-ingestion updates rather than duplicates.
    """
    conn = await get_connection()
    try:
        await conn.execute(
            """
            INSERT INTO documents
                (id, filename, source_path, format, namespace, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (id) DO UPDATE
                SET filename    = EXCLUDED.filename,
                    source_path = EXCLUDED.source_path,
                    status      = $6,
                    updated_at  = NOW()
            """,
            doc_id,
            filename,
            source_path,
            format,
            namespace,
            IngestionStatus.PENDING,
        )
    except Exception as exc:
        raise DatabaseError(f"Failed to register document: {exc}") from exc
    finally:
        await conn.close()


async def update_status(
    doc_id: str,
    status: IngestionStatus,
    chunk_count: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """Update the ingestion status of a document."""
    conn = await get_connection()
    try:
        await conn.execute(
            """
            UPDATE documents
            SET status      = $2,
                chunk_count = COALESCE($3, chunk_count),
                error_msg   = $4,
                updated_at  = NOW()
            WHERE id = $1
            """,
            doc_id,
            status,
            chunk_count,
            error,
        )
    except Exception as exc:
        raise DatabaseError(f"Failed to update document status: {exc}") from exc
    finally:
        await conn.close()


async def get_document(doc_id: str) -> Optional[dict]:
    """Fetch a document record by ID. Returns None if not found."""
    conn = await get_connection()
    try:
        row = await conn.fetchrow("SELECT * FROM documents WHERE id = $1", doc_id)
        return dict(row) if row else None
    except Exception as exc:
        raise DatabaseError(f"Failed to fetch document: {exc}") from exc
    finally:
        await conn.close()


async def list_documents(namespace: str = "default") -> list[dict]:
    """List all documents in a namespace, ordered by ingestion time."""
    conn = await get_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT id, filename, format, namespace, status,
                   chunk_count, error_msg, created_at, updated_at
            FROM documents
            WHERE namespace = $1
            ORDER BY created_at DESC
            """,
            namespace,
        )
        return [dict(r) for r in rows]
    except Exception as exc:
        raise DatabaseError(f"Failed to list documents: {exc}") from exc
    finally:
        await conn.close()
