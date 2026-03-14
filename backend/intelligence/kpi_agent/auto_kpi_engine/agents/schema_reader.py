"""
Schema Reader Agent
Reads all tables from the DB adapter and populates state.schema.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from models.kpi_models import ColumnInfo, TableSchema
from graph.state import KPIState

logger = logging.getLogger(__name__)


def schema_reader(state: KPIState) -> KPIState:
    """
    LangGraph node: reads schema from the connected db_adapter.

    Reads:
        state["db_adapter"]

    Writes:
        state["schema"]
    """
    db = state["db_adapter"]
    errors: List[str] = state.get("errors", [])

    raw_schema: Dict[str, List[Dict[str, str]]] = {}
    tables: List[str] = []

    try:
        raw_schema = db.get_schema()
        tables = list(raw_schema.keys())
        logger.info("Schema reader: found %d tables: %s", len(tables), tables)
    except Exception as exc:
        msg = f"schema_reader: failed to read schema – {exc}"
        logger.error(msg)
        errors.append(msg)
        state["errors"] = errors
        state["schema"] = {}
        return state

    schema: Dict[str, TableSchema] = {}

    for table_name, columns_raw in raw_schema.items():
        # Fetch sample rows
        try:
            sample = db.sample_rows(table_name, n=5)
        except Exception as exc:
            logger.warning("Could not sample table '%s': %s", table_name, exc)
            sample = []

        # Fetch row count
        try:
            row_count = db.row_count(table_name)
        except Exception as exc:
            logger.warning("Could not count rows for '%s': %s", table_name, exc)
            row_count = 0

        # Build ColumnInfo list
        columns: List[ColumnInfo] = []
        for col in columns_raw:
            col_name = col["name"]
            col_type = col["type"]
            sample_vals = [row.get(col_name) for row in sample if col_name in row]
            null_rate = sum(1 for v in sample_vals if v is None) / len(sample_vals) if sample_vals else 0.0
            unique_cnt = len(set(v for v in sample_vals if v is not None))

            columns.append(ColumnInfo(
                name=col_name,
                dtype=col_type,
                sample_values=sample_vals,
                null_rate=null_rate,
                unique_count=unique_cnt,
            ))

        schema[table_name] = TableSchema(
            table_name=table_name,
            columns=columns,
            row_count=row_count,
            sample_rows=sample,
        )

    state["schema"] = schema
    state["errors"] = errors
    logger.info("Schema reader: completed for tables %s", list(schema.keys()))
    return state
