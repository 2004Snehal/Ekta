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
        "SELECT insights, generated_at, data_as_of FROM internal.insight_cache WHERE cache_key = %s",
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
        INSERT INTO internal.insight_cache (cache_key, insights, generated_at, data_as_of)
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


def _safe_numeric(val) -> float | None:
    """Coerce a value to float, returning None if it's not numeric."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _write_insight_log(conn, client_id: int, response: NarratorResponse) -> None:
    """Persist each card into insight_log for the /insights/ query endpoint."""
    if not response.insights:
        return
    cur = conn.cursor()
    for card in response.insights:
        cur.execute(
            """
            INSERT INTO internal.insight_log
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
                _safe_numeric(card.current_value),
                _safe_numeric(card.reference_value),
                _safe_numeric(card.delta_pct),
                card.category,
                card.entity_type,
                str(card.entity_id) if card.entity_id is not None else None,
                card.period,
                _safe_numeric(card.current_value),
                _safe_numeric(card.reference_value),
                _safe_numeric(card.confidence),
                card.root_cause_hint,
            ),
        )
    conn.commit()


# ── Core pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(
    client_id: int,
    profile: str | None = None,
) -> NarratorResponse | None:
    """
    Full pipeline: detect → dedup → narrate → cache → log.
    Returns the NarratorResponse on success, None on fatal error.

    ``profile`` is forwarded to ``narrate()`` so the LLM frames insight cards
    for the appropriate user role. Defaults to None (generic framing).

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
            cards, digest = narrate(surfaced, include_digest=True, profile=profile)
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


# ═══════════════════════════════════════════════════════════════════════════════
# v2 Pipeline — 7-phase narrator with parallel analyzers
# ═══════════════════════════════════════════════════════════════════════════════

from concurrent.futures import ThreadPoolExecutor
from intelligence.insight_narrator.data_loader import hydrate
from intelligence.insight_narrator.consecutive_trend import detect_consecutive_trends
from intelligence.insight_narrator.funnel_analyzer import analyze_funnel
from intelligence.insight_narrator.cross_dimension import detect_cross_dimension_patterns
from intelligence.insight_narrator.operational_risk import detect_operational_risks
from intelligence.insight_narrator.data_quality_checker import check_data_quality
from intelligence.insight_narrator.milestone_detector import detect_milestones
from intelligence.insight_narrator.root_cause import decompose_root_cause
from intelligence.insight_narrator.entity_synthesizer import synthesize_entities
from intelligence.insight_narrator.follow_up_tracker import track_follow_ups
from intelligence.insight_narrator.signal_router import route_signals
from intelligence.insight_narrator.health_scorer import score_entity_health
from intelligence.insight_narrator.narrator import narrate_v2
from intelligence.insight_narrator.schemas import (
    NarratorResponseV2, FlaggedMetric, DQPeriodScore, PeriodSummary, MetricComparison,
)


def run_pipeline_v2(
    client_id: int,
    profile: str | None = None,
) -> NarratorResponseV2 | None:
    """
    Full v2 pipeline: hydrate → 7 parallel analyzers → synthesize → track →
    route → narrate (3 parallel LLM) → health score → assemble → cache.
    """
    if client_id in _RUNNING:
        logger.warning("v2 pipeline already running for client %s — skipping", client_id)
        return None

    _RUNNING.add(client_id)
    try:
        with get_conn() as conn:
            import time as _t
            t0 = _t.perf_counter()

            # ── Phase 0: Data Hydration ────────────────────────────────────
            bundle = hydrate(conn, client_id)
            logger.info(f"[v2] Phase 0 hydration: {_t.perf_counter()-t0:.2f}s")

            # ── Phase 1: Parallel Signal Generation ────────────────────────
            t1 = _t.perf_counter()

            all_signals: list[FlaggedMetric] = []
            funnel_summary = None
            dq_scorecard = None

            # Run existing anomaly detector (it hits DB directly — keep as is)
            try:
                anomaly_signals = detect_anomalies(conn, client_id)
                for s in anomaly_signals:
                    s.insight_source = "anomaly"
                all_signals.extend(anomaly_signals)
            except Exception as e:
                logger.error(f"[v2] Anomaly detector failed: {e}")

            # Run remaining 6 analyzers in parallel (all use bundle, no DB)
            with ThreadPoolExecutor(max_workers=6) as pool:
                fut_trend     = pool.submit(detect_consecutive_trends, bundle)
                fut_funnel    = pool.submit(analyze_funnel, bundle)
                fut_crossdim  = pool.submit(detect_cross_dimension_patterns, bundle)
                fut_oprisk    = pool.submit(detect_operational_risks, bundle)
                fut_dq        = pool.submit(check_data_quality, bundle)
                fut_milestone = pool.submit(detect_milestones, bundle)

                try:
                    all_signals.extend(fut_trend.result())
                except Exception as e:
                    logger.error(f"[v2] Trend detector failed: {e}")

                try:
                    funnel_sigs, funnel_summary = fut_funnel.result()
                    all_signals.extend(funnel_sigs)
                except Exception as e:
                    logger.error(f"[v2] Funnel analyzer failed: {e}")

                try:
                    all_signals.extend(fut_crossdim.result())
                except Exception as e:
                    logger.error(f"[v2] Cross-dim failed: {e}")

                try:
                    all_signals.extend(fut_oprisk.result())
                except Exception as e:
                    logger.error(f"[v2] Op risk failed: {e}")

                try:
                    dq_sigs, dq_scorecard = fut_dq.result()
                    all_signals.extend(dq_sigs)
                except Exception as e:
                    logger.error(f"[v2] DQ checker failed: {e}")

                try:
                    all_signals.extend(fut_milestone.result())
                except Exception as e:
                    logger.error(f"[v2] Milestone detector failed: {e}")

            logger.info(f"[v2] Phase 1 analyzers: {_t.perf_counter()-t1:.2f}s, {len(all_signals)} signals")

            # ── Phase 1.5: Root Cause Decomposition ────────────────────────
            for sig in all_signals:
                if sig.insight_source == "anomaly" and sig.entity_type == "channel":
                    try:
                        breakdown = decompose_root_cause(
                            bundle, sig.entity_type, sig.entity_id, sig.metric_name,
                        )
                        if breakdown:
                            sig.root_cause_breakdown = breakdown
                    except Exception as e:
                        logger.warning(f"[v2] Root cause failed for {sig.entity_id}: {e}")

            # ── Phase 2: Entity Synthesis ──────────────────────────────────
            singles, bundles = synthesize_entities(all_signals)
            # For bundles, use the highest severity signal's data
            for b in bundles:
                top_sig = max(b["signals"], key=lambda s: {"high":3,"medium":2,"low":1}.get(s.severity, 0))
                top_sig.suggested_action = (
                    f"Multiple signals ({b['signal_count']}) detected for {b['entity_label']}. "
                    f"This entity needs comprehensive review."
                )
                singles.append(top_sig)

            # ── Phase 3: Follow-Up Tracking ────────────────────────────────
            tagged, resolved = track_follow_ups(singles, bundle)

            # ── Phase 4: Signal Routing ────────────────────────────────────
            routed = route_signals(tagged, resolved)

            # ── Phase 5: LLM Narration (3 parallel calls) ─────────────────
            t5 = _t.perf_counter()
            all_cards, digest = narrate_v2(routed, profile=profile)
            logger.info(f"[v2] Phase 5 narration: {_t.perf_counter()-t5:.2f}s, {len(all_cards)} cards")

            # ── Phase 6: Health Scoring ────────────────────────────────────
            entity_health, pulse_score = score_entity_health(bundle, tagged)

            # ── Phase 7: Assemble + Cache ──────────────────────────────────
            period = bundle.monthly_kpis[0].get("month", date.today().strftime("%Y-%m")) if bundle.monthly_kpis else date.today().strftime("%Y-%m")

            # Build period summary
            period_summary = _build_period_summary(bundle)

            # Route cards to response sections
            response = NarratorResponseV2(
                client_id=client_id,
                period=period,
                generated_at=datetime.now(timezone.utc).isoformat(),
                data_as_of=date.today().isoformat(),
                # Pulse
                pulse_score=pulse_score,
                digest=digest,
                period_summary=period_summary,
                entity_health=entity_health,
                top_signals=sorted(
                    [c for c in all_cards if c.status != "resolved"],
                    key=lambda c: ({"high": 3, "medium": 2, "low": 1}.get(c.severity, 0), abs(c.delta_pct)),
                    reverse=True,
                )[:5],
                follow_ups=[c for c in all_cards if c.status in ("ongoing", "worsening")],
                resolved=[c for c in all_cards if c.status == "resolved"],
                summary_counts={
                    "watchlist": len(routed["watchlist"]["flagged_metrics"]) + len(routed["watchlist"]["consecutive_trends"]) + len(routed["watchlist"]["cross_dimension"]) + len(routed["watchlist"]["milestones"]),
                    "pipeline": len(routed["pipeline"]["funnel_gaps"]) + len(routed["pipeline"]["operational_risks"]),
                    "dq": len(routed["data_governance"]["dq_issues"]),
                },
                # Watchlist
                flagged_metrics=[c for c in all_cards if c.insight_source == "anomaly" and c.status != "resolved"],
                consecutive_trends=[c for c in all_cards if c.insight_source == "consecutive"],
                cross_dimension=[c for c in all_cards if c.insight_source == "cross_dim"],
                milestones=[c for c in all_cards if c.insight_source == "milestone" and c.status != "resolved"],
                # Pipeline
                funnel=funnel_summary,
                funnel_gaps=[c for c in all_cards if c.insight_source == "funnel"],
                operational_risks=[c for c in all_cards if c.insight_source == "op_risk"],
                # DQ
                dq_scorecard=dq_scorecard,
                dq_issues=[c for c in all_cards if c.insight_source == "dq"],
                # Dashboard layer — both lists contain FlaggedMetric, convert to InsightCard
                kpi_insights=[_signal_to_card(s) for s in routed.get("kpi_insights", [])[:5]],
                dashboard_banner=[_signal_to_card(s) for s in routed.get("dashboard_banner", [])[:3]],
                # History
                last_resolved=[c for c in all_cards if c.status == "resolved"][:3],
                checks_run=[
                    f"7 analyzers executed",
                    f"{len(all_signals)} raw signals generated",
                    f"{len(tagged)} signals after follow-up tracking",
                    f"{len(all_cards)} insight cards produced",
                ],
                # Backward compat
                insights=all_cards,
            )

            # Cache as v1-compatible + v2 extensions
            _write_cache_v2(conn, client_id, response)
            # Log + history writes are non-fatal — cache is already committed above
            try:
                _write_insight_log_v2(conn, client_id, response)
                _update_history(conn, client_id, tagged, resolved)
            except Exception as log_err:
                logger.warning(f"[v2] Log/history write failed (non-fatal): {log_err}")
                try:
                    conn.rollback()
                except Exception:
                    pass

            total_time = _t.perf_counter() - t0
            logger.info(f"[v2] Pipeline complete: {total_time:.2f}s, {len(all_cards)} cards, pulse={pulse_score}")
            return response

    except Exception as e:
        logger.exception("v2 pipeline fatal error for client %s: %s", client_id, e)
        return None
    finally:
        _RUNNING.discard(client_id)


def _signal_to_card(sig) -> "InsightCard":
    """Convert a FlaggedMetric to a minimal InsightCard (for dashboard_banner before narration)."""
    from intelligence.insight_narrator.schemas import InsightCard
    if isinstance(sig, InsightCard):
        return sig
    return InsightCard(
        title=f"{sig.entity_label}: {sig.metric_name.replace('_', ' ')} change",
        body=sig.suggested_action or f"Delta: {sig.delta_pct:.1f}%",
        category="anomaly",
        severity=sig.severity,
        metric_name=sig.metric_name,
        entity_type=sig.entity_type,
        entity_id=sig.entity_id,
        current_value=sig.current_value,
        reference_value=sig.reference_value,
        delta_pct=sig.delta_pct,
        period=sig.period,
        status=sig.status,
        insight_source=sig.insight_source,
    )


def _build_period_summary(bundle) -> PeriodSummary | None:
    """Build period-over-period comparison from monthly_kpis."""
    from collections import defaultdict

    if not bundle.monthly_kpis:
        return None

    # Aggregate by month
    monthly: dict[str, dict] = defaultdict(lambda: {"created": 0, "published": 0, "hours": 0.0})
    for row in bundle.monthly_kpis:
        m = row.get("month", "")
        monthly[m]["created"] += float(row.get("created_count", 0) or 0)
        monthly[m]["published"] += float(row.get("published_count", 0) or 0)
        monthly[m]["hours"] += float(row.get("total_uploaded_hours", 0) or 0)

    sorted_months = sorted(monthly.keys())
    if len(sorted_months) < 2:
        return None

    curr_m = sorted_months[-1]
    prev_m = sorted_months[-2]
    curr = monthly[curr_m]
    prev = monthly[prev_m]

    metrics = []
    for name, label in [("created", "Videos Created"), ("published", "Videos Published"), ("hours", "Usage Hours")]:
        c = curr[name]
        p = prev[name]
        delta = ((c - p) / p * 100) if p > 0 else 0
        direction = "improved" if delta > 2 else ("declined" if delta < -2 else "stable")
        metrics.append(MetricComparison(
            metric_name=name, metric_label=label,
            current_value=round(c, 1), previous_value=round(p, 1),
            delta_pct=round(delta, 1), direction=direction,
        ))

    # Add publish rate
    curr_rate = (curr["published"] / curr["created"] * 100) if curr["created"] > 0 else 0
    prev_rate = (prev["published"] / prev["created"] * 100) if prev["created"] > 0 else 0
    rate_delta = curr_rate - prev_rate
    metrics.append(MetricComparison(
        metric_name="publish_rate", metric_label="Publish Rate",
        current_value=round(curr_rate, 1), previous_value=round(prev_rate, 1),
        delta_pct=round(rate_delta, 1),
        direction="improved" if rate_delta > 2 else ("declined" if rate_delta < -2 else "stable"),
    ))

    improved = sum(1 for m in metrics if m.direction == "improved")
    declined = sum(1 for m in metrics if m.direction == "declined")
    stable = sum(1 for m in metrics if m.direction == "stable")

    return PeriodSummary(
        current_period=curr_m, previous_period=prev_m,
        metrics=metrics, improved_count=improved,
        declined_count=declined, stable_count=stable,
    )


def _write_cache_v2(conn, client_id: int, response: NarratorResponseV2) -> None:
    """Write v2 response to cache (backward-compatible column + v2 extensions)."""
    cur = conn.cursor()
    response_dict = response.model_dump(mode="json")
    cur.execute(
        """
        INSERT INTO internal.insight_cache (cache_key, insights, generated_at, data_as_of)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (cache_key) DO UPDATE SET
            insights     = EXCLUDED.insights,
            generated_at = EXCLUDED.generated_at,
            data_as_of   = EXCLUDED.data_as_of
        """,
        (
            _cache_key(client_id),
            json.dumps(response_dict),
            datetime.now(timezone.utc),
            date.today(),
        ),
    )
    conn.commit()


def _write_insight_log_v2(conn, client_id: int, response: NarratorResponseV2) -> None:
    """Persist each card into insight_log with v2 fields."""
    if not response.insights:
        return
    cur = conn.cursor()
    for card in response.insights:
        cur.execute(
            """
            INSERT INTO internal.insight_log
                (client_id, insight_type, severity, title, body,
                 dimensions, metric_value, baseline_value, delta_pct,
                 category, entity_type, entity_id, period,
                 current_value, reference_value, confidence, root_cause_hint,
                 status, tab_destination, suggested_action, insight_source,
                 consecutive_periods,
                 generated_at)
            VALUES
                (%s, %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s,
                 NOW())
            """,
            (
                client_id, card.category, card.severity, card.title, card.body,
                json.dumps({"entity_type": card.entity_type, "entity_id": card.entity_id}),
                _safe_numeric(card.current_value), _safe_numeric(card.reference_value),
                _safe_numeric(card.delta_pct),
                card.category, card.entity_type,
                str(card.entity_id) if card.entity_id else None,
                card.period,
                _safe_numeric(card.current_value), _safe_numeric(card.reference_value),
                _safe_numeric(card.confidence), card.root_cause_hint,
                card.status, card.tab_destination, card.suggested_action,
                card.insight_source, card.consecutive_periods,
            ),
        )
    conn.commit()


def _update_history(conn, client_id: int, tagged: list, resolved: list) -> None:
    """Update pg_insight_history with status and consecutive_periods."""
    cur = conn.cursor()
    for sig in tagged:
        cur.execute(
            """
            INSERT INTO internal.pg_insight_history
                (client_id, entity_type, entity_id, insight_type, metric_name,
                 period, first_seen_at, last_seen_at, seen_count,
                 status, consecutive_periods, last_severity)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), 1, %s, %s, %s)
            ON CONFLICT (client_id, entity_type, entity_id, insight_type, metric_name, period)
            DO UPDATE SET
                last_seen_at = NOW(),
                seen_count = internal.pg_insight_history.seen_count + 1,
                status = EXCLUDED.status,
                consecutive_periods = EXCLUDED.consecutive_periods,
                last_severity = EXCLUDED.last_severity
            """,
            (
                client_id, sig.entity_type, str(sig.entity_id),
                sig.insight_source, sig.metric_name, sig.period,
                sig.status, sig.consecutive_periods or 1, sig.severity,
            ),
        )
    for sig in resolved:
        cur.execute(
            """
            UPDATE internal.pg_insight_history
            SET status = 'resolved', last_seen_at = NOW()
            WHERE client_id = %s AND entity_type = %s AND entity_id = %s AND metric_name = %s
            """,
            (client_id, sig.entity_type, str(sig.entity_id), sig.metric_name),
        )
    conn.commit()
