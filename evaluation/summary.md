## Evaluation results

RAGAS evaluation against 10 hand-curated Q&A pairs
from the indexed corpus (pods.md + configmaps.md).
Evaluated: 2026-06-02

| Metric | Score | Threshold | Notes |
|--------|-------|-----------|-------|
| Faithfulness | 0.406 | ≥ 0.85 | Answer grounded in source context |
| Answer relevancy | 0.000 | ≥ 0.80 | Answer addresses the question |
| Context precision | 0.602 | ≥ 0.75 | Retrieved chunks are relevant |
| Context recall | 0.556 | ≥ 0.80 | Context contains the answer |

**Corpus:** Kubernetes official documentation (pods.md, configmaps.md)
**Evaluation model:** Claude claude-sonnet-4-5
**Retrieval:** Pinecone hybrid search (alpha=0.7) + Cohere Rerank v3
