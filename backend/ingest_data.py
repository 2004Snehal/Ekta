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

from config import DATABASE_URL


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


def ensure_schema(conn):
    """Create all tables, indexes, and materialized views if they don't exist."""
    print("Ensuring schema exists...")
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
        conn.commit()
        # Materialized views: CREATE IF NOT EXISTS only works on PG 9.3+
        # but won't error if view already exists with this guard
        for stmt in MATERIALIZED_VIEWS_SQL.strip().split("\n\n"):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cur.execute(stmt)
                conn.commit()
            except psycopg2.errors.DuplicateTable:
                conn.rollback()  # view already exists, skip
    print("  Schema ready.\n")


# ── DB connection ─────────────────────────────────────────────────────────────

def connect_db():
    """
    Connect to Supabase/PostgreSQL, safely handling special chars in the password.
    psycopg2 DSN parsing fails if the password contains un-encoded '%' chars,
    so we parse the URL ourselves and pass keyword arguments instead.
    """
    parsed = urlparse(DATABASE_URL)
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=unquote(parsed.password) if parsed.password else None,
        sslmode="require",   # Supabase requires SSL
        connect_timeout=15,
    )


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

def load_facts(conn, df: pd.DataFrame, resolved: dict, client_id: int,
               maps: dict, dry_run: bool = False) -> tuple[int, int]:
    inserted = skipped = 0
    batch = []
    BATCH_SIZE = 500

    def flush(cur):
        nonlocal inserted
        if not batch:
            return
        execute_values(cur, """
            INSERT INTO fact_created_videos (
                video_id, client_id, channel_id, user_id, team_id,
                input_type_id, output_type_id, language_id,
                headline, source_url,
                uploaded_duration_secs, created_duration_secs, published_duration_secs,
                uploaded_at,
                published_flag, published_platform_id, published_url
            ) VALUES %s
            ON CONFLICT (video_id) DO NOTHING
        """, batch)
        inserted += len(batch)
        batch.clear()

    cur = conn.cursor() if not dry_run else None

    try:
        for idx in df.index:
            user_name    = str(col(df, resolved, "uploaded_by")[idx] or "").strip()
            channel_code = str(col(df, resolved, "channel")[idx] or "").strip()

            user_id    = maps["user"].get(user_name)
            channel_id = maps["channel"].get(channel_code)

            if not user_id or not channel_id:
                skipped += 1
                continue

            def get(c, _idx=idx):
                v = col(df, resolved, c)[_idx]
                return str(v).strip() if pd.notna(v) and str(v).strip() else None

            team_id         = maps["team"].get(get("team_name") or "")
            input_type_id   = maps["input_type"].get(get("type") or "")
            output_type_id  = maps["output_type"].get(get("output_type") or "")
            language_id     = maps["language"].get(get("language") or "")
            pub_platform    = get("published_platform")
            pub_platform_id = maps["platform"].get(pub_platform) if pub_platform else None

            published_val  = get("published")
            published_flag = published_val.lower() in ("yes", "true", "1") if published_val else False

            video_id_ext = get("video_id") or f"row_{idx}"

            batch.append((
                video_id_ext, client_id, channel_id, user_id, team_id,
                input_type_id, output_type_id, language_id,
                get("headline"), get("source"),
                duration_to_secs(col(df, resolved, "uploaded_duration")[idx]),
                duration_to_secs(col(df, resolved, "created_duration")[idx]),
                duration_to_secs(col(df, resolved, "published_duration")[idx]),
                parse_timestamp(col(df, resolved, "uploaded_at")[idx]),
                published_flag, pub_platform_id, get("published_url"),
            ))

            if len(batch) >= BATCH_SIZE:
                if not dry_run:
                    flush(cur)
                else:
                    inserted += len(batch)
                    batch.clear()
                print(f"  {inserted + skipped}/{len(df)} rows processed…")

        if not dry_run:
            flush(cur)
        else:
            inserted += len(batch)

    finally:
        if cur:
            cur.close()

    if not dry_run:
        conn.commit()

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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest CSV into Frammer Analytics DB")
    parser.add_argument("--csv",      required=True, help="Path to the CSV file")
    parser.add_argument("--client",   default="CLIENT_1", help="Client name (default: CLIENT_1)")
    parser.add_argument("--truncate", action="store_true", help="Truncate all tables before ingestion")
    parser.add_argument("--dry-run",  action="store_true", help="Parse and validate without writing to DB")
    args = parser.parse_args()

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
