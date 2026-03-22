"""
Database dependency for FastAPI routes.
Uses a psycopg2 connection pool shared across requests.
"""

import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from urllib.parse import urlparse, unquote, quote
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from backend_config import DATABASE_URL


def _safe_parse(url: str):
    _at = url.rfind("@")
    _scheme_end = url.index("://") + 3
    if _at != -1:
        userinfo = url[_scheme_end:_at]
        if ":" in userinfo:
            _user, _raw_pass = userinfo.split(":", 1)
            # Decode first (in case already URL-encoded), then re-encode cleanly
            _decoded_pass = unquote(_raw_pass)
            url = url[:_scheme_end] + _user + ":" + quote(_decoded_pass, safe="") + url[_at:]
    return urlparse(url)

_p = _safe_parse(DATABASE_URL)
_pool = pool.ThreadedConnectionPool(
    minconn=1,
    maxconn=5,
    host=_p.hostname,
    port=_p.port or 5432,
    dbname=_p.path.lstrip("/"),
    user=_p.username,
    password=unquote(_p.password) if _p.password else None,
    sslmode="require",
)


@contextmanager
def get_conn():
    conn = _pool.getconn()
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        # Always rollback any uncommitted transaction before returning
        # the connection to the pool.  Read-only routes that never call
        # conn.commit() leave an implicit transaction open, which holds
        # ACCESS SHARE locks and blocks DDL (ALTER TABLE) indefinitely.
        try:
            conn.rollback()
        except Exception:
            pass
        _pool.putconn(conn)


def get_cursor(conn):
    cursor = conn.cursor()
    return cursor


@contextmanager
def get_ddl_conn():
    """
    Direct psycopg2 connection with autocommit=True for DDL statements
    (ALTER TABLE, CREATE TABLE, etc.).

    Uses DIRECT_DATABASE_URL if set (recommended for Supabase — set this to
    the direct connection URL, e.g. postgres://...@db.xxx.supabase.co:5432/...
    to bypass the session/transaction pooler entirely).

    Falls back to DATABASE_URL used as a raw DSN so all query-string
    parameters (e.g. ?pgbouncer=true) are preserved rather than dropped
    by the component-by-component parsing used for the pool.
    """
    ddl_url = os.getenv("DIRECT_DATABASE_URL") or DATABASE_URL
    conn = psycopg2.connect(ddl_url)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()
