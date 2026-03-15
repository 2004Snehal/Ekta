-- ============================================================
-- FRAMMER AI — CLEAN MINIMAL SCHEMA
-- Run this against your Supabase / PostgreSQL database.
--
-- TWO SCHEMAS:
--   internal  — backend/system tables (never shown to client)
--   data      — client data tables (shown in Data Manager UI)
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()

-- ============================================================
-- SCHEMA SETUP
-- ============================================================

CREATE SCHEMA IF NOT EXISTS internal;
CREATE SCHEMA IF NOT EXISTS data;

-- ============================================================
-- INTERNAL SCHEMA — system/backend tables only
-- (NLQ sessions, dashboard state, KPI cache)
-- ============================================================

-- ── Dashboard State ─────────────────────────────────────────
-- Saves and restores the user's filter/view configuration.
-- Each save is a row. Shareable links use the UUID.
CREATE TABLE IF NOT EXISTS internal.dashboard_state (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          TEXT,
    version          INTEGER NOT NULL DEFAULT 1,
    filters_json     JSONB   NOT NULL DEFAULT '{}',
    filters_expanded BOOLEAN NOT NULL DEFAULT TRUE,
    loaded_range     TEXT,           -- last-7-days | last-30-days | last-90-days | all-time
    selected_kpi_id  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ds_user_updated
    ON internal.dashboard_state (user_id, updated_at DESC);

-- Auto-bump updated_at on any change
CREATE OR REPLACE FUNCTION internal.touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_dashboard_state_updated ON internal.dashboard_state;
CREATE TRIGGER trg_dashboard_state_updated
    BEFORE UPDATE ON internal.dashboard_state
    FOR EACH ROW EXECUTE FUNCTION internal.touch_updated_at();

-- ── NLQ Session ─────────────────────────────────────────────
-- Stores Natural Language Query conversation history per user.
CREATE TABLE IF NOT EXISTS internal.nlq_session (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT,
    title       TEXT,
    messages    JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nlq_user_updated
    ON internal.nlq_session (user_id, updated_at DESC);

DROP TRIGGER IF EXISTS trg_nlq_session_updated ON internal.nlq_session;
CREATE TRIGGER trg_nlq_session_updated
    BEFORE UPDATE ON internal.nlq_session
    FOR EACH ROW EXECUTE FUNCTION internal.touch_updated_at();

-- ── KPI Registry ────────────────────────────────────────────
-- Caches discovered / user-defined KPIs and their SQL definitions.
CREATE TABLE IF NOT EXISTS internal.kpi_registry (
    kpi_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kpi_name    TEXT NOT NULL,
    description TEXT,
    sql_def     TEXT NOT NULL,       -- the SQL expression/query
    source      TEXT,                -- 'agent' | 'user'
    tags        TEXT[],              -- grouping labels
    usefulness  NUMERIC(5,2),        -- 0-100 score from KPI evaluator
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kpi_active
    ON internal.kpi_registry (is_active, created_at DESC);

DROP TRIGGER IF EXISTS trg_kpi_registry_updated ON internal.kpi_registry;
CREATE TRIGGER trg_kpi_registry_updated
    BEFORE UPDATE ON internal.kpi_registry
    FOR EACH ROW EXECUTE FUNCTION internal.touch_updated_at();

-- ── Query Log ───────────────────────────────────────────────
-- Logs every NLQ query for debugging and quality tracking.
CREATE TABLE IF NOT EXISTS internal.query_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID REFERENCES internal.nlq_session(id) ON DELETE SET NULL,
    natural_lang TEXT NOT NULL,
    generated_sql TEXT,
    success      BOOLEAN,
    row_count    INT,
    exec_ms      INT,
    user_feedback SMALLINT,         -- 1 helpful | -1 not helpful | NULL
    queried_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- DATA SCHEMA — client-facing tables shown in Data Manager
-- ============================================================

-- ============================================================
-- CLIENT DATA TABLES
--
-- Do NOT define client data tables here.
-- Run ingest_data.py --raw to upload a CSV — it creates the
-- table automatically in the data schema with the right columns.
--
-- Example:
--   python ingest_data.py --csv myfile.csv --raw --table my_table
--
-- Any table created in the data schema automatically appears
-- in the Data Manager dropdown — no code changes needed.
-- ============================================================
