-- =================================================================
-- DocuMind Migration 002 — Users + Auth
-- Run: psql $DATABASE_URL -f database/migrations/002_users.sql
--
-- Lifetime query limit design:
--   total_queries counts every query ever made by this user.
--   When total_queries >= query_limit, the atomic UPDATE returns
--   no row and access is denied. No reset mechanism — same model
--   as InsightIQ. Simple, auditable, impossible to race.
-- =================================================================

CREATE TABLE IF NOT EXISTS users (
    id            VARCHAR(36)  PRIMARY KEY,       -- UUID
    google_id     VARCHAR(255) NOT NULL UNIQUE,    -- Google sub claim
    email         VARCHAR(255) NOT NULL UNIQUE,
    name          VARCHAR(255),
    avatar_url    VARCHAR(500),
    total_queries INTEGER      NOT NULL DEFAULT 0,
    query_limit   INTEGER      NOT NULL DEFAULT 3, -- 3 lifetime queries
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
CREATE INDEX IF NOT EXISTS idx_users_email     ON users(email);

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;
