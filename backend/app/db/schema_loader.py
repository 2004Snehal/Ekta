"""
Schema introspection for PostgreSQL.

Loads table/column/type/constraint metadata and formats it as a
human-readable DDL string suitable for inclusion in LLM prompts.
"""

from typing import Dict, List

from app.db.postgres import execute_query
from app.utils.logger import get_logger

logger = get_logger("nlq.schema")

# Cached schema string — only reloaded on demand
_schema_cache: str | None = None


def load_schema(force_reload: bool = False) -> str:
    """
    Return the full DB schema as a DDL-like string.
    Result is cached in memory after the first load.
    """
    global _schema_cache
    if _schema_cache and not force_reload:
        return _schema_cache

    logger.info("Loading database schema…")
    _schema_cache = _build_schema_string()
    logger.info("Schema loaded (%d chars).", len(_schema_cache))
    return _schema_cache


def _build_schema_string() -> str:
    """Introspect information_schema and build a DDL-like representation."""
    tables = _get_tables()
    lines: List[str] = []

    for table in tables:
        table_name = table["table_name"]
        cols = _get_columns(table_name)
        fks = _get_foreign_keys(table_name)

        lines.append(f"TABLE {table_name} (")
        for col in cols:
            nullable = "NOT NULL" if col["is_nullable"] == "NO" else ""
            default = f"DEFAULT {col['column_default']}" if col["column_default"] else ""
            lines.append(
                f"  {col['column_name']} {col['data_type']} {nullable} {default}".rstrip()
                + ","
            )

        for fk in fks:
            lines.append(
                f"  FOREIGN KEY ({fk['column_name']}) REFERENCES "
                f"{fk['foreign_table_name']}({fk['foreign_column_name']}),"
            )

        # Remove trailing comma on last line
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append(");")
        lines.append("")

    return "\n".join(lines)


def _get_tables() -> List[Dict]:
    sql = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """
    return execute_query(sql)


def _get_columns(table_name: str) -> List[Dict]:
    sql = f"""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = '{table_name}'
        ORDER BY ordinal_position;
    """
    return execute_query(sql)


def _get_foreign_keys(table_name: str) -> List[Dict]:
    sql = f"""
        SELECT
            kcu.column_name,
            ccu.table_name  AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
           AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name = '{table_name}';
    """
    return execute_query(sql)


def get_table_names() -> List[str]:
    rows = _get_tables()
    return [r["table_name"] for r in rows]
