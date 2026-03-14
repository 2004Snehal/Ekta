"""
Statistics Extractor Agent
Computes per-column statistics for every table in every group.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from models.kpi_models import ColumnStats, TableSchema
from graph.state import KPIState
from utils.stats_utils import entropy, null_rate, safe_mean, safe_std, safe_min, safe_max, unique_count

logger = logging.getLogger(__name__)

# DuckDB / SQL type categories
_NUMERIC_TYPES = {
    "INTEGER", "INT", "BIGINT", "SMALLINT", "TINYINT",
    "DOUBLE", "FLOAT", "REAL", "DECIMAL", "NUMERIC", "HUGEINT",
    "UBIGINT", "UINTEGER", "USMALLINT", "UTINYINT",
}
_DATE_TYPES = {"DATE", "TIMESTAMP", "TIMESTAMPTZ", "TIME"}


def _is_numeric(dtype: str) -> bool:
    return dtype.upper().split("(")[0].strip() in _NUMERIC_TYPES


def _compute_column_stats(
    db,
    table_name: str,
    col_name: str,
    col_dtype: str,
    row_count: int,
) -> ColumnStats:
    """Compute statistics for a single column using SQL queries."""
    dtype_upper = col_dtype.upper().split("(")[0].strip()
    is_num = _is_numeric(col_dtype)

    # Null rate
    try:
        res = db.execute(
            f'SELECT SUM(CASE WHEN "{col_name}" IS NULL THEN 1 ELSE 0 END) AS nulls FROM "{table_name}"'
        )
        nulls = int(res[0]["nulls"]) if res else 0
        nr = nulls / row_count if row_count else 0.0
    except Exception:
        nr = 0.0
        nulls = 0

    # Unique count
    try:
        res = db.execute(f'SELECT COUNT(DISTINCT "{col_name}") AS uc FROM "{table_name}"')
        uc = int(res[0]["uc"]) if res else 0
    except Exception:
        uc = 0

    # Numeric stats
    mean_val = std_val = min_val = max_val = None
    if is_num:
        try:
            res = db.execute(
                f'SELECT AVG("{col_name}") AS mean, STDDEV("{col_name}") AS std, '
                f'MIN("{col_name}") AS mn, MAX("{col_name}") AS mx FROM "{table_name}"'
            )
            if res:
                mean_val = _to_float(res[0].get("mean"))
                std_val = _to_float(res[0].get("std"))
                min_val = _to_float(res[0].get("mn"))
                max_val = _to_float(res[0].get("mx"))
        except Exception as exc:
            logger.debug("Could not compute numeric stats for %s.%s: %s", table_name, col_name, exc)

    # Entropy from top values
    try:
        limit = min(1000, row_count or 1000)
        res = db.execute(
            f'SELECT "{col_name}" AS val, COUNT(*) AS cnt FROM "{table_name}" '
            f'GROUP BY "{col_name}" ORDER BY cnt DESC LIMIT 50'
        )
        freq_list: List[Any] = []
        for row in res:
            freq_list.extend([row["val"]] * int(row["cnt"]))
        ent = entropy(freq_list)
        top_vals = [r["val"] for r in res[:10]]
    except Exception:
        ent = None
        top_vals = []

    return ColumnStats(
        table=table_name,
        column=col_name,
        dtype=col_dtype,
        row_count=row_count,
        null_rate=nr,
        unique_count=uc,
        mean=mean_val,
        std=std_val,
        min=min_val,
        max=max_val,
        entropy=ent,
        top_values=top_vals,
    )


def _to_float(val: Any) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def stats_extractor(state: KPIState) -> KPIState:
    """
    LangGraph node: compute column statistics for all tables.

    Reads:
        state["schema"]
        state["db_adapter"]

    Writes:
        state["column_stats"]
    """
    schema: Dict[str, TableSchema] = state.get("schema", {})
    db = state["db_adapter"]
    errors: List[str] = state.get("errors", [])
    all_stats: List[ColumnStats] = []

    for table_name, table_schema in schema.items():
        row_count = table_schema.row_count or 0
        logger.info("Stats for table '%s' (%d rows)", table_name, row_count)

        for col in table_schema.columns:
            try:
                stats = _compute_column_stats(db, table_name, col.name, col.dtype, row_count)
                all_stats.append(stats)
            except Exception as exc:
                msg = f"stats_extractor: error on {table_name}.{col.name} – {exc}"
                logger.warning(msg)
                errors.append(msg)
                # Append minimal stats so pipeline continues
                all_stats.append(ColumnStats(
                    table=table_name,
                    column=col.name,
                    dtype=col.dtype,
                    row_count=row_count,
                ))

    state["column_stats"] = all_stats
    state["errors"] = errors
    logger.info("Stats extractor: computed stats for %d columns", len(all_stats))
    return state
