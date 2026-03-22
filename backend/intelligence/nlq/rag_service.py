"""
RAG service — Text-to-SQL using ChromaDB directly (no Vanna dependency).

On startup: trains ChromaDB with semantic DDL, tiered business rules, and Q→SQL examples.
Training is version-gated — only runs if the current KB version marker is absent.
Per query: embeds once → queries all 3 collections with the same vector → builds prompt.
Best-of-N: generate_sql_candidates() supports N>1 with concurrent LLM calls.
Qwen3 thinking: <think>...</think> blocks are extracted and surfaced in RAGResult.
"""

import hashlib
import json
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend_config import CHROMA_PATH
from llm_config import QWEN_CODER_MODEL, make_openai_client, LLM_MAX_TOKENS, LLM_TEMPERATURE
from intelligence.nlq.context import fetch_live_schema

logger = logging.getLogger("nlq.rag")

# Bump this string to force a full KB retrain on next startup
_KB_VERSION = "RAG_KB_V6_SEMANTIC_DOCS"


@dataclass
class RAGResult:
    sql: str
    chart_type: Optional[str] = None
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    title: Optional[str] = None
    answer_strategy: Optional[dict] = None
    thinking: Optional[str] = None      # Qwen3 native chain-of-thought
    routing: Optional[dict] = None      # reserved for no-SQL path signalling


# ── ChromaDB singleton ─────────────────────────────────────────────────────────

_chroma: Optional[dict] = None


def _get_chroma() -> dict:
    global _chroma
    if _chroma is None:
        import chromadb
        from chromadb.config import Settings
        from chromadb.utils import embedding_functions

        ef = embedding_functions.DefaultEmbeddingFunction()
        client = chromadb.PersistentClient(
            path=os.path.abspath(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
        _chroma = {
            "client": client,
            "ef":     ef,
            "sql":    client.get_or_create_collection(name="sql",           embedding_function=ef),
            "ddl":    client.get_or_create_collection(name="ddl",           embedding_function=ef),
            "doc":    client.get_or_create_collection(name="documentation", embedding_function=ef),
        }
        logger.info("ChromaDB initialised at %s.", os.path.abspath(CHROMA_PATH))
    return _chroma


# ── ID helpers ─────────────────────────────────────────────────────────────────

def _det_id(text: str, suffix: str) -> str:
    """Deterministic UUID from content hash — prevents duplicate entries on restart."""
    return str(uuid.UUID(hashlib.md5(text.encode()).hexdigest())) + suffix


def _safe_add(collection, doc: str, uid: str) -> None:
    """Add document; silently skip if already present (idempotent via deterministic ID)."""
    try:
        collection.add(documents=doc, ids=uid)
    except Exception:
        pass


# ── Training ───────────────────────────────────────────────────────────────────

def train_with_schema(conn) -> None:
    """
    Populate ChromaDB with semantic DDL, tiered business rules, and Q→SQL examples.

    Version-gated: skipped if _KB_VERSION marker already exists in the doc collection.
    To force a retrain, bump _KB_VERSION at the top of this file.
    """
    db = _get_chroma()

    # Check version marker — skip if this version is already trained
    version_id = _det_id(_KB_VERSION, "-doc")
    existing = db["doc"].get(ids=[version_id])
    if existing and existing.get("documents"):
        logger.info("RAG KB at version %s — skipping training.", _KB_VERSION)
        return

    logger.info("Training RAG KB (%s)…", _KB_VERSION)

    # ── 1. Business rule docs → doc collection ────────────────────────────────
    # Schema is NOT stored here — it is injected live into every prompt via
    # fetch_live_schema(conn) so the LLM always sees the real column names.

    core_doc = """Core query conventions for Frammer AI analytics:
- All objects are in the 'data' schema — always prefix tables/views with 'data.'.
- client_id isolation: always filter by client_id UNLESS the question explicitly compares clients.
- The main fact table (fact_created_videos) has: a boolean publish flag, a billable text field,
  a timestamp for when content was uploaded, duration columns for three stages (all in seconds),
  a per-video view count, and foreign keys to all dimension tables.
- Prefer materialized views for aggregates — they are pre-computed and faster:
    mv_monthly_kpis     → monthly trends, created/published counts, publish rates
    mv_channel_health   → per-channel totals, publish rate, views, hours, recency
    mv_user_performance → per-user output and publish rate
- Use the fact table for: row-level detail, billable filters, duration, per-video views,
  bot/human filters, short-form filters, platform/team breakdowns.
- Publish rate formula: ROUND(published_count::numeric / NULLIF(created_count, 0) * 100, 2)
- Month display: TO_CHAR(month, 'Mon YYYY') for human-readable x-axis labels.
- String filters: ALWAYS use ILIKE for name/label columns. Never use = for user-supplied text.
- Exact column names are in the live schema injected above — use those, do not guess."""
    _safe_add(db["doc"], core_doc, _det_id(core_doc, "-doc"))

    time_series_doc = """TIME-SERIES and TREND queries (monthly, over time, growth trends):
Use the monthly KPIs materialized view for pre-aggregated monthly data.
Always GROUP BY the time column and ORDER BY it ASC for correct trend direction.
Relative date patterns (use the live schema to pick the right timestamp column):
  "last N months"  → WHERE time_col >= DATE_TRUNC('month', NOW() - INTERVAL 'N-1 months')
  "this month"     → WHERE DATE_TRUNC('month', time_col) = DATE_TRUNC('month', NOW())
  "last month"     → WHERE DATE_TRUNC('month', time_col) = DATE_TRUNC('month', NOW() - INTERVAL '1 month')
  "last 7 days"    → WHERE time_col >= NOW() - INTERVAL '7 days'
  "today"          → WHERE DATE_TRUNC('day', time_col) = CURRENT_DATE
Use TO_CHAR(month_col, 'Mon YYYY') for human-readable month labels on the x-axis."""
    _safe_add(db["doc"], time_series_doc, _det_id(time_series_doc, "-doc"))

    ranking_doc = """RANKING and TOP-N queries (top users, best channels, highest/lowest publish rate):
Use the user performance MV for user rankings, channel health MV for channel rankings.
Always ORDER BY the metric DESC — never LIMIT 1 for "which is best/worst" questions.
Return all ranked rows so the user can compare. Use LIMIT N only when "top N" is explicit.
For filtered rankings with complex conditions, use HAVING after GROUP BY:
  HAVING <aggregate_condition> AND <another_aggregate_condition>
Check the live schema for exact column names — do not assume metric column names."""
    _safe_add(db["doc"], ranking_doc, _det_id(ranking_doc, "-doc"))

    multidim_doc = """MULTI-DIMENSION and BREAKDOWN queries (channel by language, user by channel, cross-tab):
Join fact_created_videos with any combination of dimension tables using the FK columns on the fact table.
GROUP BY all dimension label columns. Standard aggregate pattern:
  COUNT(*) AS created_count,
  COUNT(CASE WHEN published_flag THEN 1 END) AS published_count,
  ROUND(COUNT(CASE WHEN published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
Available dimensions (use the live schema for exact FK and name column names):
  channel, language, platform, team, user (has bot flag), output type (has short-form flag), input type
Always select the name/label column from dimensions, never the ID columns."""
    _safe_add(db["doc"], multidim_doc, _det_id(multidim_doc, "-doc"))

    platform_team_doc = """PLATFORM and TEAM queries:
- Platform and team data lives in their own dimension tables, joined to the fact table via FK columns.
- These dimensions are NOT on materialized views — always use the fact table for platform/team breakdowns.
- To group or filter by platform: join the platform dimension and use its name column.
- To group or filter by team: join the team dimension and use its name column.
- Use ILIKE for user-supplied platform/team name filters.
- Exact table names, FK columns, and name columns are in the live schema."""
    _safe_add(db["doc"], platform_team_doc, _det_id(platform_team_doc, "-doc"))

    user_filter_doc = """BOT vs HUMAN USER queries:
- The bot/human distinction is a boolean flag on the user dimension table — NOT on the fact table.
- To filter or group by bot status: join the user dimension via the user FK on the fact table.
- Human users: filter where the bot flag is FALSE.
- Bot users: filter where the bot flag is TRUE.
- Bot vs human comparison: group by the bot flag; use CASE WHEN for readable labels ('Bot'/'Human').
- User names are also on the user dimension table.
- Exact column names for the bot flag and user name are in the live schema."""
    _safe_add(db["doc"], user_filter_doc, _det_id(user_filter_doc, "-doc"))

    content_type_doc = """SHORT-FORM, LONG-FORM, and CONTENT TYPE queries:
- "Short-form" is NOT a duration threshold — it is a boolean flag on the output type dimension.
- "Long-form" means the short-form boolean is FALSE.
- To filter or group by content form: join the output type dimension via its FK on the fact table.
- Short-form filter: where the short-form boolean is TRUE.
- Long-form filter: where the short-form boolean is FALSE.
- For short-form vs long-form comparison: GROUP BY CASE WHEN <short_form_col> THEN 'Short-form' ELSE 'Long-form' END
- Output type name and input type name are also on their respective dimension tables.
- Exact table names, FK columns, and flag column names are in the live schema."""
    _safe_add(db["doc"], content_type_doc, _det_id(content_type_doc, "-doc"))

    duration_views_doc = """DURATION and VIEWS queries:
- The fact table has three duration columns (upload stage, created stage, published stage) — all in SECONDS.
  Exact column names are in the live schema. Convert to hours by dividing by 3600.
- Duration buckets: use CASE WHEN on the duration column for ranges (e.g. <30s, 30-60s, >60s).
- Per-video view count: on the fact table. Per-channel aggregate views: on the channel health MV.
- Recency queries (inactive channels): the channel health MV has a last_activity date column.
  Use: WHERE last_activity_col < NOW() - INTERVAL 'N days'
- Average duration: AVG(duration_col) / 60.0 for minutes."""
    _safe_add(db["doc"], duration_views_doc, _det_id(duration_views_doc, "-doc"))

    advanced_sql_doc = """ADVANCED SQL PATTERNS for complex analytics:

Weekday vs weekend (use the fact table's timestamp column):
  CASE WHEN EXTRACT(DOW FROM <timestamp_col>) IN (0, 6) THEN 'Weekend' ELSE 'Weekday' END AS day_type
  GROUP BY day_type
  (DOW: 0=Sunday, 6=Saturday)

Month-over-month growth — LAG window function over the monthly KPIs MV:
  SELECT TO_CHAR(<month_col>, 'Mon YYYY') AS month, <metric_col>,
    ROUND((<metric_col> - LAG(<metric_col>) OVER (ORDER BY <month_col>))::numeric
          / NULLIF(LAG(<metric_col>) OVER (ORDER BY <month_col>), 0) * 100, 1) AS mom_growth_pct
  FROM data.mv_monthly_kpis WHERE client_id = N ORDER BY <month_col>

Cumulative sum:
  SUM(<metric_col>) OVER (ORDER BY <time_col> ROWS UNBOUNDED PRECEDING) AS cumulative_total

HAVING clause — filter groups after aggregation (not WHERE):
  GROUP BY <dimension>
  HAVING <aggregate_expr> > threshold AND <aggregate_expr2> < threshold2

Scatter / correlation (two numeric columns, e.g. duration vs views):
  SELECT two numeric columns FROM fact table WHERE client_id = N LIMIT 500
  (set chart_type: scatter in the JSON output)

Users active across multiple channels: GROUP BY user HAVING COUNT(DISTINCT channel_id) > N

Channels with no published content: HAVING COUNT(CASE WHEN publish_flag THEN 1 END) = 0

Declining trend: use LAG() and compare current value < previous period value"""
    _safe_add(db["doc"], advanced_sql_doc, _det_id(advanced_sql_doc, "-doc"))

    ambiguous_query_doc = """AMBIGUOUS and VAGUE QUESTION interpretations — always make a best-effort attempt:
- "Are we doing better?" → compare this week vs last week on created_count and publish_rate_pct
- "Bad channels" → channels with lowest publish_rate_pct (ORDER BY publish_rate_pct ASC LIMIT 10)
- "All the data" / "everything" → aggregate summary by channel: created_count, published_count, publish_rate_pct, total_views
- "What happened on [day]?" → that day's totals: created_count, published_count, total views WHERE DATE_TRUNC('day', uploaded_at) = '[date]'
- "Videos that took too long" → WHERE created_duration_secs > uploaded_duration_secs * 2
- "High upload, low publish" → HAVING total uploads above a threshold AND publish rate below a threshold
- "Inactive channels" → channel health MV filtered where last activity was more than N days ago
- "Consistent growth" → use LAG() comparing 3+ consecutive months each higher than previous
- "Anomalies" → channels/users deviating more than 2× from the average metric value
Never refuse an analytics question — always write a reasonable SQL interpretation.
Use the live schema for exact column names."""
    _safe_add(db["doc"], ambiguous_query_doc, _det_id(ambiguous_query_doc, "-doc"))

    # ── 3. Q→SQL examples → SQL collection ────────────────────────────────────
    examples = [
        (
            "how many videos have been published",
            "SELECT COUNT(*) AS published_count FROM data.fact_created_videos WHERE published_flag = TRUE AND client_id = 1;",
        ),
        (
            "show created vs published videos by language",
            """SELECT dl.language_name AS language, COUNT(*) AS created_count,
  COUNT(CASE WHEN f.published_flag THEN 1 END) AS published_count,
  ROUND(COUNT(CASE WHEN f.published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
FROM data.fact_created_videos f
JOIN data.dim_language dl ON f.language_id = dl.language_id
WHERE f.client_id = 1
GROUP BY dl.language_name ORDER BY created_count DESC;""",
        ),
        (
            "which channel has the highest publish rate",
            """SELECT dc.channel_name AS channel,
  SUM(mk.created_count) AS total_created, SUM(mk.published_count) AS total_published,
  ROUND(AVG(mk.publish_rate_pct), 2) AS publish_rate_pct
FROM data.mv_monthly_kpis mk
JOIN data.dim_channel dc ON mk.channel_id = dc.channel_id
WHERE mk.client_id = 1
GROUP BY dc.channel_name ORDER BY publish_rate_pct DESC;""",
        ),
        (
            "top 10 users by output count",
            """SELECT du.user_name, up.created_count, up.published_count,
  ROUND(up.publish_rate_pct, 2) AS publish_rate_pct
FROM data.mv_user_performance up
JOIN data.dim_user du ON up.user_id = du.user_id
WHERE up.client_id = 1 ORDER BY up.created_count DESC LIMIT 10;""",
        ),
        (
            "monthly trend of published videos over the last 6 months",
            """SELECT TO_CHAR(month, 'Mon YYYY') AS month, SUM(published_count) AS published_count
FROM data.mv_monthly_kpis
WHERE client_id = 1 AND month >= DATE_TRUNC('month', NOW() - INTERVAL '5 months')
GROUP BY month ORDER BY month;""",
        ),
        (
            "compare publish rate across channels",
            """SELECT dc.channel_name AS channel,
  SUM(ch.total_created) AS total_created, SUM(ch.total_published) AS total_published,
  ROUND(ch.publish_rate_pct, 2) AS publish_rate_pct
FROM data.mv_channel_health ch
JOIN data.dim_channel dc ON ch.channel_id = dc.channel_id
WHERE ch.client_id = 1
GROUP BY dc.channel_name, ch.publish_rate_pct ORDER BY publish_rate_pct DESC;""",
        ),
        (
            "show output breakdown by channel and language",
            """SELECT dc.channel_name AS channel, dl.language_name AS language,
  COUNT(*) AS created_count,
  COUNT(CASE WHEN f.published_flag THEN 1 END) AS published_count,
  ROUND(COUNT(CASE WHEN f.published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
FROM data.fact_created_videos f
JOIN data.dim_channel dc ON f.channel_id = dc.channel_id
JOIN data.dim_language dl ON f.language_id = dl.language_id
WHERE f.client_id = 1
GROUP BY dc.channel_name, dl.language_name ORDER BY created_count DESC;""",
        ),
        # --- V5 examples ---
        (
            "compare videos created by bots vs human users",
            """SELECT CASE WHEN du.is_bot THEN 'Bot' ELSE 'Human' END AS user_type,
  COUNT(*) AS created_count,
  COUNT(CASE WHEN f.published_flag THEN 1 END) AS published_count,
  ROUND(COUNT(CASE WHEN f.published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
FROM data.fact_created_videos f
JOIN data.dim_user du ON f.user_id = du.user_id
WHERE f.client_id = 1
GROUP BY du.is_bot ORDER BY created_count DESC;""",
        ),
        (
            "show short-form content performance by channel",
            """SELECT dc.channel_name AS channel,
  COUNT(*) AS created_count,
  COUNT(CASE WHEN f.published_flag THEN 1 END) AS published_count,
  ROUND(COUNT(CASE WHEN f.published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
FROM data.fact_created_videos f
JOIN data.dim_channel dc ON f.channel_id = dc.channel_id
JOIN data.dim_output_type dot ON f.output_type_id = dot.output_type_id
WHERE f.client_id = 1 AND dot.is_short_form = TRUE
GROUP BY dc.channel_name ORDER BY created_count DESC;""",
        ),
        (
            "breakdown of videos by platform",
            """SELECT dp.platform_name AS platform,
  COUNT(*) AS created_count,
  COUNT(CASE WHEN f.published_flag THEN 1 END) AS published_count,
  ROUND(COUNT(CASE WHEN f.published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
FROM data.fact_created_videos f
JOIN data.dim_platform dp ON f.platform_id = dp.platform_id
WHERE f.client_id = 1
GROUP BY dp.platform_name ORDER BY created_count DESC;""",
        ),
        (
            "distribution of videos by duration bucket",
            """SELECT
  CASE WHEN f.uploaded_duration_secs < 30 THEN '<30s'
       WHEN f.uploaded_duration_secs <= 60 THEN '30-60s'
       ELSE '>60s' END AS duration_bucket,
  COUNT(*) AS video_count,
  ROUND(COUNT(*)::numeric / SUM(COUNT(*)) OVER () * 100, 1) AS share_pct
FROM data.fact_created_videos f
WHERE f.client_id = 1
GROUP BY duration_bucket ORDER BY MIN(f.uploaded_duration_secs);""",
        ),
        (
            "month over month growth in created videos",
            """SELECT TO_CHAR(month, 'Mon YYYY') AS month, created_count,
  ROUND((created_count - LAG(created_count) OVER (ORDER BY month))::numeric
        / NULLIF(LAG(created_count) OVER (ORDER BY month), 0) * 100, 1) AS mom_growth_pct
FROM data.mv_monthly_kpis
WHERE client_id = 1
ORDER BY month;""",
        ),
        (
            "channels with more than 100 uploads but less than 50% publish rate",
            """SELECT dc.channel_name AS channel,
  COUNT(*) AS total_uploads,
  COUNT(CASE WHEN f.published_flag THEN 1 END) AS published_count,
  ROUND(COUNT(CASE WHEN f.published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
FROM data.fact_created_videos f
JOIN data.dim_channel dc ON f.channel_id = dc.channel_id
WHERE f.client_id = 1
GROUP BY dc.channel_name
HAVING COUNT(*) > 100 AND
  ROUND(COUNT(CASE WHEN f.published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) < 50
ORDER BY publish_rate_pct ASC;""",
        ),
        (
            "video output breakdown by team and language",
            """SELECT dt.team_name AS team, dl.language_name AS language,
  COUNT(*) AS created_count,
  COUNT(CASE WHEN f.published_flag THEN 1 END) AS published_count,
  ROUND(COUNT(CASE WHEN f.published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
FROM data.fact_created_videos f
JOIN data.dim_team dt ON f.team_id = dt.team_id
JOIN data.dim_language dl ON f.language_id = dl.language_id
WHERE f.client_id = 1
GROUP BY dt.team_name, dl.language_name ORDER BY created_count DESC;""",
        ),
        (
            "compare video uploads on weekdays vs weekends",
            """SELECT
  CASE WHEN EXTRACT(DOW FROM f.uploaded_at) IN (0, 6) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
  COUNT(*) AS created_count,
  COUNT(CASE WHEN f.published_flag THEN 1 END) AS published_count,
  ROUND(COUNT(CASE WHEN f.published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
FROM data.fact_created_videos f
WHERE f.client_id = 1
GROUP BY day_type ORDER BY created_count DESC;""",
        ),
    ]

    for question, sql in examples:
        doc = json.dumps({"question": question, "sql": sql}, ensure_ascii=False)
        _safe_add(db["sql"], doc, _det_id(doc, "-sql"))

    # Add version marker last — only present if training completed fully
    _safe_add(db["doc"], _KB_VERSION, version_id)
    logger.info("RAG training complete — %d SQL examples, %d docs.", len(examples), db["doc"].count())


# ── Retrieval ─────────────────────────────────────────────────────────────────

def _retrieve(collection, embedding: list, n: int) -> list:
    """Query a collection by pre-computed embedding. Returns raw document strings."""
    try:
        count = collection.count()
        if count == 0:
            return []
        result = collection.query(query_embeddings=[embedding], n_results=min(n, count))
        return result.get("documents", [[]])[0]
    except Exception as exc:
        # ChromaDB can throw "Nothing found on disk" when the HNSW index is
        # uninitialised (training hasn't run yet). Return empty — the pipeline
        # will proceed without RAG context and self-healing will cover it.
        logger.warning("ChromaDB retrieve failed (collection=%s): %s", collection.name, exc)
        return []


# ── Prompt building ────────────────────────────────────────────────────────────

_SYSTEM_BASE = (
    "You are a PostgreSQL expert for the Frammer AI analytics platform. "
    "Your job is to write SQL queries AND return a JSON metadata block describing how to display the result. "
    "Always use only the tables and views from the schema provided. "
    "If a similar question was answered before, follow the same SQL pattern. "
    "For insufficient context write a SELECT that produces 0 rows (WHERE 1=0) — "
    "except greetings/off-topic, which get a direct answer with no SQL at all."
)

_SQL_SUFFIX = """

--- ANALYTICS QUESTIONS: write SQL first, then JSON ---

STEP 1 — Write the PostgreSQL query.

SQL rules:
- Schema: all tables are in the 'data' schema. Always qualify: data.fact_created_videos, etc.
- Preferred tables for aggregates (faster, pre-computed):
    mv_monthly_kpis      → monthly trends, publish rates over time
    mv_channel_health    → per-channel totals and publish rates
    mv_user_performance  → per-user output and publish rates
  Use fact_created_videos only for row-level detail or breakdowns by input_type/output_type/language.
- Ranking questions ("which is best/worst/highest/lowest/top"): SELECT ALL relevant entities
  ranked by the metric (ORDER BY metric DESC). NEVER use LIMIT 1 — one row is unplottable.
  Use LIMIT 1 ONLY for single-scalar questions ("what is the total count of X").
- ID columns (any column ending in _id, _key, _code) are identifiers — NEVER select them
  unless the user explicitly asks for IDs. Always select the name/label column instead.
- Text filters (channel names, platform names, team names, etc.): ALWAYS use ILIKE, never =.
- Relative dates (use the actual timestamp column name from the schema):
    "last month"    → DATE_TRUNC('month', ts_col) = DATE_TRUNC('month', NOW() - INTERVAL '1 month')
    "this month"    → DATE_TRUNC('month', ts_col) = DATE_TRUNC('month', NOW())
    "last N months" → ts_col >= DATE_TRUNC('month', NOW() - INTERVAL 'N-1 months')
    "last 7 days"   → ts_col >= NOW() - INTERVAL '7 days'
    For MVs use the month column; for the fact table use the timestamp column.
- Unpublished: filter by the publish flag being FALSE — not by checking a URL column.
- Publish rate: ROUND(published_count::numeric / NULLIF(created_count, 0) * 100, 2)
- Month labels: TO_CHAR(month_col, 'Mon YYYY') for human-readable x-axis.
- Bot/human: the bot flag lives on the user dimension, NOT the fact table.
    Join the user dimension via its FK, then filter or group by the bot boolean.
    For comparison: GROUP BY CASE WHEN bot_col THEN 'Bot' ELSE 'Human' END AS user_type
- Short-form: defined by a boolean on the output type dimension, NOT by duration.
    Join the output type dimension via its FK, then filter by the short-form boolean.
- Platform and team: only in their dimension tables joined to the fact table — NOT in MVs.
- Duration: three columns on the fact table (upload/created/published stages), all in seconds.
    Divide by 3600 for hours. CASE WHEN for buckets. Check schema for exact names.
- Views: per-video on the fact table; aggregate per-channel on the channel health MV.
- Weekday/weekend: EXTRACT(DOW FROM ts_col) — 0=Sunday, 6=Saturday.
- Month-over-month growth: LAG() window function over the monthly KPIs MV.
- Post-aggregation filters: use HAVING (not WHERE) after GROUP BY.
- Always make a reasonable SQL attempt — never refuse an analytics question.

STEP 2 — After the SQL, output this JSON block:
```json
{
  "requires_sql": true,
  "chart_type": "<see rules below>",
  "x": "<the PRIMARY category/dimension column alias: channel, user, month, language, etc.>",
  "y": "<the SINGLE computed metric alias: count, sum, rate, percentage — NEVER an ID column>",
  "group_by": "<stacked_bar only: the column that splits into series — omit for all other chart types>",
  "title": "<concise descriptive title, 4–7 words>",
  "answer_strategy": {
    "type": "<see rules below>",
    "focus": ["<key aspect 1>", "<key aspect 2>"]
  }
}
```

Chart type — choose based on SEMANTICS of the result, not just row count:
- line           → values over ordered time periods (months, weeks, dates)
- bar            → independent category comparisons, ≤ 8 categories, 1 metric
- horizontal_bar → same as bar but > 8 categories or category names are long
- pie            → proportions that together represent a whole (shares summing to ~100%),
                   ≤ 10 categories, exactly 1 metric; use when asking "what % / how is it split"
- scatter        → correlation or relationship between two numeric columns
- radar          → comparing 2–5 named entities each measured on 3+ shared metrics
- stacked_bar    → one category broken down by a second dimension (requires group_by)
- table          → REQUIRED when: result has ID columns, > 4 columns, individual row records,
                   or there is no single clear numeric metric to visualise

x/y field rules:
- x → always a TEXT/LABEL column (channel_name, user_name, language_name, month label, type_name)
- y → always a COMPUTED number (created_count, publish_rate_pct, total_views, video_count, etc.)
- For pie: x = category label, y = numeric value
- If result has no suitable y metric → set chart_type to "table", leave x and y as ""

Answer strategy — match the shape of the result:
- time_series_trend  → trend over time.              focus: ["peak", "trough", "direction", "change_pct"]
- top_n_ranked       → ranked list.                  focus: ["winner", "runner_up", "spread", "total"]
- distribution       → proportions/shares.           focus: ["dominant_slice", "total", "slice_count"]
- single_aggregate   → one number.                   focus: ["exact_value"]
- detail_sample      → individual records.           focus: ["total_count", "common_pattern"]
- comparison         → two-group contrast (bot vs human, weekday vs weekend, short vs long-form).
                       focus: ["group_a_value", "group_b_value", "difference"]
- filtered_ranking   → ranked list with HAVING/threshold filter.
                       focus: ["winner", "threshold", "count_passing"]

--- EXCEPTION: greetings and off-topic only ---
If the question is a greeting, small talk, or entirely unrelated to video/media analytics,
do NOT write SQL. Output ONLY this JSON (no SQL, nothing else):
```json
{
  "requires_sql": false,
  "direct_answer": "<short friendly plain-text response>"
}
```"""


def _build_messages(question: str, sql_examples: list, live_schema: str, doc_docs: list) -> list:
    """
    Build the LLM message list:
      system  = base prompt + live schema (always fresh) + business rules
      user/assistant pairs = retrieved Q→SQL few-shot examples (SQL + JSON, matching final format)
      final user = augmented question + output format instructions
    """
    system = _SYSTEM_BASE

    if live_schema:
        system += "\n\n=== Schema ===\n" + live_schema

    if doc_docs:
        system += "\n\n=== Business Rules ===\n" + "\n\n".join(doc_docs)

    messages = [{"role": "system", "content": system}]

    # Few-shot examples: SQL only — the _SQL_SUFFIX on the final message teaches the JSON format.
    # Dummy JSON in examples would teach wrong x/y/chart_type values.
    for raw in sql_examples:
        try:
            ex = json.loads(raw)
            messages.append({"role": "user",      "content": ex["question"]})
            messages.append({"role": "assistant", "content": ex["sql"]})
        except Exception:
            pass

    messages.append({"role": "user", "content": question + _SQL_SUFFIX})
    return messages


# ── LLM call ──────────────────────────────────────────────────────────────────

def _call_llm(messages: list, temperature: float = LLM_TEMPERATURE, max_retries: int = 3) -> tuple:
    """Returns (content_str, external_reasoning_str).

    Keeping reasoning separate from content avoids the parse failure that occurred
    when we injected it as a <think> block and the content field was then empty.
    Native <think> blocks inside content are handled by _extract_thinking downstream.
    External reasoning (reasoning_content field from OpenRouter) is returned as the
    second element of the tuple and merged into RAGResult.thinking as a fallback.
    """
    from intelligence.nlq.llm import _is_quota_error, _parse_retry_delay
    client = make_openai_client()

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=QWEN_CODER_MODEL,
                messages=messages,
                max_tokens=LLM_MAX_TOKENS,
                temperature=temperature,
            )
            msg = response.choices[0].message
            raw = msg.content or ""
            
            # Robustly extract partial/reasoning content from various provider formats (OpenRouter, DeepSeek, etc.)
            reasoning = (
                getattr(msg, "reasoning_content", None) 
                or getattr(msg, "reasoning", None)
                or (msg.model_extra.get("reasoning_content") if msg.model_extra else None)
                or (msg.model_extra.get("reasoning") if msg.model_extra else None)
                or ""
            )
            
            logger.info("[LLM raw] finish_reason=%s len=%d reasoning_len=%d preview=%r",
                        response.choices[0].finish_reason, len(raw), len(reasoning), raw[:300])

            # Empty content (model returned nothing) — retry before giving up
            if not raw.strip() and attempt < max_retries - 1:
                logger.warning(
                    "[LLM] Empty response on attempt %d/%d — retrying.",
                    attempt + 1, max_retries,
                )
                continue

            return raw, reasoning
        except Exception as exc:
            if _is_quota_error(exc) and attempt < max_retries - 1:
                wait = _parse_retry_delay(exc, fallback=5.0 * (2 ** attempt))
                logger.warning(
                    "LLM quota error (attempt %d/%d) — retrying in %.1fs.",
                    attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
            else:
                raise


# ── Thinking extraction ────────────────────────────────────────────────────────

def _extract_thinking(raw: str) -> tuple:
    """
    Extract Qwen3's native <think>...</think> chain-of-thought block.
    Returns (thinking_text, remaining_output).
    Handles truncated output (no closing tag) by discarding the incomplete block.
    """
    # Full block present
    match = re.search(r"<think>(.*?)</think>", raw, re.DOTALL)
    if match:
        thinking = match.group(1).strip()
        rest = (raw[: match.start()] + raw[match.end():]).strip()
        return thinking, rest

    # Truncated: <think> opened but never closed — discard everything inside it
    open_match = re.search(r"<think>", raw, re.IGNORECASE)
    if open_match:
        logger.warning("[LLM] Truncated <think> block detected — output was cut off before </think>")
        # Anything after </think> doesn't exist; return empty SQL so self-healing kicks in
        return "", ""

    return "", raw


# ── Candidate scoring ─────────────────────────────────────────────────────────

def score_candidate(vr: "RAGResult", question: str) -> int:
    """
    Score a SQL candidate by structural alignment with the question.
    Used to rank N>1 candidates before execution — no DB call needed.
    """
    score = 0
    q   = question.lower()
    sql = vr.sql.lower()

    # Column/concept alignment
    col_hints = [
        ("channel",    "channel"),
        ("language",   "language"),
        ("user",       "user"),
        ("publish",    "publish"),
        ("duration",   "duration"),
        ("hours",      "duration"),
        ("monthly",    "month"),
        ("trend",      "month"),
        ("platform",   "dim_platform"),
        ("team",       "dim_team"),
        ("bot",        "is_bot"),
        ("human",      "is_bot"),
        ("short-form", "is_short_form"),
        ("short form", "is_short_form"),
        ("views",      "views"),
        ("seconds",    "duration_secs"),
        ("secs",       "duration_secs"),
    ]
    for kw, col in col_hints:
        if kw in q and col in sql:
            score += 2

    # Rate/percentage queries must have division
    if any(w in q for w in ["rate", "percentage", "ratio", "%"]):
        score += 3 if "/" in sql else -3

    # GROUP BY should match "by X" phrasing
    m = re.search(r"\bby\s+(\w+)", q)
    if m and m.group(1) in sql:
        score += 2

    # Prefer materialized views for aggregate queries (faster + correct)
    if any(w in q for w in ["monthly", "trend", "channel", "user", "compare"]):
        if "mv_" in sql:
            score += 2

    # Penalise suspiciously short SQL
    if len(vr.sql) > 60:
        score += 1

    return score


# ── Question augmentation ─────────────────────────────────────────────────────

def _augment_question(
    question: str,
    previous_sql: Optional[str],
    user_role: Optional[str],
    client_id: int,
) -> str:
    """Inject role context, client_id constraint, and follow-up SQL into the question."""
    augmented = question

    if previous_sql:
        augmented = (
            f"Previous SQL:\n{previous_sql}\n\n"
            f"New question (modify the previous SQL to answer this): {question}"
        )

    if user_role:
        from intelligence.nlq.role_config import get_role_config
        role_cfg = get_role_config(user_role)
        if role_cfg:
            augmented = (
                f"[Answering for: {role_cfg.display_name}]\n"
                f"Focus: {role_cfg.sql_focus}\n\n"
                f"Always filter client_id = {client_id} unless comparing clients.\n\n"
                f"{augmented}"
            )
            return augmented

    return f"Always filter client_id = {client_id} unless comparing clients.\n\n{augmented}"


# ── SQL generation ─────────────────────────────────────────────────────────────

def generate_sql_candidates(
    question: str,
    n: int = 1,
    previous_sql: Optional[str] = None,
    user_role: Optional[str] = None,
    client_id: int = 1,
    conn=None,
) -> List[RAGResult]:
    """
    Generate N SQL candidates using ChromaDB RAG.

    Key optimisations:
    - Live schema is fetched directly from the DB on every call (5-min cache)
      so the LLM always sees the real column names — no stale hardcoded DDL.
    - Question is embedded once and reused for all ChromaDB queries.
    - When N>1, LLM calls are made concurrently (ThreadPoolExecutor) at T=0.7
      for candidate diversity. N=1 uses the configured LLM_TEMPERATURE.
    """
    db = _get_chroma()

    augmented = _augment_question(question, previous_sql, user_role, client_id)

    # Live schema — always accurate, injected directly (not via ChromaDB similarity search)
    live_schema = fetch_live_schema(conn) if conn is not None else ""

    # Embed once — reuse for both collection queries
    embedding = db["ef"]([question])[0]

    sql_examples = _retrieve(db["sql"], embedding, n=3)
    doc_docs     = _retrieve(db["doc"], embedding, n=2)

    messages = _build_messages(augmented, sql_examples, live_schema, doc_docs)

    logger.info("RAG generating %d SQL candidate(s) for: '%s'", n, question)

    if n == 1:
        raw, reasoning = _call_llm(messages, temperature=LLM_TEMPERATURE)
        return [_parse_candidate(raw, reasoning)]

    # N > 1: generate concurrently with higher temperature for candidate diversity
    with ThreadPoolExecutor(max_workers=n) as executor:
        futures = [executor.submit(_call_llm, messages, 0.7) for _ in range(n)]
        pairs = [f.result() for f in futures]

    return [_parse_candidate(raw, reasoning) for raw, reasoning in pairs]


def generate_sql(
    question: str,
    previous_sql: Optional[str] = None,
    user_role: Optional[str] = None,
    client_id: int = 1,
    conn=None,
) -> RAGResult:
    """Convenience wrapper — single candidate generation."""
    return generate_sql_candidates(question, n=1, previous_sql=previous_sql,
                                   user_role=user_role, client_id=client_id, conn=conn)[0]


def _parse_candidate(raw: str, external_reasoning: str = "") -> RAGResult:
    """Parse a single raw LLM response into a RAGResult (thinking + SQL + chart meta).

    Defensively coerces every field — the LLM may produce lists, ints, or
    nested objects instead of the expected scalar strings.

    external_reasoning: chain-of-thought from reasoning_content (OpenRouter field).
    Used as fallback thinking when no native <think> block is present in content.
    """
    thinking, cleaned = _extract_thinking(raw)
    # Fall back to external reasoning_content if no native <think> block found
    if not thinking and external_reasoning:
        thinking = external_reasoning.strip()
    sql, chart_meta = _parse_output(cleaned)

    def _str(v):
        """Scalar coercion: list → first element, anything else → str. None stays None."""
        if v is None:
            return None
        if isinstance(v, list):
            return str(v[0]) if v else None
        if isinstance(v, str):
            return v or None
        return str(v)

    # answer_strategy must be a dict with a "type" key; discard anything malformed
    strategy = chart_meta.get("answer_strategy")
    if not isinstance(strategy, dict) or "type" not in strategy:
        strategy = None

    # Build routing from the LLM's top-level requires_sql / direct_answer fields.
    # requires_sql=False means the question doesn't need a DB query (greetings, off-topic, etc.)
    requires_sql = chart_meta.get("requires_sql")
    if requires_sql is False:
        routing = {
            "requires_sql": False,
            "direct_answer": _str(chart_meta.get("direct_answer")) or "I can only answer questions about your analytics data.",
        }
    else:
        routing = None  # normal SQL path

    return RAGResult(
        sql=sql,
        chart_type=_str(chart_meta.get("chart_type")),
        x_column=_str(chart_meta.get("x")),
        y_column=_str(chart_meta.get("y")),
        title=_str(chart_meta.get("title")),
        answer_strategy=strategy,
        routing=routing,
        thinking=thinking or None,
    )


def store_successful_query(question: str, sql: str) -> None:
    """Persist a verified Q→SQL pair into ChromaDB for future retrieval."""
    try:
        db = _get_chroma()
        doc = json.dumps({"question": question, "sql": sql}, ensure_ascii=False)
        _safe_add(db["sql"], doc, _det_id(doc, "-sql"))
        logger.info("Stored Q→SQL in RAG KB: '%s'", question[:80])
    except Exception as exc:
        logger.warning("Failed to store Q→SQL: %s", exc)


# ── Output parsing ─────────────────────────────────────────────────────────────

def _parse_output(raw: str) -> tuple:
    """Split LLM output into (sql_string, chart_meta_dict).

    Handles:
    - ```json ... ``` fenced block (primary)
    - bare { ... } JSON object as fallback (LLM omits fences)
    - ```sql ... ``` fenced SQL block
    - bare SELECT ... fallback
    """
    chart_meta = {}

    # ── 1. Extract fenced JSON block ─────────────────────────────────────
    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if json_match:
        try:
            cleaned = re.sub(r",\s*([}\]])", r"\1", json_match.group(1))
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                chart_meta = parsed
        except json.JSONDecodeError as exc:
            logger.warning("Could not parse fenced chart JSON: %s", exc)
        raw = raw[: json_match.start()] + raw[json_match.end():]
    else:
        # ── 2. Fallback: bare JSON object anywhere in the output ─────────
        bare_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if bare_match:
            try:
                cleaned = re.sub(r",\s*([}\]])", r"\1", bare_match.group(0))
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    chart_meta = parsed
                    raw = raw[: bare_match.start()] + raw[bare_match.end():]
            except json.JSONDecodeError:
                pass  # not valid JSON, ignore

    # ── 3. Fenced SQL block ───────────────────────────────────────────────
    sql_match = re.search(r"```sql\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(1).strip(), chart_meta

    # ── 4. Bare SELECT fallback ───────────────────────────────────────────
    sql = re.sub(r"```\w*\s*", "", raw)
    sql = re.sub(r"```\s*", "", sql)
    select_match = re.search(r"((?:WITH|SELECT)\b.*)", sql, re.DOTALL | re.IGNORECASE)
    sql = select_match.group(1).strip() if select_match else sql.strip()

    return sql, chart_meta
