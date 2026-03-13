-- ============================================================
-- MIGRATION: Add dashboard_state table for shareable links
-- Run once against your Supabase / PostgreSQL database
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- provides gen_random_uuid()

CREATE TABLE IF NOT EXISTS dashboard_state (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       VARCHAR(200),                     -- optional — ties state to a user
    version       INTEGER DEFAULT 1,
    filters_json  JSONB NOT NULL DEFAULT '{}',
    filters_expanded BOOLEAN DEFAULT TRUE,
    loaded_range  VARCHAR(30),                      -- last-7-days | last-30-days | last-90-days | all-time
    selected_kpi_id VARCHAR(50),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dashboard_state_user ON dashboard_state (user_id, updated_at DESC);

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_dashboard_state_updated ON dashboard_state;
CREATE TRIGGER trg_dashboard_state_updated
    BEFORE UPDATE ON dashboard_state
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
