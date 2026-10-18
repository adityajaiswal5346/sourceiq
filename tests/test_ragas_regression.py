"""
RAGAS regression test — blocks CI if any metric drops below threshold.

CI uses RAGAS_EVAL_LIMIT=3 (~€0.35/run). Local `make test-ragas` runs all 10 (~€1+).

Thresholds set below baseline scores to allow natural variance:
    faithfulness     >= 0.85   (baseline 0.891)
    answer_relevancy >= 0.80   (baseline 0.847)
    context_precision>= 0.75   (baseline 0.823)
    context_recall   >= 0.80   (baseline 0.812)
"""

import math
import os

import pytest

_REQUIRED_KEYS = (
    "ANTHROPIC_API_KEY",
    "PINECONE_API_KEY",
    "VOYAGE_API_KEY",
    "COHERE_API_KEY",
)
_PLACEHOLDER_MARKERS = (
    "placeholder",
    "your-key",
    "your-voyage",
    "your-pinecone",
    "your-cohere",
    "ci-placeholder",
    "sk-ant-your",
    "pk-lf-your",
)


def _ragas_keys_configured() -> bool:
    for name in _REQUIRED_KEYS:
        value = os.getenv(name, "").strip()
        if not value:
            return False
        lower = value.lower()
        if any(marker in lower for marker in _PLACEHOLDER_MARKERS):
            return False
    return True


pytestmark = [
    pytest.mark.ragas,
    pytest.mark.skipif(
        not _ragas_keys_configured(),
        reason="RAGAS tests need real API keys in .env — run: make test-ragas",
    ),
]

THRESHOLDS = {
    "faithfulness": 0.85,
    "answer_relevancy": 0.80,
    "context_precision": 0.75,
    "context_recall": 0.80,
}


@pytest.fixture(scope="session")
def ragas_results():
    from app.core.config import settings
    from app.rag.ingestion.embedder import embed_query
    from app.rag.retrieval.searcher import encode_sparse, hybrid_search

    from evaluation.run_eval import run_evaluation

    # Fail fast in CI if keys are invalid (avoids ~10 min of retries + nan scores)
    try:
        embed_query("kubernetes pod health check")
    except Exception as exc:
        pytest.fail(f"API preflight failed — check GitHub secrets (VOYAGE_API_KEY): {exc}")

    probe = "What is a Kubernetes Pod?"
    chunks = hybrid_search(
        embed_query(probe),
        encode_sparse(probe),
        namespace="kubernetes-docs",
        alpha=settings.HYBRID_ALPHA,
    )
    if not chunks:
        pytest.fail(
            f"Pinecone returned 0 chunks for {probe!r}. "
            f"Index={settings.PINECONE_INDEX!r} namespace='kubernetes-docs' — "
            "run ingestion or check PINECONE_API_KEY / PINECONE_INDEX secrets."
        )
    print(
        f"Retrieval preflight OK: index={settings.PINECONE_INDEX}, "
        f"chunks={len(chunks)}, top_score={chunks[0].score:.3f}"
    )

    _raw_limit = os.getenv("RAGAS_EVAL_LIMIT", "").strip()
    limit = int(_raw_limit) if _raw_limit else None
    if limit:
        print(f"RAGAS eval limit: {limit} questions (set RAGAS_EVAL_LIMIT)")

    results = run_evaluation(limit=limit)
    bad = [m for m, s in results.items() if isinstance(s, float) and math.isnan(s)]
    if bad:
        pytest.fail(
            f"RAGAS returned nan for {', '.join(bad)}. "
            "API keys are missing or invalid — check VOYAGE_API_KEY and "
            "ANTHROPIC_API_KEY in .env (logs often show 401 / invalid key)."
        )
    return results


def test_faithfulness(ragas_results):
    s = ragas_results["faithfulness"]
    assert s >= THRESHOLDS["faithfulness"], (
        f"Faithfulness {s:.3f} below {THRESHOLDS['faithfulness']} "
        f"— a change degraded citation enforcement."
    )


def test_answer_relevancy(ragas_results):
    s = ragas_results["answer_relevancy"]
    assert (
        s >= THRESHOLDS["answer_relevancy"]
    ), f"Answer relevancy {s:.3f} below {THRESHOLDS['answer_relevancy']}."


def test_context_precision(ragas_results):
    s = ragas_results["context_precision"]
    assert s >= THRESHOLDS["context_precision"], (
        f"Context precision {s:.3f} below {THRESHOLDS['context_precision']} "
        f"— retrieval returning irrelevant chunks."
    )


def test_context_recall(ragas_results):
    s = ragas_results["context_recall"]
    assert s >= THRESHOLDS["context_recall"], (
        f"Context recall {s:.3f} below {THRESHOLDS['context_recall']} "
        f"— retrieved context missing ground truth."
    )
