"""
Database dependency for FastAPI routes.
Uses a psycopg2 connection pool shared across requests.
"""

import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from urllib.parse import urlparse, unquote
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from backend_config import DATABASE_URL

_p = urlparse(DATABASE_URL)
_pool = pool.ThreadedConnectionPool(
    minconn=2,
    maxconn=10,
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
