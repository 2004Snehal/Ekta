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
import re
from typing import Any, Dict, List, Optional

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


# ── Data Lab: allowed PostgreSQL types ────────────────────────────────────────

_ALLOWED_PG_TYPES = {
    "TEXT", "VARCHAR", "INTEGER", "BIGINT", "NUMERIC", "BOOLEAN",
    "TIMESTAMPTZ", "TIMESTAMP", "DATE", "UUID", "JSONB",
    "FLOAT", "REAL", "SMALLINT", "SERIAL", "BIGSERIAL",
}

_IDENT_RE = re.compile(r'^[A-Za-z0-9_]+$')


def _valid_ident(name: str) -> bool:
    return bool(name and _IDENT_RE.match(name))


# ── Data Lab: schema relationships ────────────────────────────────────────────

_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS internal.data_lab_links (
    id          BIGSERIAL PRIMARY KEY,
    from_table  TEXT NOT NULL,
    from_column TEXT NOT NULL,
    to_table    TEXT NOT NULL,
    to_column   TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
"""


def _ensure_links_table(cur) -> None:
    cur.execute(_LINKS_DDL)


@router.get("/schema/relationships")
def list_relationships(_admin=Depends(require_admin)) -> Dict:
    """Return FK constraints + logical links in the data schema."""
    with get_conn() as conn:
        cur = conn.cursor()

        # FK constraints from information_schema
        cur.execute(
            """
            SELECT
                tc.constraint_name,
                kcu.table_name  AS from_table,
                kcu.column_name AS from_column,
                ccu.table_name  AS to_table,
                ccu.column_name AS to_column,
                'fk'            AS link_type
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema    = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
             AND tc.table_schema    = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema    = %s
            ORDER BY kcu.table_name, kcu.column_name
            """,
            (_DATA_SCHEMA,),
        )
        fk_rows = cur.fetchall()

        # Logical (soft) links stored in internal.data_lab_links
        _ensure_links_table(cur)
        cur.execute(
            "SELECT id, from_table, from_column, to_table, to_column FROM internal.data_lab_links ORDER BY id"
        )
        soft_rows = cur.fetchall()

    relationships = [
        {
            "constraint_name": r[0],
            "from_table": r[1],
            "from_column": r[2],
            "to_table": r[3],
            "to_column": r[4],
            "link_type": r[5],
        }
        for r in fk_rows
    ] + [
        {
            "constraint_name": f"soft_{r[0]}",
            "from_table": r[1],
            "from_column": r[2],
            "to_table": r[3],
            "to_column": r[4],
            "link_type": "logical",
        }
        for r in soft_rows
    ]
    return {"relationships": relationships}


class CreateRelationshipRequest(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    link_type: str = "logical"   # "fk" or "logical"


@router.post("/schema/relationships")
def create_relationship(
    body: CreateRelationshipRequest,
    _admin=Depends(require_admin),
) -> Dict:
    """
    Define a link between two columns.

    link_type='fk'      — real FK constraint (requires referential integrity).
    link_type='logical' — soft link stored in metadata (no FK constraint).
    """
    for name in [body.from_table, body.to_table, body.from_column, body.to_column]:
        if not _valid_ident(name):
            raise HTTPException(status_code=400, detail=f"Invalid identifier: '{name}'")

    with get_conn() as conn:
        cur = conn.cursor()
        _assert_table_exists(cur, body.from_table)
        _assert_table_exists(cur, body.to_table)

        if body.link_type == "fk":
            constraint = f"fk_{body.from_table}_{body.from_column}_{body.to_table}"
            try:
                cur.execute(
                    f'ALTER TABLE {_DATA_SCHEMA}."{body.from_table}" '
                    f'ADD CONSTRAINT "{constraint}" '
                    f'FOREIGN KEY ("{body.from_column}") '
                    f'REFERENCES {_DATA_SCHEMA}."{body.to_table}" ("{body.to_column}")'
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {"created": constraint, "link_type": "fk"}
        else:
            _ensure_links_table(cur)
            cur.execute(
                """
                INSERT INTO internal.data_lab_links (from_table, from_column, to_table, to_column)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (body.from_table, body.from_column, body.to_table, body.to_column),
            )
            link_id = cur.fetchone()[0]
            conn.commit()
            return {"created": f"soft_{link_id}", "link_type": "logical"}


@router.delete("/schema/relationships/{constraint_name}")
def delete_relationship(
    constraint_name: str,
    from_table: str = Query(...),
    _admin=Depends(require_admin),
) -> Dict:
    """Remove a FK constraint or a logical link."""
    if not _valid_ident(from_table):
        raise HTTPException(status_code=400, detail="Invalid table name.")

    with get_conn() as conn:
        cur = conn.cursor()

        if constraint_name.startswith("soft_"):
            link_id_str = constraint_name[5:]
            if not link_id_str.isdigit():
                raise HTTPException(status_code=400, detail="Invalid link id.")
            _ensure_links_table(cur)
            cur.execute("DELETE FROM internal.data_lab_links WHERE id = %s", (int(link_id_str),))
        else:
            if not _valid_ident(constraint_name):
                raise HTTPException(status_code=400, detail="Invalid constraint name.")
            cur.execute(
                f'ALTER TABLE {_DATA_SCHEMA}."{from_table}" '
                f'DROP CONSTRAINT IF EXISTS "{constraint_name}"'
            )
        conn.commit()

    return {"dropped": constraint_name}


# ── Data Lab: create table from manual column definitions ─────────────────────

class ColumnDefModel(BaseModel):
    name: str
    type: str = "TEXT"
    nullable: bool = True
    is_pk: bool = False


class CreateTableManualRequest(BaseModel):
    table_name: str
    columns: List[ColumnDefModel]


@router.post("/table/create-manual")
def create_table_manual(
    body: CreateTableManualRequest,
    _admin=Depends(require_admin),
) -> Dict:
    """Create a new table from manual column definitions (no CSV needed)."""
    table_name = body.table_name.strip()
    if not _valid_ident(table_name):
        raise HTTPException(
            status_code=400,
            detail="Table name may only contain letters, numbers, and underscores.",
        )
    if not body.columns:
        raise HTTPException(status_code=400, detail="At least one column is required.")

    col_defs: List[str] = []
    pk_cols: List[str] = []
    for col in body.columns:
        name = col.name.strip()
        if not _valid_ident(name):
            raise HTTPException(status_code=400, detail=f"Invalid column name: '{name}'")
        base_type = col.type.upper().split("(")[0]
        if base_type not in _ALLOWED_PG_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported type: '{col.type}'")
        null_clause = "" if col.nullable else " NOT NULL"
        col_defs.append(f'"{name}" {col.type}{null_clause}')
        if col.is_pk:
            pk_cols.append(f'"{name}"')

    if pk_cols:
        col_defs.append(f'PRIMARY KEY ({", ".join(pk_cols)})')

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
            (_DATA_SCHEMA, table_name),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Table '{table_name}' already exists.")

        cur.execute(
            f'CREATE TABLE {_DATA_SCHEMA}."{table_name}" ({", ".join(col_defs)})'
        )
        conn.commit()

    return {"created": table_name, "columns": [c.name for c in body.columns]}


# ── Data Lab: add columns to existing table ───────────────────────────────────

class AddColumnsRequest(BaseModel):
    columns: List[ColumnDefModel]


@router.post("/table/{table_name}/add-columns")
def add_columns_to_table(
    table_name: str,
    body: AddColumnsRequest,
    _admin=Depends(require_admin),
) -> Dict:
    """Add one or more new columns to an existing data schema table.

    Uses the existing pool connection — DDL is transactional in PostgreSQL
    so ALTER TABLE works inside a normal BEGIN/COMMIT block.
    """
    if not body.columns:
        raise HTTPException(status_code=400, detail="No columns provided.")

    with get_conn() as conn:
        cur = conn.cursor()
        _assert_table_exists(cur, table_name)

        # Supabase pooler has a short default statement_timeout that kills
        # DDL before it completes.  SET LOCAL scopes to this transaction only
        # so the pool connection resets to normal after commit.
        cur.execute("SET LOCAL statement_timeout = '60s'")

        added: List[str] = []
        for col in body.columns:
            name = col.name.strip()
            if not _valid_ident(name):
                continue
            base_type = col.type.upper().split("(")[0]
            if base_type not in _ALLOWED_PG_TYPES:
                continue
            null_clause = "" if col.nullable else " NOT NULL DEFAULT ''"
            sql = (
                f'ALTER TABLE {_DATA_SCHEMA}."{table_name}" '
                f'ADD COLUMN IF NOT EXISTS "{name}" {col.type}{null_clause}'
            )
            logger.info("DDL: %s", sql)
            cur.execute(sql)
            added.append(name)

        if not added:
            raise HTTPException(status_code=400, detail="No valid columns to add.")

        conn.commit()

        # Verify columns were actually created
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            (_DATA_SCHEMA, table_name),
        )
        actual_cols = {r[0] for r in cur.fetchall()}
        verified = [c for c in added if c in actual_cols]
        missing = [c for c in added if c not in actual_cols]
        if missing:
            logger.warning("Columns not found after ALTER: %s", missing)

    return {
        "altered": table_name,
        "columns_added": verified if verified else added,
    }


# ── Data Lab: update cell with cascade ────────────────────────────────────────

class UpdateCellRequest(BaseModel):
    join_column: str    # Column used to identify matching rows (PK or FK/link column)
    join_value: Any     # Value of join_column for the target row(s)
    target_column: str  # Column whose value is being changed
    new_value: Any      # New value to set
    cascade: bool = True


def _get_all_links(cur, table_name: str, join_column: str) -> List[Dict]:
    """Return all (related_table, related_col) pairs linked to (table_name, join_column)
    via FK constraints OR logical links in data_lab_links."""
    links: List[Dict] = []

    # FK constraints
    cur.execute(
        """
        SELECT
            kcu.table_name  AS from_table,
            kcu.column_name AS from_column,
            ccu.table_name  AS to_table,
            ccu.column_name AS to_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema    = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.table_schema    = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema    = %s
          AND (
                (kcu.table_name = %s AND kcu.column_name = %s)
             OR (ccu.table_name = %s AND ccu.column_name = %s)
          )
        """,
        (_DATA_SCHEMA, table_name, join_column, table_name, join_column),
    )
    for from_t, from_c, to_t, to_c in cur.fetchall():
        if from_t == table_name and from_c == join_column:
            related_table, related_col = to_t, to_c
        else:
            related_table, related_col = from_t, from_c
        if related_table != table_name:
            links.append({"table": related_table, "col": related_col})

    # Logical links
    try:
        cur.execute(
            """
            SELECT from_table, from_column, to_table, to_column
            FROM internal.data_lab_links
            WHERE (from_table = %s AND from_column = %s)
               OR (to_table   = %s AND to_column   = %s)
            """,
            (table_name, join_column, table_name, join_column),
        )
        for from_t, from_c, to_t, to_c in cur.fetchall():
            if from_t == table_name and from_c == join_column:
                related_table, related_col = to_t, to_c
            else:
                related_table, related_col = from_t, from_c
            if related_table != table_name:
                links.append({"table": related_table, "col": related_col})
    except Exception:
        pass  # data_lab_links may not exist yet

    return links


@router.patch("/table/{table_name}/update-cell")
def update_cell(
    table_name: str,
    body: UpdateCellRequest,
    _admin=Depends(require_admin),
) -> Dict:
    """
    Update target_column to new_value for all rows where join_column = join_value.

    If cascade=True, propagates the same target_column change to every table
    linked via FK constraint or logical link on join_column — matching rows
    by their own join column value (even if row order differs).
    """
    for col in [body.join_column, body.target_column]:
        if not _valid_ident(col):
            raise HTTPException(status_code=400, detail=f"Invalid column name: '{col}'")

    with get_conn() as conn:
        cur = conn.cursor()
        _assert_table_exists(cur, table_name)

        # Update source table
        cur.execute(
            f'UPDATE {_DATA_SCHEMA}."{table_name}" '
            f'SET "{body.target_column}" = %s '
            f'WHERE "{body.join_column}" = %s',
            (body.new_value, body.join_value),
        )
        rows_updated = cur.rowcount
        cascaded: List[Dict] = []

        if body.cascade:
            links = _get_all_links(cur, table_name, body.join_column)
            for link in links:
                related_table = link["table"]
                related_join_col = link["col"]

                # Only cascade if the related table actually has the target column
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s AND column_name = %s
                    """,
                    (_DATA_SCHEMA, related_table, body.target_column),
                )
                if not cur.fetchone():
                    continue

                cur.execute(
                    f'UPDATE {_DATA_SCHEMA}."{related_table}" '
                    f'SET "{body.target_column}" = %s '
                    f'WHERE "{related_join_col}" = %s',
                    (body.new_value, body.join_value),
                )
                if cur.rowcount > 0:
                    cascaded.append({
                        "table": related_table,
                        "join_column": related_join_col,
                        "rows_updated": cur.rowcount,
                    })

        conn.commit()

    return {
        "table": table_name,
        "rows_updated": rows_updated,
        "cascaded": cascaded,
    }
