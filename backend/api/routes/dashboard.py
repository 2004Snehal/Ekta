"""
Dashboard routes — read from materialized views and dimension tables only.
Never hits fact_created_videos directly on load.
"""

from fastapi import APIRouter, Query
from typing import Optional
from api.deps import get_conn

router = APIRouter()


@router.get("/filters/options")
def get_filter_options(client_id: int = Query(1)):
    """Return dropdown options derived directly from data.shortened_filtered_data."""
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT DISTINCT channel FROM data.shortened_filtered_data WHERE client_id = %s AND channel IS NOT NULL ORDER BY channel",
            (client_id,),
        )
        channels = [{"id": r[0], "name": r[0], "code": r[0]} for r in cur.fetchall()]

        cur.execute(
            "SELECT DISTINCT type FROM data.shortened_filtered_data WHERE client_id = %s AND type IS NOT NULL ORDER BY type",
            (client_id,),
        )
        input_types = [{"id": r[0], "name": r[0], "category": r[0]} for r in cur.fetchall()]

        cur.execute(
            "SELECT DISTINCT language FROM data.shortened_filtered_data WHERE client_id = %s AND language IS NOT NULL ORDER BY language",
            (client_id,),
        )
        languages = [{"id": r[0], "code": r[0], "name": r[0]} for r in cur.fetchall()]

        cur.execute(
            "SELECT MIN(uploaded_at::date), MAX(uploaded_at::date) FROM data.shortened_filtered_data WHERE client_id = %s",
            (client_id,),
        )
        row = cur.fetchone()
        date_range = {"min": row[0].isoformat() if row[0] else None, "max": row[1].isoformat() if row[1] else None}

    return {
        "channels": channels,
        "input_types": input_types,
        "languages": languages,
        "date_range": date_range,
    }


@router.get("/kpis/summary")
def get_kpis_summary(
    client_id: int = Query(1),
    channel: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Monthly KPI rollup from data.shortened_filtered_data with optional filters."""
    filters = ["client_id = %s"]
    params = [client_id]

    if channel:
        filters.append("channel = %s")
        params.append(channel)
    if type:
        filters.append("type = %s")
        params.append(type)
    if language:
        filters.append("language = %s")
        params.append(language)
    if date_from:
        filters.append("uploaded_at::date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("uploaded_at::date <= %s")
        params.append(date_to)

    where = " AND ".join(filters)
    sql = f"""
        SELECT
            DATE_TRUNC('month', uploaded_at::date)::date     AS month,
            COALESCE(channel, 'unknown')                     AS channel_name,
            COALESCE(type, 'unknown')                        AS input_type,
            COALESCE(output_type, 'unknown')                 AS output_type,
            COALESCE(language, 'unknown')                    AS language_code,
            COUNT(*)                                         AS created_count,
            COUNT(*) FILTER (WHERE LOWER(published) = 'yes') AS published_count,
            ROUND(
                COUNT(*) FILTER (WHERE LOWER(published) = 'yes')::NUMERIC
                / NULLIF(COUNT(*), 0) * 100, 2
            )                                                AS publish_rate_pct,
            COALESCE(SUM(uploaded_hours * 3600), 0)         AS total_uploaded_secs
        FROM data.shortened_filtered_data
        WHERE {where}
        GROUP BY 1, 2, 3, 4, 5
        ORDER BY month DESC, channel_name
    """

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for row in rows:
            if row.get("month"):
                row["month"] = row["month"].isoformat()

    return {"data": rows, "count": len(rows)}


@router.get("/channels/health")
def get_channels_health(client_id: int = Query(1)):
    """Channel health summary from data.shortened_filtered_data."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COALESCE(channel, 'unknown')                                    AS channel_name,
                COUNT(*)                                                        AS total_created,
                COUNT(*) FILTER (WHERE LOWER(published) = 'yes')              AS total_published,
                ROUND(
                    COUNT(*) FILTER (WHERE LOWER(published) = 'yes')::NUMERIC
                    / NULLIF(COUNT(*), 0) * 100, 2
                )                                                               AS publish_rate_pct,
                COUNT(DISTINCT uploaded_by)                                     AS active_users,
                MAX(uploaded_at::date)                                          AS last_activity
            FROM data.shortened_filtered_data
            WHERE client_id = %s
            GROUP BY channel
            ORDER BY channel
            """,
            (client_id,),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for row in rows:
            if row.get("last_activity"):
                row["last_activity"] = row["last_activity"].isoformat()

    return {"data": rows}


@router.get("/users/performance")
def get_users_performance(
    client_id: int = Query(1),
    channel: Optional[str] = Query(None),
):
    """User performance from data.shortened_filtered_data."""
    filters = ["client_id = %s"]
    params = [client_id]
    if channel:
        filters.append("channel = %s")
        params.append(channel)

    where = " AND ".join(filters)
    sql = f"""
        SELECT
            COALESCE(uploaded_by, 'unknown')                                AS user_name,
            COALESCE(channel, 'unknown')                                    AS channel_name,
            COUNT(*)                                                        AS created_count,
            COUNT(*) FILTER (WHERE LOWER(published) = 'yes')              AS published_count,
            ROUND(
                COUNT(*) FILTER (WHERE LOWER(published) = 'yes')::NUMERIC
                / NULLIF(COUNT(*), 0) * 100, 2
            )                                                               AS publish_rate_pct,
            COALESCE(SUM(uploaded_hours * 3600), 0)                       AS total_uploaded_duration_secs
        FROM data.shortened_filtered_data
        WHERE {where}
        GROUP BY uploaded_by, channel
        ORDER BY created_count DESC
    """

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    return {"data": rows, "count": len(rows)}


@router.get("/kpis/totals")
def get_kpi_totals(
    client_id: int = Query(1),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Aggregate KPI totals for the summary cards."""
    filters = ["client_id = %s"]
    params = [client_id]
    if date_from:
        filters.append("uploaded_at::date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("uploaded_at::date <= %s")
        params.append(date_to)

    where = " AND ".join(filters)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                COUNT(DISTINCT video_id)                                            AS total_uploads,
                COUNT(*)                                                            AS total_outputs,
                COUNT(*) FILTER (WHERE LOWER(published) = 'yes')                  AS total_published,
                ROUND(
                    COUNT(*) FILTER (WHERE LOWER(published) = 'yes')::NUMERIC
                    / NULLIF(COUNT(*), 0) * 100, 2
                )                                                                   AS publish_rate_pct
            FROM data.shortened_filtered_data
            WHERE {where}
            """,
            params,
        )
        row = cur.fetchone()

    return {
        "total_uploads":    row[0] or 0,
        "total_outputs":    row[1] or 0,
        "total_published":  row[2] or 0,
        "publish_rate_pct": float(row[3]) if row[3] else 0.0,
    }
