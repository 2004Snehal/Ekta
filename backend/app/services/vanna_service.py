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
            # Fallback: use OpenAI-compatible wrapper pointed at Gemini
            logger.warning(
                "vanna.google not available — falling back to OpenAI-compat wrapper for Gemini."
            )
            raise RuntimeError(
                "Install 'vanna[google]' or switch LLM_PROVIDER to 'openai'."
            )
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


def generate_sql(question: str, previous_sql: Optional[str] = None) -> VannaResult:
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

    # Append chart inference instructions
    full_question = augmented_question + _CHART_INFERENCE_SUFFIX

    logger.info("Asking Vanna to generate SQL for: %s", question)
    raw_sql = vn.generate_sql(full_question)
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
