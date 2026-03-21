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
_KB_VERSION = "RAG_KB_V3_LIVE_SCHEMA"


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
- All objects are in the 'data' schema — always prefix: data.fact_created_videos, data.mv_monthly_kpis, etc.
- client_id isolation: always filter WHERE client_id = N UNLESS the question explicitly compares clients.
- fact_created_videos: published_flag is BOOLEAN — use published_flag = TRUE.
- fact_created_videos: billable is TEXT — use billable = 'Yes' or billable = 'No'.
- fact_created_videos: the timestamp column is uploaded_at (NOT created_at).
- shortened_filtered_data: published and billable are TEXT ('Yes'/'No'), channel is TEXT (not channel_id).
- Prefer materialized views (mv_monthly_kpis, mv_channel_health, mv_user_performance) over fact_created_videos for any aggregate — they are pre-computed and faster.
- For raw row access or billable/input_type breakdowns, use fact_created_videos (has all FK columns).
- Publish rate formula: ROUND(published_count::numeric / NULLIF(created_count, 0) * 100, 2)
- Month display: TO_CHAR(month, 'Mon YYYY') for human-readable x-axis labels."""
    _safe_add(db["doc"], core_doc, _det_id(core_doc, "-doc"))

    time_series_doc = """TIME-SERIES and TREND queries (monthly, over time, growth trends):
Use data.mv_monthly_kpis — pre-computed month, created_count, published_count, publish_rate_pct.
Always GROUP BY month and ORDER BY month ASC.
For "last N months": WHERE month >= DATE_TRUNC('month', NOW() - INTERVAL 'N-1 months')
Example pattern for monthly publish rate:
  SELECT TO_CHAR(month, 'Mon YYYY') AS month, SUM(publish_rate_pct) / COUNT(*) AS avg_rate
  FROM data.mv_monthly_kpis WHERE client_id = 1
  GROUP BY month ORDER BY month"""
    _safe_add(db["doc"], time_series_doc, _det_id(time_series_doc, "-doc"))

    ranking_doc = """RANKING and TOP-N queries (top users, best channels, highest/lowest publish rate):
Use mv_user_performance for user rankings, mv_channel_health for channel rankings.
Always include ORDER BY <metric> DESC LIMIT N.
For publish rate rankings, ORDER BY publish_rate_pct DESC.
For output volume rankings, ORDER BY created_count DESC or total_created DESC."""
    _safe_add(db["doc"], ranking_doc, _det_id(ranking_doc, "-doc"))

    multidim_doc = """MULTI-DIMENSION and BREAKDOWN queries (channel by language, user by channel, cross-tab):
Join fact_created_videos with the relevant dimension tables.
GROUP BY both dimensions. Always include:
  COUNT(*) AS created_count,
  COUNT(CASE WHEN published_flag THEN 1 END) AS published_count,
  ROUND(COUNT(CASE WHEN published_flag THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 2) AS publish_rate_pct
Example: breakdown by channel and language →
  JOIN data.dim_channel dc ON f.channel_id = dc.channel_id
  JOIN data.dim_language dl ON f.language_id = dl.language_id
  GROUP BY dc.channel_name, dl.language_name"""
    _safe_add(db["doc"], multidim_doc, _det_id(multidim_doc, "-doc"))

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
    "Generate valid PostgreSQL queries based only on the schema and business rules provided. "
    "If a similar question was answered before, follow the same SQL pattern."
)

_SQL_SUFFIX = """

After writing the SQL, output a JSON block fenced with ```json ... ``` containing:
{
  "requires_sql": true,
  "chart_type": "line|bar|horizontal_bar|pie|scatter|radar|stacked_bar|table",
  "x": "<exact column alias from SELECT list — entity/category column>",
  "y": "<exact column alias from SELECT list — primary numeric column>",
  "title": "<short descriptive chart title>",
  "answer_strategy": {
    "type": "time_series_trend|top_n_ranked|distribution|single_aggregate|detail_sample",
    "focus": ["<aspect1>", "<aspect2>"]
  }
}

Exception — if the question is a greeting, small talk, or completely unrelated to analytics:
do NOT write SQL. Output only this JSON:
{
  "requires_sql": false,
  "direct_answer": "<short friendly plain-text response>"
}

Chart type rules:
- line           → time series / trends over months or dates
- bar            → comparisons across a small number of categories (≤ 8)
- horizontal_bar → comparisons across many categories (> 8) or long category names
- pie            → distributions / proportions (≤ 10 categories, 1 numeric column only)
- scatter        → correlation between two numeric columns
- radar          → compare one entity across 3+ metrics, or compare 2-5 entities across the same metrics
- stacked_bar    → multi-series category comparisons (use group_by field)
- table          → row-level detail, many columns, or no clear chart mapping

Answer strategy rules:
- time_series_trend → over-time trends. focus: peak, trough, direction, change_pct
- top_n_ranked      → ranking questions. focus: winner, spread, total
- distribution      → share/proportion. focus: dominant_slice, total
- single_aggregate  → one-row COUNT/SUM. focus: exact_value
- detail_sample     → row-level. focus: top_rows, row_count"""


def _build_messages(question: str, sql_examples: list, live_schema: str, doc_docs: list) -> list:
    """
    Build the LLM message list:
      system  = base prompt + live schema (always fresh) + business rules + response guidelines
      user/assistant pairs = retrieved Q→SQL few-shot examples
      final user = augmented question + output format instructions
    """
    system = _SYSTEM_BASE

    if live_schema:
        system += "\n\n=== Schema ===\n" + live_schema

    if doc_docs:
        system += "\n\n=== Business Rules ===\n" + "\n\n".join(doc_docs)

    system += (
        "\n\n=== Response Guidelines ===\n"
        "1. Generate valid SQL without explanations.\n"
        "2. Use only the tables and views from the schema above.\n"
        "3. Ensure the SQL is PostgreSQL-compliant and free of syntax errors.\n"
        "4. If context is insufficient, return SELECT that produces 0 rows (WHERE 1=0).\n"
    )

    messages = [{"role": "system", "content": system}]

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

def _call_llm(messages: list, temperature: float = LLM_TEMPERATURE, max_retries: int = 3) -> str:
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


# ── Thinking extraction ────────────────────────────────────────────────────────

def _extract_thinking(raw: str) -> tuple:
    """
    Extract Qwen3's native <think>...</think> chain-of-thought block.
    Returns (thinking_text, remaining_output).
    If no thinking block is present, returns ("", raw).
    """
    match = re.search(r"<think>(.*?)</think>", raw, re.DOTALL)
    if match:
        thinking = match.group(1).strip()
        rest = (raw[: match.start()] + raw[match.end():]).strip()
        return thinking, rest
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
        ("channel",  "channel"),
        ("language", "language"),
        ("user",     "user"),
        ("publish",  "publish"),
        ("duration", "duration"),
        ("hours",    "duration"),
        ("monthly",  "month"),
        ("trend",    "month"),
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
        raw = _call_llm(messages, temperature=LLM_TEMPERATURE)
        return [_parse_candidate(raw)]

    # N > 1: generate concurrently with higher temperature for candidate diversity
    with ThreadPoolExecutor(max_workers=n) as executor:
        futures = [executor.submit(_call_llm, messages, 0.7) for _ in range(n)]
        raws = [f.result() for f in futures]

    return [_parse_candidate(raw) for raw in raws]


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


def _parse_candidate(raw: str) -> RAGResult:
    """Parse a single raw LLM response into a RAGResult (thinking + SQL + chart meta).

    Defensively coerces every field — the LLM may produce lists, ints, or
    nested objects instead of the expected scalar strings.
    """
    thinking, cleaned = _extract_thinking(raw)
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
            parsed = json.loads(json_match.group(1))
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
                parsed = json.loads(bare_match.group(0))
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
