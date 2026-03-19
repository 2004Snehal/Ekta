"""
Vanna RAG service — Text-to-SQL with a self-improving ChromaDB knowledge base.

On startup: trains Vanna with the live schema + business documentation + example Q→SQL pairs.
Training is skipped if ChromaDB already has entries (persists across restarts).
Per query: stores successful (question → SQL) pairs back into ChromaDB.
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend_config import VANNA_CHROMA_PATH
from llm_config import QWEN_CODER_MODEL, LLM_API_KEY, LLM_BASE_URL

from intelligence.nlq.context import fetch_live_schema

logger = logging.getLogger("nlq.vanna")


@dataclass
class VannaResult:
    sql: str
    chart_type: Optional[str] = None
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    title: Optional[str] = None
    answer_strategy: Optional[dict] = None


# ── Singleton ─────────────────────────────────────────────────────────────────

_vanna_instance = None


def _build_vanna():
    from vanna.legacy.openai.openai_chat import OpenAI_Chat
    from vanna.legacy.chromadb.chromadb_vector import ChromaDB_VectorStore
    from openai import OpenAI as OpenAIClient

    class VannaOpenRouter(ChromaDB_VectorStore, OpenAI_Chat):
        def __init__(self, config=None):
            ChromaDB_VectorStore.__init__(self, config=config)
            OpenAI_Chat.__init__(self, config=config)
            self.client = OpenAIClient(
                api_key=config.get("api_key"),
                base_url=config.get("base_url"),
            )

        def extract_sql(self, llm_response: str) -> str:
            # Return the full LLM response so _parse_vanna_output can
            # extract both the SQL and our JSON metadata block.
            return llm_response

    vn = VannaOpenRouter(config={
        "api_key": LLM_API_KEY,
        "base_url": LLM_BASE_URL,
        "model": QWEN_CODER_MODEL,
        "path": VANNA_CHROMA_PATH,
    })
    logger.info("Vanna initialised with OpenRouter backend (%s).", QWEN_CODER_MODEL)
    return vn


def get_vanna():
    global _vanna_instance
    if _vanna_instance is None:
        _vanna_instance = _build_vanna()
    return _vanna_instance


# ── Training ──────────────────────────────────────────────────────────────────

def train_vanna_with_schema(conn) -> None:
    """
    Feed the live DB schema into Vanna's knowledge base.
    Skipped if ChromaDB already has training data (persists to disk).
    """
    vn = get_vanna()

    existing = vn.get_training_data()
    if existing is not None and len(existing) > 0:
        logger.info("Vanna already has %d training entries — skipping.", len(existing))
        return

    logger.info("Training Vanna with live schema…")

    # ── 1. Live schema as documentation ───────────────────────────────────────
    schema_doc = fetch_live_schema(conn)
    vn.train(documentation=schema_doc)

    # ── 2. Business semantics documentation ───────────────────────────────────
    vn.train(documentation="""
Business rules for Frammer AI analytics queries:

- "published" means published_flag = TRUE (boolean column on fact_created_videos).
- "publish rate" = published_count / created_count * 100 (available in mv_monthly_kpis as publish_rate_pct).
- "outputs" or "created videos" = COUNT(*) from fact_created_videos OR SUM(created_count) from mv_monthly_kpis.
- "uploads" or "source videos" = COUNT(DISTINCT video_id) from fact_created_videos.
- Always filter by client_id unless the question explicitly asks to compare clients.
- Prefer materialized views for aggregate queries:
    mv_monthly_kpis    → time-series / monthly trends (has month DATE column, created_count, published_count, publish_rate_pct)
    mv_channel_health  → per-channel comparisons (total_created, total_published, publish_rate_pct, active_users)
    mv_user_performance → per-user stats (created_count, published_count, publish_rate_pct)
- Format month column: TO_CHAR(month, 'Mon YYYY') for human-readable x-axis labels.
- All tables and views live in the 'data' schema — always prefix with data. (e.g. data.fact_created_videos).
""")

    # ── 3. Example Q→SQL pairs ────────────────────────────────────────────────
    examples = [
        (
            "how many videos have been published",
            "SELECT COUNT(*) AS published_count FROM data.fact_created_videos WHERE published_flag = TRUE;"
        ),
        (
            "show created vs published videos by language",
            """SELECT
  dl.language_name AS language,
  COUNT(*) AS created_count,
  COUNT(CASE WHEN f.published_flag THEN 1 END) AS published_count
FROM data.fact_created_videos f
JOIN data.dim_language dl ON f.language_id = dl.language_id
WHERE f.client_id = 1
GROUP BY dl.language_name
ORDER BY created_count DESC;"""
        ),
        (
            "which channel has the highest publish rate",
            """SELECT
  dc.channel_name AS channel,
  SUM(mk.created_count) AS total_created,
  SUM(mk.published_count) AS total_published,
  ROUND(AVG(mk.publish_rate_pct), 2) AS publish_rate_pct
FROM data.mv_monthly_kpis mk
JOIN data.dim_channel dc ON mk.channel_id = dc.channel_id
WHERE mk.client_id = 1
GROUP BY dc.channel_name
ORDER BY publish_rate_pct DESC
LIMIT 1;"""
        ),
        (
            "top 10 users by output count",
            """SELECT
  du.user_name,
  up.created_count,
  up.published_count,
  ROUND(up.publish_rate_pct, 2) AS publish_rate_pct
FROM data.mv_user_performance up
JOIN data.dim_user du ON up.user_id = du.user_id
WHERE up.client_id = 1
ORDER BY up.created_count DESC
LIMIT 10;"""
        ),
        (
            "monthly trend of published videos over the last 6 months",
            """SELECT
  TO_CHAR(month, 'Mon YYYY') AS month,
  SUM(published_count) AS published_count
FROM data.mv_monthly_kpis
WHERE client_id = 1
  AND month >= DATE_TRUNC('month', NOW() - INTERVAL '5 months')
GROUP BY month
ORDER BY month;"""
        ),
        (
            "compare publish rate across channels",
            """SELECT
  dc.channel_name AS channel,
  SUM(ch.total_created) AS total_created,
  SUM(ch.total_published) AS total_published,
  ROUND(ch.publish_rate_pct, 2) AS publish_rate_pct
FROM data.mv_channel_health ch
JOIN data.dim_channel dc ON ch.channel_id = dc.channel_id
WHERE ch.client_id = 1
GROUP BY dc.channel_name, ch.publish_rate_pct
ORDER BY publish_rate_pct DESC;"""
        ),
    ]

    for question, sql in examples:
        vn.train(question=question, sql=sql)

    logger.info("Vanna training complete (%d examples).", len(examples))


# ── Query generation ──────────────────────────────────────────────────────────

_QUERY_OUTPUT_SUFFIX = """

After writing the SQL, also output a JSON block fenced with ```json ... ``` containing:
{
  "chart_type": "line|bar|pie|table|stacked_bar",
  "x": "<exact column alias from SELECT list for x-axis>",
  "y": "<exact column alias from SELECT list for y-axis>",
  "title": "<short descriptive chart title>",
  "description": "<one sentence describing what the chart shows>",
  "answer_strategy": {
    "type": "time_series_trend|top_n_ranked|distribution|single_aggregate|detail_sample",
    "focus": ["<aspect1>", "<aspect2>"]
  }
}

Chart type rules:
- line        → time series / trends over months
- bar         → comparisons across categories (channels, users, types)
- pie         → distributions / proportions (use only when ≤ 10 categories)
- stacked_bar → multi-series category comparisons
- table       → detailed row-level data or queries with many columns

Answer strategy rules:
- time_series_trend  → any over-time trend (line chart). focus: peak, trough, direction, change_pct
- top_n_ranked       → ranking questions (bar chart, "which X has most/least"). focus: winner, spread, total
- distribution       → share/proportion questions (pie, stacked_bar). focus: dominant_slice, total
- single_aggregate   → COUNT/SUM returning one row. focus: exact_value
- detail_sample      → row-level table queries. focus: top_rows, row_count
"""


def _with_retry(vn, question: str, max_retries: int = 3) -> str:
    """Call vn.generate_sql with automatic quota-aware retry logic."""
    from intelligence.nlq.llm import _is_quota_error, _parse_retry_delay

    for attempt in range(max_retries):
        try:
            return vn.generate_sql(question)
        except Exception as exc:
            if _is_quota_error(exc) and attempt < max_retries - 1:
                wait = _parse_retry_delay(exc, fallback=5.0 * (2 ** attempt))
                logger.warning("Vanna quota error (attempt %d/%d) — retrying in %.1fs.", attempt + 1, max_retries, wait)
                time.sleep(wait)
            else:
                raise


def generate_sql(
    question: str,
    previous_sql: Optional[str] = None,
    user_role: Optional[str] = None,
    client_id: int = 1,
) -> VannaResult:
    """
    Convert a natural language question to SQL using Vanna RAG.
    Returns VannaResult with sql + chart metadata + answer_strategy.
    """
    vn = get_vanna()

    augmented = question

    # Inject previous SQL for follow-up questions
    if previous_sql:
        augmented = (
            f"Previous SQL:\n{previous_sql}\n\n"
            f"New question (modify the previous SQL to answer this): {question}"
        )

    # Inject role-specific SQL focus
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
    else:
        augmented = f"Always filter client_id = {client_id} unless comparing clients.\n\n{augmented}"

    full_question = augmented + _QUERY_OUTPUT_SUFFIX

    logger.info("Vanna generating SQL for: '%s'", question)
    raw = _with_retry(vn, full_question)
    logger.info("Raw Vanna output:\n%s", raw)

    sql, chart_meta = _parse_vanna_output(raw)
    return VannaResult(
        sql=sql,
        chart_type=chart_meta.get("chart_type"),
        x_column=chart_meta.get("x"),
        y_column=chart_meta.get("y"),
        title=chart_meta.get("title"),
        answer_strategy=chart_meta.get("answer_strategy"),
    )


def store_successful_query(question: str, sql: str) -> None:
    """Persist a verified (question → SQL) pair into Vanna's knowledge base."""
    try:
        vn = get_vanna()
        vn.train(question=question, sql=sql)
        logger.info("Stored Q→SQL pair in Vanna KB: '%s'", question[:80])
    except Exception as exc:
        logger.warning("Failed to store Q→SQL in Vanna: %s", exc)


# ── Parsing ───────────────────────────────────────────────────────────────────

def _parse_vanna_output(raw: str) -> tuple:
    """Split Vanna's raw output into (sql_string, chart_meta_dict)."""
    chart_meta = {}

    # Extract JSON block first and remove it from the string
    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if json_match:
        try:
            chart_meta = json.loads(json_match.group(1))
        except json.JSONDecodeError as exc:
            logger.warning("Could not parse chart JSON: %s", exc)
        raw = raw[: json_match.start()] + raw[json_match.end():]

    # Try to extract SQL from inside ```sql ... ``` fence (ignores any preamble text)
    sql_match = re.search(r"```sql\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    if sql_match:
        sql = sql_match.group(1).strip()
    else:
        # No fence — strip any remaining backtick blocks and take what's left
        sql = re.sub(r"```\w*\s*", "", raw)
        sql = re.sub(r"```\s*", "", sql)
        # If model added preamble text, try to find the SELECT statement
        select_match = re.search(r"(SELECT\b.*)", sql, re.DOTALL | re.IGNORECASE)
        sql = select_match.group(1).strip() if select_match else sql.strip()

    return sql, chart_meta
