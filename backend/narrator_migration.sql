-- ============================================================
-- MIGRATION: Insight Narrator tables
-- Run once against your Supabase / PostgreSQL database
-- ============================================================

-- -------------------------------------------------------
-- insight_cache: stores the latest generated insight cards
-- per client. FastAPI reads from here — zero LLM latency
-- on request path.
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS insight_cache (
    cache_key       TEXT PRIMARY KEY,         -- 'narrator:{client_id}'
    insights        JSONB NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL,
    data_as_of      DATE NOT NULL             -- most recent month covered
);

-- -------------------------------------------------------
-- pg_insight_history: key-based deduplication store.
-- Suppresses repeating the same (entity, metric, period)
-- insight within the configured window (default 7 days).
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS pg_insight_history (
    id              SERIAL PRIMARY KEY,
    client_id       INT NOT NULL REFERENCES dim_client(client_id),
    entity_type     VARCHAR(50)  NOT NULL,    -- channel | user | language | input_type
    entity_id       VARCHAR(100) NOT NULL,    -- channel_code or user_name etc.
    insight_type    VARCHAR(50)  NOT NULL,    -- anomaly | trend | comparison | milestone
    metric_name     VARCHAR(100) NOT NULL,
    period          VARCHAR(10)  NOT NULL,    -- YYYY-MM
    first_seen_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    seen_count      INT          NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_insight_history
    ON pg_insight_history (client_id, entity_type, entity_id, insight_type, metric_name, period);

CREATE INDEX IF NOT EXISTS idx_insight_history_client_seen
    ON pg_insight_history (client_id, last_seen_at DESC);

-- -------------------------------------------------------
-- Extend insight_log with richer narrator output fields
-- (safe to run even if columns already exist — use DO block)
-- -------------------------------------------------------
DO $$
BEGIN
    -- category: anomaly | trend | comparison | milestone
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'insight_log' AND column_name = 'category'
    ) THEN
        ALTER TABLE insight_log ADD COLUMN category VARCHAR(50);
    END IF;

    -- entity_type / entity_id for flexible querying
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'insight_log' AND column_name = 'entity_type'
    ) THEN
        ALTER TABLE insight_log ADD COLUMN entity_type VARCHAR(50);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'insight_log' AND column_name = 'entity_id'
    ) THEN
        ALTER TABLE insight_log ADD COLUMN entity_id VARCHAR(100);
    END IF;

    -- period: YYYY-MM string
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'insight_log' AND column_name = 'period'
    ) THEN
        ALTER TABLE insight_log ADD COLUMN period VARCHAR(10);
    END IF;

    -- current_value / reference_value (numeric)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'insight_log' AND column_name = 'current_value'
    ) THEN
        ALTER TABLE insight_log ADD COLUMN current_value NUMERIC;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'insight_log' AND column_name = 'reference_value'
    ) THEN
        ALTER TABLE insight_log ADD COLUMN reference_value NUMERIC;
    END IF;

    -- confidence: statistical | contextual
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'insight_log' AND column_name = 'confidence'
    ) THEN
        ALTER TABLE insight_log ADD COLUMN confidence VARCHAR(20);
    END IF;

    -- root_cause_hint (Phase 2 root cause analysis)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'insight_log' AND column_name = 'root_cause_hint'
    ) THEN
        ALTER TABLE insight_log ADD COLUMN root_cause_hint TEXT;
    END IF;

    -- user feedback: 1 (thumbs up), -1 (thumbs down), null (no feedback)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'insight_log' AND column_name = 'user_feedback'
    ) THEN
        ALTER TABLE insight_log ADD COLUMN user_feedback SMALLINT;
    END IF;
END
$$;
