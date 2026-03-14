"""
ClickHouse stub adapter (future support).
Installing clickhouse-driver is optional; the adapter will raise a clear
ImportError at runtime if the package is absent.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from db.adapter_base import DBAdapter

logger = logging.getLogger(__name__)


class ClickHouseAdapter(DBAdapter):
    """
    ClickHouse-backed adapter.

    Requires the `clickhouse-driver` package:
        pip install clickhouse-driver

    Parameters
    ----------
    host, port, database, user, password:
        Standard ClickHouse connection parameters.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9000,
        database: str = "default",
        user: str = "default",
        password: str = "",
    ) -> None:
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._client: Any = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        try:
            from clickhouse_driver import Client  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "clickhouse-driver is required for ClickHouseAdapter. "
                "Install it with: pip install clickhouse-driver"
            ) from exc

        self._client = Client(
            host=self._host,
            port=self._port,
            database=self._database,
            user=self._user,
            password=self._password,
        )
        logger.info("ClickHouse connected: %s:%s/%s", self._host, self._port, self._database)

    def close(self) -> None:
        # clickhouse-driver connections are stateless; nothing to do
        self._client = None
        logger.info("ClickHouse connection released")

    @property
    def client(self) -> Any:
        if self._client is None:
            self.connect()
        return self._client

    # ------------------------------------------------------------------ #
    # Query execution
    # ------------------------------------------------------------------ #

    def execute(self, query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        rows, columns_meta = self.client.execute(query, with_column_types=True)
        col_names = [col[0] for col in columns_meta]
        return [dict(zip(col_names, row)) for row in rows]

    def execute_no_return(self, query: str, params: Optional[List[Any]] = None) -> None:
        self.client.execute(query)

    # ------------------------------------------------------------------ #
    # Schema introspection
    # ------------------------------------------------------------------ #

    def list_tables(self) -> List[str]:
        rows = self.execute(f"SHOW TABLES FROM `{self._database}`")
        return [list(r.values())[0] for r in rows]

    def get_schema(self) -> Dict[str, List[Dict[str, str]]]:
        schema: Dict[str, List[Dict[str, str]]] = {}
        for table in self.list_tables():
            rows = self.execute(f"DESCRIBE TABLE `{self._database}`.`{table}`")
            schema[table] = [{"name": r["name"], "type": r["type"]} for r in rows]
        return schema

    def sample_rows(self, table: str, n: int = 5) -> List[Dict[str, Any]]:
        return self.execute(f"SELECT * FROM `{self._database}`.`{table}` LIMIT {n}")

    def row_count(self, table: str) -> int:
        result = self.execute(
            f"SELECT count() AS cnt FROM `{self._database}`.`{table}`"
        )
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
