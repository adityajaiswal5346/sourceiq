"""
Sourciq — RAGAS Dataset Tests
================================
Validates ground truth dataset structure without API calls.
Ensures every entry has the required fields and non-empty content.

Run: make test
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


class TestGroundTruthDataset:
    """Validate the RAGAS ground truth dataset structure."""

    def _load(self):
        from evaluation.ground_truth import GROUND_TRUTH

        return GROUND_TRUTH

    def test_has_minimum_entries(self):
        gt = self._load()
        assert len(gt) >= 5, f"Expected at least 5 entries, got {len(gt)}"

    def test_every_entry_has_required_fields(self):
        gt = self._load()
        required = {"question", "answer", "contexts", "source"}
        for i, entry in enumerate(gt):
            missing = required - set(entry.keys())
            assert not missing, f"Entry {i} missing fields: {missing}"

    def test_no_empty_questions(self):
        gt = self._load()
        for i, entry in enumerate(gt):
            assert entry["question"].strip(), f"Entry {i} has empty question"
            assert len(entry["question"]) >= 10, f"Entry {i} question too short"

    def test_no_empty_answers(self):
        gt = self._load()
        for i, entry in enumerate(gt):
            assert entry["answer"].strip(), f"Entry {i} has empty answer"
            assert len(entry["answer"]) >= 20, f"Entry {i} answer too short"

    def test_every_entry_has_at_least_one_context(self):
        gt = self._load()
        for i, entry in enumerate(gt):
            assert entry["contexts"], f"Entry {i} has no contexts"
            assert all(c.strip() for c in entry["contexts"]), f"Entry {i} has empty context string"

    def test_source_is_valid_file(self):
        gt = self._load()
        valid_sources = {"pods.md", "configmaps.md"}
        for i, entry in enumerate(gt):
            assert (
                entry["source"] in valid_sources
            ), f"Entry {i} has invalid source: {entry['source']}"

    def test_sources_cover_both_indexed_files(self):
        gt = self._load()
        sources = {entry["source"] for entry in gt}
        assert "pods.md" in sources, "No entries from pods.md"
        assert "configmaps.md" in sources, "No entries from configmaps.md"

    def test_questions_are_unique(self):
        gt = self._load()
        questions = [entry["question"] for entry in gt]
        assert len(questions) == len(set(questions)), "Duplicate questions found"

    def test_answers_mention_kubernetes_concepts(self):
        """Sanity check — answers should be about Kubernetes."""
        gt = self._load()
        k8s_terms = {"pod", "container", "kubernetes", "configmap", "cluster"}
        for i, entry in enumerate(gt):
            answer_lower = entry["answer"].lower()
            has_k8s_term = any(term in answer_lower for term in k8s_terms)
            assert (
                has_k8s_term
            ), f"Entry {i} answer doesn't mention any Kubernetes term: {entry['question']}"

    def test_pods_entries_count(self):
        gt = self._load()
        pods_entries = [e for e in gt if e["source"] == "pods.md"]
        assert (
            len(pods_entries) >= 4
        ), f"Expected at least 4 pods.md entries, got {len(pods_entries)}"

    def test_configmaps_entries_count(self):
        gt = self._load()
        cm_entries = [e for e in gt if e["source"] == "configmaps.md"]
        assert (
            len(cm_entries) >= 3
        ), f"Expected at least 3 configmaps.md entries, got {len(cm_entries)}"
