"""
Chart Description Service — DB get/save for chart_description_cache.

Cache key: SHA256(chart_title|chart_type|x_label|y_label)
Descriptions are static — generated once and never expire.
"""

from __future__ import annotations
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def make_cache_key(chart_title: str, chart_type: str, x_label: Optional[str], y_label: Optional[str]) -> str:
    raw = f"{chart_title}|{chart_type}|{x_label or ''}|{y_label or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_description(cache_key: str, conn) -> Optional[str]:
    """Return cached description or None if not found."""
    cur = conn.cursor()
    cur.execute(
        "SELECT description FROM internal.chart_description_cache WHERE cache_key = %s",
        (cache_key,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def save_description(
    cache_key: str,
    chart_title: str,
    chart_type: str,
    x_label: Optional[str],
    y_label: Optional[str],
    description: str,
    conn,
) -> None:
    """Insert description into cache. Skips if key already exists (race-safe)."""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO internal.chart_description_cache
            (cache_key, chart_title, chart_type, x_label, y_label, description)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (cache_key) DO NOTHING
        """,
        (cache_key, chart_title, chart_type, x_label, y_label, description),
    )
    conn.commit()
    logger.info("chart_description_cache: saved description for '%s'", chart_title)
