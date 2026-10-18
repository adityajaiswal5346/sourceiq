"""
DocuMind — Voyage AI Embedder
===============================
Generates dense embeddings for document chunks using Voyage AI voyage-2.

Design decisions:
- Batching: Voyage AI supports up to 128 texts per request. Sending
  chunks individually would hit rate limits and be 100x slower.
  Batches of 64 balance throughput against request size.
- Retry: transient API errors (429, 5xx) are retried with exponential
  backoff. Persistent failures raise EmbeddingError after max_retries.
- Dimension validation: if the returned vectors don't match the
  configured VOYAGE_DIMS, every Pinecone upsert would fail silently
  with a dimension mismatch. We catch it here with a clear error.
- Input type: "document" tells Voyage to optimise for storage-side
  representation. Query-time embeddings use "query" — asymmetric
  retrieval produces better results than symmetric for this use case.
"""

import logging
import time

import voyageai

from app.core.config import settings
from app.core.exceptions import EmbeddingDimensionError, EmbeddingError
from app.core.models import DocumentChunk

logger = logging.getLogger(__name__)

_BATCH_SIZE = 64  # Voyage AI max is 128; 64 is safe and fast
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # seconds, doubled on each retry


def embed_chunks(chunks: list[DocumentChunk]) -> list[list[float]]:
    """
    Generate dense embeddings for a list of document chunks.

    Processes chunks in batches of _BATCH_SIZE. Each batch is sent
    to Voyage AI with input_type="document" for storage-side optimisation.

    Args:
        chunks: Document chunks to embed. Order is preserved in output.

    Returns:
        List of embedding vectors, one per chunk, same order as input.

    Raises:
        EmbeddingError:          API call failed after max retries.
        EmbeddingDimensionError: Returned dimensions don't match config.
    """
    if not chunks:
        return []

    client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
    all_embeddings: list[list[float]] = []
    total = len(chunks)

    logger.info(
        "Generating embeddings",
        extra={"chunks": total, "model": settings.VOYAGE_MODEL, "batch_size": _BATCH_SIZE},
    )

    for batch_start in range(0, total, _BATCH_SIZE):
        batch = chunks[batch_start : batch_start + _BATCH_SIZE]
        texts = [chunk.text for chunk in batch]

        embeddings = _embed_with_retry(client, texts)
        all_embeddings.extend(embeddings)

        logger.debug(
            "Batch embedded",
            extra={"batch": f"{batch_start // _BATCH_SIZE + 1}", "size": len(batch)},
        )

    # Validate dimensions on the first embedding
    if all_embeddings:
        actual_dims = len(all_embeddings[0])
        if actual_dims != settings.VOYAGE_DIMS:
            raise EmbeddingDimensionError(
                f"Voyage AI returned {actual_dims}-dim vectors but "
                f"config expects {settings.VOYAGE_DIMS}. "
                f"Check VOYAGE_MODEL and VOYAGE_DIMS in .env — "
                f"voyage-2 produces 1024 dimensions."
            )

    logger.info("Embeddings generated", extra={"total": len(all_embeddings)})
    return all_embeddings


def embed_query(text: str) -> list[float]:
    """
    Generate a query-side embedding for retrieval.

    Uses input_type="query" for asymmetric retrieval — Voyage AI
    optimises the representation differently for queries vs documents,
    producing better retrieval results than symmetric embeddings.

    Args:
        text: The user's natural language question.

    Returns:
        Single embedding vector (1024-dim for voyage-2).
    """
    client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
    result = _embed_with_retry(client, [text], input_type="query")
    return result[0]


def _embed_with_retry(
    client: voyageai.Client,
    texts: list[str],
    input_type: str = "document",
    attempt: int = 0,
) -> list[list[float]]:
    """
    Call Voyage AI with exponential backoff retry.
    Raises EmbeddingError after _MAX_RETRIES failed attempts.
    """
    try:
        result = client.embed(
            texts,
            model=settings.VOYAGE_MODEL,
            input_type=input_type,
        )
        return result.embeddings

    except voyageai.error.RateLimitError as exc:
        if attempt >= _MAX_RETRIES:
            raise EmbeddingError(
                f"Voyage AI rate limit exceeded after {_MAX_RETRIES} retries."
            ) from exc
        wait = _RETRY_DELAY * (2**attempt)
        logger.warning(f"Rate limited — retrying in {wait}s", extra={"attempt": attempt + 1})
        time.sleep(wait)
        return _embed_with_retry(client, texts, input_type, attempt + 1)

    except Exception as exc:
        if attempt >= _MAX_RETRIES:
            raise EmbeddingError(
                f"Voyage AI embedding failed after {_MAX_RETRIES} retries: {exc}"
            ) from exc
        wait = _RETRY_DELAY * (2**attempt)
        logger.warning(f"Embedding error — retrying in {wait}s", extra={"error": str(exc)})
        time.sleep(wait)
        return _embed_with_retry(client, texts, input_type, attempt + 1)
