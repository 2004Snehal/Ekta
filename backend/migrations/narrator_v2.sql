-- Narrator v2 Migration
-- Run this against Supabase/PostgreSQL to add v2 columns.
-- All statements use IF NOT EXISTS — safe to run multiple times.

-- 1. Extend pg_insight_history for follow-up tracking
ALTER TABLE internal.pg_insight_history
  ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'new';
ALTER TABLE internal.pg_insight_history
  ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE internal.pg_insight_history
  ADD COLUMN IF NOT EXISTS consecutive_periods INT DEFAULT 1;
ALTER TABLE internal.pg_insight_history
  ADD COLUMN IF NOT EXISTS last_severity VARCHAR(10);

-- 2. Extend insight_log for richer cards
ALTER TABLE internal.insight_log
  ADD COLUMN IF NOT EXISTS status VARCHAR(20);
ALTER TABLE internal.insight_log
  ADD COLUMN IF NOT EXISTS tab_destination VARCHAR(30);
ALTER TABLE internal.insight_log
  ADD COLUMN IF NOT EXISTS suggested_action TEXT;
ALTER TABLE internal.insight_log
  ADD COLUMN IF NOT EXISTS insight_source VARCHAR(30);
ALTER TABLE internal.insight_log
  ADD COLUMN IF NOT EXISTS consecutive_periods INT;

-- 3. Index for follow-up queries
CREATE INDEX IF NOT EXISTS idx_insight_history_active
  ON internal.pg_insight_history(client_id, status)
  WHERE status IN ('new', 'ongoing', 'worsening');

-- 4. Index for insight_log by source
CREATE INDEX IF NOT EXISTS idx_insight_log_source
  ON internal.insight_log(client_id, insight_source, generated_at DESC);
