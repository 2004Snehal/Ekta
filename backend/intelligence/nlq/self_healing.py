"""
Self-healing SQL layer.

When a SQL query fails, sends the error + original SQL + live schema back
to the LLM to generate a corrected query, then retries.
Max attempts: MAX_SQL_RETRIES (default 2).
"""

import logging
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend_config import MAX_SQL_RETRIES

from intelligence.nlq.context import fetch_live_schema
from intelligence.nlq.llm import call_llm_text

logger = logging.getLogger("nlq.self_healing")


def _get_table_names(conn) -> list:
    """Return fully-qualified table names available in the data schema."""
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'data' AND table_type = 'BASE TABLE'
        UNION ALL
        SELECT matviewname FROM pg_matviews WHERE schemaname = 'data'
        ORDER BY 1
    """)
    return [f"data.{r[0]}" for r in cur.fetchall()]


def _execute(conn, sql: str) -> list:
    """Execute SQL and return rows as list of dicts. Raises on failure."""
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql)
    return [dict(r) for r in cur.fetchall()]


def heal_sql(conn, original_sql: str, error_message: str, question: str) -> str:
    """Ask the LLM to fix a broken SQL query. Returns corrected SQL string."""
    schema = fetch_live_schema(conn)
    tables = _get_table_names(conn)
    tables_str = ", ".join(tables) if tables else "none found"

    prompt = f"""You are a PostgreSQL expert. The following SQL query produced an error.

## Available Tables (ONLY use these)
{tables_str}

## Full Database Schema
{schema}

## Original User Question
{question}

## Broken SQL
```sql
{original_sql}
```

## Error
{error_message}

Fix the SQL so it runs without errors using ONLY the tables listed above.
Do NOT generate placeholder SQL like SELECT 0 or SELECT 'not available'.
If the required data does not exist, return a SELECT that produces 0 rows (e.g. WHERE 1=0).
Return ONLY the corrected SQL — no explanation, no markdown fences, no extra text.
"""
    corrected = call_llm_text(
        prompt,
        system=(
            "You are a PostgreSQL expert for the Frammer AI analytics platform. "
            "Return ONLY the corrected SQL — no explanation, no markdown fences, no JSON, no extra text."
        ),
    )
    # Strip think blocks (Qwen3 chain-of-thought)
    corrected = re.sub(r"<think>.*?</think>", "", corrected, flags=re.DOTALL)
    corrected = re.sub(r"<think>.*", "", corrected, flags=re.DOTALL)  # truncated block
    corrected = re.sub(r"```sql\s*", "", corrected)
    corrected = re.sub(r"```\s*", "", corrected)
    return corrected.strip()


def run_sql_with_healing(conn, sql: str, question: str) -> tuple:
    """
    Execute SQL with automatic self-healing on failure.
    Returns (final_sql, rows) — rows is list of dicts.
    Raises if all retry attempts are exhausted.
    """
    current_sql = sql

    for attempt in range(MAX_SQL_RETRIES + 1):
        try:
            rows = _execute(conn, current_sql)
            if attempt > 0:
                logger.info("SQL succeeded after %d fix(es).", attempt)
            return current_sql, rows

        except Exception as exc:
            error_msg = str(exc)
            logger.warning("SQL attempt %d/%d failed: %s", attempt + 1, MAX_SQL_RETRIES + 1, error_msg)
            conn.rollback()

            if attempt >= MAX_SQL_RETRIES:
                logger.error("All SQL retries exhausted.")
                raise

            logger.info("Requesting SQL fix from LLM (attempt %d)…", attempt + 1)
            current_sql = heal_sql(conn, current_sql, error_msg, question)
            logger.info("Healed SQL:\n%s", current_sql)

    raise RuntimeError("run_sql_with_healing: unexpected exit from retry loop.")
