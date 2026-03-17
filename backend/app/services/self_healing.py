"""
Self-healing SQL layer (Step 2).

When a SQL query fails, this module sends the error + original SQL +
schema context back to the LLM to generate a corrected query, then retries.
Maximum retries: MAX_SQL_RETRIES (default 2).
"""

import re
from typing import Any, Dict, List

import psycopg2

from app.config.settings import get_settings
from app.db.postgres import execute_query
from app.db.schema_loader import load_schema
from app.services.llm_service import call_llm
from app.utils.logger import get_logger

logger = get_logger("nlq.self_healing")


def heal_sql(
    original_sql: str,
    error_message: str,
    question: str,
) -> str:
    """
    Ask the LLM to fix a broken SQL query.

    Args:
        original_sql:   The SQL that caused the error.
        error_message:  The PostgreSQL error string.
        question:       The original user question (for context).

    Returns:
        A corrected SQL string.
    """
    schema = load_schema(force_reload=True)  # always use live schema when healing

    # Extract available table names for explicit guidance
    from app.db.schema_loader import get_table_names
    available_tables = get_table_names()
    tables_str = ", ".join(available_tables) if available_tables else "none found"

    prompt = f"""You are a PostgreSQL expert. The following SQL query produced an error.

## Available Tables (ONLY use these — do not reference any other table)
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
IMPORTANT: Do NOT generate placeholder/dummy SQL like SELECT 0 or SELECT 'data not available'.
If the required data does not exist in these tables, generate a SELECT that returns 0 rows (e.g. SELECT ... WHERE 1=0).
Return ONLY the corrected SQL with no explanation, no markdown fences, no extra text.
"""
    logger.info("Requesting SQL fix from LLM…")
    corrected = call_llm(prompt, system="You are a PostgreSQL SQL expert.")

    # Strip any accidental code fences the LLM might include
    corrected = re.sub(r"```sql\s*", "", corrected)
    corrected = re.sub(r"```\s*", "", corrected)
    return corrected.strip()


def run_sql_with_retry(
    sql: str,
    question: str,
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Execute SQL with automatic self-healing on failure.

    Attempts up to MAX_SQL_RETRIES fixes before raising the final error.

    Returns:
        (final_sql, rows) — the (possibly corrected) SQL and its results.

    Raises:
        Exception: if all retry attempts are exhausted.
    """
    settings = get_settings()
    max_retries = settings.max_sql_retries
    current_sql = sql

    for attempt in range(max_retries + 1):
        try:
            rows = execute_query(current_sql)
            if attempt > 0:
                logger.info("SQL succeeded after %d fix(es).", attempt)
            return current_sql, rows

        except (psycopg2.Error, Exception) as exc:
            error_msg = str(exc)
            logger.warning(
                "SQL attempt %d/%d failed: %s",
                attempt + 1,
                max_retries + 1,
                error_msg,
            )

            if attempt >= max_retries:
                logger.error("All SQL retries exhausted. Raising final error.")
                raise

            # Ask LLM to heal the SQL
            current_sql = heal_sql(
                original_sql=current_sql,
                error_message=error_msg,
                question=question,
            )
            logger.info("Healed SQL (attempt %d):\n%s", attempt + 1, current_sql)

    # Should never reach here, but satisfies type checker
    raise RuntimeError("run_sql_with_retry: unexpected exit from retry loop.")
