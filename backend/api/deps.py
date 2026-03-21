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
    finally:
        _pool.putconn(conn)


def get_cursor(conn):
    cursor = conn.cursor()
    return cursor
