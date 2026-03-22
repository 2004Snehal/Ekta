"""Error classification and breakdown metrics for NLQ evaluation results."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evaluation.pipelines.base import EvalResult

# ---------------------------------------------------------------------------
# Error category labels
# ---------------------------------------------------------------------------

SYNTAX_ERROR = "syntax_error"
WRONG_TABLE = "wrong_table"
EMPTY_RESULT = "empty_result"
TIMEOUT = "timeout"
TYPE_ERROR = "type_error"
OTHER = "other"


def classify_error(error_msg: str, sql: str) -> str:
    """Classify a query error into a canonical category string.

    Categories (checked in priority order):
      'syntax_error'  — SQL parse / syntax issue.
                        Keywords: syntax, parse, unexpected, invalid input
      'wrong_table'   — Table or column not found.
                        Keywords: does not exist, undefined, no such
      'empty_result'  — SQL executed successfully but returned 0 rows.
                        Detected from the SQL string (not the error message)
                        by checking whether it is a non-empty SELECT with no
                        result rows implied by context.  Triggered when
                        error_msg is empty/None and sql is a SELECT statement —
                        callers should pass an empty string as error_msg when
                        the query returned zero rows.
      'timeout'       — Query timed out.
                        Keywords: timeout, canceling
      'type_error'    — Type mismatch.
                        Keywords: cannot cast, operator does not exist
      'other'         — Everything else.

    Parameters
    ----------
    error_msg:
        The error string from the database or execution layer.  Pass an empty
        string (``""``) to signal an empty-result condition.
    sql:
        The SQL string that was executed (used for empty_result detection).
    """
    msg_lower = (error_msg or "").lower()
    sql_upper = (sql or "").upper().strip()

    # Empty result: no error message but the query is a SELECT statement.
    if not msg_lower and re.match(r"^\s*SELECT\b", sql_upper):
        return EMPTY_RESULT

    # Syntax error
    if re.search(r"syntax|parse error|unexpected|invalid input", msg_lower):
        return SYNTAX_ERROR

    # Wrong table / column
    if re.search(r"does not exist|undefined|no such", msg_lower):
        return WRONG_TABLE

    # Timeout
    if re.search(r"timeout|canceling", msg_lower):
        return TIMEOUT

    # Type error
    if re.search(r"cannot cast|operator does not exist", msg_lower):
        return TYPE_ERROR

    return OTHER


def compute_error_breakdown(results: list["EvalResult"]) -> dict:
    """Classify and count errors among failed results.

    Only results where ``success=False`` are considered.

    Returns a dict with one key per error category (only categories that
    occurred are included), plus:
      - total_errors: Total count of failed results.
      - error_rate:   Fraction of all results that failed (float 0–1, 4 dp).
    """
    n_total = len(results)
    failed = [r for r in results if not r.success]
    total_errors = len(failed)

    counts: dict[str, int] = {}
    for r in failed:
        label = classify_error(r.error or "", r.sql or "")
        counts[label] = counts.get(label, 0) + 1

    error_rate = round(total_errors / n_total, 4) if n_total else 0.0

    return {
        **counts,
        "total_errors": total_errors,
        "error_rate": error_rate,
    }
