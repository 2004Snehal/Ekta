"""
Insight Narrator Pipeline — orchestrates Steps 1–6.

    Step 1  Data pull          → detector.py
    Step 2  Anomaly detection  → detector.py
    Step 3  Deduplication      → deduplicator.py
    Step 4  LLM narration      → narrator.py
    Step 5  Schema validation  → schemas.py (Pydantic)
    Step 6  Cache + store      → insight_cache table + insight_log

Usage
-----
    # From FastAPI route or APScheduler job:
    from intelligence.insight_narrator.pipeline import run_pipeline
    result = run_pipeline(client_id=1)

Stale-while-revalidate
----------------------
The FastAPI endpoint always returns the cached result immediately.
If the cache is older than CACHE_STALE_HOURS, it triggers background
regeneration WITHOUT blocking the request.
"""

from __future__ import annotations
import json
import logging
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.deps import get_conn
from intelligence.insight_narrator.detector      import detect_anomalies
from intelligence.insight_narrator.deduplicator  import deduplicate_and_rank, record_surfaced
from intelligence.insight_narrator.narrator      import narrate
from intelligence.insight_narrator.schemas       import NarratorResponse

logger = logging.getLogger(__name__)

CACHE_STALE_HOURS = 24
_RUNNING: set[int] = set()   # simple in-process guard against concurrent runs


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(client_id: int) -> str:
    return f"narrator:{client_id}"


def _read_cache(conn, client_id: int) -> dict | None:
    cur = conn.cursor()
    cur.execute(
        "SELECT insights, generated_at, data_as_of FROM insight_cache WHERE cache_key = %s",
        (_cache_key(client_id),),
    )
    row = cur.fetchone()
    if row is None:
        return None
    insights_raw, generated_at, data_as_of = row
    return {
        "insights":     insights_raw,  # already a dict (JSONB → Python dict via psycopg2)
        "generated_at": generated_at.isoformat(),
        "data_as_of":   data_as_of.isoformat(),
    }


def _write_cache(conn, client_id: int, response: NarratorResponse) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO insight_cache (cache_key, insights, generated_at, data_as_of)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (cache_key) DO UPDATE SET
            insights     = EXCLUDED.insights,
            generated_at = EXCLUDED.generated_at,
            data_as_of   = EXCLUDED.data_as_of
        """,
        (
            _cache_key(client_id),
            json.dumps(response.model_dump()),
            datetime.now(timezone.utc),
            date.fromisoformat(response.data_as_of if len(response.data_as_of) == 10 else response.data_as_of + "-01"),
        ),
    )
    conn.commit()


def _write_insight_log(conn, client_id: int, response: NarratorResponse) -> None:
    """Persist each card into insight_log for the /insights/ query endpoint."""
    if not response.insights:
        return
    cur = conn.cursor()
    for card in response.insights:
        cur.execute(
            """
            INSERT INTO insight_log
                (client_id, insight_type, severity, title, body,
                 dimensions, metric_value, baseline_value, delta_pct,
                 category, entity_type, entity_id, period,
                 current_value, reference_value, confidence, root_cause_hint,
                 generated_at)
            VALUES
                (%s, %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 NOW())
            """,
            (
                client_id,
                card.category,            # insight_type reuses category
                card.severity,
                card.title,
                card.body,
                json.dumps({"entity_type": card.entity_type, "entity_id": card.entity_id}),
                card.current_value,
                card.reference_value,
                card.delta_pct,
                card.category,
                card.entity_type,
                card.entity_id,
                card.period,
                card.current_value,
                card.reference_value,
                card.confidence,
                card.root_cause_hint,
            ),
        )
    conn.commit()


# ── Core pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(client_id: int) -> NarratorResponse | None:
    """
    Full pipeline: detect → dedup → narrate → cache → log.
    Returns the NarratorResponse on success, None on fatal error.

    Uses an in-process lock to prevent concurrent runs for the same client.
    """
    if client_id in _RUNNING:
        logger.warning("pipeline already running for client %s — skipping", client_id)
        return None

    _RUNNING.add(client_id)
    try:
        with get_conn() as conn:
            # Step 1 + 2: data pull + statistical detection
            flagged = detect_anomalies(conn, client_id)
            if not flagged:
                logger.info("pipeline: no anomalies detected for client %s", client_id)
                # Still write an empty cache so the UI knows it ran
                empty = NarratorResponse(
                    client_id  = client_id,
                    period     = date.today().strftime("%Y-%m"),
                    generated_at = datetime.now(timezone.utc).isoformat(),
                    data_as_of = date.today().isoformat(),
                    digest     = "No significant anomalies detected this period.",
                    insights   = [],
                )
                _write_cache(conn, client_id, empty)
                return empty

            # Step 3: deduplication + ranking
            surfaced = deduplicate_and_rank(conn, client_id, flagged)
            if not surfaced:
                logger.info("pipeline: all anomalies suppressed by dedup for client %s", client_id)
                empty = NarratorResponse(
                    client_id    = client_id,
                    period       = flagged[0].period,
                    generated_at = datetime.now(timezone.utc).isoformat(),
                    data_as_of   = flagged[0].period,
                    digest       = "All anomalies this period were surfaced recently. Nothing new to report.",
                    insights     = [],
                )
                _write_cache(conn, client_id, empty)
                return empty

            # Step 4: LLM narration
            cards, digest = narrate(surfaced, include_digest=True)
            if not cards:
                logger.error("pipeline: narrator returned no cards for client %s", client_id)
                return None

            # Step 5: assemble validated response
            period     = surfaced[0].period
            data_as_of = period  # most recent period in analysis
            response   = NarratorResponse(
                client_id    = client_id,
                period       = period,
                generated_at = datetime.now(timezone.utc).isoformat(),
                data_as_of   = data_as_of,
                digest       = digest,
                insights     = cards,
            )

            # Step 6: cache + store
            _write_cache(conn, client_id, response)
            _write_insight_log(conn, client_id, response)
            record_surfaced(conn, client_id, surfaced)

            logger.info(
                "pipeline: client %s — %d insights generated and cached",
                client_id, len(cards),
            )
            return response

    except Exception as e:
        logger.exception("pipeline fatal error for client %s: %s", client_id, e)
        return None
    finally:
        _RUNNING.discard(client_id)


# ── Read-path: serve from cache ───────────────────────────────────────────────

def get_cached(client_id: int) -> dict | None:
    """
    Returns the cached NarratorResponse dict for the client, or None if
    no cache exists. Caller decides whether to trigger background refresh.
    """
    with get_conn() as conn:
        return _read_cache(conn, client_id)


def cache_age_hours(cached: dict) -> float:
    """Returns how many hours old the cached result is."""
    generated_at = datetime.fromisoformat(cached["generated_at"])
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - generated_at
    return delta.total_seconds() / 3600


def is_stale(cached: dict, threshold_hours: float = CACHE_STALE_HOURS) -> bool:
    return cache_age_hours(cached) > threshold_hours
