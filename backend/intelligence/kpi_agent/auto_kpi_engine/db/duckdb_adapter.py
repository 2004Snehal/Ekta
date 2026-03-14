"""
DuckDB implementation of DBAdapter.
Also handles CSV / Parquet file ingestion into in-process DuckDB tables.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb

from db.adapter_base import DBAdapter

logger = logging.getLogger(__name__)


class DuckDBAdapter(DBAdapter):
    """
    DuckDB-backed adapter.

    Parameters
    ----------
    db_path:
        Path to a persistent DuckDB file, or ":memory:" for an in-memory DB.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)
            logger.info("DuckDB connected: %s", self._db_path)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.info("DuckDB connection closed")

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self.connect()
        return self._conn  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Query execution
    # ------------------------------------------------------------------ #

    def execute(self, query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        try:
            rel = self.conn.execute(query, params or [])
            columns = [desc[0] for desc in rel.description]
            rows = rel.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            logger.error("DuckDB execute error | query=%s | err=%s", query[:200], exc)
            raise

    def execute_no_return(self, query: str, params: Optional[List[Any]] = None) -> None:
        try:
            self.conn.execute(query, params or [])
        except Exception as exc:
            logger.error("DuckDB execute_no_return error | query=%s | err=%s", query[:200], exc)
            raise

    # ------------------------------------------------------------------ #
    # Schema introspection
    # ------------------------------------------------------------------ #

    def list_tables(self) -> List[str]:
        rows = self.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        )
        return [r["table_name"] for r in rows]

    def get_schema(self) -> Dict[str, List[Dict[str, str]]]:
        schema: Dict[str, List[Dict[str, str]]] = {}
        for table in self.list_tables():
            rows = self.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [table],
            )
            schema[table] = [{"name": r["column_name"], "type": r["data_type"]} for r in rows]
        return schema

    def sample_rows(self, table: str, n: int = 5) -> List[Dict[str, Any]]:
        sanitized = self._sanitize_identifier(table)
        return self.execute(f'SELECT * FROM "{sanitized}" LIMIT {n}')

    def row_count(self, table: str) -> int:
        sanitized = self._sanitize_identifier(table)
        result = self.execute(f'SELECT COUNT(*) AS cnt FROM "{sanitized}"')
        return int(result[0]["cnt"]) if result else 0

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    def explain(self, query: str) -> str:
        try:
            rows = self.execute(f"EXPLAIN {query}")
            return "\n".join(str(r) for r in rows)
        except Exception as exc:
            raise ValueError(f"SQL validation failed: {exc}") from exc

    # ------------------------------------------------------------------ #
    # CSV / file ingestion helpers
    # ------------------------------------------------------------------ #

    def load_csv(self, file_path: str | Path, table_name: Optional[str] = None) -> str:
        """
        Load a CSV file into a DuckDB table using auto-detection.

        Returns the resulting table name.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        tbl = table_name or self._stem_to_table_name(path.stem)
        sanitized = self._sanitize_identifier(tbl)

        # Use DuckDB's powerful read_csv_auto
        self.execute_no_return(
            f'CREATE OR REPLACE TABLE "{sanitized}" AS '
            f"SELECT * FROM read_csv_auto('{path.as_posix()}', header=true, all_varchar=false)"
        )
        logger.info("Loaded CSV %s → table '%s'", path.name, sanitized)
        return sanitized

    def load_multiple_csvs(
        self, file_paths: List[str | Path], table_names: Optional[List[str]] = None
    ) -> List[str]:
        """
        Load multiple CSV files, each into its own table.
        Returns the list of created table names.
        """
        table_names = table_names or [None] * len(file_paths)  # type: ignore[list-item]
        return [
            self.load_csv(fp, tn) for fp, tn in zip(file_paths, table_names)
        ]

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _sanitize_identifier(name: str) -> str:
        """Strip characters that are not alphanumeric or underscore."""
        return re.sub(r"[^A-Za-z0-9_]", "_", name)

    @staticmethod
    def _stem_to_table_name(stem: str) -> str:
        """Convert a file stem (e.g. 'sales-2024') to a safe table name."""
        return re.sub(r"[^A-Za-z0-9]", "_", stem).strip("_").lower() or "uploaded_table"
