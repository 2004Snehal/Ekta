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
    """Return dropdown options: channels, input types, languages, date range."""
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT DISTINCT dch.channel_id, dch.channel_name, dch.channel_code
            FROM data.dim_channel dch
            JOIN data.fact_created_videos f ON f.channel_id = dch.channel_id
            WHERE f.client_id = %s
            ORDER BY dch.channel_code
            """,
            (client_id,),
        )
        channels = [{"id": r[0], "name": r[1], "code": r[2]} for r in cur.fetchall()]

        cur.execute(
            "SELECT input_type_id, type_name, category FROM data.dim_input_type ORDER BY type_name"
        )
        input_types = [{"id": r[0], "name": r[1], "category": r[2]} for r in cur.fetchall()]

        cur.execute(
            "SELECT language_id, language_code, language_name FROM data.dim_language ORDER BY language_name"
        )
        languages = [{"id": r[0], "code": r[1], "name": r[2]} for r in cur.fetchall()]

        cur.execute(
            "SELECT MIN(uploaded_at), MAX(uploaded_at) FROM data.fact_created_videos WHERE client_id = %s",
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
    channel_id: Optional[int] = Query(None),
    input_type_id: Optional[int] = Query(None),
    language_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Monthly KPI rollup from mv_monthly_kpis with optional filters."""
    filters = ["m.client_id = %s"]
    params = [client_id]

    if channel_id:
        filters.append("m.channel_id = %s")
        params.append(channel_id)
    if input_type_id:
        filters.append("m.input_type_id = %s")
        params.append(input_type_id)
    if language_id:
        filters.append("m.language_id = %s")
        params.append(language_id)
    if date_from:
        filters.append("m.month >= %s")
        params.append(date_from)
    if date_to:
        filters.append("m.month <= %s")
        params.append(date_to)

    where = " AND ".join(filters)
    sql = f"""
        SELECT
            m.month,
            m.channel_id,
            dc.channel_code,
            dc.channel_name,
            m.input_type_id,
            di.type_name AS input_type,
            m.output_type_id,
            dot.type_name AS output_type,
            m.language_id,
            dl.language_code,
            SUM(m.created_count)                    AS created_count,
            SUM(m.published_count)                  AS published_count,
            SUM(m.total_uploaded_duration_secs)     AS total_uploaded_secs,
            SUM(m.total_created_duration_secs)      AS total_created_secs,
            SUM(m.total_published_duration_secs)    AS total_published_secs,
            ROUND(
                SUM(m.published_count)::NUMERIC / NULLIF(SUM(m.created_count), 0) * 100, 2
            ) AS publish_rate_pct
        FROM data.mv_monthly_kpis m
        JOIN data.dim_channel  dc ON dc.channel_id  = m.channel_id
        LEFT JOIN data.dim_input_type  di  ON di.input_type_id   = m.input_type_id
        LEFT JOIN data.dim_output_type dot ON dot.output_type_id = m.output_type_id
        LEFT JOIN data.dim_language    dl  ON dl.language_id     = m.language_id
        WHERE {where}
        GROUP BY m.month, m.channel_id, dc.channel_code, dc.channel_name,
                 m.input_type_id, di.type_name,
                 m.output_type_id, dot.type_name,
                 m.language_id, dl.language_code
        ORDER BY m.month DESC, dc.channel_code
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
    """Channel health summary from mv_channel_health."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                dc.channel_id,
                dc.channel_name,
                dc.channel_code,
                ch.total_created,
                ch.total_published,
                ch.publish_rate_pct,
                ch.active_users,
                ch.last_activity
            FROM data.mv_channel_health ch
            JOIN data.dim_channel dc ON dc.channel_id = ch.channel_id
            WHERE ch.client_id = %s
            ORDER BY dc.channel_code
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
    channel_id: Optional[int] = Query(None),
):
    """User performance from mv_user_performance."""
    filters = ["up.client_id = %s"]
    params = [client_id]
    if channel_id:
        filters.append("up.channel_id = %s")
        params.append(channel_id)

    where = " AND ".join(filters)
    sql = f"""
        SELECT
            du.user_id,
            du.user_name,
            du.role,
            du.is_bot,
            dc.channel_id,
            dc.channel_name,
            dc.channel_code,
            up.created_count,
            up.published_count,
            up.publish_rate_pct,
            up.total_uploaded_duration_secs,
            up.total_created_duration_secs
        FROM data.mv_user_performance up
        JOIN data.dim_user    du ON du.user_id    = up.user_id
        JOIN data.dim_channel dc ON dc.channel_id = up.channel_id
        WHERE {where}
        ORDER BY up.created_count DESC
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
    channel_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Aggregate KPI totals for the summary cards. Queries fact table directly."""
    filters = ["client_id = %s"]
    params = [client_id]
    if channel_id:
        filters.append("channel_id = %s")
        params.append(channel_id)
    if date_from:
        filters.append("uploaded_at >= %s")
        params.append(date_from)
    if date_to:
        filters.append("uploaded_at <= %s")
        params.append(date_to)

    where = " AND ".join(filters)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                COUNT(DISTINCT video_id)                                            AS total_uploads,
                COUNT(*)                                                            AS total_outputs,
                COUNT(*) FILTER (WHERE published_flag)                             AS total_published,
                ROUND(
                    COUNT(*) FILTER (WHERE published_flag)::NUMERIC
                    / NULLIF(COUNT(*), 0) * 100, 2
                )                                                                   AS publish_rate_pct
            FROM data.fact_created_videos
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
