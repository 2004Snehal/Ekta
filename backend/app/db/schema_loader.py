"""
Schema introspection for PostgreSQL.

Loads table/column/type/constraint metadata from BOTH 'public' and 'data' schemas
and formats it as a DDL string for Vanna/LLM prompts.
Tables are referenced with their fully-qualified schema prefix (e.g. data.dim_channel)
so generated SQL uses the correct schema.
"""

from typing import Dict, List

from app.db.postgres import execute_query
from app.utils.logger import get_logger

logger = get_logger("nlq.schema")

# Schemas to introspect — 'data' first (analytics tables), then 'public' (utility tables)
TARGET_SCHEMAS = ["data", "public"]

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
        schema_name = table["table_schema"]
        table_name = table["table_name"]
        qualified = f"{schema_name}.{table_name}"

        cols = _get_columns(schema_name, table_name)
        fks = _get_foreign_keys(schema_name, table_name)

        lines.append(f"TABLE {qualified} (")
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
                f"{fk['foreign_table_schema']}.{fk['foreign_table_name']}({fk['foreign_column_name']}),"
            )

        # Remove trailing comma on last line
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append(");")
        lines.append("")

    return "\n".join(lines)


def _get_tables() -> List[Dict]:
    schemas = ", ".join(f"'{s}'" for s in TARGET_SCHEMAS)
    sql = f"""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ({schemas})
          AND table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name;
    """
    return execute_query(sql)


def _get_columns(schema_name: str, table_name: str) -> List[Dict]:
    sql = f"""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = '{schema_name}'
          AND table_name = '{table_name}'
        ORDER BY ordinal_position;
    """
    return execute_query(sql)


def _get_foreign_keys(schema_name: str, table_name: str) -> List[Dict]:
    sql = f"""
        SELECT
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name   AS foreign_table_name,
            ccu.column_name  AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
           AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = '{schema_name}'
          AND tc.table_name = '{table_name}';
    """
    return execute_query(sql)


def get_table_names() -> List[str]:
    """Return fully-qualified table names (schema.table) for all discovered tables."""
    rows = _get_tables()
    return [f"{r['table_schema']}.{r['table_name']}" for r in rows]
