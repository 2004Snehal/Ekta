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

DROP TABLE IF EXISTS fact_outputs CASCADE;

DROP TABLE IF EXISTS fact_videos CASCADE;

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
-- FACT TABLES
-- ============================================================

-- -------------------------------------------------------
-- fact_videos: one row per source video uploaded to Frammer
-- this is the upload grain
-- -------------------------------------------------------
CREATE TABLE fact_videos (
    video_id            BIGSERIAL PRIMARY KEY,
    client_id           INT NOT NULL REFERENCES dim_client(client_id),
    channel_id          INT NOT NULL REFERENCES dim_channel(channel_id),
    user_id             INT NOT NULL REFERENCES dim_user(user_id),
    team_id             INT REFERENCES dim_team(team_id),
    input_type_id       INT REFERENCES dim_input_type(input_type_id),
    language_id         INT REFERENCES dim_language(language_id),

-- timestamps (now available via synthetic data)
uploaded_at TIMESTAMPTZ NOT NULL,
processed_at TIMESTAMPTZ, -- when Frammer finished processing
processing_secs INT, -- processed_at - uploaded_at

-- content metadata
headline TEXT,
source_url TEXT,
duration_secs INT NOT NULL, -- source video duration

-- billing
billable_flag BOOLEAN DEFAULT TRUE,

-- data quality flags (set by ingestion)
is_enriched         BOOLEAN DEFAULT FALSE,  -- was input_type inferred?
    enrichment_confidence NUMERIC(4,3),          -- confidence of inference
    has_quality_issues  BOOLEAN DEFAULT FALSE,

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------------------------------------
-- fact_outputs: one row per generated output
-- 1 video → multiple outputs (avg 3.2x from real data)
-- this is where output_type, publish status live
-- -------------------------------------------------------
CREATE TABLE fact_outputs (
    output_id           BIGSERIAL PRIMARY KEY,
    video_id            BIGINT NOT NULL REFERENCES fact_videos(video_id),
    client_id           INT NOT NULL REFERENCES dim_client(client_id),
    channel_id          INT NOT NULL REFERENCES dim_channel(channel_id),
    output_type_id      INT NOT NULL REFERENCES dim_output_type(output_type_id),

-- generation timing
created_at TIMESTAMPTZ NOT NULL,

-- output content
duration_secs INT,

-- publish state
published_flag BOOLEAN DEFAULT FALSE,
published_at TIMESTAMPTZ,
published_platform_id INT REFERENCES dim_platform (platform_id),
published_url TEXT,

-- time to publish (published_at - created_at)
time_to_publish_secs INT );

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

-- pgvector: embeddings for NLQ (DISABLED - requires pgvector extension)
-- CREATE TABLE embeddings (
--     embedding_id    SERIAL PRIMARY KEY,
--     content_type    VARCHAR(50) NOT NULL,
--     -- metric_definition, schema_doc, example_query,
--     -- dimension_description, video_headline
--     content_id      INT,                   -- FK to relevant table
--     content_text    TEXT NOT NULL,
--     embedding       vector(1536),          -- OpenAI ada-002 dimensions
--     metadata        JSONB,
--     created_at      TIMESTAMPTZ DEFAULT NOW()
-- );

-- ============================================================
-- MATERIALIZED VIEWS (pre-computed KPIs)
-- refreshed hourly via pg_cron
-- ============================================================

CREATE MATERIALIZED VIEW mv_monthly_kpis AS
SELECT
    v.client_id,
    v.channel_id,
    v.input_type_id,
    v.language_id,
    date_trunc('month', v.uploaded_at) AS month,
    COUNT(DISTINCT v.video_id) AS uploaded_count,
    SUM(v.duration_secs) AS uploaded_duration_secs,
    COUNT(DISTINCT o.output_id) AS created_count,
    SUM(o.duration_secs) AS created_duration_secs,
    COUNT(DISTINCT o.output_id) FILTER (
        WHERE
            o.published_flag = TRUE
    ) AS published_count,
    SUM(o.duration_secs) FILTER (
        WHERE
            o.published_flag = TRUE
    ) AS published_duration_secs,
    ROUND(
        COUNT(DISTINCT o.output_id) FILTER (
            WHERE
                o.published_flag
        )::NUMERIC / NULLIF(
            COUNT(DISTINCT o.output_id),
            0
        ) * 100,
        2
    ) AS publish_rate_pct,
    ROUND(
        COUNT(DISTINCT o.output_id)::NUMERIC / NULLIF(COUNT(DISTINCT v.video_id), 0),
        2
    ) AS output_multiplier
FROM fact_videos v
    LEFT JOIN fact_outputs o ON o.video_id = v.video_id
GROUP BY
    1,
    2,
    3,
    4,
    5;

CREATE MATERIALIZED VIEW mv_channel_health AS
SELECT
    v.client_id,
    v.channel_id,
    COUNT(DISTINCT v.video_id) AS total_uploads,
    COUNT(DISTINCT o.output_id) AS total_created,
    COUNT(DISTINCT o.output_id) FILTER (
        WHERE
            o.published_flag
    ) AS total_published,
    ROUND(
        COUNT(DISTINCT o.output_id) FILTER (
            WHERE
                o.published_flag
        )::NUMERIC / NULLIF(
            COUNT(DISTINCT o.output_id),
            0
        ) * 100,
        2
    ) AS publish_rate_pct,
    ROUND(
        COUNT(DISTINCT o.output_id)::NUMERIC / NULLIF(COUNT(DISTINCT v.video_id), 0),
        2
    ) AS output_multiplier,
    COUNT(DISTINCT v.user_id) AS active_users,
    MAX(v.uploaded_at) AS last_activity
FROM fact_videos v
    LEFT JOIN fact_outputs o ON o.video_id = v.video_id
GROUP BY
    1,
    2;

CREATE MATERIALIZED VIEW mv_user_performance AS
SELECT
    v.client_id,
    v.channel_id,
    v.user_id,
    COUNT(DISTINCT v.video_id) AS uploaded_count,
    COUNT(DISTINCT o.output_id) AS created_count,
    COUNT(DISTINCT o.output_id) FILTER (
        WHERE
            o.published_flag
    ) AS published_count,
    SUM(v.duration_secs) AS uploaded_duration_secs,
    ROUND(
        COUNT(DISTINCT o.output_id) FILTER (
            WHERE
                o.published_flag
        )::NUMERIC / NULLIF(
            COUNT(DISTINCT o.output_id),
            0
        ) * 100,
        2
    ) AS publish_rate_pct
FROM fact_videos v
    LEFT JOIN fact_outputs o ON o.video_id = v.video_id
GROUP BY
    1,
    2,
    3;

-- ============================================================
-- INDEXES (performance for dashboard query patterns)
-- ============================================================

-- fact_videos: primary access patterns
CREATE INDEX idx_fv_client_channel_uploaded ON fact_videos (
    client_id,
    channel_id,
    uploaded_at DESC
);

CREATE INDEX idx_fv_client_uploaded ON fact_videos (client_id, uploaded_at DESC);

CREATE INDEX idx_fv_input_type ON fact_videos (client_id, input_type_id);

CREATE INDEX idx_fv_language ON fact_videos (client_id, language_id);

CREATE INDEX idx_fv_user ON fact_videos (
    client_id,
    user_id,
    uploaded_at DESC
);

CREATE INDEX idx_fv_team ON fact_videos (team_id);

-- fact_outputs: primary access patterns
CREATE INDEX idx_fo_video_id ON fact_outputs (video_id);

CREATE INDEX idx_fo_client_channel ON fact_outputs (client_id, channel_id);

CREATE INDEX idx_fo_output_type ON fact_outputs (output_type_id);

CREATE INDEX idx_fo_published ON fact_outputs (
    client_id,
    published_flag,
    published_at
);

CREATE INDEX idx_fo_platform ON fact_outputs (published_platform_id)
WHERE
    published_flag = TRUE;

-- embeddings: vector similarity search (DISABLED - requires pgvector extension)
-- CREATE INDEX idx_embeddings_vector
--     ON embeddings USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);
-- CREATE INDEX idx_embeddings_type
--     ON embeddings (content_type);

-- materialized views: refresh schedule via pg_cron
-- SELECT cron.schedule('refresh-mv', '0 * * * *',
--   'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_kpis;
--    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_channel_health;
--    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_user_performance;');