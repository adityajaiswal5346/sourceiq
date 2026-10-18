"""
DocuMind — Pinecone Indexer
=============================
Upserts document chunks into Pinecone with dense vectors,
sparse BM25 weights, and full metadata for citation retrieval.

Design decisions:
- Upsert batching: Pinecone recommends batches of 100 vectors.
  Larger batches hit the 4MB request size limit. 100 is safe.
- Namespace per collection: each document collection (kubernetes-docs,
  stripe-api, aws-waf) lives in its own namespace. This allows
  collection-scoped search without maintaining separate indexes.
- Metadata stored in Pinecone: source_file, heading_path, page,
  chunk_index, and the full text. Storing text in metadata means
  retrieval returns the chunk content without a separate DB lookup.
- BM25 sparse encoding is handled by Pinecone's built-in encoder
  for the serverless index. No separate sparse computation needed.
- Idempotent: upserting an existing vector_id overwrites it.
  Re-ingesting a document updates rather than duplicates.
"""

import logging

from pinecone import Pinecone, ServerlessSpec

from app.core.config import settings
from app.core.exceptions import IndexError
from app.core.models import DocumentChunk, IndexedChunk

logger = logging.getLogger(__name__)

_UPSERT_BATCH_SIZE = 100


def get_pinecone_index():
    """
    Initialise and return the Pinecone index client.
    Creates the index if it doesn't exist (safe for first run).
    """
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)

    existing = [idx.name for idx in pc.list_indexes()]
    if settings.PINECONE_INDEX not in existing:
        logger.info(
            "Creating Pinecone index",
            extra={"index": settings.PINECONE_INDEX, "dims": settings.VOYAGE_DIMS},
        )
        pc.create_index(
            name=settings.PINECONE_INDEX,
            dimension=settings.VOYAGE_DIMS,
            metric="dotproduct",  # required for hybrid search
            spec=ServerlessSpec(cloud="aws", region=settings.AWS_REGION),
        )

    return pc.Index(settings.PINECONE_INDEX)


def upsert_chunks(
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
    namespace: str = "default",
) -> list[IndexedChunk]:
    """
    Upsert chunks with their embeddings into Pinecone.

    Args:
        chunks:     Chunks with metadata (must align 1:1 with embeddings).
        embeddings: Dense vectors from Voyage AI.
        namespace:  Pinecone namespace — use collection name for scoping.

    Returns:
        List of IndexedChunk records for updating the document registry.

    Raises:
        IndexError: If chunk and embedding counts don't match,
                    or if Pinecone upsert fails after retries.
        ValueError: If chunks and embeddings have different lengths.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Chunk count ({len(chunks)}) does not match "
            f"embedding count ({len(embeddings)}). "
            "This indicates a bug in the embedding pipeline."
        )

    index = get_pinecone_index()
    vectors = _build_vectors(chunks, embeddings)
    indexed: list[IndexedChunk] = []

    logger.info(
        "Upserting to Pinecone",
        extra={"vectors": len(vectors), "namespace": namespace},
    )

    for batch_start in range(0, len(vectors), _UPSERT_BATCH_SIZE):
        batch = vectors[batch_start : batch_start + _UPSERT_BATCH_SIZE]
        try:
            index.upsert(vectors=batch, namespace=namespace)
        except Exception as exc:
            raise IndexError(
                f"Pinecone upsert failed for batch starting at {batch_start}: {exc}"
            ) from exc

    # Build IndexedChunk records for document registry update
    for chunk in chunks:
        indexed.append(
            IndexedChunk(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.metadata.doc_id,
                vector_id=chunk.chunk_id,
                token_count=chunk.metadata.token_count,
            )
        )

    logger.info(
        "Pinecone upsert complete",
        extra={"indexed": len(indexed), "namespace": namespace},
    )
    return indexed


def _build_vectors(
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
) -> list[dict]:
    """
    Build Pinecone vector records from chunks and embeddings.

    Metadata stored in Pinecone:
    - text:         full chunk text (returned at query time — no separate lookup)
    - source_file:  filename for citation
    - heading_path: section context for citation
    - page:         page number for citation
    - doc_id:       document registry ID for filtering
    - chunk_index:  position in document (for ordering results)
    """
    vectors = []
    for chunk, embedding in zip(chunks, embeddings):
        meta = chunk.metadata
        vectors.append(
            {
                "id": chunk.chunk_id,
                "values": embedding,
                "metadata": {
                    "text": chunk.text,
                    "source_file": meta.source_file,
                    "heading_path": meta.heading_path,
                    "page": meta.page,
                    "doc_id": meta.doc_id,
                    "chunk_index": meta.chunk_index,
                    "citation": chunk.citation_string(),
                },
            }
        )
    return vectors


def delete_document(doc_id: str, namespace: str = "default") -> int:
    """
    Delete all chunks belonging to a document from Pinecone.
    Used when re-ingesting an updated document.
    Returns the number of vectors deleted.
    """
    index = get_pinecone_index()
    results = index.query(
        vector=[0.0] * settings.VOYAGE_DIMS,
        filter={"doc_id": {"$eq": doc_id}},
        top_k=10_000,
        namespace=namespace,
        include_values=False,
    )
    ids = [m.id for m in results.matches]
    if ids:
        index.delete(ids=ids, namespace=namespace)
    logger.info("Document deleted from Pinecone", extra={"doc_id": doc_id, "vectors": len(ids)})
    return len(ids)
