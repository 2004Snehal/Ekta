"""
Abstract base class for database adapters.
All agents must interact with the database through this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class DBAdapter(ABC):
    """
    Database-agnostic interface used by all agents.
    
    Implementations:
        DuckDBAdapter  – default / CSV ingestion
        ClickHouseAdapter – future analytics warehouse support
    """

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    @abstractmethod
    def connect(self) -> None:
        """Open / initialise the database connection."""

    @abstractmethod
    def close(self) -> None:
        """Close / release the database connection."""

    # ------------------------------------------------------------------ #
    # Query execution
    # ------------------------------------------------------------------ #

    @abstractmethod
    def execute(self, query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute *query* and return results as a list of row dicts.

        Parameters
        ----------
        query:
            SQL statement to execute.
        params:
            Optional positional parameters for parameterised queries.
        """

    @abstractmethod
    def execute_no_return(self, query: str, params: Optional[List[Any]] = None) -> None:
        """Execute a DML/DDL statement that returns no rows (CREATE, INSERT, …)."""

    # ------------------------------------------------------------------ #
    # Schema introspection
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_schema(self) -> Dict[str, List[Dict[str, str]]]:
        """
        Return the schema of all tables in the connected database.

        Returns
        -------
        dict mapping table_name → list of {name: str, type: str}
        """

    @abstractmethod
    def list_tables(self) -> List[str]:
        """Return the names of all discoverable tables."""

    @abstractmethod
    def sample_rows(self, table: str, n: int = 5) -> List[Dict[str, Any]]:
        """Return up to *n* sample rows from *table*."""

    @abstractmethod
    def row_count(self, table: str) -> int:
        """Return the number of rows in *table*."""

    # ------------------------------------------------------------------ #
    # Validation helper
    # ------------------------------------------------------------------ #

    @abstractmethod
    def explain(self, query: str) -> str:
        """
        Run EXPLAIN on *query* and return the plan as a string.
        Used for SQL validation before execution.
        """

    # ------------------------------------------------------------------ #
    # Context manager support
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "DBAdapter":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
