"""
Deduplicator — Step 3 of the Insight Narrator pipeline.

Phase 1: key-based suppression using pg_insight_history.
  - A (client, entity_type, entity_id, insight_type, metric_name, period) tuple
    that was surfaced within the last SUPPRESS_WINDOW_DAYS is suppressed.
  - After filtering, apply freshness-weighted ranking so truly novel insights
    float to the top.

Phase 2 (pgvector cosine similarity) is slotted for later — the architecture
is prepared for it here via a comment placeholder.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from intelligence.insight_narrator.schemas import FlaggedMetric

logger = logging.getLogger(__name__)

SUPPRESS_WINDOW_DAYS = 7     # suppress same key seen within N days
MAX_INSIGHTS         = 7     # cap total insights surfaced per run


# ── Key-based suppression ─────────────────────────────────────────────────────

def _load_recent_keys(conn, client_id: int, window_days: int) -> set[tuple]:
    """
    Returns a set of (entity_type, entity_id, metric_name, period) tuples
    seen within the suppression window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT entity_type, entity_id, metric_name, period
        FROM internal.pg_insight_history
        WHERE client_id = %s
          AND last_seen_at >= %s
        """,
        (client_id, cutoff),
    )
    return {(r[0], r[1], r[2], r[3]) for r in cur.fetchall()}


def _upsert_history(conn, client_id: int, metrics: list[FlaggedMetric]) -> None:
    """
    Insert or update pg_insight_history for each metric being surfaced.
    Uses INSERT … ON CONFLICT DO UPDATE to keep seen_count and last_seen_at fresh.
    """
    if not metrics:
        return
    cur = conn.cursor()
    for m in metrics:
        cur.execute(
            """
            INSERT INTO internal.pg_insight_history
                (client_id, entity_type, entity_id, insight_type, metric_name, period,
                 first_seen_at, last_seen_at, seen_count)
            VALUES
                (%s, %s, %s, %s, %s, %s, NOW(), NOW(), 1)
            ON CONFLICT (client_id, entity_type, entity_id, insight_type, metric_name, period)
            DO UPDATE SET
                last_seen_at = NOW(),
                seen_count   = pg_insight_history.seen_count + 1
            """,
            (client_id, m.entity_type, m.entity_id, "anomaly", m.metric_name, m.period),
        )
    conn.commit()


# ── Freshness-weighted ranking ────────────────────────────────────────────────

def _freshness_multiplier(conn, client_id: int, metric: FlaggedMetric) -> float:
    """
    1.0  → never seen before (or last seen > 21 days ago)
    0.0  → seen very recently (within suppression window)
    Linearly interpolated between 0 and 21 days.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT last_seen_at
        FROM internal.pg_insight_history
        WHERE client_id = %s
          AND entity_type = %s
          AND entity_id   = %s
          AND metric_name = %s
          AND period      = %s
        ORDER BY last_seen_at DESC
        LIMIT 1
        """,
        (client_id, metric.entity_type, metric.entity_id, metric.metric_name, metric.period),
    )
    row = cur.fetchone()
    if row is None:
        return 1.0   # brand new
    days_since = (datetime.now(timezone.utc) - row[0]).days
    return min(1.0, days_since / 21.0)


def _ranking_score(metric: FlaggedMetric, freshness: float) -> float:
    """
    score = zscore_magnitude × freshness_multiplier
    Fall back to abs(delta_pct) / 100 if no z-score available.
    """
    magnitude = abs(metric.zscore) if metric.zscore is not None else abs(metric.delta_pct) / 100.0
    return magnitude * freshness


# ── Public entry point ────────────────────────────────────────────────────────

def deduplicate_and_rank(
    conn,
    client_id: int,
    flagged: list[FlaggedMetric],
    window_days: int = SUPPRESS_WINDOW_DAYS,
    max_insights: int = MAX_INSIGHTS,
) -> list[FlaggedMetric]:
    """
    1. Load recently-seen keys from pg_insight_history.
    2. Filter out suppressed metrics.
    3. Rank survivors by freshness-weighted score.
    4. Return top max_insights metrics.

    Phase 2 slot: after step 2, embed survivors with text-embedding model,
    query pgvector for cosine similarity > 0.88, and suppress matches.
    """
    if not flagged:
        return []

    recent_keys = _load_recent_keys(conn, client_id, window_days)

    novel: list[FlaggedMetric] = []
    for m in flagged:
        key = (m.entity_type, m.entity_id, m.metric_name, m.period)
        if key not in recent_keys:
            novel.append(m)

    if not novel:
        logger.info("deduplicator: all %d flagged metrics suppressed", len(flagged))
        return []

    # Rank by freshness-weighted score
    scored = [
        (m, _ranking_score(m, _freshness_multiplier(conn, client_id, m)))
        for m in novel
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    top = [m for m, _ in scored[:max_insights]]
    logger.info(
        "deduplicator: %d flagged → %d novel → %d surfaced",
        len(flagged), len(novel), len(top),
    )
    return top


def record_surfaced(conn, client_id: int, metrics: list[FlaggedMetric]) -> None:
    """
    Write the surfaced metrics into pg_insight_history so future runs
    can suppress them. Call AFTER the LLM narration succeeds.
    """
    _upsert_history(conn, client_id, metrics)
