"""
Sourciq — RAGAS Evaluation Pipeline
=======================================
Evaluates the full RAG pipeline against the ground truth dataset.

Metrics:
    faithfulness        — Does the answer hallucinate beyond the context?
                          Score: 0.0 (full hallucination) → 1.0 (fully grounded)

    answer_relevancy    — Does the answer address the question asked?
                          Score: 0.0 (irrelevant) → 1.0 (directly relevant)

    context_precision   — Of the retrieved chunks, how many are actually relevant?
                          Score: 0.0 (all noise) → 1.0 (all relevant)

    context_recall      — Does the retrieved context contain the ground truth answer?
                          Score: 0.0 (answer not found) → 1.0 (fully contained)

Usage:
    export PYTHONPATH=.:backend
    python evaluation/run_eval.py

    # Save results to JSON:
    python evaluation/run_eval.py --output evaluation/results.json

    # Run on subset (faster, for iteration):
    python evaluation/run_eval.py --limit 3

Output:
    - Prints a results table to stdout
    - Writes evaluation/results.json with per-question breakdown
    - Writes evaluation/summary.md for inclusion in README
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from evaluation.ground_truth import GROUND_TRUTH  # noqa: E402

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── RAGAS setup ───────────────────────────────────────────────────


def get_ragas_metrics():
    """Import RAGAS metrics. Raises clear error if not installed."""
    try:
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        return [faithfulness, answer_relevancy, context_precision, context_recall]
    except ImportError as e:
        print(f"\nMissing dependency: {e}")
        print("Install RAGAS evaluation deps:")
        print("  pip install ragas langchain-anthropic langchain-openai")
        sys.exit(1)


# ── Query pipeline ────────────────────────────────────────────────


async def run_query(question: str, namespace: str = "kubernetes-docs") -> dict:
    """
    Run a question through the Sourciq pipeline.
    Returns answer + retrieved context chunks.
    """
    from app.core.config import settings
    from app.core.exceptions import InsufficientContextError
    from app.rag.generation.generator import generate_answer
    from app.rag.ingestion.embedder import embed_query
    from app.rag.retrieval.reranker import compute_answer_confidence, rerank_chunks
    from app.rag.retrieval.searcher import encode_sparse, hybrid_search

    try:
        embedding = embed_query(question)
        query_sparse = encode_sparse(question)
        retrieved = hybrid_search(
            query_embedding=embedding,
            query_sparse=query_sparse,
            namespace=namespace,
            alpha=settings.HYBRID_ALPHA,
        )
        if not retrieved:
            return {"answer": "No relevant context found.", "contexts": []}

        ranked = rerank_chunks(question, retrieved)
        confidence = compute_answer_confidence(ranked)
        contexts = [chunk.text for chunk in ranked]

        try:
            answer = generate_answer(question, ranked, confidence)
        except InsufficientContextError as e:
            answer = str(e)

        return {"answer": answer, "contexts": contexts}

    except Exception as exc:
        logger.error("Query failed: %s", exc)
        return {"answer": f"Error: {exc}", "contexts": []}


# ── Evaluation ────────────────────────────────────────────────────


async def build_dataset(limit: int | None = None, namespace: str = "kubernetes-docs") -> dict:
    """
    Run every ground truth question through the pipeline
    and collect (question, answer, contexts, ground_truth) tuples.
    """
    samples = GROUND_TRUTH if limit is None else GROUND_TRUTH[:limit]
    print(f"\nRunning {len(samples)} questions through the pipeline...")

    questions: list[str] = []
    answers: list[str] = []
    contexts: list[list[str]] = []
    ground_truth: list[str] = []

    for i, sample in enumerate(samples, start=1):
        print(f"  [{i}/{len(samples)}] {sample['question'][:60]}...")
        result = await run_query(sample["question"], namespace=namespace)
        print(f"       → {len(result['contexts'])} contexts, " f"answer: {result['answer'][:80]!r}")

        questions.append(sample["question"])
        answers.append(result["answer"])
        contexts.append(result["contexts"] or ["No context retrieved."])
        ground_truth.append(sample["answer"])

        # Be gentle with API rate limits
        if i < len(samples):
            time.sleep(1.0)

    return {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truth,
    }


def run_ragas(dataset: dict) -> dict:
    try:
        import ragas.embeddings.base as ragas_emb
        import ragas.llms.base as ragas_base
        from datasets import Dataset
        from langchain_anthropic import ChatAnthropic
        from langchain_community.embeddings import VoyageEmbeddings
        from ragas import evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        claude_llm = LangchainLLMWrapper(
            ChatAnthropic(
                model="claude-sonnet-4-5",
                anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            )
        )
        voyage_emb = LangchainEmbeddingsWrapper(
            VoyageEmbeddings(
                voyage_api_key=os.environ["VOYAGE_API_KEY"],
                model="voyage-2",
            )
        )

        # Patch both factories
        ragas_base.llm_factory = lambda: claude_llm
        ragas_emb.embedding_factory = lambda: voyage_emb

        for metric in [faithfulness, answer_relevancy, context_precision, context_recall]:
            metric.llm = claude_llm
            metric.embeddings = voyage_emb

    except ImportError as e:
        print(f"Missing: {e}\npip install ragas datasets langchain-anthropic langchain-community")
        sys.exit(1)

    hf_dataset = Dataset.from_dict(dataset)
    print("\nRunning RAGAS evaluation with Claude + Voyage AI...")

    result = evaluate(
        hf_dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )
    return result


# ── Programmatic entry point (used by CI regression tests) ──────


def _evaluate(
    limit: int | None = None, namespace: str = "kubernetes-docs"
) -> tuple[dict[str, float], dict]:
    dataset = asyncio.run(build_dataset(limit=limit, namespace=namespace))
    result = run_ragas(dataset)
    scores = {k: v for k, v in dict(result).items() if isinstance(v, float)}
    return scores, dataset


def run_evaluation(
    limit: int | None = None, namespace: str = "kubernetes-docs"
) -> dict[str, float]:
    """Run the full RAGAS pipeline and return aggregate metric scores."""
    scores, _ = _evaluate(limit=limit, namespace=namespace)
    return scores


# ── Output formatting ─────────────────────────────────────────────


def print_results_table(scores: dict, per_question: list[dict]) -> None:
    """Print a clean results table to stdout."""
    print("\n" + "=" * 60)
    print("  Sourciq — RAGAS Evaluation Results")
    print("=" * 60)
    print(f"  {'Metric':<25} {'Score':>8}  {'Rating'}")
    print("  " + "-" * 54)

    thresholds = {
        "faithfulness": (0.85, 0.70),
        "answer_relevancy": (0.80, 0.65),
        "context_precision": (0.75, 0.60),
        "context_recall": (0.80, 0.65),
    }

    for metric, (high, med) in thresholds.items():
        score = scores.get(metric, 0.0)
        if isinstance(score, float):
            rating = "✓ High" if score >= high else "~ Medium" if score >= med else "✗ Low"
            print(f"  {metric:<25} {score:>7.3f}  {rating}")

    print("=" * 60)
    print(f"  Questions evaluated: {len(per_question)}")
    print(f"  Corpus: pods.md + configmaps.md ({len(per_question)} Q&A pairs)")
    print("=" * 60)


def write_summary_md(scores: dict, output_path: Path) -> None:
    """
    Write evaluation/summary.md — included verbatim in the README.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def fmt(v):
        return f"{v:.3f}" if isinstance(v, float) else "n/a"

    content = f"""## Evaluation results

RAGAS evaluation against {len(GROUND_TRUTH)} hand-curated Q&A pairs
from the indexed corpus (pods.md + configmaps.md).
Evaluated: {now}

| Metric | Score | Threshold | Notes |
|--------|-------|-----------|-------|
| Faithfulness | {fmt(scores.get('faithfulness', 0))} | ≥ 0.85 | Answer grounded in source context |
| Answer relevancy | {fmt(scores.get('answer_relevancy', 0))} | ≥ 0.80 | Answer addresses the question |
| Context precision | {fmt(scores.get('context_precision', 0))} | ≥ 0.75 | Retrieved chunks are relevant |
| Context recall | {fmt(scores.get('context_recall', 0))} | ≥ 0.80 | Context contains the answer |

**Corpus:** Kubernetes official documentation (pods.md, configmaps.md)
**Evaluation model:** Claude claude-sonnet-4-5
**Retrieval:** Pinecone hybrid search (alpha=0.7) + Cohere Rerank v3
"""
    output_path.write_text(content)
    print(f"\nSummary written to {output_path}")


def write_results_json(
    scores: dict,
    per_question: list[dict],
    output_path: Path,
) -> None:
    """Write full results JSON for archival."""
    data = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "corpus": ["pods.md", "configmaps.md"],
        "num_questions": len(per_question),
        "scores": {k: round(v, 4) for k, v in scores.items() if isinstance(v, float)},
        "per_question": per_question,
    }
    output_path.write_text(json.dumps(data, indent=2))
    print(f"Results written to {output_path}")


# ── CLI ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sourciq RAGAS evaluation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python evaluation/run_eval.py
  python evaluation/run_eval.py --limit 3
  python evaluation/run_eval.py --output evaluation/results.json
        """,
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit questions (faster for testing)"
    )
    parser.add_argument(
        "--output", type=str, default="evaluation/results.json", help="Output JSON path"
    )
    parser.add_argument("--namespace", default="kubernetes-docs")
    args = parser.parse_args()

    print("\nSourciq RAGAS Evaluation")
    print(
        f"  Questions: {len(GROUND_TRUTH)}" + (f" (limited to {args.limit})" if args.limit else "")
    )
    print(f"  Namespace: {args.namespace}")

    # Build dataset by running each question through the pipeline
    scores, dataset = _evaluate(limit=args.limit, namespace=args.namespace)

    # Extract per-question scores if available
    per_question = []
    for i, q in enumerate(dataset["question"]):
        per_question.append(
            {
                "question": q,
                "answer": dataset["answer"][i],
                "ground_truth": dataset["ground_truth"][i],
            }
        )

    # Print results
    print_results_table(scores, per_question)

    # Write outputs
    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)
    write_results_json(scores, per_question, output_path)
    write_summary_md(scores, Path("evaluation/summary.md"))


if __name__ == "__main__":
    main()
