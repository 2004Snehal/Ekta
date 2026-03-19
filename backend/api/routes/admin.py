"""
Admin routes — data management and user profile assignment.

All endpoints require role='admin' (enforced via JWT dependency).
Admin operates only on the 'data' schema; 'internal' schema is never touched here.

Endpoints:
  GET    /admin/users                           — list all users
  PATCH  /admin/users/{user_id}/profile         — assign user_profile to a user

  GET    /admin/tables                          — list data schema tables (same as data-manager)
  GET    /admin/table/{table_name}/rows         — paginated rows (same as data-manager)
  POST   /admin/table/{table_name}/upload-csv   — create NEW table from CSV (or append)
  POST   /admin/table/{table_name}/append-csv   — append rows to existing table
  DELETE /admin/table/{table_name}/rows         — delete rows by PK
  DELETE /admin/table/{table_name}              — drop an entire table
"""

from __future__ import annotations

import io
import logging
from typing import Any, Dict, List

import pandas as pd
import psycopg2.extras
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from api.deps import get_conn
from api.routes.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

_DATA_SCHEMA = "data"


# ── Helpers (shared with data_manager) ───────────────────────────────────────

def _assert_table_exists(cur, table_name: str) -> None:
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


# ── User management ───────────────────────────────────────────────────────────

@router.get("/users")
def list_users(_admin=Depends(require_admin)) -> Dict:
    """Return all registered users (id, email, role, user_profile, created_at)."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, email, role, profile, created_at
            FROM internal.users
            ORDER BY created_at DESC
            """
        )
        rows = cur.fetchall()

    return {
        "users": [
            {
                "user_id": str(r[0]),
                "email": r[1],
                "role": r[2],
                "user_profile": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
            }
            for r in rows
        ]
    }


class AssignProfileRequest(BaseModel):
    user_profile: str


@router.patch("/users/{user_id}/profile")
def assign_profile(
    user_id: str,
    body: AssignProfileRequest,
    _admin=Depends(require_admin),
) -> Dict:
    """Assign a user_profile to a user. Admin-only."""
    if not body.user_profile.strip():
        raise HTTPException(status_code=400, detail="user_profile cannot be empty.")

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE internal.users SET profile = %s
            WHERE id = %s
            RETURNING id, email, role, profile
            """,
            (body.user_profile.strip(), user_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")
        conn.commit()

    return {
        "user_id": str(row[0]),
        "email": row[1],
        "role": row[2],
        "user_profile": row[3],
    }


# ── Table list ────────────────────────────────────────────────────────────────

@router.get("/tables")
def list_tables(_admin=Depends(require_admin)) -> Dict:
    """Return all tables in the data schema with column definitions and PKs."""
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT c.table_name, c.column_name, c.data_type,
                   c.column_default, c.is_nullable, c.ordinal_position
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
    for table_name, col_name, data_type, col_default, is_nullable, _ in col_rows:
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


# ── Table rows ────────────────────────────────────────────────────────────────

@router.get("/table/{table_name}/rows")
def get_table_rows(
    table_name: str,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _admin=Depends(require_admin),
) -> Dict:
    with get_conn() as conn:
        cur = conn.cursor()
        _assert_table_exists(cur, table_name)

        cur = conn.cursor()
        cur.execute(f'SELECT COUNT(*) FROM {_DATA_SCHEMA}."{table_name}"')
        total = cur.fetchone()[0]

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            f'SELECT * FROM {_DATA_SCHEMA}."{table_name}" LIMIT %s OFFSET %s',
            (limit, offset),
        )
        rows = [dict(r) for r in cur.fetchall()]

    safe_rows = [
        {
            k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v)
            for k, v in row.items()
        }
        for row in rows
    ]

    return {"rows": safe_rows, "total": total, "limit": limit, "offset": offset}


# ── Create table from CSV (admin-only new-table upload) ───────────────────────

@router.post("/table/{table_name}/upload-csv")
async def create_table_from_csv(
    table_name: str,
    file: UploadFile = File(...),
    _admin=Depends(require_admin),
) -> Dict:
    """
    Create a new table in the data schema from a CSV file.
    If the table already exists, rows are appended instead (upsert-friendly).

    Column types are inferred from the CSV; all columns default to TEXT
    so no type errors occur on import. The table gets an auto _row_id PK.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    # Validate table name (alphanumeric + underscores only)
    if not table_name.replace("_", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail="Table name may only contain letters, numbers, and underscores.",
        )

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc

    if df.empty:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    with get_conn() as conn:
        cur = conn.cursor()

        # Check if table already exists
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (_DATA_SCHEMA, table_name),
        )
        table_exists = cur.fetchone() is not None

        if not table_exists:
            # Build CREATE TABLE with TEXT columns + serial PK
            col_defs = ", ".join(f'"{c}" TEXT' for c in df.columns)
            cur.execute(
                f'CREATE TABLE {_DATA_SCHEMA}."{table_name}" '
                f'(_row_id BIGSERIAL PRIMARY KEY, {col_defs})'
            )

        # Insert rows
        cols_sql = ", ".join(f'"{c}"' for c in df.columns)
        placeholders = ", ".join(f"%({c})s" for c in df.columns)
        insert_sql = (
            f'INSERT INTO {_DATA_SCHEMA}."{table_name}" ({cols_sql}) VALUES ({placeholders})'
        )
        df_insert = df.where(pd.notna(df), None)
        rows_to_insert = df_insert.to_dict("records")
        psycopg2.extras.execute_batch(cur, insert_sql, rows_to_insert, page_size=500)
        conn.commit()

    action = "appended" if table_exists else "created"
    return {
        "action": action,
        "table": table_name,
        "inserted": len(rows_to_insert),
        "columns": list(df.columns),
    }


# ── Append CSV to existing table ──────────────────────────────────────────────

@router.post("/table/{table_name}/append-csv")
async def append_csv(
    table_name: str,
    file: UploadFile = File(...),
    _admin=Depends(require_admin),
) -> Dict:
    """Append rows from CSV to an existing data schema table (same rules as data-manager)."""
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
            detail=f"CSV is missing required column(s): {sorted(missing)}.",
        )

    unknown = csv_cols - table_cols
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"CSV contains columns not in table '{table_name}': {sorted(unknown)}.",
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


# ── Delete rows ───────────────────────────────────────────────────────────────

class DeleteRowsRequest(BaseModel):
    primary_key_column: str
    values: List[Any]


@router.delete("/table/{table_name}/rows")
def delete_rows(
    table_name: str,
    body: DeleteRowsRequest,
    _admin=Depends(require_admin),
) -> Dict:
    """Delete rows from a data schema table by primary key values."""
    if not body.values:
        raise HTTPException(status_code=400, detail="No row values provided.")

    with get_conn() as conn:
        cur = conn.cursor()
        _assert_table_exists(cur, table_name)

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
                detail=f"Column '{body.primary_key_column}' does not exist in {_DATA_SCHEMA}.{table_name}.",
            )

        cur.execute(
            f'DELETE FROM {_DATA_SCHEMA}."{table_name}" '
            f'WHERE "{body.primary_key_column}" = ANY(%s)',
            (body.values,),
        )
        deleted = cur.rowcount
        conn.commit()

    return {"deleted": deleted, "table": table_name}


# ── Drop table ────────────────────────────────────────────────────────────────

@router.delete("/table/{table_name}")
def drop_table(
    table_name: str,
    _admin=Depends(require_admin),
) -> Dict:
    """Permanently drop a table from the data schema."""
    with get_conn() as conn:
        cur = conn.cursor()
        _assert_table_exists(cur, table_name)
        cur.execute(f'DROP TABLE {_DATA_SCHEMA}."{table_name}" CASCADE')
        conn.commit()

    return {"dropped": table_name}
