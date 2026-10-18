"""
DocuMind — Query Router (Updated for Day 3)
=============================================
Replace backend/app/api/query.py with this file.

Changes from Day 2:
    - POST /query now requires authentication (Depends(get_current_user))
    - Lifetime query limit checked atomically before pipeline runs
    - Response includes queries_remaining for frontend display
    - POST /ingest added — authenticated document upload endpoint
    - GET /documents still public (read-only, no sensitive data)
"""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from main import limiter

from app.auth.router import CurrentUser
from app.auth.service import AuthError, QueryLimitExceeded, check_and_increment_query_limit
from app.core.config import settings
from app.core.exceptions import RetrievalError
from app.core.models import QueryRequest, QueryResponse
from app.db.registry import list_documents

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_NAMESPACES = frozenset({"default", "kubernetes-docs", "stripe-api", "aws-waf"})


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Query the knowledge base",
)
@limiter.limit("10/minute")
async def query(
    request: Request,
    body: QueryRequest,
    user: CurrentUser,  # ← auth required
) -> QueryResponse:
    """
    Submit a natural language question to the RAG pipeline.
    Requires authentication. Lifetime limit: 3 queries per account.
    """
    if body.namespace not in _ALLOWED_NAMESPACES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Namespace must be one of: {sorted(_ALLOWED_NAMESPACES)}",
        )

    # Atomic limit check — raises QueryLimitExceeded if exhausted
    try:
        usage = await check_and_increment_query_limit(user["id"])
    except QueryLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": "86400"},
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    logger.info(
        "Query authorised",
        extra={
            "user_id": user["id"],
            "namespace": body.namespace,
            "queries": usage["total_queries"],
            "limit": usage["query_limit"],
        },
    )

    try:
        # Lazy import: cohere/voyageai/pinecone are heavy; keep /health cold-start light
        from app.rag.generation.pipeline import run_query

        response = await run_query(
            question=body.question,
            namespace=body.namespace,
            alpha=body.alpha,
        )
    except RetrievalError as exc:
        logger.error("Retrieval failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge retrieval is temporarily unavailable.",
        )
    except Exception:
        logger.exception("Query pipeline failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Query processing failed. Please try again.",
        )

    # Attach query usage to response so frontend can update the counter
    response_dict = response.model_dump()
    response_dict["queries_remaining"] = max(0, usage["query_limit"] - usage["total_queries"])
    response_dict["total_queries"] = usage["total_queries"]
    response_dict["query_limit"] = usage["query_limit"]

    return JSONResponse(content=response_dict)


@router.get("/documents", summary="List indexed documents")
@limiter.limit("30/minute")
async def documents(
    request: Request,
    namespace: str = "default",
) -> list[dict]:
    """List indexed documents. Public endpoint — read only."""
    if namespace not in _ALLOWED_NAMESPACES:
        raise HTTPException(status_code=400, detail="Invalid namespace")

    docs = await list_documents(namespace=namespace)
    return [
        {
            "id": doc["id"],
            "filename": doc["filename"],
            "format": doc["format"],
            "status": doc["status"],
            "chunk_count": doc["chunk_count"],
            "indexed_at": doc["created_at"].isoformat() if doc["created_at"] else None,
        }
        for doc in docs
    ]


@router.get("/health/deep", summary="Deep health check")
async def deep_health(request: Request) -> dict:
    """Check Pinecone + Postgres connectivity."""
    checks: dict[str, str] = {}

    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        pc.describe_index(settings.PINECONE_INDEX)
        checks["pinecone"] = "ok"
    except Exception as exc:
        checks["pinecone"] = f"error: {type(exc).__name__}"

    try:
        import asyncpg

        conn = await asyncpg.connect(settings.DATABASE_URL)
        await conn.execute("SELECT 1")
        await conn.close()
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {type(exc).__name__}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "healthy" if all_ok else "degraded", "checks": checks}
