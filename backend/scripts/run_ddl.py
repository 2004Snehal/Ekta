#!/usr/bin/env python3
"""
Standalone DDL runner — executes ALTER TABLE statements via a fresh
psycopg2 connection, completely outside FastAPI's connection pool.

Reads a JSON task from stdin, connects to the DB using DATABASE_URL
(or DIRECT_DATABASE_URL if set), runs the DDL, and prints JSON result
to stdout.

Usage (called by the backend, not manually):
    echo '{"table":"dim_channel","columns":[{"name":"dummy","type":"TEXT","nullable":true}]}' \
        | python3 scripts/run_ddl.py
"""

import json
import os
import re
import sys
from urllib.parse import urlparse, unquote, quote

ALLOWED_TYPES = {
    "TEXT", "VARCHAR", "INTEGER", "BIGINT", "NUMERIC", "BOOLEAN",
    "TIMESTAMPTZ", "TIMESTAMP", "DATE", "UUID", "JSONB",
    "FLOAT", "REAL", "SMALLINT", "SERIAL", "BIGSERIAL",
}
IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")
DATA_SCHEMA = "data"


def safe_parse(url: str):
    at = url.rfind("@")
    scheme_end = url.index("://") + 3
    if at != -1:
        userinfo = url[scheme_end:at]
        if ":" in userinfo:
            user, raw_pass = userinfo.split(":", 1)
            decoded_pass = unquote(raw_pass)
            url = url[:scheme_end] + user + ":" + quote(decoded_pass, safe="") + url[at:]
    return urlparse(url)


def main():
    try:
        import psycopg2
    except ImportError:
        print(json.dumps({"ok": False, "error": "psycopg2 not installed"}))
        sys.exit(1)

    raw = sys.stdin.read()
    try:
        task = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    table = task.get("table", "").strip()
    columns = task.get("columns", [])

    if not table or not IDENT_RE.match(table):
        print(json.dumps({"ok": False, "error": f"Invalid table name: {table!r}"}))
        sys.exit(1)

    db_url = os.getenv("DIRECT_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print(json.dumps({"ok": False, "error": "DATABASE_URL not set"}))
        sys.exit(1)

    p = safe_parse(db_url)

    try:
        conn = psycopg2.connect(
            host=p.hostname,
            port=p.port or 5432,
            dbname=p.path.lstrip("/"),
            user=p.username,
            password=unquote(p.password) if p.password else None,
            sslmode="require",
        )
        conn.autocommit = True
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"DB connect failed: {e}"}))
        sys.exit(1)

    added = []
    errors = []
    try:
        cur = conn.cursor()

        # Verify table exists
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s",
            (DATA_SCHEMA, table),
        )
        if not cur.fetchone():
            print(json.dumps({"ok": False, "error": f"Table '{table}' not found in schema '{DATA_SCHEMA}'"}))
            sys.exit(1)

        for col in columns:
            name = col.get("name", "").strip()
            col_type = col.get("type", "TEXT").upper()
            nullable = col.get("nullable", True)

            if not name or not IDENT_RE.match(name):
                errors.append(f"Skipped invalid column name: {name!r}")
                continue

            base_type = col_type.split("(")[0]
            if base_type not in ALLOWED_TYPES:
                errors.append(f"Skipped unsupported type: {col_type!r}")
                continue

            null_clause = "" if nullable else " NOT NULL DEFAULT ''"
            sql = (
                f'ALTER TABLE {DATA_SCHEMA}."{table}" '
                f'ADD COLUMN IF NOT EXISTS "{name}" {col_type}{null_clause}'
            )
            try:
                cur.execute(sql)
                added.append(name)
            except Exception as e:
                conn.rollback()  # reset for next statement
                errors.append(f"Failed to add '{name}': {e}")

        # Verify columns were actually added
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            (DATA_SCHEMA, table),
        )
        actual_cols = {r[0] for r in cur.fetchall()}
        verified = [c for c in added if c in actual_cols]
        missing = [c for c in added if c not in actual_cols]
        if missing:
            errors.append(f"Columns executed OK but not found in DB: {missing}")

        cur.close()
    finally:
        conn.close()

    print(json.dumps({
        "ok": len(verified) > 0 if added else False,
        "added": verified,
        "errors": errors,
    }))


if __name__ == "__main__":
    main()
