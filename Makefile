# =================================================================
# DocuMind — Makefile
# Wraps common commands so PYTHONPATH is set correctly every time.
#
# Usage:
#   make test                                    run unit tests (no live APIs)
#   make test-ragas                              RAGAS regression (live APIs, ~2 min)
#   make test-watch                              re-run on file change
#   make ingest ARGS="docs/kubernetes/ --namespace kubernetes-docs"
#   make dry-run ARGS="docs/kubernetes/"
#   make lint                                    ruff check + format
#   make fmt                                     auto-fix formatting
#   make migrate                                 apply DB migrations
#   make verify                                  check all imports work
#   make clean                                   remove __pycache__
# =================================================================

# Python with both project root and backend/ on the path
PYTHON  = PYTHONPATH=.:backend python
PYTEST  = PYTHONPATH=.:backend pytest
RUFF    = ruff

.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "DocuMind — available commands"
	@echo "────────────────────────────────────────"
	@echo "  make test              Run unit tests (fast, no live APIs)"
	@echo "  make test-ragas        RAGAS regression (~2 min, live APIs)"
	@echo "  make test-v            Run tests (verbose)"
	@echo "  make lint              Ruff check + format check"
	@echo "  make fmt               Auto-fix formatting"
	@echo "  make ingest ARGS=...   Run ingestion pipeline"
	@echo "  make dry-run ARGS=...  Parse + chunk only (no API calls)"
	@echo "  make migrate           Apply DB migrations to Neon"
	@echo "  make verify            Verify all imports work"
	@echo "  make clean             Remove __pycache__ files"
	@echo ""
	@echo "Examples:"
	@echo "  make ingest ARGS=\"docs/kubernetes/ --namespace kubernetes-docs\""
	@echo "  make dry-run ARGS=\"docs/kubernetes/pods.md\""
	@echo ""

# ── Tests ─────────────────────────────────────────────────────────
.PHONY: test
test:
	$(PYTEST) tests/ -v --tb=short -m "not ragas"

.PHONY: test-ragas
test-ragas:
	$(PYTEST) tests/test_ragas_regression.py -v --tb=short -s

.PHONY: test-v
test-v:
	$(PYTEST) tests/ -v --tb=long -m "not ragas"

.PHONY: test-watch
test-watch:
	$(PYTEST) tests/ -v --tb=short -f -m "not ragas"

# ── Ingestion ─────────────────────────────────────────────────────
.PHONY: ingest
ingest:
	$(PYTHON) ingestion/ingest.py $(ARGS)

.PHONY: dry-run
dry-run:
	$(PYTHON) ingestion/ingest.py $(ARGS) --dry-run

# ── Code quality ──────────────────────────────────────────────────
.PHONY: lint
lint:
	$(RUFF) check .
	$(RUFF) format . --check

.PHONY: fmt
fmt:
	$(RUFF) check . --fix
	$(RUFF) format .

# ── Database ──────────────────────────────────────────────────────
.PHONY: migrate
migrate:
	@echo "Applying migrations to Neon..."
	psql $(DATABASE_URL) -f database/migrations/001_initial.sql
	@echo "Done."

# ── Verification ──────────────────────────────────────────────────
.PHONY: verify
verify:
	@echo "Verifying all package imports..."
	$(PYTHON) -c "import pinecone, voyageai, cohere, anthropic, ragas, pypdf, tiktoken, asyncpg; print('All packages OK')"
	@echo "Verifying app modules..."
	$(PYTHON) -c "from app.core.config import settings; from app.core.models import DocumentChunk; print('App modules OK')"
	@echo "Verifying ingestion modules..."
	$(PYTHON) -c "from ingestion.parsers import parse_document; from ingestion.chunkers.header_aware import chunk_document; print('Ingestion modules OK')"

# ── Clean ─────────────────────────────────────────────────────────
.PHONY: clean
clean:
	find . -type d -name __pycache__ -not -path "./venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -not -path "./venv/*" -delete 2>/dev/null || true
	@echo "Cleaned."

.PHONY: eval
eval:
	$(PYTHON) evaluation/run_eval.py $(ARGS)

.PHONY: eval-quick
eval-quick:
	$(PYTHON) evaluation/run_eval.py --limit 3
