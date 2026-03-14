"""
SQL executor service — thin wrapper around the self-healing layer.

Exposes a single `execute` function that the API route calls.
Returns the final SQL (possibly healed) plus the result rows.
"""

from typing import Any, Dict, List, Tuple

import pandas as pd

from app.services.self_healing import run_sql_with_retry
from app.utils.logger import get_logger

logger = get_logger("nlq.sql_executor")


def execute(
    sql: str,
    question: str,
) -> Tuple[str, List[Dict[str, Any]], pd.DataFrame]:
    """
    Run SQL through the self-healing executor.

    Args:
        sql:       Generated SQL query.
        question:  Original user question (used by healer if SQL fails).

    Returns:
        Tuple of (final_sql, rows_as_list_of_dicts, rows_as_dataframe).
    """
    logger.info("SQL executor called for question: '%s'", question[:100])
    final_sql, rows = run_sql_with_retry(sql, question)
    df = pd.DataFrame(rows)
    logger.info("Execution complete: %d rows returned.", len(rows))
    return final_sql, rows, df
