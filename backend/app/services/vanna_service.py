"""
Vanna RAG service — Text-to-SQL with internal knowledge base.

Vanna.AI uses a ChromaDB vector store internally (no pgvector needed).
On startup it receives the full DB schema as context.
Each successful query pair (question → sql) is stored back into Vanna
so retrieval improves over time.

The service also asks Vanna / the LLM to infer the best chart type for
the query so the frontend can render immediately.
"""

import json
import re
import time
from dataclasses import dataclass
from typing import Optional

from app.config.settings import get_settings
from app.db.schema_loader import load_schema
from app.utils.logger import get_logger

logger = get_logger("nlq.vanna")


@dataclass
class VannaResult:
    sql: str
    chart_type: Optional[str] = None
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    title: Optional[str] = None


# ── Vanna singleton ───────────────────────────────────────────────────────────

_vanna_instance = None


def _build_vanna():
    """
    Build and return a Vanna instance wired to the configured LLM provider.
    Vanna supports pluggable LLMs; we use the OpenAI or Gemini adapters.
    """
    settings = get_settings()
    provider = settings.llm_provider.lower()

    if provider == "openai":
        from vanna.legacy.openai.openai_chat import OpenAI_Chat
        from vanna.legacy.chromadb.chromadb_vector import ChromaDB_VectorStore

        class VannaOpenAI(ChromaDB_VectorStore, OpenAI_Chat):
            pass

        vn = VannaOpenAI(
            config={
                "api_key": settings.openai_api_key,
                "model": settings.openai_model,
                "path": settings.vanna_chroma_path,
            }
        )
        logger.info("Vanna initialised with OpenAI backend.")
        return vn

    elif provider == "gemini":
        # Vanna has a Gemini adapter; fall back to a custom wrapper if needed
        try:
            from vanna.legacy.google.gemini_chat import GoogleGeminiChat
            from vanna.legacy.chromadb.chromadb_vector import ChromaDB_VectorStore

            class VannaGemini(ChromaDB_VectorStore, GoogleGeminiChat):
                def __init__(self, config=None):
                    ChromaDB_VectorStore.__init__(self, config=config)
                    GoogleGeminiChat.__init__(self, config=config)

            vn = VannaGemini(
                config={
                    "api_key": settings.gemini_api_key,
                    "model_name": settings.gemini_model,
                    "path": settings.vanna_chroma_path,
                }
            )
            logger.info("Vanna initialised with Gemini backend.")
            return vn
        except ImportError:
            logger.warning(
                "vanna.google not available — falling back to OpenAI-compat wrapper for Gemini."
            )
            raise RuntimeError(
                "Install 'vanna[google]' or switch LLM_PROVIDER to 'openai'."
            )

    elif provider == "groq":
        # Groq is OpenAI-API-compatible; reuse OpenAI_Chat but override the
        # client so it points at Groq's base URL (OpenAI_Chat doesn't use
        # base_url from config, so self.client would never be set otherwise).
        from openai import OpenAI
        from vanna.legacy.openai.openai_chat import OpenAI_Chat
        from vanna.legacy.chromadb.chromadb_vector import ChromaDB_VectorStore

        class VannaGroq(ChromaDB_VectorStore, OpenAI_Chat):
            def __init__(self, config=None):
                ChromaDB_VectorStore.__init__(self, config=config)
                OpenAI_Chat.__init__(self, config=config)
                # Override the auto-created client with Groq's endpoint
                self.client = OpenAI(
                    api_key=config.get("api_key"),
                    base_url=config.get("base_url", "https://api.groq.com/openai/v1"),
                )

        vn = VannaGroq(
            config={
                "api_key": settings.groq_api_key,
                "model": settings.groq_model,
                "base_url": "https://api.groq.com/openai/v1",
                "path": settings.vanna_chroma_path,
            }
        )
        logger.info("Vanna initialised with Groq backend (model=%s).", settings.groq_model)
        return vn

    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def get_vanna():
    """Return the cached Vanna singleton, building it on first call."""
    global _vanna_instance
    if _vanna_instance is None:
        _vanna_instance = _build_vanna()
    return _vanna_instance


# ── Schema injection ──────────────────────────────────────────────────────────

def train_vanna_with_schema() -> None:
    """
    Feed the PostgreSQL schema into Vanna's knowledge base.
    Skipped if the ChromaDB collection already contains training data.
    """
    vn = get_vanna()

    # Skip if already trained — ChromaDB persists to disk, no need to re-add on every restart
    existing = vn.get_training_data()
    if existing is not None and len(existing) > 0:
        logger.info("Vanna already has %d training entries — skipping schema training.", len(existing))
        return

    schema_ddl = load_schema()
    logger.info("Training Vanna with schema (%d chars)…", len(schema_ddl))

    blocks = [b.strip() for b in schema_ddl.split(";") if b.strip()]
    for block in blocks:
        if block:
            vn.train(ddl=block + ";")

    logger.info("Vanna schema training complete (%d DDL blocks).", len(blocks))

    # ── Documentation: explain the key table and column semantics ─────────────
    vn.train(documentation="""
The PRIMARY table for all video analytics queries is: data.shortened_filtered_data

Key columns in data.shortened_filtered_data:
- video_id: unique identifier for a video
- published: TEXT — indicates whether a video was published. Use: LOWER(published) = 'yes'
- language: TEXT — language name (e.g. 'English', 'Spanish'). No join needed.
- channel: TEXT — channel name. No join needed.
- team_name: TEXT — team that produced the video
- type: TEXT — input/content type
- uploaded_by: TEXT — username who uploaded
- output_type: TEXT — type of output
- published_platform: TEXT — platform where published
- uploaded_at: TEXT — upload timestamp
- uploaded_hours, cumulative_uploaded_hours: numeric duration metrics
- client_id: bigint — client identifier

ALWAYS query data.shortened_filtered_data directly for video counts, publish rates, language breakdowns, channel breakdowns, user stats.
DO NOT reference fact_created_videos, fact_videos, fact_outputs — these tables do not exist.
For dimension lookups (language names, channel names) use the columns directly in data.shortened_filtered_data — no joins required.
""")

    # ── Example Q→SQL pairs ───────────────────────────────────────────────────
    examples = [
        (
            "how many videos have been published",
            "SELECT COUNT(*) AS published_count FROM data.shortened_filtered_data WHERE LOWER(published) = 'yes';"
        ),
        (
            "show me created vs published videos by language",
            """SELECT
  language,
  COUNT(*) AS created_videos_count,
  COUNT(CASE WHEN LOWER(published) = 'yes' THEN 1 END) AS published_videos_count
FROM data.shortened_filtered_data
GROUP BY language
ORDER BY language;"""
        ),
        (
            "which channel has the highest publish rate",
            """SELECT
  channel,
  COUNT(*) AS total_videos,
  COUNT(CASE WHEN LOWER(published) = 'yes' THEN 1 END) AS published_videos,
  ROUND(100.0 * COUNT(CASE WHEN LOWER(published) = 'yes' THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS publish_rate_pct
FROM data.shortened_filtered_data
GROUP BY channel
ORDER BY publish_rate_pct DESC
LIMIT 1;"""
        ),
        (
            "top 10 users by output count",
            """SELECT
  uploaded_by AS user_name,
  COUNT(*) AS output_count
FROM data.shortened_filtered_data
GROUP BY uploaded_by
ORDER BY output_count DESC
LIMIT 10;"""
        ),
        (
            "monthly trend of uploads over the last 6 months",
            """SELECT
  DATE_TRUNC('month', uploaded_at::timestamp) AS upload_month,
  COUNT(*) AS total_uploads
FROM data.shortened_filtered_data
WHERE uploaded_at::timestamp >= DATE_TRUNC('month', NOW() - INTERVAL '5 months')
GROUP BY upload_month
ORDER BY upload_month;"""
        ),
        (
            "compare publish rate across languages",
            """SELECT
  language,
  COUNT(*) AS total_videos,
  COUNT(CASE WHEN LOWER(published) = 'yes' THEN 1 END) AS published_videos,
  ROUND(100.0 * COUNT(CASE WHEN LOWER(published) = 'yes' THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS publish_rate_pct
FROM data.shortened_filtered_data
GROUP BY language
ORDER BY publish_rate_pct DESC;"""
        ),
    ]

    for question, sql in examples:
        vn.train(question=question, sql=sql)

    logger.info("Vanna example SQL training complete (%d examples).", len(examples))


# ── Retry helper ──────────────────────────────────────────────────────────────

def _vanna_generate_with_retry(vn, question: str, max_retries: int = 3) -> str:
    """Call vn.generate_sql() with retries on quota/rate-limit errors, using the delay suggested by the API."""
    import re
    for attempt in range(max_retries):
        try:
            return vn.generate_sql(question)
        except Exception as exc:
            msg = str(exc)
            is_quota = "429" in msg or "quota" in msg.lower() or "rate limit" in msg.lower() or "resource_exhausted" in msg.lower()
            if is_quota and attempt < max_retries - 1:
                # Use the retry_delay from the API response if present
                delay_match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+(?:\.\d+)?)', msg)
                wait = float(delay_match.group(1)) + 1.0 if delay_match else 5.0 * (2 ** attempt)
                logger.warning(
                    "Vanna LLM quota error (attempt %d/%d) — retrying in %.1fs.",
                    attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
            else:
                raise


# ── Core generation ───────────────────────────────────────────────────────────

_CHART_INFERENCE_SUFFIX = """

After writing the SQL, also output a JSON block (fenced with ```json ... ```) with:
{
  "chart_type": "line|bar|pie|table|scatter",
  "x_column": "<column name for x-axis or category>",
  "y_column": "<column name for y-axis or value>",
  "title": "<short descriptive chart title>"
}

Rules:
- Time series (month/date/year trend) → line
- Category vs numeric value → bar
- Part-of-whole (percentage/share) → pie
- Two continuous numeric columns → scatter
- Otherwise → table
"""


def generate_sql(question: str, previous_sql: Optional[str] = None, user_role: Optional[str] = None) -> VannaResult:
    """
    Convert a natural language question to SQL using Vanna RAG.

    If `previous_sql` is provided (follow-up question), it is injected
    into the prompt so Vanna modifies the existing query rather than
    starting from scratch.

    Returns a VannaResult with sql + chart metadata.
    """
    vn = get_vanna()

    augmented_question = question
    if previous_sql:
        augmented_question = (
            f"Previous SQL: {previous_sql}\n\n"
            f"New question (modify the previous SQL to answer this): {question}"
        )

    # Prepend role-specific focus if a role is set
    if user_role:
        from app.services.role_config import get_role_config
        role_cfg = get_role_config(user_role)
        if role_cfg:
            augmented_question = (
                f"[Answering for: {role_cfg.display_name}]\n"
                f"Focus: {role_cfg.sql_focus}\n\n"
                f"{augmented_question}"
            )

    # Append chart inference instructions
    full_question = augmented_question + _CHART_INFERENCE_SUFFIX

    logger.info("Asking Vanna to generate SQL for: %s", question)
    raw_sql = _vanna_generate_with_retry(vn, full_question)
    logger.info("Raw Vanna output:\n%s", raw_sql)

    sql, chart_meta = _parse_vanna_output(raw_sql)
    return VannaResult(
        sql=sql,
        chart_type=chart_meta.get("chart_type"),
        x_column=chart_meta.get("x_column"),
        y_column=chart_meta.get("y_column"),
        title=chart_meta.get("title"),
    )


def store_successful_query(question: str, sql: str) -> None:
    """
    Persist a verified (question → SQL) pair back into Vanna's knowledge base
    so future similar questions benefit from this example (Step 6).
    """
    try:
        vn = get_vanna()
        vn.train(question=question, sql=sql)
        logger.info("Stored Q→SQL pair in Vanna KB: '%s'", question[:80])
    except Exception as exc:
        # Non-fatal — log and continue
        logger.warning("Failed to store Q→SQL in Vanna: %s", exc)


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _parse_vanna_output(raw: str) -> tuple[str, dict]:
    """
    Separate the SQL statement from the JSON chart metadata block.
    Returns (sql_string, chart_dict).
    """
    chart_meta: dict = {}

    # Extract JSON fenced block
    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if json_match:
        try:
            chart_meta = json.loads(json_match.group(1))
        except json.JSONDecodeError as exc:
            logger.warning("Could not parse chart JSON: %s", exc)
        # Remove the JSON block from the raw string
        raw = raw[: json_match.start()] + raw[json_match.end() :]

    # Strip any remaining code fences and whitespace
    sql = re.sub(r"```sql\s*", "", raw)
    sql = re.sub(r"```\s*", "", sql)
    sql = sql.strip()

    return sql, chart_meta
