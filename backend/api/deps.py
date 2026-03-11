"""
Database dependency for FastAPI routes.
Uses a psycopg2 connection pool shared across requests.
"""

import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import DATABASE_URL

_pool = pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)


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
