"""
RAG service — Text-to-SQL using ChromaDB directly (no Vanna dependency).

On startup: trains ChromaDB with live schema + business rules + example Q→SQL pairs.
Training is skipped if ChromaDB already has entries (persists across restarts).
Per query: embeds the question once → queries all 3 collections with the same
           vector (latency win) → builds prompt → calls LLM.
On success: stores the verified Q→SQL pair back into ChromaDB.
"""

import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend_config import CHROMA_PATH
from llm_config import QWEN_CODER_MODEL, make_openai_client, LLM_MAX_TOKENS, LLM_TEMPERATURE
from intelligence.nlq.context import fetch_live_schema

logger = logging.getLogger("nlq.rag")


@dataclass
class RAGResult:
    sql: str
    chart_type: Optional[str] = None
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    title: Optional[str] = None
    answer_strategy: Optional[dict] = None


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
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        _chroma = {
            "ef":  ef,
            "sql": client.get_or_create_collection(name="sql",           embedding_function=ef),
            "ddl": client.get_or_create_collection(name="ddl",           embedding_function=ef),
            "doc": client.get_or_create_collection(name="documentation", embedding_function=ef),
        }
        logger.info("ChromaDB initialised at %s.", CHROMA_PATH)
    return _chroma


# ── ID helpers ─────────────────────────────────────────────────────────────────

def _det_id(text: str, suffix: str) -> str:
    """Deterministic UUID from content hash — prevents duplicate entries on restart."""
    return str(uuid.UUID(hashlib.md5(text.encode()).hexdigest())) + suffix


def _safe_add(collection, doc: str, uid: str) -> None:
    """Add a document; silently skip if already present (duplicate deterministic ID)."""
    try:
        collection.add(documents=doc, ids=uid)
    except Exception:
        pass


# ── Training ───────────────────────────────────────────────────────────────────

def train_with_schema(conn) -> None:
    """
    Populate ChromaDB on first run with schema, business rules, and Q→SQL examples.
    Skipped entirely if SQL collection already has entries.
    """
    db = _get_chroma()

    if db["sql"].count() > 0:
        logger.info("RAG KB already trained (%d SQL entries) — skipping.", db["sql"].count())
        return

    logger.info("Training RAG KB…")

    # 1. Live schema → DDL collection
    schema_doc = fetch_live_schema(conn)
    _safe_add(db["ddl"], schema_doc, _det_id(schema_doc, "-ddl"))

    # 2. Business rules → documentation collection
    business_rules = """Business rules for Frammer AI analytics queries:

- "published" means published_flag = TRUE (boolean column on fact_created_videos).
- "publish rate" = published_count / created_count * 100 (available in mv_monthly_kpis as publish_rate_pct).
- "outputs" or "created videos" = COUNT(*) from fact_created_videos OR SUM(created_count) from mv_monthly_kpis.
- "uploads" or "source videos" = COUNT(DISTINCT video_id) from fact_created_videos.
- Always filter by client_id unless the question explicitly asks to compare clients.
- Prefer materialized views for aggregate queries:
    mv_monthly_kpis     → time-series / monthly trends (month DATE, created_count, published_count, publish_rate_pct)
    mv_channel_health   → per-channel comparisons (total_created, total_published, publish_rate_pct, active_users)
    mv_user_performance → per-user stats (created_count, published_count, publish_rate_pct)
- Format month column: TO_CHAR(month, 'Mon YYYY') for human-readable x-axis labels.
- All tables and views live in the 'data' schema — always prefix with data. (e.g. data.fact_created_videos)."""
    _safe_add(db["doc"], business_rules, _det_id(business_rules, "-doc"))

    # 3. Q→SQL examples → SQL collection
    examples = [
        (
            "how many videos have been published",
            "SELECT COUNT(*) AS published_count FROM data.fact_created_videos WHERE published_flag = TRUE;",
        ),
        (
            "show created vs published videos by language",
            """SELECT dl.language_name AS language, COUNT(*) AS created_count,
  COUNT(CASE WHEN f.published_flag THEN 1 END) AS published_count
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
GROUP BY dc.channel_name ORDER BY publish_rate_pct DESC LIMIT 1;""",
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
    ]

    for question, sql in examples:
        doc = json.dumps({"question": question, "sql": sql}, ensure_ascii=False)
        _safe_add(db["sql"], doc, _det_id(doc, "-sql"))

    logger.info("RAG training complete (%d SQL examples).", len(examples))


# ── Retrieval ─────────────────────────────────────────────────────────────────

def _retrieve(collection, embedding: list, n: int) -> list:
    """Query a collection by pre-computed embedding. Returns raw document strings."""
    count = collection.count()
    if count == 0:
        return []
    result = collection.query(query_embeddings=[embedding], n_results=min(n, count))
    return result.get("documents", [[]])[0]


# ── Prompt building ────────────────────────────────────────────────────────────

_SYSTEM_BASE = (
    "You are a PostgreSQL expert for the Frammer AI analytics platform. "
    "Generate valid PostgreSQL queries based only on the schema and business rules provided. "
    "If a similar question was answered before, follow the same SQL pattern."
)

_SQL_SUFFIX = """

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
- time_series_trend  → any over-time trend. focus: peak, trough, direction, change_pct
- top_n_ranked       → ranking questions. focus: winner, spread, total
- distribution       → share/proportion questions. focus: dominant_slice, total
- single_aggregate   → COUNT/SUM returning one row. focus: exact_value
- detail_sample      → row-level table queries. focus: top_rows, row_count"""


def _build_messages(question: str, sql_examples: list, ddl_docs: list, doc_docs: list) -> list:
    """
    Build the LLM message list:
      system  = base + schema + business rules + response guidelines
      user/assistant pairs = retrieved Q→SQL few-shot examples
      final user = the actual question + output format instructions
    """
    system = _SYSTEM_BASE

    if ddl_docs:
        system += "\n\n=== Schema ===\n" + "\n\n".join(ddl_docs)

    if doc_docs:
        system += "\n\n=== Business Rules ===\n" + "\n\n".join(doc_docs)

    system += (
        "\n\n=== Response Guidelines ===\n"
        "1. Generate a valid SQL query without explanations.\n"
        "2. Use the most relevant table(s) from the schema above.\n"
        "3. Ensure the SQL is PostgreSQL-compliant and free of syntax errors.\n"
        "4. If context is insufficient, return a SELECT that produces 0 rows (WHERE 1=0).\n"
    )

    messages = [{"role": "system", "content": system}]

    # Inject retrieved Q→SQL pairs as few-shot examples
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

def _call_llm(messages: list, max_retries: int = 3) -> str:
    from intelligence.nlq.llm import _is_quota_error, _parse_retry_delay
    client = make_openai_client()

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=QWEN_CODER_MODEL,
                messages=messages,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
            )
            return response.choices[0].message.content
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


# ── SQL generation ─────────────────────────────────────────────────────────────

def generate_sql(
    question: str,
    previous_sql: Optional[str] = None,
    user_role: Optional[str] = None,
    client_id: int = 1,
) -> RAGResult:
    """
    Convert a natural language question to SQL using ChromaDB RAG.

    Key optimisation: the question is embedded once and the same vector is
    reused for all three ChromaDB queries (sql / ddl / doc), avoiding two
    redundant embedding model calls per request.
    """
    db = _get_chroma()

    # Augment question with context
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
    else:
        augmented = f"Always filter client_id = {client_id} unless comparing clients.\n\n{augmented}"

    # Embed once — reuse for all 3 collection queries
    embedding = db["ef"]([question])[0]

    sql_examples = _retrieve(db["sql"], embedding, n=5)
    ddl_docs     = _retrieve(db["ddl"], embedding, n=3)
    doc_docs     = _retrieve(db["doc"], embedding, n=3)

    messages = _build_messages(augmented, sql_examples, ddl_docs, doc_docs)

    logger.info("RAG generating SQL for: '%s'", question)
    raw = _call_llm(messages)
    logger.info("Raw LLM output:\n%s", raw)

    sql, chart_meta = _parse_output(raw)
    return RAGResult(
        sql=sql,
        chart_type=chart_meta.get("chart_type"),
        x_column=chart_meta.get("x"),
        y_column=chart_meta.get("y"),
        title=chart_meta.get("title"),
        answer_strategy=chart_meta.get("answer_strategy"),
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
    """Split LLM output into (sql_string, chart_meta_dict)."""
    chart_meta = {}

    # Extract and remove the JSON block first
    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if json_match:
        try:
            chart_meta = json.loads(json_match.group(1))
        except json.JSONDecodeError as exc:
            logger.warning("Could not parse chart JSON: %s", exc)
        raw = raw[: json_match.start()] + raw[json_match.end():]

    # Try fenced SQL block
    sql_match = re.search(r"```sql\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(1).strip(), chart_meta

    # Fallback: strip any remaining fences and find the SELECT
    sql = re.sub(r"```\w*\s*", "", raw)
    sql = re.sub(r"```\s*", "", sql)
    select_match = re.search(r"(SELECT\b.*)", sql, re.DOTALL | re.IGNORECASE)
    sql = select_match.group(1).strip() if select_match else sql.strip()

    return sql, chart_meta
