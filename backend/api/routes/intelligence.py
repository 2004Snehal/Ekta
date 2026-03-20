"""
Intelligence routes — reads from operational tables written to by intelligence agents.
"""

import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from typing import Optional, Any
from api.deps import get_conn

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/insights/")
def get_insights(
    client_id: int = Query(1),
    insight_type: Optional[str] = Query(None, description="anomaly | recommendation | trend | digest"),
    entity_type: Optional[str] = Query(None, description="channel | user | language | input_type"),
    entity_id: Optional[str] = Query(None, description="entity identifier e.g. channel_code or user_name"),
    is_read: Optional[bool] = Query(None),
    limit: int = Query(50),
):
    """Recent insights from insight_log."""
    filters = ["client_id = %s"]
    params = [client_id]

    if insight_type:
        filters.append("insight_type = %s")
        params.append(insight_type)
    if entity_type:
        filters.append("entity_type = %s")
        params.append(entity_type)
    if entity_id:
        filters.append("entity_id = %s")
        params.append(entity_id)
    if is_read is not None:
        filters.append("is_read = %s")
        params.append(is_read)

    where = " AND ".join(filters)
    params.append(limit)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT insight_id, insight_type, severity, title, body,
                   entity_type, entity_id, metric_name,
                   metric_value, baseline_value, delta_pct,
                   generated_at, is_read
            FROM internal.insight_log
            WHERE {where}
            ORDER BY generated_at DESC
            LIMIT %s
            """,
            params,
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for row in rows:
            if row.get("generated_at"):
                row["generated_at"] = row["generated_at"].isoformat()

    return {"data": rows, "count": len(rows)}


# ── Insight Narrator endpoints ────────────────────────────────────────────────

@router.get("/narrator/insights")
def get_narrator_insights(
    client_id: int = Query(1),
    profile: Optional[str] = Query(None, description="leadership|client_success|operations|editorial|tech"),
    background_tasks: BackgroundTasks = None,
):
    """
    Returns cached Insight Narrator output for a client.

    Stale-while-revalidate pattern:
    - Serves the last cached result immediately (zero LLM latency).
    - If the cache is older than 24 h and no job is running, fires
      background regeneration so the NEXT request gets fresh data.
    - If no cache exists at all, runs the v2 pipeline synchronously.
    """
    from intelligence.insight_narrator.pipeline import (
        get_cached, is_stale, run_pipeline_v2,
    )

    cached = get_cached(client_id)

    if cached is None:
        # First-ever call: run v2 pipeline synchronously
        logger.info("narrator: no cache for client %s — running v2 pipeline now", client_id)
        result = run_pipeline_v2(client_id, profile=profile)
        if result is None:
            raise HTTPException(status_code=500, detail="Narrator pipeline failed")
        return result.model_dump(mode="json")

    # Cache exists: check staleness and optionally trigger background refresh
    if is_stale(cached) and background_tasks is not None:
        logger.info("narrator: cache stale for client %s — scheduling v2 background refresh", client_id)
        background_tasks.add_task(run_pipeline_v2, client_id, profile)

    return cached["insights"]


@router.get("/narrator/health")
def get_narrator_health(client_id: int = Query(1)):
    """Fast endpoint returning only entity health scores from cache."""
    from intelligence.insight_narrator.pipeline import get_cached

    cached = get_cached(client_id)
    if cached is None:
        return {"entity_health": [], "pulse_score": 0}

    insights = cached.get("insights", {})
    if isinstance(insights, dict):
        return {
            "entity_health": insights.get("entity_health", []),
            "pulse_score": insights.get("pulse_score", 0),
            "pulse_delta": insights.get("pulse_delta"),
        }
    return {"entity_health": [], "pulse_score": 0}


@router.post("/narrator/run")
def trigger_narrator(
    client_id: int = Query(1),
    profile: Optional[str] = Query(None),
    sync: bool = Query(False, description="Run synchronously for debugging"),
    background_tasks: BackgroundTasks = None,
):
    """
    Manually trigger a narrator v2 pipeline run for a client.
    Runs in background — returns immediately with a 202 Accepted.
    Pass ?sync=true to run synchronously (blocks, but shows errors directly).
    """
    from intelligence.insight_narrator.pipeline import run_pipeline_v2

    if sync:
        # Synchronous mode: blocks and returns actual error details
        import traceback
        from intelligence.insight_narrator.pipeline import _RUNNING
        _RUNNING.discard(client_id)  # clear any stuck lock from previous failed run
        try:
            result = run_pipeline_v2(client_id, profile=profile)
            if result is None:
                raise HTTPException(status_code=500, detail="Pipeline returned None — check uvicorn terminal for traceback")
            return result.model_dump(mode="json")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("narrator sync run error")
            raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")

    if background_tasks is not None:
        background_tasks.add_task(run_pipeline_v2, client_id, profile)
        return {"status": "accepted", "message": f"Narrator v2 pipeline queued for client {client_id}"}
    else:
        result = run_pipeline_v2(client_id, profile=profile)
        if result is None:
            raise HTTPException(status_code=500, detail="Narrator pipeline failed")
        return result.model_dump(mode="json")


@router.post("/narrator/feedback")
def record_insight_feedback(
    insight_id: int = Query(...),
    feedback: int = Query(..., description="1 = helpful, -1 = not helpful"),
):
    """Record thumbs-up / thumbs-down feedback for an insight card."""
    if feedback not in (1, -1):
        raise HTTPException(status_code=400, detail="feedback must be 1 or -1")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE internal.insight_log SET user_feedback = %s WHERE insight_id = %s",
            (feedback, insight_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="insight not found")
        conn.commit()
    return {"status": "ok"}


# ── Chart Insight Agent endpoints ────────────────────────────────────────────

@router.get("/chart/description")
def get_chart_description(
    chart_title: str = Query(...),
    chart_type:  str = Query(...),
    x_label:     Optional[str] = Query(None),
    y_label:     Optional[str] = Query(None),
):
    """
    Returns a static 1–2 sentence description of what a chart depicts.
    Checks DB cache first; generates via LLM and saves on cache miss.
    Cache key is derived from chart metadata only — no data dependency.
    """
    from intelligence.chart_insight_agent.agent import generate_chart_description
    from intelligence.chart_insight_agent.schemas import ChartDescriptionRequest
    from intelligence.chart_insight_agent.description_service import (
        make_cache_key, get_description, save_description,
    )

    cache_key = make_cache_key(chart_title, chart_type, x_label, y_label)

    try:
        with get_conn() as conn:
            cached = get_description(cache_key, conn)
            if cached:
                logger.info("chart_description: cache hit for '%s'", chart_title)
                return {"description": cached, "cached": True}

            # Cache miss — generate via LLM
            logger.info("chart_description: cache miss for '%s' — calling LLM", chart_title)
            req = ChartDescriptionRequest(
                chart_title=chart_title, chart_type=chart_type,
                x_label=x_label, y_label=y_label,
            )
            result = generate_chart_description(req)
            save_description(cache_key, chart_title, chart_type, x_label, y_label, result.description, conn)
            return {"description": result.description, "cached": False}

    except Exception as e:
        logger.error("chart description failed: %s", e)
        raise HTTPException(status_code=500, detail="Chart description generation failed")


@router.post("/chart/data-insights")
def get_chart_data_insights(payload: dict[str, Any]):
    """
    On-demand LLM analysis of a single chart's visible data.
    Called by the frontend on hover. Always calls the LLM — no DB cache.
    Client-side caches the result keyed by a data fingerprint.
    """
    from intelligence.chart_insight_agent.agent import generate_chart_insights
    from intelligence.chart_insight_agent.schemas import ChartInsightRequest

    try:
        req = ChartInsightRequest(**payload)
        logger.info("[/chart/data-insights] chart: '%s', type: %s, rows: %d", req.chart_title, req.chart_type, len(req.data))
        result = generate_chart_insights(req)
        logger.info("[/chart/data-insights] done — %d insight(s)", len(result.insights))
        return result.model_dump()
    except Exception as e:
        logger.error("chart data-insights failed: %s", e)
        import traceback
        raise HTTPException(status_code=500, detail=traceback.format_exc())


@router.get("/kpis/registry")
def get_kpi_registry(
    client_id: int = Query(1),
    active_only: bool = Query(True),
):
    """All defined KPIs from kpi_registry (client-specific + global)."""
    params = [client_id]
    active_clause = "AND is_active = TRUE" if active_only else ""

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT id, client_id, name, description, sql_expression,
                   formula, category, unit, usefulness_score,
                   dimensions, created_by, is_active,
                   created_at, last_computed
            FROM internal.kpi_registry
            WHERE (client_id = %s OR client_id IS NULL) {active_clause}
            ORDER BY created_at DESC
            """,
            params,
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for row in rows:
            if row.get("created_at"):
                row["created_at"] = row["created_at"].isoformat()
            if row.get("last_computed"):
                row["last_computed"] = row["last_computed"].isoformat()

    return {"data": rows, "count": len(rows)}
