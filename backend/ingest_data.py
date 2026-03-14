"""
Dynamic Data Ingestion Script — Frammer AI Analytics Platform
Ingests any CSV into the Supabase PostgreSQL schema.

Usage:
    python ingest_data.py --csv path/to/file.csv
    python ingest_data.py --csv path/to/file.csv --client "MyClient" --truncate
    python ingest_data.py --csv path/to/file.csv --dry-run

Column aliases are resolved automatically (case-insensitive).
"""

import argparse
import sys
from datetime import datetime
from urllib.parse import urlparse, unquote

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

from backend_config import DATABASE_URL


# ── Column alias map ──────────────────────────────────────────────────────────
# Maps canonical name → list of CSV column name variants (case-insensitive).
COLUMN_ALIASES = {
    "video_id":           ["video id", "videoid", "id"],
    "channel":            ["channel", "channel code", "channel_code"],
    "uploaded_by":        ["uploaded by", "uploader", "user", "user name", "username"],
    "type":               ["type", "input type", "input_type", "content type"],
    "output_type":        ["output type", "output_type", "output"],
    "language":           ["language", "lang"],
    "published_platform": ["published platform", "platform", "publish platform"],
    "published":          ["published", "is published", "publish status"],
    "published_url":      ["published url", "publish url", "pub url"],
    "team_name":          ["team name", "team", "team_name"],
    "headline":           ["headline", "title", "video title"],
    "source":             ["source", "source url", "src url"],
    "uploaded_at":        ["uploaded at", "upload time", "created time", "date", "upload date"],
    "uploaded_duration":  ["uploaded duration", "source duration", "duration"],
    "created_duration":   ["created duration", "output duration"],
    "published_duration": ["published duration", "pub duration"],
}

INPUT_TYPE_CATEGORIES = {
    "interview": "recorded", "news bulletin": "live",
    "special reports": "recorded", "speech": "recorded",
    "debate": "recorded", "press conference": "recorded",
    "discussion-show": "recorded", "sports show": "recorded",
    "podcast": "recorded", "drama": "scripted", "in-brief": "scripted",
}

SHORT_FORM_OUTPUT_TYPES = {"key moments", "my key moments", "summary"}

PLATFORM_TYPES = {
    "youtube": "video", "reels": "short_form", "shorts": "short_form",
    "instagram": "social", "facebook": "social", "facebook-reels": "short_form",
    "linkedin": "professional", "x": "social", "threads": "social",
}

LANG_NAMES = {
    "en": "English", "hi": "Hindi", "mix": "Mixed",
    "es": "Spanish", "ar": "Arabic", "mr": "Marathi", "ta": "Tamil",
    "te": "Telugu", "kn": "Kannada", "bn": "Bengali", "gu": "Gujarati",
}

KNOWN_TIMESTAMP_FORMATS = [
    "%H:%M:%S, %d, %b, %Y",   # 10:00:40, 06, Apr, 2025
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y",
    "%Y-%m-%d",
]


# ── Schema DDL ────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS dim_client (
    client_id   SERIAL PRIMARY KEY,
    client_name VARCHAR(100) NOT NULL,
    plan_type   VARCHAR(50),
    industry    VARCHAR(100),
    region      VARCHAR(50),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    is_active   BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dim_channel (
    channel_id       SERIAL PRIMARY KEY,
    client_id        INT NOT NULL REFERENCES dim_client(client_id),
    channel_name     VARCHAR(100) NOT NULL,
    channel_code     VARCHAR(10),
    primary_language VARCHAR(10),
    content_focus    VARCHAR(100),
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    is_active        BOOLEAN DEFAULT TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_channel_code
    ON dim_channel(channel_code);

CREATE TABLE IF NOT EXISTS dim_user (
    user_id    SERIAL PRIMARY KEY,
    client_id  INT NOT NULL REFERENCES dim_client(client_id),
    user_name  VARCHAR(100) NOT NULL,
    email      VARCHAR(200),
    role       VARCHAR(50),
    is_bot     BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active  BOOLEAN DEFAULT TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_user_client_name
    ON dim_user(client_id, user_name);

CREATE TABLE IF NOT EXISTS user_channel_map (
    user_id    INT NOT NULL REFERENCES dim_user(user_id),
    channel_id INT NOT NULL REFERENCES dim_channel(channel_id),
    joined_at  TIMESTAMPTZ DEFAULT NOW(),
    is_primary BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (user_id, channel_id)
);

CREATE TABLE IF NOT EXISTS dim_team (
    team_id    SERIAL PRIMARY KEY,
    client_id  INT NOT NULL REFERENCES dim_client(client_id),
    channel_id INT REFERENCES dim_channel(channel_id),
    team_name  VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_team_client_name
    ON dim_team(client_id, team_name);

CREATE TABLE IF NOT EXISTS dim_input_type (
    input_type_id  SERIAL PRIMARY KEY,
    type_name      VARCHAR(100) NOT NULL UNIQUE,
    category       VARCHAR(50),
    avg_duration_mins NUMERIC(6,2)
);

CREATE TABLE IF NOT EXISTS dim_output_type (
    output_type_id    SERIAL PRIMARY KEY,
    type_name         VARCHAR(100) NOT NULL UNIQUE,
    typical_length_secs INT,
    is_short_form     BOOLEAN
);

CREATE TABLE IF NOT EXISTS dim_language (
    language_id   SERIAL PRIMARY KEY,
    language_code VARCHAR(10) NOT NULL UNIQUE,
    language_name VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_platform (
    platform_id   SERIAL PRIMARY KEY,
    platform_name VARCHAR(50) NOT NULL UNIQUE,
    platform_type VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS fact_created_videos (
    id                      BIGSERIAL PRIMARY KEY,
    video_id                VARCHAR(50) NOT NULL UNIQUE,
    client_id               INT NOT NULL REFERENCES dim_client(client_id),
    channel_id              INT NOT NULL REFERENCES dim_channel(channel_id),
    user_id                 INT NOT NULL REFERENCES dim_user(user_id),
    team_id                 INT REFERENCES dim_team(team_id),
    input_type_id           INT REFERENCES dim_input_type(input_type_id),
    output_type_id          INT REFERENCES dim_output_type(output_type_id),
    language_id             INT REFERENCES dim_language(language_id),
    headline                TEXT,
    source_url              TEXT,
    uploaded_duration_secs  INT,
    created_duration_secs   INT,
    published_duration_secs INT,
    uploaded_at             TIMESTAMPTZ,
    processed_at            TIMESTAMPTZ,
    published_at            TIMESTAMPTZ,
    published_flag          BOOLEAN DEFAULT FALSE,
    published_platform_id   INT REFERENCES dim_platform(platform_id),
    published_url           TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kpi_registry (
    kpi_id          SERIAL PRIMARY KEY,
    client_id       INT REFERENCES dim_client(client_id),
    kpi_name        VARCHAR(200) NOT NULL,
    kpi_description TEXT,
    sql_definition  TEXT NOT NULL,
    dimensions      TEXT[],
    created_by      VARCHAR(50),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_computed   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS insight_log (
    insight_id    SERIAL PRIMARY KEY,
    client_id     INT NOT NULL REFERENCES dim_client(client_id),
    insight_type  VARCHAR(50) NOT NULL,
    severity      VARCHAR(20),
    title         TEXT NOT NULL,
    body          TEXT NOT NULL,
    dimensions    JSONB,
    metric_value  NUMERIC,
    baseline_value NUMERIC,
    delta_pct     NUMERIC,
    generated_at  TIMESTAMPTZ DEFAULT NOW(),
    is_read       BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS forecast_log (
    forecast_id     SERIAL PRIMARY KEY,
    client_id       INT NOT NULL REFERENCES dim_client(client_id),
    channel_id      INT REFERENCES dim_channel(channel_id),
    metric_name     VARCHAR(100) NOT NULL,
    forecast_month  DATE NOT NULL,
    predicted_value NUMERIC NOT NULL,
    lower_bound     NUMERIC,
    upper_bound     NUMERIC,
    model_used      VARCHAR(50),
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quality_log (
    log_id       SERIAL PRIMARY KEY,
    client_id    INT REFERENCES dim_client(client_id),
    source_file  VARCHAR(200),
    issue_type   VARCHAR(100) NOT NULL,
    field_name   VARCHAR(100),
    issue_count  INT DEFAULT 1,
    sample_value TEXT,
    resolution   VARCHAR(100),
    logged_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS query_log (
    query_id         SERIAL PRIMARY KEY,
    client_id        INT REFERENCES dim_client(client_id),
    natural_language TEXT NOT NULL,
    generated_sql    TEXT,
    query_type       VARCHAR(50),
    executed         BOOLEAN DEFAULT FALSE,
    success          BOOLEAN,
    row_count        INT,
    execution_ms     INT,
    user_feedback    INT,
    queried_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dashboard_state (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          VARCHAR(200),
    version          INTEGER DEFAULT 1,
    filters_json     JSONB NOT NULL DEFAULT '{}',
    filters_expanded BOOLEAN DEFAULT TRUE,
    loaded_range     VARCHAR(30),
    selected_kpi_id  VARCHAR(50),
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fcv_client_channel_uploaded
    ON fact_created_videos(client_id, channel_id, uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_fcv_user
    ON fact_created_videos(client_id, user_id, uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_fcv_video_id
    ON fact_created_videos(video_id);
CREATE INDEX IF NOT EXISTS idx_dashboard_state_user
    ON dashboard_state(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS nlq_session (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    VARCHAR(200),
    title      TEXT,
    messages   JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nlq_session_user
    ON nlq_session(user_id, updated_at DESC);
"""

MATERIALIZED_VIEWS_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_monthly_kpis AS
SELECT
    f.client_id, f.channel_id, f.input_type_id, f.output_type_id, f.language_id,
    date_trunc('month', f.uploaded_at) AS month,
    COUNT(*) AS created_count,
    SUM(f.uploaded_duration_secs)  AS total_uploaded_duration_secs,
    SUM(f.created_duration_secs)   AS total_created_duration_secs,
    COUNT(*) FILTER (WHERE f.published_flag) AS published_count,
    SUM(f.published_duration_secs) FILTER (WHERE f.published_flag) AS total_published_duration_secs,
    ROUND(COUNT(*) FILTER (WHERE f.published_flag)::NUMERIC / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
FROM fact_created_videos f
GROUP BY 1,2,3,4,5,6;

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_channel_health AS
SELECT
    f.client_id, f.channel_id,
    COUNT(*) AS total_created,
    COUNT(*) FILTER (WHERE f.published_flag) AS total_published,
    ROUND(COUNT(*) FILTER (WHERE f.published_flag)::NUMERIC / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct,
    COUNT(DISTINCT f.user_id) AS active_users,
    MAX(f.uploaded_at) AS last_activity
FROM fact_created_videos f
GROUP BY 1,2;

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_user_performance AS
SELECT
    f.client_id, f.channel_id, f.user_id,
    COUNT(*) AS created_count,
    COUNT(*) FILTER (WHERE f.published_flag) AS published_count,
    SUM(f.uploaded_duration_secs) AS total_uploaded_duration_secs,
    SUM(f.created_duration_secs)  AS total_created_duration_secs,
    ROUND(COUNT(*) FILTER (WHERE f.published_flag)::NUMERIC / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
FROM fact_created_videos f
GROUP BY 1,2,3;
"""


def _split_sql(sql: str) -> list[str]:
    """Split a SQL string into individual statements, skipping blanks."""
    return [s.strip() for s in sql.strip().split(";") if s.strip()]


def ensure_schema(conn):
    """Create all tables and indexes one statement at a time (avoids Supabase timeouts)."""
    print("Ensuring schema exists...")
    stmts = _split_sql(SCHEMA_SQL)
    total = len(stmts)
    with conn.cursor() as cur:
        for i, stmt in enumerate(stmts, 1):
            try:
                cur.execute(stmt)
                conn.commit()
            except psycopg2.errors.DuplicateTable:
                conn.rollback()
            except psycopg2.errors.DuplicateObject:
                conn.rollback()
            except Exception as e:
                conn.rollback()
                print(f"  [WARN] stmt {i}/{total} skipped: {e}")
            if i % 5 == 0 or i == total:
                print(f"  {i}/{total} statements done…")

        # Materialized views — each is one statement, catch if already exists
        for stmt in MATERIALIZED_VIEWS_SQL.strip().split("\n\n"):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cur.execute(stmt)
                conn.commit()
            except (psycopg2.errors.DuplicateTable, psycopg2.errors.DuplicateObject):
                conn.rollback()
            except Exception as e:
                conn.rollback()
                print(f"  [WARN] view skipped: {e}")

    print("  Schema ready.\n")


# ── DB connection ─────────────────────────────────────────────────────────────

def connect_db():
    """
    Connect to Supabase/PostgreSQL, safely handling special chars in the password.
    Disables statement_timeout for the session so bulk inserts are not cancelled.
    """
    parsed = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=unquote(parsed.password) if parsed.password else None,
        sslmode="require",
        connect_timeout=15,
    )
    # Disable statement timeout for this session (Supabase default is ~30s)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = 0")
        cur.execute("SET lock_timeout = 0")
    conn.commit()
    return conn


# ── Column resolution ─────────────────────────────────────────────────────────

def resolve_columns(df: pd.DataFrame) -> dict[str, str | None]:
    """
    Return {canonical_name: actual_df_column} for every alias group.
    Logs warnings for columns that couldn't be matched.
    """
    lower_cols = {c.lower().strip(): c for c in df.columns}
    resolved = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        match = next((lower_cols[a] for a in aliases if a in lower_cols), None)
        resolved[canonical] = match
        if match is None:
            print(f"  [WARN] Column '{canonical}' not found — tried: {aliases}")
    return resolved


def col(df: pd.DataFrame, resolved: dict, name: str):
    """Return series for a resolved column, or None series if missing."""
    actual = resolved.get(name)
    return df[actual] if actual else pd.Series([None] * len(df), index=df.index)


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_timestamp(val) -> datetime | None:
    if pd.isna(val):
        return None
    s = str(val).strip()
    for fmt in KNOWN_TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    print(f"  [WARN] Could not parse timestamp: '{s}'")
    return None


def duration_to_secs(val) -> int | None:
    if pd.isna(val):
        return None
    s = str(val).strip()
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(float(s))  # bare seconds
    except (ValueError, IndexError):
        return None


# ── Schema helpers ────────────────────────────────────────────────────────────

def truncate_all(conn):
    with conn.cursor() as cur:
        print("Truncating all tables...")
        cur.execute("""
            TRUNCATE TABLE
                fact_created_videos, user_channel_map,
                dim_team, dim_platform, dim_language,
                dim_output_type, dim_input_type,
                dim_user, dim_channel, dim_client
            CASCADE;
        """)
    conn.commit()
    print("  All tables truncated.\n")


def upsert_returning(cur, table: str, cols: list[str], values: list[tuple],
                     conflict_col: str, return_col: str) -> dict:
    """
    Bulk-insert rows into `table`, ignoring conflicts on `conflict_col`.
    Returns {conflict_col_value: return_col_value}.
    """
    if not values:
        return {}
    sql = f"""
        INSERT INTO {table} ({", ".join(cols)})
        VALUES %s
        ON CONFLICT ({conflict_col}) DO NOTHING
        RETURNING {conflict_col}, {return_col};
    """
    execute_values(cur, sql, values)
    result = {row[0]: row[1] for row in cur.fetchall()}
    # For rows that already existed, fetch their IDs
    existing_keys = [v[cols.index(conflict_col)] for v in values
                     if v[cols.index(conflict_col)] not in result]
    if existing_keys:
        cur.execute(
            f"SELECT {conflict_col}, {return_col} FROM {table} "
            f"WHERE {conflict_col} = ANY(%s)",
            (existing_keys,),
        )
        result.update({row[0]: row[1] for row in cur.fetchall()})
    return result


# ── Dimension population ──────────────────────────────────────────────────────

def ensure_client(conn, client_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT client_id FROM dim_client WHERE client_name = %s",
            (client_name,),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            """INSERT INTO dim_client (client_name, plan_type, industry, region, is_active)
               VALUES (%s, 'enterprise', 'news', 'india', TRUE)
               RETURNING client_id""",
            (client_name,),
        )
        client_id = cur.fetchone()[0]
    conn.commit()
    print(f"  Created client '{client_name}' → id={client_id}")
    return client_id


def populate_dimensions(conn, df: pd.DataFrame, resolved: dict, client_id: int) -> dict:
    """
    Upsert all dimension rows. Returns a maps dict with all lookup tables.
    """
    print("Populating dimension tables...")
    maps = {}

    with conn.cursor() as cur:

        # dim_channel
        channel_codes = sorted(col(df, resolved, "channel").dropna().str.strip().unique())
        rows = [(client_id, f"Channel {c}", c, "en", True) for c in channel_codes]
        if rows:
            execute_values(cur, """
                INSERT INTO dim_channel (client_id, channel_name, channel_code, primary_language, is_active)
                VALUES %s ON CONFLICT (channel_code) DO NOTHING
            """, rows)
        cur.execute("SELECT channel_code, channel_id FROM dim_channel WHERE client_id = %s", (client_id,))
        maps["channel"] = {code: cid for code, cid in cur.fetchall()}
        print(f"  dim_channel: {len(maps['channel'])} channels")

        # dim_user
        user_names = sorted(col(df, resolved, "uploaded_by").dropna().str.strip().unique())
        rows = [
            (client_id, u, "auto" if u == "Auto Upload" else "editor",
             u == "Auto Upload", True)
            for u in user_names
        ]
        if rows:
            execute_values(cur, """
                INSERT INTO dim_user (client_id, user_name, role, is_bot, is_active)
                VALUES %s ON CONFLICT (client_id, user_name) DO NOTHING
            """, rows)
        cur.execute("SELECT user_name, user_id FROM dim_user WHERE client_id = %s", (client_id,))
        maps["user"] = {name: uid for name, uid in cur.fetchall()}
        print(f"  dim_user: {len(maps['user'])} users")

        # dim_input_type
        input_types = sorted(col(df, resolved, "type").dropna().str.strip().unique())
        rows = [(t, INPUT_TYPE_CATEGORIES.get(t.lower(), "recorded")) for t in input_types]
        if rows:
            execute_values(cur, """
                INSERT INTO dim_input_type (type_name, category)
                VALUES %s ON CONFLICT (type_name) DO NOTHING
            """, rows)
        cur.execute("SELECT type_name, input_type_id FROM dim_input_type")
        maps["input_type"] = {n: i for n, i in cur.fetchall()}
        print(f"  dim_input_type: {len(maps['input_type'])} types")

        # dim_output_type
        output_types = sorted(col(df, resolved, "output_type").dropna().str.strip().unique())
        rows = [(n, n.lower() in SHORT_FORM_OUTPUT_TYPES) for n in output_types]
        if rows:
            execute_values(cur, """
                INSERT INTO dim_output_type (type_name, is_short_form)
                VALUES %s ON CONFLICT (type_name) DO NOTHING
            """, rows)
        cur.execute("SELECT type_name, output_type_id FROM dim_output_type")
        maps["output_type"] = {n: i for n, i in cur.fetchall()}
        print(f"  dim_output_type: {len(maps['output_type'])} output types")

        # dim_language
        langs = sorted(col(df, resolved, "language").dropna().str.strip().unique())
        rows = [(c, LANG_NAMES.get(c, c.title())) for c in langs]
        if rows:
            execute_values(cur, """
                INSERT INTO dim_language (language_code, language_name)
                VALUES %s ON CONFLICT (language_code) DO NOTHING
            """, rows)
        cur.execute("SELECT language_code, language_id FROM dim_language")
        maps["language"] = {c: i for c, i in cur.fetchall()}
        print(f"  dim_language: {len(maps['language'])} languages")

        # dim_platform — from CSV + common extras
        csv_platforms = col(df, resolved, "published_platform").dropna().str.strip().unique().tolist()
        all_platforms = sorted(set(csv_platforms + [
            "YouTube", "Reels", "Shorts", "Instagram",
            "Facebook", "LinkedIn", "X", "Threads",
        ]))
        rows = [(p, PLATFORM_TYPES.get(p.lower(), "social")) for p in all_platforms]
        if rows:
            execute_values(cur, """
                INSERT INTO dim_platform (platform_name, platform_type)
                VALUES %s ON CONFLICT (platform_name) DO NOTHING
            """, rows)
        cur.execute("SELECT platform_name, platform_id FROM dim_platform")
        maps["platform"] = {n: i for n, i in cur.fetchall()}
        print(f"  dim_platform: {len(maps['platform'])} platforms")

        # dim_team
        teams = sorted(col(df, resolved, "team_name").dropna().str.strip().unique())
        rows = [(client_id, t) for t in teams]
        if rows:
            execute_values(cur, """
                INSERT INTO dim_team (client_id, team_name)
                VALUES %s ON CONFLICT DO NOTHING
            """, rows)
        cur.execute("SELECT team_name, team_id FROM dim_team WHERE client_id = %s", (client_id,))
        maps["team"] = {n: i for n, i in cur.fetchall()}
        print(f"  dim_team: {len(maps['team'])} teams")

    conn.commit()
    print("  Dimensions done.\n")
    return maps


# ── Fact table ────────────────────────────────────────────────────────────────

def _parse_duration_vec(series: pd.Series) -> pd.Series:
    """Vectorized HH:MM:SS → seconds. Returns int or None per row."""
    def _one(v):
        if pd.isna(v):
            return None
        parts = str(v).strip().split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return int(float(str(v)))
        except (ValueError, IndexError):
            return None
    return series.apply(_one)


def _parse_timestamp_vec(series: pd.Series) -> pd.Series:
    """Try common formats; return NaT (→ None) on failure."""
    for fmt in KNOWN_TIMESTAMP_FORMATS:
        try:
            parsed = pd.to_datetime(series, format=fmt, errors="coerce")
            if parsed.notna().mean() > 0.5:   # more than half parsed → good format
                return parsed
        except Exception:
            continue
    return pd.to_datetime(series, errors="coerce")   # last-resort generic parse


def _to_int(v):
    """Convert to Python int, or None if null/NaN."""
    try:
        if v is None or pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return int(v)


def _to_str(v):
    """Convert to Python str, or None if null/NaN."""
    try:
        if v is None or pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    return s if s else None


def load_facts(conn, df: pd.DataFrame, resolved: dict, client_id: int,
               maps: dict, dry_run: bool = False) -> tuple[int, int]:
    """
    Vectorized bulk insert — all FK lookups done with pandas .map(),
    timestamps and durations parsed as whole Series, then inserted in
    large batches of 5000. Safe to re-run: ON CONFLICT (video_id) DO NOTHING.
    """
    BATCH_SIZE = 5000

    print("  Vectorizing columns…")

    def gcol(name) -> pd.Series:
        return col(df, resolved, name)

    def sstrip(s: pd.Series) -> pd.Series:
        return s.astype(str).str.strip().where(s.notna(), None)

    # ── FK lookups (vectorized) ────────────────────────────────────────────
    user_ids    = sstrip(gcol("uploaded_by")).map(maps["user"])
    channel_ids = sstrip(gcol("channel")).map(maps["channel"])

    valid_mask  = user_ids.notna() & channel_ids.notna()
    skipped     = int((~valid_mask).sum())
    print(f"  Valid rows: {valid_mask.sum():,}  |  Skipped (no user/channel): {skipped:,}")

    if valid_mask.sum() == 0:
        return 0, skipped

    team_ids        = sstrip(gcol("team_name")).map(maps["team"])
    input_type_ids  = sstrip(gcol("type")).map(maps["input_type"])
    output_type_ids = sstrip(gcol("output_type")).map(maps["output_type"])
    language_ids    = sstrip(gcol("language")).map(maps["language"])
    platform_ids    = sstrip(gcol("published_platform")).map(maps["platform"])

    # ── Scalars ────────────────────────────────────────────────────────────
    pub_raw    = sstrip(gcol("published")).str.lower()
    pub_flags  = pub_raw.isin(["yes", "true", "1"])

    vid_raw    = gcol("video_id")
    video_ids  = vid_raw.astype(str).str.strip().where(vid_raw.notna(),
                     pd.Series([f"row_{i}" for i in df.index], index=df.index))

    headlines  = gcol("headline").where(gcol("headline").notna(), None)
    sources    = gcol("source").where(gcol("source").notna(), None)
    pub_urls   = gcol("published_url").where(gcol("published_url").notna(), None)

    # ── Timestamps & durations ─────────────────────────────────────────────
    print("  Parsing timestamps…")
    uploaded_at = _parse_timestamp_vec(gcol("uploaded_at"))

    print("  Parsing durations…")
    up_dur = _parse_duration_vec(gcol("uploaded_duration"))
    cr_dur = _parse_duration_vec(gcol("created_duration"))
    pu_dur = _parse_duration_vec(gcol("published_duration"))

    # ── Build rows list (only valid rows) ──────────────────────────────────
    print("  Building row tuples…")
    valid_idx = df.index[valid_mask]

    rows = [
        (
            _to_str(video_ids[i]),
            client_id,
            _to_int(channel_ids[i]),
            _to_int(user_ids[i]),
            _to_int(team_ids[i]),
            _to_int(input_type_ids[i]),
            _to_int(output_type_ids[i]),
            _to_int(language_ids[i]),
            _to_str(headlines[i]),
            _to_str(sources[i]),
            _to_int(up_dur[i]),
            _to_int(cr_dur[i]),
            _to_int(pu_dur[i]),
            None if pd.isna(uploaded_at[i]) else uploaded_at[i].to_pydatetime(),
            bool(pub_flags[i]),
            _to_int(platform_ids[i]),
            _to_str(pub_urls[i]),
        )
        for i in valid_idx
    ]

    total   = len(rows)
    inserted = 0

    if dry_run:
        print(f"  DRY RUN — would insert {total:,} rows")
        return total, skipped

    INSERT_SQL = """
        INSERT INTO fact_created_videos (
            video_id, client_id, channel_id, user_id, team_id,
            input_type_id, output_type_id, language_id,
            headline, source_url,
            uploaded_duration_secs, created_duration_secs, published_duration_secs,
            uploaded_at,
            published_flag, published_platform_id, published_url
        ) VALUES %s
        ON CONFLICT (video_id) DO NOTHING
    """

    print(f"  Inserting {total:,} rows in batches of {BATCH_SIZE}…")
    with conn.cursor() as cur:
        for start in range(0, total, BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            execute_values(cur, INSERT_SQL, batch, page_size=BATCH_SIZE)
            conn.commit()
            inserted += len(batch)
            print(f"  {inserted:,}/{total:,} rows inserted…")

    return inserted, skipped


# ── User-channel bridge ───────────────────────────────────────────────────────

def populate_user_channel_map(conn, df: pd.DataFrame, resolved: dict,
                               client_id: int, maps: dict):
    pairs = (
        df[[resolved["channel"], resolved["uploaded_by"]]]
        .dropna()
        .drop_duplicates()
    )
    rows = []
    for _, row in pairs.iterrows():
        uid = maps["user"].get(str(row[resolved["uploaded_by"]]).strip())
        cid = maps["channel"].get(str(row[resolved["channel"]]).strip())
        if uid and cid:
            rows.append((uid, cid))

    if rows:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO user_channel_map (user_id, channel_id)
                VALUES %s ON CONFLICT (user_id, channel_id) DO NOTHING
            """, rows)
        conn.commit()
    print(f"  user_channel_map: {len(rows)} pairs upserted")


# ── Materialized views ────────────────────────────────────────────────────────

def refresh_views(conn):
    with conn.cursor() as cur:
        for view in ["mv_monthly_kpis", "mv_channel_health", "mv_user_performance"]:
            print(f"  Refreshing {view}…")
            cur.execute(f"REFRESH MATERIALIZED VIEW {view};")
    conn.commit()
    print("  Views refreshed.\n")


# ── Row counts ────────────────────────────────────────────────────────────────

def print_counts(conn):
    tables = [
        "dim_client", "dim_channel", "dim_user", "dim_input_type",
        "dim_output_type", "dim_language", "dim_platform", "dim_team",
        "fact_created_videos", "user_channel_map",
    ]
    with conn.cursor() as cur:
        print("\nRow counts:")
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            print(f"  {t}: {cur.fetchone()[0]}")


# ── Raw mode ──────────────────────────────────────────────────────────────────

import hashlib
import re


def _pg_type(dtype) -> str:
    """Map a pandas dtype to a PostgreSQL column type."""
    s = str(dtype)
    if s.startswith("int"):
        return "BIGINT"
    if s.startswith("float"):
        return "DOUBLE PRECISION"
    if s == "bool":
        return "BOOLEAN"
    if s.startswith("datetime"):
        return "TIMESTAMPTZ"
    return "TEXT"


def _safe_col(name: str) -> str:
    """Convert any column name to a safe SQL identifier."""
    return re.sub(r"[^a-z0-9_]", "_", name.strip().lower())


def _row_hash(row) -> str:
    raw = "|".join("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
                   for v in row)
    return hashlib.md5(raw.encode()).hexdigest()


def ingest_raw(csv_path: str, table_name: str):
    """
    Upload a CSV directly as its own table (no star-schema ETL).

    - Table is created if it does not exist.
    - A _row_hash column (MD5 of all values) is used as the unique key so
      re-running the same file never inserts duplicates.
    - New rows in a re-run are appended; existing rows are skipped silently.
    """
    print("=" * 60)
    print("FRAMMER AI ANALYTICS — RAW CSV UPLOAD")
    print(f"  CSV   : {csv_path}")
    print(f"  Table : {table_name}")
    print("=" * 60)

    # Load CSV
    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except FileNotFoundError:
        print(f"\nERROR: File not found: {csv_path}")
        sys.exit(1)

    print(f"\nLoaded {len(df):,} rows, {len(df.columns)} columns")

    # Safe column names
    safe_cols = [_safe_col(c) for c in df.columns]
    df.columns = safe_cols

    # Build CREATE TABLE DDL
    col_defs = ",\n    ".join(f'"{c}" {_pg_type(df[c].dtype)}' for c in safe_cols)
    create_sql = f"""
CREATE TABLE IF NOT EXISTS "{table_name}" (
    _row_hash TEXT PRIMARY KEY,
    {col_defs}
)
""".strip()

    # Connect and create table
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(create_sql)
        conn.commit()
        print(f"  Table '{table_name}' ready.\n")

        # Build insert SQL
        quoted_cols = ", ".join(f'"{c}"' for c in safe_cols)
        insert_sql = f"""
INSERT INTO "{table_name}" (_row_hash, {quoted_cols})
VALUES %s
ON CONFLICT (_row_hash) DO NOTHING
""".strip()

        # Batch insert
        BATCH = 5_000
        total_inserted = total_skipped = 0

        for start in range(0, len(df), BATCH):
            batch = df.iloc[start : start + BATCH]
            rows = []
            for _, row in batch.iterrows():
                vals = [None if pd.isna(v) else v for v in row]
                h = _row_hash(vals)
                # Convert numpy types to Python natives
                native = []
                for v in vals:
                    if v is None:
                        native.append(None)
                    else:
                        if _HAS_NUMPY:
                            if isinstance(v, np.integer):
                                v = int(v)
                            elif isinstance(v, np.floating):
                                v = float(v)
                            elif isinstance(v, np.bool_):
                                v = bool(v)
                        native.append(v)
                rows.append((h, *native))

            with conn.cursor() as cur:
                execute_values(cur, insert_sql, rows, page_size=BATCH)
                inserted_count = cur.rowcount
            conn.commit()

            batch_skipped = len(rows) - inserted_count
            total_inserted += inserted_count
            total_skipped  += batch_skipped
            end = min(start + BATCH, len(df))
            print(f"  Rows {start+1:>7,}–{end:>7,}  |  inserted {inserted_count:,}  skipped {batch_skipped:,}")

        print(f"\n  Total inserted : {total_inserted:,}")
        print(f"  Total skipped  : {total_skipped:,}  (already in DB)")

    except Exception as e:
        print(f"\nERROR: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

    print("\n" + "=" * 60)
    print("RAW UPLOAD COMPLETE")
    print("=" * 60)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest CSV into Frammer Analytics DB")
    parser.add_argument("--csv",      required=True, help="Path to the CSV file")
    parser.add_argument("--client",   default="CLIENT_1", help="Client name (default: CLIENT_1)")
    parser.add_argument("--truncate", action="store_true", help="Truncate all tables before ingestion")
    parser.add_argument("--dry-run",  action="store_true", help="Parse and validate without writing to DB")
    parser.add_argument("--raw",      action="store_true",
                        help="Upload CSV as its own table (no star-schema ETL)")
    parser.add_argument("--table",    default=None,
                        help="Table name for --raw mode (default: derived from filename)")
    args = parser.parse_args()

    # ── Raw mode ──────────────────────────────────────────────────────────────
    if args.raw:
        table = args.table or _safe_col(
            args.csv.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        )
        ingest_raw(args.csv, table)
        return

    print("=" * 60)
    print("FRAMMER AI ANALYTICS — DATA INGESTION")
    print(f"  CSV    : {args.csv}")
    print(f"  Client : {args.client}")
    print(f"  Mode   : {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)

    # Load CSV
    try:
        df = pd.read_csv(args.csv)
    except FileNotFoundError:
        print(f"\nERROR: File not found: {args.csv}")
        sys.exit(1)

    print(f"\nLoaded {len(df)} rows, {len(df.columns)} columns")
    print(f"Columns: {list(df.columns)}\n")

    # Resolve columns
    print("Resolving column mappings...")
    resolved = resolve_columns(df)
    matched = {k: v for k, v in resolved.items() if v}
    print(f"  Matched {len(matched)}/{len(COLUMN_ALIASES)} columns\n")

    if resolved["uploaded_by"] is None or resolved["channel"] is None:
        print("ERROR: 'uploaded_by' and 'channel' columns are required.")
        sys.exit(1)

    if args.dry_run:
        print("DRY RUN — skipping DB writes.\n")
        conn = None
    else:
        print("Connecting to Supabase...")
        conn = connect_db()
        print("  Connected.\n")
        ensure_schema(conn)

    try:
        if not args.dry_run:
            if args.truncate:
                truncate_all(conn)

            client_id = ensure_client(conn, args.client)
            maps = populate_dimensions(conn, df, resolved, client_id)
        else:
            client_id = 1
            maps = {k: {} for k in ["channel", "user", "input_type",
                                     "output_type", "language", "platform", "team"]}

        print("Loading fact_created_videos...")
        inserted, skipped = load_facts(conn, df, resolved, client_id, maps,
                                       dry_run=args.dry_run)
        print(f"  Inserted: {inserted}  |  Skipped: {skipped}\n")

        if not args.dry_run:
            print("Populating user_channel_map...")
            populate_user_channel_map(conn, df, resolved, client_id, maps)

            print("\nRefreshing materialized views...")
            refresh_views(conn)

            print_counts(conn)

        print("\n" + "=" * 60)
        print("DATA INGESTION COMPLETE")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
