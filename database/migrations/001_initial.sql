-- =================================================================
-- DocuMind Migration 001 — Document Registry
-- Run: psql $DATABASE_URL -f database/migrations/001_initial.sql
-- =================================================================

-- ── Documents table ───────────────────────────────────────────────
-- One row per source document.
-- Tracks ingestion status through the pipeline stages.

CREATE TABLE IF NOT EXISTS documents (
    id          VARCHAR(36)  PRIMARY KEY,         -- UUID
    filename    VARCHAR(500) NOT NULL,
    source_path VARCHAR(1000) NOT NULL,
    format      VARCHAR(20)  NOT NULL,            -- pdf | markdown | html | text
    namespace   VARCHAR(100) NOT NULL DEFAULT 'default',
    status      VARCHAR(20)  NOT NULL DEFAULT 'pending',
    chunk_count INTEGER,
    error_msg   TEXT,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_documents_namespace  ON documents(namespace);
CREATE INDEX IF NOT EXISTS idx_documents_status     ON documents(status);

-- ── Ingestion jobs table ──────────────────────────────────────────
-- Audit log of every ingestion run.
-- Multiple runs of the same document are tracked separately.

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id             VARCHAR(36)  PRIMARY KEY,
    doc_id         VARCHAR(36)  NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status         VARCHAR(20)  NOT NULL,
    chunks_created INTEGER,
    duration_ms    INTEGER,
    error_msg      TEXT,
    started_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_jobs_doc_id ON ingestion_jobs(doc_id);

-- ── Query log table ───────────────────────────────────────────────
-- Every query logged for cost monitoring and quality analysis.

CREATE TABLE IF NOT EXISTS query_log (
    id               VARCHAR(36)  PRIMARY KEY,
    question         TEXT         NOT NULL,
    namespace        VARCHAR(100) NOT NULL DEFAULT 'default',
    chunks_retrieved INTEGER,
    confidence_score NUMERIC(4, 3),
    response_ms      INTEGER,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Verify
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('documents', 'ingestion_jobs', 'query_log')
ORDER BY table_name, ordinal_position;
