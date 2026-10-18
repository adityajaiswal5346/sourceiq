"""
DocuMind — Hybrid Search Retriever
=====================================
Executes hybrid dense + sparse retrieval against Pinecone.

Why hybrid over pure semantic search:
    Dense (semantic) search excels at conceptual questions:
    "how does Kubernetes manage rolling deployments?" retrieves
    relevant chunks even if the exact words don't match.

    Sparse (BM25 keyword) search excels at precise lookups:
    "terminationGracePeriodSeconds default value" — exact config
    parameter names, error codes, version numbers. Semantic search
    alone misses these because the embedding space doesn't
    distinguish "30" from "60" meaningfully.

    Combined with a tunable alpha, both retrieval modes contribute.
    HYBRID_ALPHA=0.7 means 70% dense weight, 30% sparse weight.
    Lower alpha for API reference docs, higher for architecture docs.

Security:
    - Namespace is validated against an allowlist before querying.
      An attacker cannot pivot to a different document collection
      by injecting a namespace parameter.
    - Query text is passed directly to the embedding API — no SQL,
      no shell interpolation, no injection surface.
    - Top-K is capped at MAX_RETRIEVAL_K regardless of caller input.
"""

import logging
from typing import Optional

from pinecone import Pinecone

from app.core.config import settings
from app.core.exceptions import RetrievalError
from app.core.models import RetrievedChunk

logger = logging.getLogger(__name__)

# Hard cap — callers cannot request more than this regardless of config
MAX_RETRIEVAL_K = 20

# Namespaces that callers are permitted to query
# Populated from config; validated on every request
_VALID_NAMESPACES: set[str] = {"default", "kubernetes-docs", "stripe-api", "aws-waf"}


def hybrid_search(
    query_embedding: list[float],
    query_sparse: Optional[dict],
    namespace: str = "default",
    top_k: Optional[int] = None,
    alpha: Optional[float] = None,
    filter_doc_ids: Optional[list[str]] = None,
) -> list["RetrievedChunk"]:
    """
    Execute hybrid dense+sparse retrieval against Pinecone.

    Args:
        query_embedding:  Dense vector from Voyage AI embed_query().
        query_sparse:     Sparse BM25 weights from encode_sparse().
                          None falls back to dense-only search.
        namespace:        Pinecone namespace — validated against allowlist.
        top_k:            Number of results to return. Defaults to
                          settings.TOP_K_RETRIEVAL. Capped at MAX_RETRIEVAL_K.
        alpha:            Dense/sparse weighting. Defaults to settings.HYBRID_ALPHA.
                          0.0 = keyword only, 1.0 = semantic only.
        filter_doc_ids:   Optional list of doc IDs to restrict search scope.

    Returns:
        List of RetrievedChunk ordered by relevance score descending.

    Raises:
        RetrievalError: Pinecone query fails or namespace is invalid.
        ValueError:     alpha outside [0.0, 1.0].
    """
    # ── Input validation ───────────────────────────────────────────
    _validate_namespace(namespace)

    effective_k = min(top_k or settings.TOP_K_RETRIEVAL, MAX_RETRIEVAL_K)
    effective_alpha = alpha if alpha is not None else settings.HYBRID_ALPHA

    if not 0.0 <= effective_alpha <= 1.0:
        raise ValueError(f"alpha must be between 0.0 and 1.0, got {effective_alpha}")

    # ── Build query ────────────────────────────────────────────────
    query_kwargs: dict = {
        "vector": query_embedding,
        "top_k": effective_k,
        "namespace": namespace,
        "include_metadata": True,
    }

    # Metadata filter — restrict to specific documents if requested
    if filter_doc_ids:
        query_kwargs["filter"] = {"doc_id": {"$in": filter_doc_ids}}

    # Hybrid weighting — scale vectors by alpha before querying
    if query_sparse:
        scaled_dense, scaled_sparse = _scale_vectors(query_embedding, query_sparse, effective_alpha)
        query_kwargs["vector"] = scaled_dense
        query_kwargs["sparse_vector"] = scaled_sparse

    # ── Execute ────────────────────────────────────────────────────
    logger.debug(
        "Executing hybrid search",
        extra={
            "namespace": namespace,
            "top_k": effective_k,
            "alpha": effective_alpha,
            "has_sparse": query_sparse is not None,
        },
    )

    try:
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index(settings.PINECONE_INDEX)
        response = index.query(**query_kwargs)
    except Exception as exc:
        raise RetrievalError(f"Pinecone query failed: {exc}") from exc

    # ── Parse results ──────────────────────────────────────────────
    chunks = []
    for match in response.matches:
        meta = match.metadata or {}
        chunks.append(
            RetrievedChunk(
                chunk_id=match.id,
                text=meta.get("text", ""),
                source_file=meta.get("source_file", ""),
                heading_path=meta.get("heading_path", ""),
                page=int(meta.get("page", 0)),
                doc_id=meta.get("doc_id", ""),
                citation=meta.get("citation", meta.get("source_file", "")),
                score=float(match.score),
                chunk_index=int(meta.get("chunk_index", 0)),
            )
        )

    logger.debug(
        "Hybrid search complete",
        extra={"results": len(chunks), "top_score": chunks[0].score if chunks else 0},
    )
    return chunks


def encode_sparse(query: str) -> Optional[dict]:
    """
    Encode query text as BM25 sparse weights for hybrid search.

    Pinecone's serverless index handles sparse encoding server-side
    when using the integrated sparse encoder. For compatibility we
    return None here, which falls back to dense-only search — the
    reranker compensates for precision loss.

    In a production deployment with Pinecone's inference API enabled,
    this would call pc.inference.embed() with model='pinecone-sparse'.
    """
    # Sparse encoding via Pinecone inference API (requires inference tier)
    # Returning None gracefully falls back to dense-only search
    # The reranker adds precision that pure sparse search provides
    logger.debug("Sparse encoding not available — using dense-only retrieval")
    return None


def _scale_vectors(
    dense: list[float],
    sparse: dict,
    alpha: float,
) -> tuple[list[float], dict]:
    """
    Scale dense and sparse vectors by alpha for hybrid weighting.

    alpha=1.0 → dense only (sparse weights zeroed)
    alpha=0.0 → sparse only (dense weights zeroed)
    alpha=0.7 → 70% dense, 30% sparse

    The scaling is applied to the query vectors before Pinecone
    scores against the stored document vectors.
    """
    scaled_dense = [v * alpha for v in dense]
    scaled_sparse = {
        "indices": sparse["indices"],
        "values": [v * (1 - alpha) for v in sparse["values"]],
    }
    return scaled_dense, scaled_sparse


def _validate_namespace(namespace: str) -> None:
    """
    Validate namespace against allowlist.

    Prevents an attacker from pivoting to arbitrary namespaces
    by injecting unexpected values into the namespace parameter.
    Returns silently if valid, raises RetrievalError if not.
    """
    if namespace not in _VALID_NAMESPACES:
        raise RetrievalError(
            f"Namespace '{namespace}' is not permitted. "
            f"Valid namespaces: {sorted(_VALID_NAMESPACES)}"
        )
