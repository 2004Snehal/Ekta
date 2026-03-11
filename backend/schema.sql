-- ============================================================
-- FRAMMER AI ANALYTICS PLATFORM
-- PostgreSQL Schema
-- ============================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- DROP EXISTING OBJECTS (makes script re-runnable)
-- ============================================================
DROP MATERIALIZED VIEW IF EXISTS mv_user_performance CASCADE;

DROP MATERIALIZED VIEW IF EXISTS mv_channel_health CASCADE;

DROP MATERIALIZED VIEW IF EXISTS mv_monthly_kpis CASCADE;

DROP TABLE IF EXISTS query_log CASCADE;

DROP TABLE IF EXISTS quality_log CASCADE;

DROP TABLE IF EXISTS forecast_log CASCADE;

DROP TABLE IF EXISTS insight_log CASCADE;

DROP TABLE IF EXISTS kpi_registry CASCADE;

DROP TABLE IF EXISTS fact_created_videos CASCADE;

DROP TABLE IF EXISTS user_channel_map CASCADE;

DROP TABLE IF EXISTS dim_team CASCADE;

DROP TABLE IF EXISTS dim_platform CASCADE;

DROP TABLE IF EXISTS dim_language CASCADE;

DROP TABLE IF EXISTS dim_output_type CASCADE;

DROP TABLE IF EXISTS dim_input_type CASCADE;

DROP TABLE IF EXISTS dim_user CASCADE;

DROP TABLE IF EXISTS dim_channel CASCADE;

DROP TABLE IF EXISTS dim_client CASCADE;

-- ============================================================
-- DIMENSION TABLES
-- ============================================================

CREATE TABLE dim_client (
    client_id SERIAL PRIMARY KEY,
    client_name VARCHAR(100) NOT NULL,
    plan_type VARCHAR(50), -- basic, pro, enterprise
    industry VARCHAR(100), -- news, sports, entertainment
    region VARCHAR(50), -- india, us, europe
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- -------------------------------------------------------
-- dim_channel: one workspace per row, belongs to one client
-- -------------------------------------------------------
CREATE TABLE dim_channel (
    channel_id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES dim_client (client_id),
    channel_name VARCHAR(100) NOT NULL,
    channel_code VARCHAR(10), -- A, B, C as in real data
    primary_language VARCHAR(10), -- dominant language of channel
    content_focus VARCHAR(100), -- news, sports, politics etc
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- -------------------------------------------------------
-- dim_user: independent of channel (users span channels)
-- -------------------------------------------------------
CREATE TABLE dim_user (
    user_id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES dim_client (client_id),
    user_name VARCHAR(100) NOT NULL,
    email VARCHAR(200),
    role VARCHAR(50), -- editor, producer, qa, auto
    is_bot BOOLEAN DEFAULT FALSE, -- for Auto Upload users
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- -------------------------------------------------------
-- bridge: user can work across multiple channels
-- (40 of 45 users in real data work across multiple channels)
-- -------------------------------------------------------
CREATE TABLE user_channel_map (
    user_id INT NOT NULL REFERENCES dim_user (user_id),
    channel_id INT NOT NULL REFERENCES dim_channel (channel_id),
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    is_primary BOOLEAN DEFAULT FALSE, -- user's main channel
    PRIMARY KEY (user_id, channel_id)
);

CREATE TABLE dim_team (
    team_id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES dim_client (client_id),
    channel_id INT REFERENCES dim_channel (channel_id),
    team_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------------------------------------
-- Small lookup dimensions — match exactly to real data values
-- -------------------------------------------------------
CREATE TABLE dim_input_type (
    input_type_id SERIAL PRIMARY KEY,
    type_name VARCHAR(100) NOT NULL UNIQUE,
    -- from real data: interview, news bulletin, speech,
    -- special reports, debate, press conference,
    -- discussion-show, sports show, podcast, drama, in-brief
    category VARCHAR(50), -- live, recorded, scripted
    avg_duration_mins NUMERIC(6, 2)
);

CREATE TABLE dim_output_type (
    output_type_id SERIAL PRIMARY KEY,
    type_name VARCHAR(100) NOT NULL UNIQUE,
    -- from real data: Full package, Key moments,
    -- My Key moments, Chapters, Summary
    typical_length_secs INT,
    is_short_form BOOLEAN -- reels/shorts eligible
);

CREATE TABLE dim_language (
    language_id SERIAL PRIMARY KEY,
    language_code VARCHAR(10) NOT NULL UNIQUE,
    language_name VARCHAR(50) NOT NULL
    -- from real data: en, hi, mix, es, ar, mr
);

CREATE TABLE dim_platform (
    platform_id SERIAL PRIMARY KEY,
    platform_name VARCHAR(50) NOT NULL UNIQUE,
    platform_type VARCHAR(50)
    -- from real data: YouTube, Reels, Shorts,
    -- Instagram, Facebook, LinkedIn, X, Threads
);

-- ============================================================
-- FACT TABLE
-- One row per CREATED VIDEO (output grain)
-- 1 source video → ~3.2 created videos on average
-- ============================================================

CREATE TABLE fact_created_videos (
    id                    BIGSERIAL PRIMARY KEY,
    video_id              VARCHAR(50) NOT NULL,          -- external video_id / job_id
    client_id             INT NOT NULL REFERENCES dim_client(client_id),
    channel_id            INT NOT NULL REFERENCES dim_channel(channel_id),
    user_id               INT NOT NULL REFERENCES dim_user(user_id),
    team_id               INT REFERENCES dim_team(team_id),
    input_type_id         INT REFERENCES dim_input_type(input_type_id),
    output_type_id        INT REFERENCES dim_output_type(output_type_id),
    language_id           INT REFERENCES dim_language(language_id),

-- content
headline TEXT,
source_url TEXT,
uploaded_duration_secs INT, -- source video duration
created_duration_secs INT, -- created output duration
published_duration_secs INT, -- published clip duration

-- timestamps
uploaded_at TIMESTAMPTZ,
processed_at TIMESTAMPTZ,
published_at TIMESTAMPTZ,

-- publish info
published_flag        BOOLEAN DEFAULT FALSE,
    published_platform_id INT REFERENCES dim_platform(platform_id),
    published_url         TEXT,

    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- OPERATIONAL TABLES (Layer 3 agents write here)
-- ============================================================

-- KPI Agent: stores all defined metrics
CREATE TABLE kpi_registry (
    kpi_id SERIAL PRIMARY KEY,
    client_id INT REFERENCES dim_client (client_id), -- null = global
    kpi_name VARCHAR(200) NOT NULL,
    kpi_description TEXT,
    sql_definition TEXT NOT NULL, -- the actual SQL formula
    dimensions TEXT [], -- which dims this KPI supports
    created_by VARCHAR(50), -- 'user' or 'agent'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_computed TIMESTAMPTZ
);

-- Insight Narrator + Recommendation Agent: all outputs
CREATE TABLE insight_log (
    insight_id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES dim_client (client_id),
    insight_type VARCHAR(50) NOT NULL, -- anomaly, trend, recommendation, digest
    severity VARCHAR(20), -- info, warning, critical
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    dimensions JSONB, -- {channel: 'A', metric: 'publish_rate'}
    metric_value NUMERIC,
    baseline_value NUMERIC,
    delta_pct NUMERIC,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    is_read BOOLEAN DEFAULT FALSE
);

-- Forecasting Agent: stores predictions
CREATE TABLE forecast_log (
    forecast_id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES dim_client (client_id),
    channel_id INT REFERENCES dim_channel (channel_id),
    metric_name VARCHAR(100) NOT NULL,
    forecast_month DATE NOT NULL,
    predicted_value NUMERIC NOT NULL,
    lower_bound NUMERIC,
    upper_bound NUMERIC,
    model_used VARCHAR(50), -- prophet, arima, linear
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ingestion: data quality issues log
CREATE TABLE quality_log (
    log_id SERIAL PRIMARY KEY,
    client_id INT REFERENCES dim_client (client_id),
    source_file VARCHAR(200),
    issue_type VARCHAR(100) NOT NULL, -- null_field, duplicate, type_mismatch
    field_name VARCHAR(100),
    issue_count INT DEFAULT 1,
    sample_value TEXT,
    resolution VARCHAR(100), -- skipped, enriched, defaulted
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

-- SQL RAG: query log for learning and improvement
CREATE TABLE query_log (
    query_id SERIAL PRIMARY KEY,
    client_id INT REFERENCES dim_client (client_id),
    natural_language TEXT NOT NULL,
    generated_sql TEXT,
    query_type VARCHAR(50), -- analytical, semantic_search
    executed BOOLEAN DEFAULT FALSE,
    success BOOLEAN,
    row_count INT,
    execution_ms INT,
    user_feedback INT, -- 1 helpful, -1 not helpful
    queried_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- MATERIALIZED VIEWS (pre-computed KPIs)
-- ============================================================

CREATE MATERIALIZED VIEW mv_monthly_kpis AS
SELECT
    f.client_id,
    f.channel_id,
    f.input_type_id,
    f.output_type_id,
    f.language_id,
    date_trunc('month', f.uploaded_at) AS month,
    COUNT(*) AS created_count,
    SUM(f.uploaded_duration_secs) AS total_uploaded_duration_secs,
    SUM(f.created_duration_secs) AS total_created_duration_secs,
    COUNT(*) FILTER (
        WHERE
            f.published_flag
    ) AS published_count,
    SUM(f.published_duration_secs) FILTER (
        WHERE
            f.published_flag
    ) AS total_published_duration_secs,
    ROUND(
        COUNT(*) FILTER (
            WHERE
                f.published_flag
        )::NUMERIC / NULLIF(COUNT(*), 0) * 100,
        2
    ) AS publish_rate_pct
FROM fact_created_videos f
GROUP BY
    1,
    2,
    3,
    4,
    5,
    6;

CREATE MATERIALIZED VIEW mv_channel_health AS
SELECT
    f.client_id,
    f.channel_id,
    COUNT(*) AS total_created,
    COUNT(*) FILTER (
        WHERE
            f.published_flag
    ) AS total_published,
    ROUND(
        COUNT(*) FILTER (
            WHERE
                f.published_flag
        )::NUMERIC / NULLIF(COUNT(*), 0) * 100,
        2
    ) AS publish_rate_pct,
    COUNT(DISTINCT f.user_id) AS active_users,
    MAX(f.uploaded_at) AS last_activity
FROM fact_created_videos f
GROUP BY
    1,
    2;

CREATE MATERIALIZED VIEW mv_user_performance AS
SELECT
    f.client_id,
    f.channel_id,
    f.user_id,
    COUNT(*) AS created_count,
    COUNT(*) FILTER (
        WHERE
            f.published_flag
    ) AS published_count,
    SUM(f.uploaded_duration_secs) AS total_uploaded_duration_secs,
    SUM(f.created_duration_secs) AS total_created_duration_secs,
    ROUND(
        COUNT(*) FILTER (
            WHERE
                f.published_flag
        )::NUMERIC / NULLIF(COUNT(*), 0) * 100,
        2
    ) AS publish_rate_pct
FROM fact_created_videos f
GROUP BY
    1,
    2,
    3;

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_fcv_client_channel_uploaded ON fact_created_videos (
    client_id,
    channel_id,
    uploaded_at DESC
);

CREATE INDEX idx_fcv_client_uploaded ON fact_created_videos (client_id, uploaded_at DESC);

CREATE INDEX idx_fcv_input_type ON fact_created_videos (client_id, input_type_id);

CREATE INDEX idx_fcv_output_type ON fact_created_videos (client_id, output_type_id);

CREATE INDEX idx_fcv_language ON fact_created_videos (client_id, language_id);

CREATE INDEX idx_fcv_user ON fact_created_videos (
    client_id,
    user_id,
    uploaded_at DESC
);

CREATE INDEX idx_fcv_team ON fact_created_videos (team_id);

CREATE INDEX idx_fcv_video_id ON fact_created_videos (video_id);

CREATE INDEX idx_fcv_published ON fact_created_videos (
    client_id,
    published_flag,
    published_at
)
WHERE
    published_flag = TRUE;

CREATE INDEX idx_fcv_platform ON fact_created_videos (published_platform_id)
WHERE
    published_flag = TRUE;