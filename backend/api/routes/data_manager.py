"""
Data Manager routes — CSV row append and row deletion for client data tables.

All operations are scoped to the 'data' PostgreSQL schema.
System/backend tables (nlq_session, dashboard_state, kpi_registry, etc.)
live in the 'internal' schema and are never exposed here.

Endpoints:
  GET    /data-manager/tables                        — list all tables in 'data' schema
  GET    /data-manager/table/{table_name}/rows       — paginated rows
  POST   /data-manager/table/{table_name}/append-csv — validate columns and insert rows from CSV
  DELETE /data-manager/table/{table_name}/rows       — delete rows by primary key values
"""

from __future__ import annotations

import io
import logging
from typing import Any, Dict, List

import pandas as pd
import psycopg2.extras
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from api.deps import get_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data-manager", tags=["Data Manager"])

# The schema that holds client-facing data tables.
# System tables live in 'internal' and are never touched here.
_DATA_SCHEMA = "data"


def _assert_table_exists(cur, table_name: str) -> None:
    """Raise 404 if table_name does not exist in the data schema."""
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (_DATA_SCHEMA, table_name),
    )
    if not cur.fetchone():
        raise HTTPException(
            status_code=404,
            detail=f"Table '{table_name}' does not exist in the data schema.",
        )


def _get_col_info(cur, table_name: str) -> list:
    cur.execute(
        """
        SELECT column_name, column_default, is_nullable, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (_DATA_SCHEMA, table_name),
    )
    return cur.fetchall()


# ------------------------------------------------------------------ #
# GET /data-manager/tables
# ------------------------------------------------------------------ #

@router.get("/tables")
def list_tables() -> Dict:
    """
    Return all tables in the 'data' schema with column definitions and primary keys.
    Any table you create in the 'data' schema automatically appears here.
    """
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                c.table_name,
                c.column_name,
                c.data_type,
                c.column_default,
                c.is_nullable,
                c.ordinal_position
            FROM information_schema.columns c
            WHERE c.table_schema = %s
            ORDER BY c.table_name, c.ordinal_position
            """,
            (_DATA_SCHEMA,),
        )
        col_rows = cur.fetchall()

        cur.execute(
            """
            SELECT kcu.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema   = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema   = %s
            """,
            (_DATA_SCHEMA,),
        )
        pk_rows = cur.fetchall()

    pk_map: Dict[str, List[str]] = {}
    for table_name, col_name in pk_rows:
        pk_map.setdefault(table_name, []).append(col_name)

    tables: Dict[str, Dict] = {}
    for table_name, col_name, data_type, col_default, is_nullable, _ordinal in col_rows:
        if table_name not in tables:
            tables[table_name] = {
                "name": table_name,
                "columns": [],
                "primary_keys": pk_map.get(table_name, []),
            }
        tables[table_name]["columns"].append(
            {
                "name": col_name,
                "type": data_type,
                "nullable": is_nullable == "YES",
                "has_default": col_default is not None,
                "is_pk": col_name in pk_map.get(table_name, []),
            }
        )

    return {"tables": list(tables.values())}


# ------------------------------------------------------------------ #
# GET /data-manager/table/{table_name}/rows
# ------------------------------------------------------------------ #

@router.get("/table/{table_name}/rows")
def get_table_rows(
    table_name: str,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> Dict:
    """Return paginated rows from a table in the data schema."""
    with get_conn() as conn:
        cur = conn.cursor()
        _assert_table_exists(cur, table_name)

        # Use plain cursor for COUNT to avoid RealDictCursor key issues
        cur = conn.cursor()
        cur.execute(f'SELECT COUNT(*) FROM {_DATA_SCHEMA}."{table_name}"')
        total = cur.fetchone()[0]

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            f'SELECT * FROM {_DATA_SCHEMA}."{table_name}" LIMIT %s OFFSET %s',
            (limit, offset),
        )
        rows = [dict(r) for r in cur.fetchall()]

    # Stringify non-JSON-serialisable types (datetime, Decimal, UUID, etc.)
    safe_rows = []
    for row in rows:
        safe_rows.append(
            {
                k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v)
                for k, v in row.items()
            }
        )

    return {"rows": safe_rows, "total": total, "limit": limit, "offset": offset}


# ------------------------------------------------------------------ #
# POST /data-manager/table/{table_name}/append-csv
# ------------------------------------------------------------------ #

@router.post("/table/{table_name}/append-csv")
async def append_csv(
    table_name: str,
    file: UploadFile = File(...),
) -> Dict:
    """
    Validate CSV columns against the target table then bulk-insert rows.

    Rules:
    - Column names matched case-insensitively after stripping whitespace.
    - Auto-generated columns (serial / uuid / now()) may be omitted.
    - Required columns (NOT NULL, no default) must be present.
    - Columns not in the table are rejected to avoid silent data loss.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc

    if df.empty:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    df.columns = [str(c).strip().lower() for c in df.columns]

    with get_conn() as conn:
        cur = conn.cursor()
        _assert_table_exists(cur, table_name)
        col_info = _get_col_info(cur, table_name)

    if not col_info:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' has no columns.")

    # Columns auto-filled by the database (serial, uuid, timestamps)
    auto_cols = {
        row[0]
        for row in col_info
        if row[1] and (
            "nextval" in str(row[1])
            or "uuid_generate" in str(row[1])
            or "gen_random_uuid" in str(row[1])
            or "now()" in str(row[1]).lower()
            or "current_timestamp" in str(row[1]).lower()
        )
    }

    table_cols = {row[0] for row in col_info}
    csv_cols = set(df.columns)

    required_cols = {
        row[0]
        for row in col_info
        if row[0] not in auto_cols and row[2] == "NO" and not row[1]
    }

    missing = required_cols - csv_cols
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"CSV is missing required column(s): {sorted(missing)}. "
                f"Required: {sorted(required_cols)}. "
                f"CSV has: {sorted(csv_cols)}."
            ),
        )

    unknown = csv_cols - table_cols
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(
                f"CSV contains column(s) not in table '{table_name}': {sorted(unknown)}. "
                f"Table columns: {sorted(table_cols)}."
            ),
        )

    cols_to_insert = [c for c in df.columns if c in table_cols and c not in auto_cols]
    if not cols_to_insert:
        raise HTTPException(status_code=400, detail="No insertable columns found in CSV.")

    df_insert = df[cols_to_insert].where(pd.notna(df[cols_to_insert]), None)
    rows_to_insert = df_insert.to_dict("records")

    col_sql = ", ".join(f'"{c}"' for c in cols_to_insert)
    placeholders = ", ".join(f"%({c})s" for c in cols_to_insert)
    insert_sql = (
        f'INSERT INTO {_DATA_SCHEMA}."{table_name}" ({col_sql}) VALUES ({placeholders})'
    )

    with get_conn() as conn:
        cur = conn.cursor()
        psycopg2.extras.execute_batch(cur, insert_sql, rows_to_insert, page_size=500)
        conn.commit()

    return {"inserted": len(rows_to_insert), "table": table_name}


# ------------------------------------------------------------------ #
# DELETE /data-manager/table/{table_name}/rows
# ------------------------------------------------------------------ #

class DeleteRowsRequest(BaseModel):
    primary_key_column: str
    values: List[Any]


@router.delete("/table/{table_name}/rows")
def delete_rows(table_name: str, body: DeleteRowsRequest) -> Dict:
    """Delete rows from a data schema table by primary key values."""
    if not body.values:
        raise HTTPException(status_code=400, detail="No row values provided.")

    with get_conn() as conn:
        cur = conn.cursor()
        _assert_table_exists(cur, table_name)

        # Confirm the PK column actually exists in this table
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s AND column_name = %s
            """,
            (_DATA_SCHEMA, table_name, body.primary_key_column),
        )
        if not cur.fetchone():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Column '{body.primary_key_column}' does not exist "
                    f"in {_DATA_SCHEMA}.{table_name}."
                ),
            )

        cur.execute(
            f'DELETE FROM {_DATA_SCHEMA}."{table_name}" '
            f'WHERE "{body.primary_key_column}" = ANY(%s)',
            (body.values,),
        )
        deleted = cur.rowcount
        conn.commit()

    return {"deleted": deleted, "table": table_name}
