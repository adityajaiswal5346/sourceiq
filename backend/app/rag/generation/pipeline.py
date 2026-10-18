"""
SourceIq — Query Pipeline (Production Layer)
===============================================
Orchestrates the full query flow:
    embed → search → rerank → generate → respond

Production layers added:
    Layer 1 — Langfuse v4 tracing (4 spans per query)
    Layer 3 — Guardrails (confidence threshold, scope, injection)
    Layer 4 — Cost tracking (per-query, logged to Langfuse)

Latency breakdown (typical):
    Voyage AI embed:   ~100ms
    Pinecone search:   ~50ms
    Cohere rerank:     ~200ms
    Claude generate:   ~1500ms
    Total:             ~1850ms
"""

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from app.core.config import settings
from app.core.exceptions import InsufficientContextError, RetrievalError
from app.core.models import Citation, QueryResponse
from app.rag.generation.generator import generate_answer
from app.rag.ingestion.embedder import embed_query
from app.rag.retrieval.reranker import (
    compute_answer_confidence,
    confidence_label,
    rerank_chunks,
)
from app.rag.retrieval.searcher import encode_sparse, hybrid_search

logger = logging.getLogger(__name__)

# ── Langfuse v4 client (optional — must not break queries) ───────
_langfuse_client: Any | None = None
_langfuse_checked = False


def _get_langfuse() -> Any | None:
    global _langfuse_client, _langfuse_checked
    if _langfuse_checked:
        return _langfuse_client
    _langfuse_checked = True
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.info("Langfuse keys not set — tracing disabled")
        return None
    try:
        from langfuse import get_client

        _langfuse_client = get_client()
    except Exception as exc:
        logger.warning("Langfuse init failed (non-fatal): %s", exc)
        _langfuse_client = None
    return _langfuse_client


class _NoOpObservation:
    def update(self, **kwargs: Any) -> None:
        pass


@contextmanager
def _observation(**kwargs: Any) -> Iterator[Any]:
    client = _get_langfuse()
    if client is None:
        yield _NoOpObservation()
        return
    try:
        with client.start_as_current_observation(**kwargs) as obs:
            yield obs
    except Exception as exc:
        logger.warning("Langfuse observation failed (non-fatal): %s", exc)
        yield _NoOpObservation()


def _flush_langfuse() -> None:
    client = _get_langfuse()
    if client is None:
        return
    try:
        client.flush()
        # Lambda freezes after the response — block until traces are exported
        if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            client.shutdown()
    except Exception as exc:
        logger.warning("Langfuse flush failed (non-fatal): %s", exc)


# ── Cost model — $ per 1K tokens (approximate 2026 pricing) ────────
COST_PER_1K = {
    "claude_in": 0.003,
    "claude_out": 0.015,
    "voyage": 0.00012,
    "cohere": 0.0002,
}

# ── Guardrail patterns ──────────────────────────────────────────────
OUT_OF_SCOPE = [
    "tell me a joke",
    "write code",
    "what is the weather",
    "who is the president",
    "help me write",
    "translate",
    "write a poem",
    "sing a song",
]

INJECTION_PATTERNS = [
    "ignore previous instructions",
    "disregard your instructions",
    "you are now",
    "forget everything",
    "system prompt",
    "jailbreak",
    "bypass",
    "override your",
]

CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.6"))


def _check_guardrails(question: str) -> Optional[dict]:
    """
    Check out-of-scope and prompt injection BEFORE any API call.
    Returns a blocked response dict, or None if clean.
    Cost: $0 — no external calls made.
    """
    q = question.lower()

    # Guardrail 1 — out of scope
    if any(p in q for p in OUT_OF_SCOPE):
        return {
            "blocked": True,
            "reason": "out-of-scope",
            "answer": (
                "I can only answer questions about the indexed "
                "documentation. This appears to be outside that scope."
            ),
        }

    # Guardrail 2 — prompt injection
    if any(p in q for p in INJECTION_PATTERNS):
        return {
            "blocked": True,
            "reason": "injection",
            "answer": "This query cannot be processed.",
        }

    return None


async def run_query(
    question: str,
    namespace: str = "default",
    alpha: Optional[float] = None,
    filter_doc_ids: Optional[list[str]] = None,
) -> QueryResponse:
    """
    Execute the full query pipeline with Langfuse tracing.

    Stages (each traced as a Langfuse span):
        1. Guardrails — scope + injection check (no API cost)
        2. Embed      — encode question with Voyage AI
        3. Search     — hybrid Pinecone search (dense + sparse)
        4. Rerank     — Cohere cross-encoder reranking
        5. Confidence — threshold check (guardrail 3)
        6. Generate   — Claude answer with citation constraints
        7. Log        — write to query_log (non-blocking)
    """
    start_ms = int(time.perf_counter() * 1000)

    try:
        # ── Start Langfuse trace ─────────────────────────────────────
        with _observation(
            as_type="span",
            name="rag-query",
            input={"question": question, "namespace": namespace},
        ) as root:
            try:
                # ── Guardrails (scope + injection) ───────────────────
                blocked = _check_guardrails(question)
                if blocked:
                    root.update(
                        output={"blocked": blocked["reason"]},
                        tags=[blocked["reason"]],
                    )
                    return _guardrail_response(
                        blocked["answer"], namespace, start_ms, blocked["reason"]
                    )

                # ── Span 1: Embed query ──────────────────────────────
                with _observation(
                    as_type="span",
                    name="embed-query",
                ) as s_embed:
                    query_embedding = embed_query(question)
                    query_sparse = encode_sparse(question)
                    embed_toks = len(question.split()) * 2  # rough estimate
                    s_embed.update(
                        output={
                            "embedding_dim": len(query_embedding),
                            "has_sparse": query_sparse is not None,
                        }
                    )

                # ── Span 2: Hybrid search ────────────────────────────
                with _observation(
                    as_type="span",
                    name="retrieve-chunks",
                ) as s_retrieve:
                    try:
                        retrieved_chunks = hybrid_search(
                            query_embedding=query_embedding,
                            query_sparse=query_sparse,
                            namespace=namespace,
                            alpha=alpha,
                            filter_doc_ids=filter_doc_ids,
                        )
                    except RetrievalError as exc:
                        s_retrieve.update(
                            level="ERROR",
                            status_message=str(exc),
                        )
                        raise

                    s_retrieve.update(
                        output={
                            "chunks_retrieved": len(retrieved_chunks),
                        }
                    )

                if not retrieved_chunks:
                    root.update(
                        output={"confidence": "none", "chunks": 0},
                        tags=["no-results"],
                    )
                    return _insufficient_response(
                        "No relevant documentation was found for this question.",
                        namespace,
                        start_ms,
                    )

                # ── Span 3: Rerank ───────────────────────────────────
                with _observation(
                    as_type="span",
                    name="rerank-cohere",
                ) as s_rerank:
                    ranked_chunks = rerank_chunks(
                        query=question,
                        chunks=retrieved_chunks,
                    )
                    confidence = compute_answer_confidence(ranked_chunks)
                    label = confidence_label(confidence)
                    s_rerank.update(
                        output={
                            "chunks_after_rerank": len(ranked_chunks),
                            "confidence": round(confidence, 3),
                            "label": label,
                        }
                    )

                # ── Guardrail 3: confidence threshold ────────────────
                if confidence < CONFIDENCE_THRESHOLD:
                    root.update(
                        output={
                            "confidence": round(confidence, 3),
                            "label": "low",
                            "threshold": CONFIDENCE_THRESHOLD,
                        },
                        tags=["low-confidence"],
                    )
                    return _insufficient_response(
                        "I don't have enough relevant information in the "
                        "indexed documentation to answer this confidently.",
                        namespace,
                        start_ms,
                    )

                # ── Span 4: Generate answer ──────────────────────────
                with _observation(
                    as_type="generation",
                    name="generate-answer",
                    model="claude-sonnet",
                ) as s_gen:
                    try:
                        answer = generate_answer(
                            question=question,
                            chunks=ranked_chunks,
                            confidence=confidence,
                        )
                        insufficient = False
                        warning = ""
                    except InsufficientContextError as exc:
                        answer = str(exc)
                        insufficient = True
                        warning = (
                            "Confidence is low. The retrieved documentation may not "
                            "directly answer this question."
                        )

                    # Token counts — extract from your generate_answer if available
                    # If generate_answer doesn't return tokens, estimate:
                    in_tok = (
                        getattr(s_gen, "_input_tokens", 0)
                        or len(question.split()) * 4
                        + sum(len(c.text.split()) for c in ranked_chunks) * 2
                    )
                    out_tok = len(answer.split()) * 2  # rough estimate

                    cost_usd = (
                        (in_tok / 1000) * COST_PER_1K["claude_in"]
                        + (out_tok / 1000) * COST_PER_1K["claude_out"]
                        + (embed_toks / 1000) * COST_PER_1K["voyage"]
                        + COST_PER_1K["cohere"] * 0.5
                    )

                    s_gen.update(
                        output=answer[:500],  # truncate for Langfuse display
                        usage={"input": in_tok, "output": out_tok},
                        metadata={"cost_usd": round(cost_usd, 5)},
                    )

                # ── Build response ───────────────────────────────────
                citations = [
                    Citation(
                        source_file=chunk.source_file,
                        heading_path=chunk.heading_path,
                        page=chunk.page,
                        citation=chunk.citation,
                        confidence=chunk.confidence_score,
                    )
                    for chunk in ranked_chunks
                ]

                duration_ms = int(time.perf_counter() * 1000) - start_ms

                response = QueryResponse(
                    answer=answer,
                    citations=citations,
                    confidence_score=confidence,
                    confidence_label=label,
                    chunks_used=len(ranked_chunks),
                    namespace=namespace,
                    response_ms=duration_ms,
                    insufficient_context=insufficient,
                    warning_message=warning,
                )

                # ── Complete Langfuse trace ──────────────────────────
                root.update(
                    output={
                        "confidence": round(confidence, 3),
                        "label": label,
                        "cost_usd": round(cost_usd, 5),
                        "duration_ms": duration_ms,
                        "citations": len(citations),
                    }
                )

                # ── Stage 5: Log (best-effort) ───────────────────────
                try:
                    await _log_query(question, namespace, response)
                except Exception as exc:
                    logger.warning("Query log failed (non-fatal)", extra={"error": str(exc)})

                return response

            except Exception as exc:
                root.update(level="ERROR", status_message=str(exc))
                raise
    finally:
        # Flush only after rag-query span closes — otherwise children export
        # without a parent and rag-query never appears in Langfuse.
        _flush_langfuse()


def _insufficient_response(
    message: str,
    namespace: str,
    start_ms: int,
) -> QueryResponse:
    """Return a structured insufficient-context response."""
    return QueryResponse(
        answer=message,
        citations=[],
        confidence_score=0.0,
        confidence_label="low",
        chunks_used=0,
        namespace=namespace,
        response_ms=int(time.perf_counter() * 1000) - start_ms,
        insufficient_context=True,
        warning_message=message,
    )


def _guardrail_response(
    message: str,
    namespace: str,
    start_ms: int,
    reason: str,
) -> QueryResponse:
    """Return a structured guardrail-blocked response."""
    return QueryResponse(
        answer=message,
        citations=[],
        confidence_score=0.0,
        confidence_label=reason,
        chunks_used=0,
        namespace=namespace,
        response_ms=int(time.perf_counter() * 1000) - start_ms,
        insufficient_context=True,
        warning_message=f"Query blocked: {reason}",
    )


async def _log_query(
    question: str,
    namespace: str,
    response: QueryResponse,
) -> None:
    """Write query to Postgres query_log for cost and quality analysis."""
    import asyncpg

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        await conn.execute(
            """
            INSERT INTO query_log
                (id, question, namespace, chunks_retrieved, confidence_score, response_ms)
            VALUES (gen_random_uuid()::text, $1, $2, $3, $4, $5)
            """,
            question[:1000],
            namespace,
            response.chunks_used,
            response.confidence_score,
            response.response_ms,
        )
    finally:
        await conn.close()
