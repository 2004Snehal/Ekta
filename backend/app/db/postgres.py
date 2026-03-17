"""
PostgreSQL connection pool and query executor.

Uses psycopg2 with a simple connection pool (ThreadedConnectionPool).
All results are returned as list[dict] for easy JSON serialisation and
Pandas ingestion downstream.
"""

from typing import Any, Dict, List
from urllib.parse import unquote

import pandas as pd
import psycopg2
import psycopg2.extras
from psycopg2 import pool

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger("nlq.db")

# Module-level connection pool; initialised once at startup
_pool: pool.ThreadedConnectionPool | None = None


def _parse_database_url(url: str) -> dict:
    """
    Parse a postgresql:// URL safely, handling special characters in the password
    (e.g. &, /, *, +) that break standard urlparse.

    Strategy:
      - Use rfind('@') to locate the real userinfo/host boundary.
      - Use find(':') on userinfo to split username from password.
    """
    # Strip scheme
    rest = url.split("://", 1)[1]  # "user:pass@host:port/dbname"

    # Last '@' separates credentials from host (password may contain '@' in theory, but rare)
    at = rest.rfind("@")
    userinfo = rest[:at]
    hostinfo = rest[at + 1:]

    # Split username:password (first colon only)
    colon = userinfo.find(":")
    username = unquote(userinfo[:colon])
    password = unquote(userinfo[colon + 1:])

    # Split host:port/dbname
    slash = hostinfo.find("/")
    host_port = hostinfo[:slash]
    dbname = hostinfo[slash + 1:]

    if ":" in host_port:
        host, port_str = host_port.rsplit(":", 1)
        port = int(port_str)
    else:
        host, port = host_port, 5432

    return {"host": host, "port": port, "dbname": dbname, "user": username, "password": password}


def init_pool() -> None:
    """Create the global connection pool. Called once from main.py lifespan."""
    global _pool
    settings = get_settings()

    if settings.database_url:
        params = _parse_database_url(settings.database_url)
        logger.info(
            "Initialising PostgreSQL connection pool via DATABASE_URL → %s:%s/%s",
            params["host"], params["port"], params["dbname"],
        )
        _pool = pool.ThreadedConnectionPool(minconn=1, maxconn=10, **params)
    else:
        logger.info(
            "Initialising PostgreSQL connection pool → %s:%s/%s",
            settings.db_host, settings.db_port, settings.db_name,
        )
        _pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
        )
    logger.info("PostgreSQL pool ready.")


def close_pool() -> None:
    """Gracefully close all connections. Called on app shutdown."""
    global _pool
    if _pool:
        _pool.closeall()
        logger.info("PostgreSQL pool closed.")


def _get_pool() -> pool.ThreadedConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised. Call init_pool() first.")
    return _pool


def execute_query(sql: str) -> List[Dict[str, Any]]:
    """
    Run a SELECT query and return results as a list of dicts.

    Raises psycopg2.Error on DB errors so the self-healing layer can catch them.
    """
    db_pool = _get_pool()
    conn = db_pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            logger.info("Executing SQL:\n%s", sql)
            cur.execute(sql)
            rows = cur.fetchall()
            result = [dict(row) for row in rows]
            logger.info("Query returned %d rows.", len(result))
            return result
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        db_pool.putconn(conn)


def execute_query_as_df(sql: str) -> pd.DataFrame:
    """Convenience wrapper — returns a Pandas DataFrame instead of a list."""
    rows = execute_query(sql)
    return pd.DataFrame(rows)


def check_connection() -> bool:
    """Ping the database. Returns True if reachable."""
    try:
        execute_query("SELECT 1")
        return True
    except Exception as exc:
        logger.error("DB connectivity check failed: %s", exc)
        return False
