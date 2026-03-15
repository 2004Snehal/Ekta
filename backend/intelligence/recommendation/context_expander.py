"""
Context expander — runs 4 targeted SQL queries for each view type.
All queries hit materialized views (no fact table scans on the hot path).
"""

import logging
from intelligence.recommendation.models import DashboardContext, ExpandedContext

log = logging.getLogger("recommendation.expander")


# ── helpers ────────────────────────────────────────────────────────────────────

def _fetch(conn, sql: str, params: tuple) -> list[dict]:
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── dispatcher ─────────────────────────────────────────────────────────────────

def expand_context(ctx: DashboardContext, conn) -> ExpandedContext:
    handlers = {
        "channel_detail":    _expand_channel_detail,
        "user_detail":       _expand_user_detail,
        "content_mix":       _expand_content_mix,
        "executive_summary": _expand_executive_summary,
        "trend_view":        _expand_trend_view,
    }
    handler = handlers.get(ctx.view, _expand_executive_summary)
    log.info(f"[REC] Expanding context for view={ctx.view} entity={ctx.entity_name}")
    return handler(ctx, conn)


# ── channel_detail ─────────────────────────────────────────────────────────────

def _expand_channel_detail(ctx: DashboardContext, conn) -> ExpandedContext:
    cid, eid = ctx.client_id, ctx.entity_id

    entity_profile = _fetch(conn, """
        SELECT ch.channel_name, ch.content_focus, ch.primary_language,
               h.total_created, h.total_published,
               h.publish_rate_pct, h.active_users,
               h.last_activity::date AS last_activity
        FROM   mv_channel_health h
        JOIN   dim_channel ch ON ch.channel_id = h.channel_id
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
        FROM     mv_monthly_kpis m
        WHERE    m.client_id = %s AND m.channel_id = %s
        GROUP BY m.month
        ORDER BY m.month DESC
        LIMIT    6
    """, (cid, eid))
    # Merge trend into entity_profile as a nested list
    if entity_profile:
        entity_profile[0]["monthly_trend"] = trend

    peer_comparison = _fetch(conn, """
        SELECT ch.channel_name, h.total_created, h.total_published,
               h.publish_rate_pct, h.active_users
        FROM   mv_channel_health h
        JOIN   dim_channel ch ON ch.channel_id = h.channel_id
        WHERE  h.client_id = %s AND h.channel_id != %s
        ORDER  BY h.publish_rate_pct DESC
        LIMIT  5
    """, (cid, eid))

    related_actors = _fetch(conn, """
        SELECT u.user_name, u.role,
               up.created_count, up.published_count, up.publish_rate_pct
        FROM   mv_user_performance up
        JOIN   dim_user u ON u.user_id = up.user_id
        WHERE  up.client_id = %s AND up.channel_id = %s
        ORDER  BY up.created_count DESC
        LIMIT  10
    """, (cid, eid))

    # benchmark = input type breakdown for this channel vs network
    channel_mix = _fetch(conn, """
        SELECT it.type_name,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   mv_monthly_kpis m
        JOIN   dim_input_type it ON it.input_type_id = m.input_type_id
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
        FROM   mv_monthly_kpis m
        JOIN   dim_input_type it ON it.input_type_id = m.input_type_id
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
    cid, eid = ctx.client_id, ctx.entity_id

    entity_profile = _fetch(conn, """
        SELECT ch.channel_name, up.created_count, up.published_count,
               up.publish_rate_pct
        FROM   mv_user_performance up
        JOIN   dim_channel ch ON ch.channel_id = up.channel_id
        WHERE  up.client_id = %s AND up.user_id = %s
        ORDER  BY up.created_count DESC
    """, (cid, eid))

    # Peers = other users on the same primary channel
    peer_comparison = _fetch(conn, """
        WITH user_primary AS (
            SELECT channel_id FROM mv_user_performance
            WHERE  client_id = %s AND user_id = %s
            ORDER  BY created_count DESC LIMIT 1
        )
        SELECT u.user_name, up.created_count, up.published_count,
               up.publish_rate_pct
        FROM   mv_user_performance up
        JOIN   dim_user u  ON u.user_id  = up.user_id
        JOIN   user_primary p ON p.channel_id = up.channel_id
        WHERE  up.client_id = %s AND up.user_id != %s
        ORDER  BY up.publish_rate_pct DESC
        LIMIT  5
    """, (cid, eid, cid, eid))

    # Channels this user is mapped to
    related_actors = _fetch(conn, """
        SELECT ch.channel_name, ucm.is_primary,
               up.created_count, up.publish_rate_pct
        FROM   user_channel_map ucm
        JOIN   dim_channel ch ON ch.channel_id = ucm.channel_id
        LEFT JOIN mv_user_performance up
               ON up.user_id = ucm.user_id AND up.channel_id = ucm.channel_id
               AND up.client_id = %s
        WHERE  ucm.user_id = %s
        ORDER  BY ucm.is_primary DESC, up.created_count DESC NULLS LAST
    """, (cid, eid))

    # Top user in the same channel (benchmark)
    benchmark = _fetch(conn, """
        WITH user_primary AS (
            SELECT channel_id FROM mv_user_performance
            WHERE  client_id = %s AND user_id = %s
            ORDER  BY created_count DESC LIMIT 1
        )
        SELECT u.user_name, up.created_count, up.published_count,
               up.publish_rate_pct
        FROM   mv_user_performance up
        JOIN   dim_user u ON u.user_id = up.user_id
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
    cid, eid = ctx.client_id, ctx.entity_id  # entity_id = input_type_id

    entity_profile = _fetch(conn, """
        SELECT TO_CHAR(m.month, 'YYYY-MM') AS month,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   mv_monthly_kpis m
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
        FROM   mv_monthly_kpis m
        JOIN   dim_input_type it ON it.input_type_id = m.input_type_id
        WHERE  m.client_id = %s AND m.input_type_id IS NOT NULL
        GROUP  BY it.type_name, m.input_type_id
        ORDER  BY publish_rate_pct DESC
    """, (cid,))

    # Which channels use this content type most/least
    related_actors = _fetch(conn, """
        SELECT ch.channel_name,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   mv_monthly_kpis m
        JOIN   dim_channel ch ON ch.channel_id = m.channel_id
        WHERE  m.client_id = %s AND m.input_type_id = %s
        GROUP  BY ch.channel_name
        ORDER  BY created DESC
        LIMIT  10
    """, (cid, eid))

    # Best channel for this content type
    benchmark = _fetch(conn, """
        SELECT ch.channel_name,
               SUM(m.created_count)   AS created,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   mv_monthly_kpis m
        JOIN   dim_channel ch ON ch.channel_id = m.channel_id
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
        FROM   mv_channel_health h
        JOIN   dim_channel ch ON ch.channel_id = h.channel_id
        WHERE  h.client_id = %s
        ORDER  BY h.publish_rate_pct DESC
    """, (cid,))

    # Current month vs previous month network-wide
    peer_comparison = _fetch(conn, """
        WITH monthly AS (
            SELECT TO_CHAR(month, 'YYYY-MM')   AS month,
                   SUM(created_count)          AS created,
                   SUM(published_count)        AS published,
                   ROUND(
                       SUM(published_count)::numeric
                       / NULLIF(SUM(created_count), 0) * 100, 1
                   ) AS publish_rate_pct
            FROM   mv_monthly_kpis
            WHERE  client_id = %s
            GROUP  BY month
            ORDER  BY month DESC
            LIMIT  2
        )
        SELECT * FROM monthly ORDER BY month ASC
    """, (cid,))

    # Bottom 5 users by publish rate (need attention)
    related_actors = _fetch(conn, """
        SELECT u.user_name, ch.channel_name,
               up.created_count, up.publish_rate_pct
        FROM   mv_user_performance up
        JOIN   dim_user u    ON u.user_id    = up.user_id
        JOIN   dim_channel ch ON ch.channel_id = up.channel_id
        WHERE  up.client_id = %s AND up.created_count >= 5 AND NOT u.is_bot
        ORDER  BY up.publish_rate_pct ASC
        LIMIT  5
    """, (cid,))

    # Best and worst performing content types
    benchmark = _fetch(conn, """
        SELECT it.type_name,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   mv_monthly_kpis m
        JOIN   dim_input_type it ON it.input_type_id = m.input_type_id
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


# ── trend_view ─────────────────────────────────────────────────────────────────

def _expand_trend_view(ctx: DashboardContext, conn) -> ExpandedContext:
    cid, eid = ctx.client_id, ctx.entity_id

    # Full monthly series for this channel
    entity_profile = _fetch(conn, """
        SELECT TO_CHAR(m.month, 'YYYY-MM') AS month,
               SUM(m.created_count)   AS created,
               SUM(m.published_count) AS published,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct
        FROM   mv_monthly_kpis m
        WHERE  m.client_id = %s AND m.channel_id = %s
        GROUP  BY m.month
        ORDER  BY m.month ASC
    """, (cid, eid))

    # Top 3 peer channels — same metric trend
    peer_comparison = _fetch(conn, """
        SELECT ch.channel_name,
               TO_CHAR(m.month, 'YYYY-MM') AS month,
               ROUND(
                   SUM(m.published_count)::numeric
                   / NULLIF(SUM(m.created_count), 0) * 100, 1
               ) AS publish_rate_pct,
               SUM(m.created_count) AS created
        FROM   mv_monthly_kpis m
        JOIN   dim_channel ch ON ch.channel_id = m.channel_id
        WHERE  m.client_id = %s AND m.channel_id != %s
        GROUP  BY ch.channel_name, m.month
        ORDER  BY m.month ASC, ch.channel_name
    """, (cid, eid))

    # Month-over-month deltas — flag anomalies
    related_actors = _fetch(conn, """
        WITH series AS (
            SELECT TO_CHAR(month, 'YYYY-MM') AS month,
                   ROUND(
                       SUM(published_count)::numeric
                       / NULLIF(SUM(created_count), 0) * 100, 1
                   ) AS publish_rate_pct
            FROM   mv_monthly_kpis
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

    # Current network leader for this metric
    benchmark = _fetch(conn, """
        SELECT ch.channel_name, h.publish_rate_pct, h.total_created, h.active_users
        FROM   mv_channel_health h
        JOIN   dim_channel ch ON ch.channel_id = h.channel_id
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
