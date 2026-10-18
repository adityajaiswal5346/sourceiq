"""
DocuMind — Cohere Reranker
============================
Reranks retrieved chunks using Cohere's cross-encoder model.

Why reranking matters:
    Pinecone's hybrid search returns candidates ranked by a bi-encoder:
    query and document are embedded independently and compared by
    cosine similarity. This is fast but imprecise — the query and
    document representations never interact during scoring.

    Cohere Rerank uses a cross-encoder: query and document are
    processed jointly by the model, allowing it to reason about
    relevance in context. This is slower but substantially more
    accurate for passage retrieval, especially on technical content
    where exact phrasing matters.

    The architecture: fast bi-encoder retrieval over the full index
    (top 10) → accurate cross-encoder reranking over the small
    candidate set (top 5). Best of both: scale and precision.

Confidence scoring:
    The reranker returns a relevance score in [0, 1] for each chunk.
    We normalise the top-k scores to produce a single confidence
    value for the answer:
        - High confidence (>0.7): answer is directly supported
        - Medium confidence (0.4-0.7): answer is likely relevant
        - Low confidence (<0.4): insufficient context warning shown

Security:
    - Query text and chunk text are passed to the Cohere API.
      No PII should be present in the document corpus.
    - Reranker scores are bounded [0, 1] — no normalisation
      overflow possible.
    - API key is read from settings, never from request parameters.
"""

import logging
import time
from typing import Optional

import cohere

from app.core.config import settings
from app.core.exceptions import RetrievalError
from app.core.models import RankedChunk, RetrievedChunk

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0

# Confidence thresholds — surfaced in the API response and UI
CONFIDENCE_HIGH = 0.70
CONFIDENCE_MEDIUM = 0.40


def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    top_k: Optional[int] = None,
) -> list[RankedChunk]:
    """
    Rerank retrieved chunks using Cohere cross-encoder.

    Args:
        query:   The original user question.
        chunks:  Candidates from hybrid search (typically top 10).
        top_k:   Number of chunks to return after reranking.
                 Defaults to settings.TOP_K_RERANK (typically 5).

    Returns:
        List of RankedChunk ordered by rerank score descending,
        truncated to top_k. Each chunk carries a normalised
        confidence_score in [0, 1].

    Raises:
        RetrievalError: Cohere API fails after max retries.
    """
    if not chunks:
        return []

    effective_k = top_k or settings.TOP_K_RERANK

    # Cohere reranks all candidates and we take top_k after
    documents = [chunk.text for chunk in chunks]

    logger.debug(
        "Reranking chunks",
        extra={
            "candidates": len(chunks),
            "top_k": effective_k,
            "model": settings.COHERE_MODEL,
        },
    )

    results = _rerank_with_retry(query, documents, effective_k)

    # Build RankedChunk list — map reranker results back to original chunks
    ranked: list[RankedChunk] = []
    for result in results:
        original = chunks[result.index]
        rerank_score = float(result.relevance_score)

        ranked.append(
            RankedChunk(
                chunk_id=original.chunk_id,
                text=original.text,
                source_file=original.source_file,
                heading_path=original.heading_path,
                page=original.page,
                doc_id=original.doc_id,
                citation=original.citation,
                retrieval_score=original.score,
                rerank_score=rerank_score,
                confidence_score=rerank_score,  # Cohere scores are already in [0,1]
                chunk_index=original.chunk_index,
            )
        )

    logger.debug(
        "Reranking complete",
        extra={
            "returned": len(ranked),
            "top_confidence": ranked[0].confidence_score if ranked else 0,
        },
    )
    return ranked


def compute_answer_confidence(chunks: list[RankedChunk]) -> float:
    """
    Compute a single confidence score for the answer from ranked chunks.

    Uses a weighted average of the top chunk scores, with the
    highest-scoring chunk weighted most heavily.

    Returns:
        Float in [0, 1]. Above CONFIDENCE_HIGH means direct source
        evidence. Below CONFIDENCE_MEDIUM triggers a UI warning.
    """
    if not chunks:
        return 0.0

    if len(chunks) == 1:
        return chunks[0].confidence_score

    # Weighted: top chunk carries 60%, remainder share 40%
    top = chunks[0].confidence_score * 0.6
    rest_avg = sum(c.confidence_score for c in chunks[1:]) / len(chunks[1:])
    rest = rest_avg * 0.4

    return round(min(top + rest, 1.0), 3)


def confidence_label(score: float) -> str:
    """Return a human-readable confidence label for UI display."""
    if score >= CONFIDENCE_HIGH:
        return "high"
    if score >= CONFIDENCE_MEDIUM:
        return "medium"
    return "low"


def _rerank_with_retry(
    query: str,
    documents: list[str],
    top_k: int,
    attempt: int = 0,
) -> list:
    """Call Cohere rerank with exponential backoff on transient errors."""
    try:
        client = cohere.Client(api_key=settings.COHERE_API_KEY)
        response = client.rerank(
            query=query,
            documents=documents,
            top_n=top_k,
            model=settings.COHERE_MODEL,
        )
        return response.results

    except cohere.TooManyRequestsError as exc:
        if attempt >= _MAX_RETRIES:
            raise RetrievalError(
                f"Cohere rate limit exceeded after {_MAX_RETRIES} retries."
            ) from exc
        wait = _RETRY_DELAY * (2**attempt)
        logger.warning(f"Cohere rate limited — retrying in {wait}s")
        time.sleep(wait)
        return _rerank_with_retry(query, documents, top_k, attempt + 1)

    except Exception as exc:
        if attempt >= _MAX_RETRIES:
            raise RetrievalError(
                f"Cohere rerank failed after {_MAX_RETRIES} retries: {exc}"
            ) from exc
        wait = _RETRY_DELAY * (2**attempt)
        logger.warning(f"Reranking error — retrying in {wait}s: {exc}")
        time.sleep(wait)
        return _rerank_with_retry(query, documents, top_k, attempt + 1)
