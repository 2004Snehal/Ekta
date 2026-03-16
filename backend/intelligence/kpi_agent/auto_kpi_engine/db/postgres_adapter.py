"""
PostgreSQL implementation of DBAdapter.

Instead of managing its own psycopg2 connection, this adapter accepts a
`conn_factory` — a callable that returns a context manager yielding a
psycopg2 connection.  This lets the KPI engine reuse the existing backend
connection pool (from api.deps) and avoids exhausting Supabase's
MaxClientsInSessionMode limit.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, List, Optional

from db.adapter_base import DBAdapter

logger = logging.getLogger(__name__)


class PostgreSQLAdapter(DBAdapter):
    """
    PostgreSQL-backed adapter for the KPI discovery engine.

    Parameters
    ----------
    conn_factory:
        A zero-argument callable that returns a context manager yielding a
        live psycopg2 connection.  Pass ``api.deps.get_conn`` here so the
        adapter borrows from the shared pool rather than opening a new
        connection.
    schema:
        PostgreSQL schema to introspect. Defaults to 'public'.
    """

    def __init__(
        self,
        conn_factory: Callable[[], Any],
        schema: str = "public",
    ) -> None:
        self._conn_factory = conn_factory
        self._schema = schema

    # ------------------------------------------------------------------ #
    # Lifecycle — no-ops: connections are managed by the factory
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        pass  # pool is managed externally

    def close(self) -> None:
        pass  # pool is managed externally

    # ------------------------------------------------------------------ #
    # Internal helper — borrow a connection for one operation
    # ------------------------------------------------------------------ #

    @contextmanager
    def _borrow(self) -> Generator:
        with self._conn_factory() as conn:
            yield conn

    # ------------------------------------------------------------------ #
    # Query execution
    # ------------------------------------------------------------------ #

    def execute(self, query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        try:
            with self._borrow() as conn:
                cur = conn.cursor()
                cur.execute(query, params or [])
                if cur.description is None:
                    cur.close()
                    return []
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                cur.close()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            logger.error("PostgreSQL execute error | query=%.200s | err=%s", query, exc)
            raise

    def execute_no_return(self, query: str, params: Optional[List[Any]] = None) -> None:
        try:
            with self._borrow() as conn:
                cur = conn.cursor()
                cur.execute(query, params or [])
                conn.commit()
                cur.close()
        except Exception as exc:
            logger.error("PostgreSQL execute_no_return error | query=%.200s | err=%s", query, exc)
            raise

    # ------------------------------------------------------------------ #
    # Schema introspection
    # ------------------------------------------------------------------ #

    def list_tables(self) -> List[str]:
        rows = self.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            [self._schema],
        )
        return [r["table_name"] for r in rows]

    def get_schema(self) -> Dict[str, List[Dict[str, str]]]:
        schema: Dict[str, List[Dict[str, str]]] = {}
        for table in self.list_tables():
            rows = self.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                [self._schema, table],
            )
            schema[table] = [{"name": r["column_name"], "type": r["data_type"]} for r in rows]
        return schema

    def sample_rows(self, table: str, n: int = 5) -> List[Dict[str, Any]]:
        qualified = self._qualify(table)
        return self.execute(f"SELECT * FROM {qualified} LIMIT %s", [n])

    def row_count(self, table: str) -> int:
        qualified = self._qualify(table)
        result = self.execute(f"SELECT COUNT(*) AS cnt FROM {qualified}")
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
    # Private helpers
    # ------------------------------------------------------------------ #

    def _qualify(self, table: str) -> str:
        """Returns a schema-qualified, double-quoted table reference.

        If *table* already contains a dot (e.g. ``data.fact_created_videos``)
        both parts are quoted separately; otherwise ``self._schema`` is
        prepended so bare names resolve correctly.
        """
        if '.' in table:
            schema, tbl = table.split('.', 1)
            return f'"{schema}"."{re.sub(r"[^A-Za-z0-9_]", "_", tbl)}"'
        safe = re.sub(r'[^A-Za-z0-9_]', '_', table)
        return f'"{self._schema}"."{safe}"'

    @staticmethod
    def _quote(name: str) -> str:
        safe = re.sub(r'[^A-Za-z0-9_]', '_', name)
        return f'"{safe}"'
