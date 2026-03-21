-- ============================================================
-- FRAMMER AI — CLEAN SCHEMA (source of truth)
-- Apply with: python run_migration.py
--
-- TWO SCHEMAS:
--   internal  — system/backend tables (sessions, logs, KPIs)
--   data      — client data + star schema (dims, fact, MVs)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE SCHEMA IF NOT EXISTS internal;
CREATE SCHEMA IF NOT EXISTS data;

-- ============================================================
-- INTERNAL SCHEMA
-- ============================================================

-- ── Auto-updated timestamp trigger ──────────────────────────
CREATE OR REPLACE FUNCTION internal.touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

-- ── Dashboard State ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS internal.dashboard_state (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          TEXT,
    version          INTEGER NOT NULL DEFAULT 1,
    filters_json     JSONB   NOT NULL DEFAULT '{}',
    filters_expanded BOOLEAN NOT NULL DEFAULT TRUE,
    loaded_range     TEXT,
    selected_kpi_id  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ds_user_updated
    ON internal.dashboard_state (user_id, updated_at DESC);

DROP TRIGGER IF EXISTS trg_dashboard_state_updated ON internal.dashboard_state;
CREATE TRIGGER trg_dashboard_state_updated
    BEFORE UPDATE ON internal.dashboard_state
    FOR EACH ROW EXECUTE FUNCTION internal.touch_updated_at();

-- ── NLQ Session ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS internal.nlq_session (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    TEXT,
    title      TEXT,
    messages   JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nlq_user_updated
    ON internal.nlq_session (user_id, updated_at DESC);

DROP TRIGGER IF EXISTS trg_nlq_session_updated ON internal.nlq_session;
CREATE TRIGGER trg_nlq_session_updated
    BEFORE UPDATE ON internal.nlq_session
    FOR EACH ROW EXECUTE FUNCTION internal.touch_updated_at();

-- ── KPI Registry ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS internal.kpi_registry (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL UNIQUE,
    description      TEXT,
    formula          TEXT,
    sql_expression   TEXT NOT NULL,
    columns_used     JSONB NOT NULL DEFAULT '[]',
    tables_used      JSONB NOT NULL DEFAULT '[]',
    category         TEXT CHECK (category IN (
                         'Founders and Executive Leadership',
                         'Client Success Teams',
                         'Operations Teams',
                         'Editorial and Production Teams',
                         'Technology and Product Teams'
                     )),
    current_value    JSONB,
    unit             TEXT,
    usefulness_score FLOAT8,
    source           TEXT NOT NULL DEFAULT 'manual',
    expand_page      JSONB,
    client_id        BIGINT,
    dimensions       TEXT[],
    created_by       TEXT,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ,
    last_computed    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_kpi_active
    ON internal.kpi_registry (is_active, created_at DESC);

DROP TRIGGER IF EXISTS trg_kpi_registry_updated ON internal.kpi_registry;
CREATE TRIGGER trg_kpi_registry_updated
    BEFORE UPDATE ON internal.kpi_registry
    FOR EACH ROW EXECUTE FUNCTION internal.touch_updated_at();

-- ── Users ────────────────────────────────────────────────────
-- All signups land here with role='user'. role='admin' must be set
-- directly in the database (never via the API).
CREATE TABLE IF NOT EXISTS internal.users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL UNIQUE,
    name          TEXT,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    profile       TEXT NOT NULL DEFAULT 'team_member',  -- one of the 5 dashboard personas or 'team_member'
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON internal.users (email);

DROP TRIGGER IF EXISTS trg_users_updated ON internal.users;
CREATE TRIGGER trg_users_updated
    BEFORE UPDATE ON internal.users
    FOR EACH ROW EXECUTE FUNCTION internal.touch_updated_at();

-- ── Insight Dedup History ────────────────────────────────────
-- Suppresses repeated insights within a rolling window.
CREATE TABLE IF NOT EXISTS internal.pg_insight_history (
    id            BIGSERIAL PRIMARY KEY,
    client_id     BIGINT NOT NULL,
    entity_type   TEXT NOT NULL,
    entity_id     TEXT NOT NULL,
    insight_type  TEXT NOT NULL,
    metric_name   TEXT NOT NULL,
    period        TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    seen_count    INT NOT NULL DEFAULT 1,
    CONSTRAINT uq_insight_history UNIQUE (client_id, entity_type, entity_id, insight_type, metric_name, period)
);

CREATE INDEX IF NOT EXISTS idx_insight_history_client
    ON internal.pg_insight_history (client_id, last_seen_at DESC);

-- ── Chart Description Cache ──────────────────────────────────
-- Stores LLM-generated descriptions of what each chart depicts.
-- Keyed by chart metadata only (no data dependency) — generated once.
CREATE TABLE IF NOT EXISTS internal.chart_description_cache (
    cache_key    TEXT PRIMARY KEY,  -- SHA256(title|type|x_label|y_label)
    chart_title  TEXT,
    chart_type   TEXT,
    x_label      TEXT,
    y_label      TEXT,
    description  TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Insight Cache ────────────────────────────────────────────
-- Stale-while-revalidate cache for the narrator pipeline output.
CREATE TABLE IF NOT EXISTS internal.insight_cache (
    cache_key    TEXT PRIMARY KEY,
    insights     JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data_as_of   DATE NOT NULL
);

-- ── Query Log ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS internal.query_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    UUID REFERENCES internal.nlq_session(id) ON DELETE SET NULL,
    natural_lang  TEXT NOT NULL,
    generated_sql TEXT,
    success       BOOLEAN,
    row_count     INT,
    exec_ms       INT,
    user_feedback SMALLINT,
    queried_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Insight Log ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS internal.insight_log (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    insight_id     BIGSERIAL,
    client_id      BIGINT,
    insight_type   VARCHAR(50) NOT NULL,
    severity       VARCHAR(20),
    title          TEXT NOT NULL,
    body           TEXT NOT NULL,
    dimensions     JSONB,
    metric_value   NUMERIC,
    baseline_value NUMERIC,
    delta_pct      NUMERIC,
    category       TEXT,
    entity_type    TEXT,
    entity_id      TEXT,
    period         TEXT,
    current_value  NUMERIC,
    reference_value NUMERIC,
    confidence     NUMERIC,
    root_cause_hint TEXT,
    user_feedback  SMALLINT,
    is_read        BOOLEAN DEFAULT FALSE,
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insight_log_client
    ON internal.insight_log (client_id, generated_at DESC);

-- ============================================================
-- DATA SCHEMA — helpers
-- ============================================================

-- ── Duration parser (HH:MM:SS → seconds) ────────────────────
CREATE OR REPLACE FUNCTION data.duration_to_secs(v TEXT) RETURNS INTEGER AS $$
DECLARE
    parts TEXT[];
BEGIN
    IF v IS NULL OR TRIM(v) = '' THEN RETURN NULL; END IF;
    parts := string_to_array(TRIM(v), ':');
    IF array_length(parts, 1) = 3 THEN
        RETURN (parts[1]::int * 3600 + parts[2]::int * 60 + parts[3]::int);
    ELSIF array_length(parts, 1) = 2 THEN
        RETURN (parts[1]::int * 60 + parts[2]::int);
    ELSE
        RETURN TRIM(v)::int;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ── Timestamp parser (handles "HH:MM:SS, DD, Mon, YYYY") ────
CREATE OR REPLACE FUNCTION data.parse_uploaded_at(v TEXT) RETURNS TIMESTAMPTZ AS $$
BEGIN
    IF v IS NULL OR TRIM(v) = '' THEN RETURN NULL; END IF;
    BEGIN
        RETURN TO_TIMESTAMP(TRIM(v), 'HH24:MI:SS, DD, Mon, YYYY');
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
    BEGIN
        RETURN TRIM(v)::TIMESTAMPTZ;
    EXCEPTION WHEN OTHERS THEN
        RETURN NULL;
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================
-- DATA SCHEMA — dimension tables
-- (populated from data.shortened_filtered_data via ingest_data.py)
-- ============================================================

CREATE TABLE IF NOT EXISTS data.dim_client (
    client_id   BIGINT PRIMARY KEY,
    client_type TEXT,
    client_name TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS data.dim_channel (
    channel_id   SERIAL PRIMARY KEY,
    client_id    BIGINT NOT NULL REFERENCES data.dim_client(client_id),
    channel_code TEXT NOT NULL,
    channel_name TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_dim_channel_client_code UNIQUE (client_id, channel_code)
);

CREATE TABLE IF NOT EXISTS data.dim_user (
    user_id    SERIAL PRIMARY KEY,
    client_id  BIGINT NOT NULL REFERENCES data.dim_client(client_id),
    user_name  TEXT NOT NULL,
    role       TEXT,
    is_bot     BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_dim_user_client_name UNIQUE (client_id, user_name)
);

CREATE TABLE IF NOT EXISTS data.dim_input_type (
    input_type_id SERIAL PRIMARY KEY,
    type_name     TEXT NOT NULL UNIQUE,
    category      TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS data.dim_output_type (
    output_type_id SERIAL PRIMARY KEY,
    type_name      TEXT NOT NULL UNIQUE,
    is_short_form  BOOLEAN DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS data.dim_language (
    language_id   SERIAL PRIMARY KEY,
    language_code TEXT NOT NULL UNIQUE,
    language_name TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS data.dim_platform (
    platform_id   SERIAL PRIMARY KEY,
    platform_name TEXT NOT NULL UNIQUE,
    platform_type TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS data.dim_team (
    team_id    SERIAL PRIMARY KEY,
    team_name  TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- DATA SCHEMA — source table
-- (created by ingest_data.py --raw -- do not define columns here)
-- ============================================================

-- data.shortened_filtered_data is created dynamically by ingest_data.py --raw
-- Schema: _row_hash TEXT PK, headline, source, published, team_name, type,
--         uploaded_by, video_id, published_platform, published_url,
--         uploaded_duration, created_duration, published_duration,
--         output_type, channel, language, uploaded_at, views,
--         client_type, client_id, uploaded_hours, cumulative_uploaded_hours, billable

-- ============================================================
-- DATA SCHEMA — fact table (materialized view over source)
-- ============================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS data.fact_created_videos AS
SELECT
    s._row_hash,
    s.video_id,
    dc.client_id,
    dch.channel_id,
    du.user_id,
    dit.input_type_id,
    dot.output_type_id,
    dl.language_id,
    dp.platform_id,
    dt.team_id,
    s.headline,
    s.source,
    s.published_url,
    data.duration_to_secs(s.uploaded_duration)  AS uploaded_duration_secs,
    data.duration_to_secs(s.created_duration)    AS created_duration_secs,
    data.duration_to_secs(s.published_duration)  AS published_duration_secs,
    s.uploaded_hours,
    s.cumulative_uploaded_hours,
    s.views,
    LOWER(s.published) IN ('yes', 'true', '1')   AS published_flag,
    s.billable,
    data.parse_uploaded_at(s.uploaded_at)        AS uploaded_at
FROM data.shortened_filtered_data s
LEFT JOIN data.dim_client      dc  ON dc.client_id     = s.client_id
LEFT JOIN data.dim_channel     dch ON dch.channel_code = s.channel    AND dch.client_id = s.client_id
LEFT JOIN data.dim_user        du  ON du.user_name     = s.uploaded_by AND du.client_id  = s.client_id
LEFT JOIN data.dim_input_type  dit ON dit.type_name    = s.type
LEFT JOIN data.dim_output_type dot ON dot.type_name    = s.output_type
LEFT JOIN data.dim_language    dl  ON dl.language_code = s.language
LEFT JOIN data.dim_platform    dp  ON dp.platform_name = s.published_platform
LEFT JOIN data.dim_team        dt  ON dt.team_name     = s.team_name;

CREATE UNIQUE INDEX IF NOT EXISTS idx_fact_row_hash   ON data.fact_created_videos (_row_hash);
CREATE INDEX        IF NOT EXISTS idx_fact_client_ch  ON data.fact_created_videos (client_id, channel_id, uploaded_at DESC);
CREATE INDEX        IF NOT EXISTS idx_fact_client_usr ON data.fact_created_videos (client_id, user_id, uploaded_at DESC);
CREATE INDEX        IF NOT EXISTS idx_fact_client_at  ON data.fact_created_videos (client_id, uploaded_at DESC);

-- ============================================================
-- DATA SCHEMA — aggregate materialized views
-- ============================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS data.mv_monthly_kpis AS
SELECT
    f.client_id,
    f.channel_id,
    f.input_type_id,
    f.output_type_id,
    f.language_id,
    DATE_TRUNC('month', f.uploaded_at)                                              AS month,
    COUNT(*)                                                                         AS created_count,
    SUM(f.uploaded_duration_secs)                                                    AS total_uploaded_duration_secs,
    SUM(f.created_duration_secs)                                                     AS total_created_duration_secs,
    COUNT(*) FILTER (WHERE f.published_flag)                                         AS published_count,
    SUM(f.published_duration_secs) FILTER (WHERE f.published_flag)                  AS total_published_duration_secs,
    ROUND(COUNT(*) FILTER (WHERE f.published_flag)::NUMERIC / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct,
    SUM(f.views)                                                                     AS total_views,
    SUM(f.uploaded_hours)                                                            AS total_uploaded_hours
FROM data.fact_created_videos f
WHERE f.uploaded_at IS NOT NULL
GROUP BY 1, 2, 3, 4, 5, 6;

CREATE INDEX IF NOT EXISTS idx_mv_monthly_client_ch ON data.mv_monthly_kpis (client_id, channel_id, month DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS data.mv_channel_health AS
SELECT
    f.client_id,
    f.channel_id,
    COUNT(*)                                                                          AS total_created,
    COUNT(*) FILTER (WHERE f.published_flag)                                         AS total_published,
    ROUND(COUNT(*) FILTER (WHERE f.published_flag)::NUMERIC / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct,
    COUNT(DISTINCT f.user_id)                                                        AS active_users,
    SUM(f.views)                                                                     AS total_views,
    SUM(f.uploaded_hours)                                                            AS total_uploaded_hours,
    MAX(f.uploaded_at)                                                               AS last_activity
FROM data.fact_created_videos f
GROUP BY 1, 2;

CREATE INDEX IF NOT EXISTS idx_mv_channel_health ON data.mv_channel_health (client_id, channel_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS data.mv_user_performance AS
SELECT
    f.client_id,
    f.channel_id,
    f.user_id,
    COUNT(*)                                                                          AS created_count,
    COUNT(*) FILTER (WHERE f.published_flag)                                         AS published_count,
    SUM(f.uploaded_duration_secs)                                                    AS total_uploaded_duration_secs,
    SUM(f.created_duration_secs)                                                     AS total_created_duration_secs,
    ROUND(COUNT(*) FILTER (WHERE f.published_flag)::NUMERIC / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct,
    SUM(f.views)                                                                     AS total_views,
    SUM(f.uploaded_hours)                                                            AS total_uploaded_hours
FROM data.fact_created_videos f
GROUP BY 1, 2, 3;

CREATE INDEX IF NOT EXISTS idx_mv_user_perf ON data.mv_user_performance (client_id, channel_id, user_id);
