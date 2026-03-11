"""
Intelligence routes — reads from operational tables written to by intelligence agents.
"""

from fastapi import APIRouter, Query
from typing import Optional
from api.deps import get_conn

router = APIRouter()


@router.get("/insights/")
def get_insights(
    client_id: int = Query(1),
    insight_type: Optional[str] = Query(None, description="anomaly | recommendation | trend | digest"),
    is_read: Optional[bool] = Query(None),
    limit: int = Query(50),
):
    """Recent insights from insight_log."""
    filters = ["client_id = %s"]
    params = [client_id]

    if insight_type:
        filters.append("insight_type = %s")
        params.append(insight_type)
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
                   dimensions, metric_value, baseline_value, delta_pct,
                   generated_at, is_read
            FROM insight_log
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


@router.get("/forecasts/")
def get_forecasts(
    client_id: int = Query(1),
    channel_id: Optional[int] = Query(None),
    metric_name: Optional[str] = Query(None),
):
    """3-month forward projections from forecast_log."""
    filters = ["f.client_id = %s"]
    params = [client_id]

    if channel_id:
        filters.append("f.channel_id = %s")
        params.append(channel_id)
    if metric_name:
        filters.append("f.metric_name = %s")
        params.append(metric_name)

    where = " AND ".join(filters)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                f.forecast_id,
                f.channel_id,
                dc.channel_name,
                dc.channel_code,
                f.metric_name,
                f.forecast_month,
                f.predicted_value,
                f.lower_bound,
                f.upper_bound,
                f.model_used,
                f.generated_at
            FROM forecast_log f
            JOIN dim_channel dc ON dc.channel_id = f.channel_id
            WHERE {where}
            ORDER BY f.channel_id, f.metric_name, f.forecast_month
            """,
            params,
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for row in rows:
            if row.get("forecast_month"):
                row["forecast_month"] = row["forecast_month"].isoformat()
            if row.get("generated_at"):
                row["generated_at"] = row["generated_at"].isoformat()

    return {"data": rows, "count": len(rows)}


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
            SELECT kpi_id, client_id, kpi_name, kpi_description,
                   sql_definition, dimensions, created_by, is_active,
                   created_at, last_computed
            FROM kpi_registry
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
