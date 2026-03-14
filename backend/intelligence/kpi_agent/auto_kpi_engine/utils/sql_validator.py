"""
SQL validation utilities.
Validates queries via EXPLAIN before actual execution.
"""

from __future__ import annotations

import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)

# Patterns that indicate dangerous SQL operations
_DANGEROUS_PATTERNS = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|UPDATE|INSERT|CREATE|ALTER|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)

# Minimal pattern: query must start with SELECT (after optional WITH clause)
_ALLOWED_START = re.compile(
    r"^\s*(WITH\s+.+?AS\s*\(|SELECT\s)",
    re.IGNORECASE | re.DOTALL,
)


def is_safe_sql(query: str) -> Tuple[bool, str]:
    """
    Lightweight static check: confirm the query is a read-only SELECT.

    Returns (is_safe, reason).
    """
    if _DANGEROUS_PATTERNS.search(query):
        return False, "Query contains a dangerous DML/DDL keyword."
    if not _ALLOWED_START.match(query):
        return False, "Query must start with SELECT (or WITH ... SELECT)."
    return True, "OK"


def validate_with_explain(db_adapter, query: str) -> Tuple[bool, str]:
    """
    Validate *query* using EXPLAIN on the database adapter.

    Returns (is_valid, message).
    """
    # Static check first
    safe, reason = is_safe_sql(query)
    if not safe:
        return False, reason

    # EXPLAIN check
    try:
        db_adapter.explain(query)
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


def sanitize_identifier(name: str) -> str:
    """Remove characters not suitable for SQL identifiers."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name)
