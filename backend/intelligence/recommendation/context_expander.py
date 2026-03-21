"""
Context expander — runs 4 targeted SQL queries for each view type.
All queries hit materialized views in the data schema (no fact table scans on the hot path).
"""

import logging
import time
from intelligence.recommendation.models import DashboardContext, ExpandedContext

log = logging.getLogger("recommendation.expander")

_db_cache: dict[str, tuple[float, ExpandedContext]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes

def _get_cache_key(ctx: DashboardContext) -> str:
    return f"{ctx.client_id}:{ctx.view}:{ctx.entity_type}:{ctx.entity_id}:{ctx.entity_name}:{ctx.time_range}"


# ── helpers ────────────────────────────────────────────────────────────────────

def _fetch(conn, sql: str, params: tuple) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
    except Exception as e:
        conn.rollback()
        log.warning(f"[REC] Query failed: {e}")
        return []
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── dispatcher ─────────────────────────────────────────────────────────────────

def expand_context(ctx: DashboardContext, conn) -> ExpandedContext:
    k = _get_cache_key(ctx)
    entry = _db_cache.get(k)
    if entry is not None:
        stored_at, expanded = entry
        if time.time() - stored_at <= CACHE_TTL_SECONDS:
            log.info(f"[REC] DB Context cache hit for view={ctx.view} entity={ctx.entity_name}")
            return expanded
        else:
            del _db_cache[k]

    handlers = {
        "channel_detail":    _expand_channel_detail,
        "user_detail":       _expand_user_detail,
        "content_mix":       _expand_content_mix,
        "executive_summary": _expand_executive_summary,
        "trend_view":        _expand_trend_view,
        "client_health":     _expand_client_health,
        "data_quality":      _expand_data_quality,
    }
    handler = handlers.get(ctx.view, _expand_executive_summary)
    log.info(f"[REC] Expanding context for view={ctx.view} entity={ctx.entity_name}")
    result = handler(ctx, conn)
    _db_cache[k] = (time.time(), result)
    return result


# ── name→id resolver ──────────────────────────────────────────────────────────

def _resolve_entity_id(conn, ctx: DashboardContext) -> int | None:
    """Look up entity_id from entity_name when the frontend only sends a name."""
    if ctx.entity_id is not None:
        return ctx.entity_id
    if not ctx.entity_name or ctx.entity_name == "All Channels":
        return None
    table_map = {
        "channel": ("data.dim_channel", "channel_id", "channel_name"),
        "user":    ("data.dim_user",    "user_id",    "user_name"),
    }
    entry = table_map.get(ctx.entity_type)
    if not entry:
        return None
    tbl, pk, name_col = entry
    rows = _fetch(conn, f"SELECT {pk} FROM {tbl} WHERE {name_col} = %s LIMIT 1", (ctx.entity_name,))
    return rows[0][pk] if rows else None


# ── channel_detail ─────────────────────────────────────────────────────────────

def _expand_channel_detail(ctx: DashboardContext, conn) -> ExpandedContext:
    eid = _resolve_entity_id(conn, ctx)
    if eid is None:
        return _expand_executive_summary(ctx, conn)
    cid = ctx.client_id

    entity_profile = _fetch(conn, """
        SELECT ch.channel_name, ch.channel_code,
               h.total_created, h.total_published,
               h.publish_rate_pct, h.active_users,
               h.last_activity::date AS last_activity
        FROM   data.mv_channel_health h
        JOIN   data.dim_channel ch ON ch.channel_id = h.channel_id
        WHERE  h.client_id = %s AND h.channel_id = %s
    """, (cid, eid))

    trend = _fetch(conn, """
        SELECT   TO_CHAR(m.month, 'YYYY-MM') AS month,
                 SUM(m.created_count)   AS created,
                 SUM(m.published_count) AS published,
                 ROUND(
                     SUM(m.published_count)::numeric
                     / NULLIF(SUM(m.created_count), 0) * 100, 1
                 ) AS publish_rate_pct
        FROM     data.mv_monthly_kpis m
        WHERE    m.client_id = %s AND m.channel_id = %s
        GROUP BY m.month
        ORDER BY m.month DESC
        LIMIT    6
    """, (cid, eid))

    if entity_profile:
        entity_profile[0]["monthly_trend"] = trend

    peer_comparison = _fetch(conn, """
        SELECT ch.channel_name, h.total_created, h.total_published,
               h.publish_rate_pct, h.active_users
        FROM   data.mv_channel_health h
        JOIN   data.dim_channel ch ON ch.channel_id = h.channel_id
        WHERE  h.client_id = %s AND h.channel_id != %s
        ORDER  BY h.publish_rate_pct DESC
        LIMIT  5
    """, (cid, eid))

    related_actors = _fetch(conn, """
        SELECT u.user_name, u.role,
               up.created_count, up.published_count, up.publish_rate_pct
        FROM   data.mv_user_performance up
        JOIN   data.dim_user u ON u.user_id = up.user_id
        WHERE  up.client_id = %s AND up.channel_id = %s
        ORDER  BY up.created_count DESC
        LIMIT  10
    """, (cid, eid))

    channel_mix = _fetch(conn, """
        SELECT it.type_name,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   data.mv_monthly_kpis m
        JOIN   data.dim_input_type it ON it.input_type_id = m.input_type_id
        WHERE  m.client_id = %s AND m.channel_id = %s AND m.input_type_id IS NOT NULL
        GROUP  BY it.type_name
        ORDER  BY created DESC
    """, (cid, eid))

    network_mix = _fetch(conn, """
        SELECT it.type_name,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   data.mv_monthly_kpis m
        JOIN   data.dim_input_type it ON it.input_type_id = m.input_type_id
        WHERE  m.client_id = %s AND m.input_type_id IS NOT NULL
        GROUP  BY it.type_name
        ORDER  BY created DESC
    """, (cid,))

    benchmark = [
        {"section": "this_channel", "rows": channel_mix},
        {"section": "network_wide", "rows": network_mix},
    ]

    return ExpandedContext(
        entity_profile=entity_profile,
        peer_comparison=peer_comparison,
        related_actors=related_actors,
        benchmark=benchmark,
    )


# ── user_detail ────────────────────────────────────────────────────────────────

def _expand_user_detail(ctx: DashboardContext, conn) -> ExpandedContext:
    eid = _resolve_entity_id(conn, ctx)
    if eid is None:
        return _expand_executive_summary(ctx, conn)
    cid = ctx.client_id

    entity_profile = _fetch(conn, """
        SELECT ch.channel_name, up.created_count, up.published_count,
               up.publish_rate_pct
        FROM   data.mv_user_performance up
        JOIN   data.dim_channel ch ON ch.channel_id = up.channel_id
        WHERE  up.client_id = %s AND up.user_id = %s
        ORDER  BY up.created_count DESC
    """, (cid, eid))

    peer_comparison = _fetch(conn, """
        WITH user_primary AS (
            SELECT channel_id FROM data.mv_user_performance
            WHERE  client_id = %s AND user_id = %s
            ORDER  BY created_count DESC LIMIT 1
        )
        SELECT u.user_name, up.created_count, up.published_count,
               up.publish_rate_pct
        FROM   data.mv_user_performance up
        JOIN   data.dim_user u  ON u.user_id  = up.user_id
        JOIN   user_primary p ON p.channel_id = up.channel_id
        WHERE  up.client_id = %s AND up.user_id != %s
        ORDER  BY up.publish_rate_pct DESC
        LIMIT  5
    """, (cid, eid, cid, eid))

    # Channels this user appears on (from performance view)
    related_actors = _fetch(conn, """
        SELECT ch.channel_name,
               up.created_count, up.publish_rate_pct
        FROM   data.mv_user_performance up
        JOIN   data.dim_channel ch ON ch.channel_id = up.channel_id
        WHERE  up.client_id = %s AND up.user_id = %s
        ORDER  BY up.created_count DESC
    """, (cid, eid))

    benchmark = _fetch(conn, """
        WITH user_primary AS (
            SELECT channel_id FROM data.mv_user_performance
            WHERE  client_id = %s AND user_id = %s
            ORDER  BY created_count DESC LIMIT 1
        )
        SELECT u.user_name, up.created_count, up.published_count,
               up.publish_rate_pct
        FROM   data.mv_user_performance up
        JOIN   data.dim_user u ON u.user_id = up.user_id
        JOIN   user_primary p ON p.channel_id = up.channel_id
        WHERE  up.client_id = %s
        ORDER  BY up.publish_rate_pct DESC
        LIMIT  3
    """, (cid, eid, cid))

    return ExpandedContext(
        entity_profile=entity_profile,
        peer_comparison=peer_comparison,
        related_actors=related_actors,
        benchmark=benchmark,
    )


# ── content_mix ────────────────────────────────────────────────────────────────

def _expand_content_mix(ctx: DashboardContext, conn) -> ExpandedContext:
    eid = _resolve_entity_id(conn, ctx)
    if eid is None:
        return _expand_executive_summary(ctx, conn)
    cid = ctx.client_id

    entity_profile = _fetch(conn, """
        SELECT TO_CHAR(m.month, 'YYYY-MM') AS month,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   data.mv_monthly_kpis m
        WHERE  m.client_id = %s AND m.input_type_id = %s
        GROUP  BY m.month
        ORDER  BY m.month DESC
        LIMIT  6
    """, (cid, eid))

    peer_comparison = _fetch(conn, """
        SELECT it.type_name,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   data.mv_monthly_kpis m
        JOIN   data.dim_input_type it ON it.input_type_id = m.input_type_id
        WHERE  m.client_id = %s AND m.input_type_id IS NOT NULL
        GROUP  BY it.type_name, m.input_type_id
        ORDER  BY publish_rate_pct DESC
    """, (cid,))

    related_actors = _fetch(conn, """
        SELECT ch.channel_name,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   data.mv_monthly_kpis m
        JOIN   data.dim_channel ch ON ch.channel_id = m.channel_id
        WHERE  m.client_id = %s AND m.input_type_id = %s
        GROUP  BY ch.channel_name
        ORDER  BY created DESC
        LIMIT  10
    """, (cid, eid))

    benchmark = _fetch(conn, """
        SELECT ch.channel_name,
               SUM(m.created_count)   AS created,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   data.mv_monthly_kpis m
        JOIN   data.dim_channel ch ON ch.channel_id = m.channel_id
        WHERE  m.client_id = %s AND m.input_type_id = %s
        GROUP  BY ch.channel_name
        ORDER  BY publish_rate_pct DESC
        LIMIT  3
    """, (cid, eid))

    return ExpandedContext(
        entity_profile=entity_profile,
        peer_comparison=peer_comparison,
        related_actors=related_actors,
        benchmark=benchmark,
    )


# ── executive_summary ──────────────────────────────────────────────────────────

def _expand_executive_summary(ctx: DashboardContext, conn) -> ExpandedContext:
    cid = ctx.client_id

    entity_profile = _fetch(conn, """
        SELECT ch.channel_name, h.total_created, h.total_published,
               h.publish_rate_pct, h.active_users,
               h.last_activity::date AS last_activity
        FROM   data.mv_channel_health h
        JOIN   data.dim_channel ch ON ch.channel_id = h.channel_id
        WHERE  h.client_id = %s
        ORDER  BY h.publish_rate_pct DESC
    """, (cid,))

    peer_comparison = _fetch(conn, """
        WITH monthly AS (
            SELECT TO_CHAR(month, 'YYYY-MM')   AS month,
                   SUM(created_count)          AS created,
                   SUM(published_count)        AS published,
                   ROUND(
                       SUM(published_count)::numeric
                       / NULLIF(SUM(created_count), 0) * 100, 1
                   ) AS publish_rate_pct
            FROM   data.mv_monthly_kpis
            WHERE  client_id = %s
            GROUP  BY month
            ORDER  BY month DESC
            LIMIT  2
        )
        SELECT * FROM monthly ORDER BY month ASC
    """, (cid,))

    related_actors = _fetch(conn, """
        SELECT u.user_name, ch.channel_name,
               up.created_count, up.publish_rate_pct
        FROM   data.mv_user_performance up
        JOIN   data.dim_user u     ON u.user_id     = up.user_id
        JOIN   data.dim_channel ch ON ch.channel_id = up.channel_id
        WHERE  up.client_id = %s AND up.created_count >= 5 AND NOT u.is_bot
        ORDER  BY up.publish_rate_pct ASC
        LIMIT  5
    """, (cid,))

    benchmark = _fetch(conn, """
        SELECT it.type_name,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   data.mv_monthly_kpis m
        JOIN   data.dim_input_type it ON it.input_type_id = m.input_type_id
        WHERE  m.client_id = %s AND m.input_type_id IS NOT NULL
        GROUP  BY it.type_name
        ORDER  BY publish_rate_pct DESC
    """, (cid,))

    return ExpandedContext(
        entity_profile=entity_profile,
        peer_comparison=peer_comparison,
        related_actors=related_actors,
        benchmark=benchmark,
    )


# ── client_health ──────────────────────────────────────────────────────────────

def _expand_client_health(ctx: DashboardContext, conn) -> ExpandedContext:
    """
    Client-level aggregations for the client_success profile.
    Surfaces channels-per-client counts, active-user totals, and publish
    rates grouped by client so account managers can triage quickly.
    """
    cid = ctx.client_id

    # Entity profile — aggregate health for this client
    entity_profile = _fetch(conn, """
        SELECT COUNT(h.channel_id)            AS total_channels,
               SUM(h.active_users)            AS total_active_users,
               SUM(h.total_created)           AS total_created,
               SUM(h.total_published)         AS total_published,
               ROUND(
                   SUM(h.total_published)::numeric
                   / NULLIF(SUM(h.total_created), 0) * 100, 1
               )                              AS publish_rate_pct
        FROM   data.mv_channel_health h
        WHERE  h.client_id = %s
    """, (cid,))

    # Peer comparison — per-channel publish rates ranked worst-first (churn risk)
    peer_comparison = _fetch(conn, """
        SELECT ch.channel_name,
               h.publish_rate_pct,
               h.active_users,
               h.total_created,
               h.total_published,
               h.last_activity::date AS last_activity
        FROM   data.mv_channel_health h
        JOIN   data.dim_channel ch ON ch.channel_id = h.channel_id
        WHERE  h.client_id = %s
        ORDER  BY h.publish_rate_pct ASC
        LIMIT  10
    """, (cid,))

    # Related actors — monthly publish rate trend for this client
    related_actors = _fetch(conn, """
        SELECT TO_CHAR(m.month, 'YYYY-MM') AS month,
               SUM(m.created_count)        AS created,
               SUM(m.published_count)      AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               )                           AS publish_rate_pct
        FROM   data.mv_monthly_kpis m
        WHERE  m.client_id = %s
        GROUP  BY m.month
        ORDER  BY m.month DESC
        LIMIT  6
    """, (cid,))

    # Benchmark — top 3 channels by publish rate for positive comparison
    benchmark = _fetch(conn, """
        SELECT ch.channel_name,
               h.publish_rate_pct,
               h.active_users,
               h.total_created
        FROM   data.mv_channel_health h
        JOIN   data.dim_channel ch ON ch.channel_id = h.channel_id
        WHERE  h.client_id = %s
        ORDER  BY h.publish_rate_pct DESC
        LIMIT  3
    """, (cid,))

    return ExpandedContext(
        entity_profile=entity_profile,
        peer_comparison=peer_comparison,
        related_actors=related_actors,
        benchmark=benchmark,
    )


# ── data_quality ───────────────────────────────────────────────────────────────

def _expand_data_quality(ctx: DashboardContext, conn) -> ExpandedContext:
    """
    Data-quality diagnostics for the tech_product profile.
    Counts NULLs and unknowns across key columns in fact_created_videos
    so engineers and PMs can prioritise coverage fixes.
    """
    cid = ctx.client_id

    # Entity profile — total row count and per-column NULL rates
    entity_profile = _fetch(conn, """
        SELECT COUNT(*)                                          AS total_rows,
               COUNT(*) FILTER (WHERE channel_id  IS NULL)     AS null_channel_id,
               COUNT(*) FILTER (WHERE user_id     IS NULL)     AS null_user_id,
               COUNT(*) FILTER (WHERE input_type_id  IS NULL)  AS missing_input_type,
               COUNT(*) FILTER (WHERE output_type_id IS NULL)  AS missing_output_type,
               COUNT(*) FILTER (WHERE uploaded_at    IS NULL)  AS null_uploaded_at,
               ROUND(
                   COUNT(*) FILTER (WHERE channel_id IS NULL)::numeric
                   / NULLIF(COUNT(*), 0) * 100, 2
               )                                               AS null_channel_pct
        FROM   data.fact_created_videos
        WHERE  client_id = %s
    """, (cid,))

    # Peer comparison — NULL rates broken down by channel (worst first)
    peer_comparison = _fetch(conn, """
        SELECT ch.channel_name,
               COUNT(*)                                          AS total_rows,
               COUNT(*) FILTER (WHERE f.input_type_id  IS NULL) AS missing_input_type,
               COUNT(*) FILTER (WHERE f.output_type_id IS NULL) AS missing_output_type,
               ROUND(
                   COUNT(*) FILTER (WHERE f.input_type_id IS NULL)::numeric
                   / NULLIF(COUNT(*), 0) * 100, 2
               )                                               AS missing_input_type_pct
        FROM   data.fact_created_videos f
        JOIN   data.dim_channel ch ON ch.channel_id = f.channel_id
        WHERE  f.client_id = %s
        GROUP  BY ch.channel_name
        ORDER  BY missing_input_type_pct DESC
        LIMIT  10
    """, (cid,))

    # Related actors — monthly NULL-rate trend (data quality over time)
    related_actors = _fetch(conn, """
        SELECT TO_CHAR(DATE_TRUNC('month', uploaded_at), 'YYYY-MM') AS month,
               COUNT(*)                                             AS total_rows,
               COUNT(*) FILTER (WHERE input_type_id IS NULL)    AS missing_input_type,
               ROUND(
                   COUNT(*) FILTER (WHERE input_type_id IS NULL)::numeric
                   / NULLIF(COUNT(*), 0) * 100, 2
               )                                                   AS missing_input_type_pct
        FROM   data.fact_created_videos
        WHERE  client_id = %s AND uploaded_at IS NOT NULL
        GROUP  BY DATE_TRUNC('month', uploaded_at)
        ORDER  BY month DESC
        LIMIT  6
    """, (cid,))

    # Benchmark — channels with zero NULL issues (fully clean, for contrast)
    benchmark = _fetch(conn, """
        SELECT ch.channel_name,
               COUNT(*) AS total_rows,
               0        AS missing_input_type,
               0.0      AS missing_input_type_pct
        FROM   data.fact_created_videos f
        JOIN   data.dim_channel ch ON ch.channel_id = f.channel_id
        WHERE  f.client_id = %s
        GROUP  BY ch.channel_name
        HAVING COUNT(*) FILTER (WHERE f.input_type_id IS NULL) = 0
        ORDER  BY total_rows DESC
        LIMIT  5
    """, (cid,))

    return ExpandedContext(
        entity_profile=entity_profile,
        peer_comparison=peer_comparison,
        related_actors=related_actors,
        benchmark=benchmark,
    )


# ── trend_view ─────────────────────────────────────────────────────────────────

def _expand_trend_view(ctx: DashboardContext, conn) -> ExpandedContext:
    cid, eid = ctx.client_id, ctx.entity_id

    # When no entity selected, show network-level trends
    if eid is None:
        return _expand_executive_summary(ctx, conn)

    entity_profile = _fetch(conn, """
        SELECT TO_CHAR(m.month, 'YYYY-MM') AS month,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   data.mv_monthly_kpis m
        WHERE  m.client_id = %s AND m.channel_id = %s
        GROUP  BY m.month
        ORDER  BY m.month ASC
    """, (cid, eid))

    peer_comparison = _fetch(conn, """
        SELECT ch.channel_name,
               TO_CHAR(m.month, 'YYYY-MM') AS month,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct,
               SUM(m.created_count) AS created
        FROM   data.mv_monthly_kpis m
        JOIN   data.dim_channel ch ON ch.channel_id = m.channel_id
        WHERE  m.client_id = %s AND m.channel_id != %s
        GROUP  BY ch.channel_name, m.month
        ORDER  BY m.month ASC, ch.channel_name
    """, (cid, eid))

    related_actors = _fetch(conn, """
        WITH series AS (
            SELECT TO_CHAR(month, 'YYYY-MM') AS month,
                   ROUND(
                       SUM(published_count)::numeric
                       / NULLIF(SUM(created_count), 0) * 100, 1
                   ) AS publish_rate_pct
            FROM   data.mv_monthly_kpis
            WHERE  client_id = %s AND channel_id = %s
            GROUP  BY month ORDER BY month
        ),
        with_lag AS (
            SELECT month, publish_rate_pct,
                   LAG(publish_rate_pct) OVER (ORDER BY month) AS prev_rate
            FROM series
        )
        SELECT month, publish_rate_pct, prev_rate,
               ROUND(publish_rate_pct - COALESCE(prev_rate, publish_rate_pct), 1) AS delta
        FROM   with_lag
        ORDER  BY ABS(publish_rate_pct - COALESCE(prev_rate, publish_rate_pct)) DESC
        LIMIT  3
    """, (cid, eid))

    benchmark = _fetch(conn, """
        SELECT ch.channel_name, h.publish_rate_pct, h.total_created, h.active_users
        FROM   data.mv_channel_health h
        JOIN   data.dim_channel ch ON ch.channel_id = h.channel_id
        WHERE  h.client_id = %s
        ORDER  BY h.publish_rate_pct DESC
        LIMIT  3
    """, (cid,))

    return ExpandedContext(
        entity_profile=entity_profile,
        peer_comparison=peer_comparison,
        related_actors=related_actors,
        benchmark=benchmark,
    )
