"""
Phase 0 — Hydrate a shared data bundle for all analyzers.

One DB round-trip, all results stored as list[dict].
Every analyzer receives the same HydratedDataBundle — no analyzer hits the DB directly.
"""

import logging
from dataclasses import dataclass, field
from datetime import date

log = logging.getLogger("narrator.data_loader")


@dataclass
class HydratedDataBundle:
    """All data needed by the 7 analyzers, pulled once."""

    client_id: int
    as_of: date

    # From mv_monthly_kpis — 6 months of monthly aggregates
    monthly_kpis: list[dict] = field(default_factory=list)

    # From mv_channel_health — all-time per-channel rollup
    channel_health: list[dict] = field(default_factory=list)

    # From mv_user_performance — all-time per-user per-channel
    user_performance: list[dict] = field(default_factory=list)

    # From fact_created_videos — 90-day raw sample for cross-dim + DQ
    fact_sample: list[dict] = field(default_factory=list)

    # From pg_insight_history — 30-day follow-up context
    insight_history: list[dict] = field(default_factory=list)

    # Dimension lookups (id → label)
    dim_channels: dict = field(default_factory=dict)
    dim_users: dict = field(default_factory=dict)
    dim_input_types: dict = field(default_factory=dict)
    dim_output_types: dict = field(default_factory=dict)
    dim_languages: dict = field(default_factory=dict)
    dim_teams: dict = field(default_factory=dict)


def _fetch(conn, sql: str, params: tuple = ()) -> list[dict]:
    """Execute SQL and return rows as list[dict]."""
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
    except Exception as e:
        conn.rollback()
        log.warning(f"[DATA] Query failed: {e}")
        return []
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def hydrate(conn, client_id: int) -> HydratedDataBundle:
    """Pull all data needed by the narrator pipeline in one burst."""

    log.info(f"[DATA] Hydrating data for client_id={client_id}")

    bundle = HydratedDataBundle(
        client_id=client_id,
        as_of=date.today(),
    )

    # ── 1. Monthly KPIs (6 months) ─────────────────────────────────────────
    bundle.monthly_kpis = _fetch(conn, """
        SELECT  m.channel_id, m.input_type_id, m.output_type_id, m.language_id,
                TO_CHAR(m.month, 'YYYY-MM') AS month,
                m.created_count, m.published_count,
                m.publish_rate_pct,
                m.total_uploaded_duration_secs,
                m.total_created_duration_secs,
                m.total_published_duration_secs,
                m.total_views,
                m.total_uploaded_hours
        FROM    data.mv_monthly_kpis m
        WHERE   m.client_id = %s
          AND   m.month >= DATE_TRUNC('month', NOW() - INTERVAL '6 months')
        ORDER BY m.month DESC
    """, (client_id,))
    log.info(f"[DATA]   monthly_kpis: {len(bundle.monthly_kpis)} rows")

    # ── 2. Channel health ──────────────────────────────────────────────────
    bundle.channel_health = _fetch(conn, """
        SELECT  h.channel_id, ch.channel_name, ch.channel_code,
                h.total_created, h.total_published,
                h.publish_rate_pct, h.active_users,
                h.total_views, h.total_uploaded_hours,
                h.last_activity
        FROM    data.mv_channel_health h
        JOIN    data.dim_channel ch ON ch.channel_id = h.channel_id
        WHERE   h.client_id = %s
        ORDER BY h.total_created DESC
    """, (client_id,))
    log.info(f"[DATA]   channel_health: {len(bundle.channel_health)} rows")

    # ── 3. User performance ────────────────────────────────────────────────
    bundle.user_performance = _fetch(conn, """
        SELECT  up.user_id, u.user_name, up.channel_id,
                up.created_count, up.published_count, up.publish_rate_pct,
                up.total_uploaded_duration_secs,
                up.total_created_duration_secs,
                up.total_views
        FROM    data.mv_user_performance up
        JOIN    data.dim_user u ON u.user_id = up.user_id
        WHERE   up.client_id = %s AND NOT u.is_bot
        ORDER BY up.created_count DESC
    """, (client_id,))
    log.info(f"[DATA]   user_performance: {len(bundle.user_performance)} rows")

    # ── 4. Fact sample (90 days, for cross-dim + DQ + operational risk) ────
    bundle.fact_sample = _fetch(conn, """
        SELECT  f.video_id, f.channel_id, f.user_id,
                f.input_type_id, f.output_type_id, f.language_id,
                f.team_id, f.platform_id,
                f.published_flag,
                f.published_url,
                f.uploaded_at,
                f.uploaded_duration_secs,
                f.created_duration_secs
        FROM    data.fact_created_videos f
        WHERE   f.client_id = %s
          AND   f.uploaded_at >= NOW() - INTERVAL '90 days'
        ORDER BY f.uploaded_at DESC
    """, (client_id,))
    log.info(f"[DATA]   fact_sample: {len(bundle.fact_sample)} rows")

    # ── 5. Insight history (30 days, for follow-up tracking) ───────────────
    bundle.insight_history = _fetch(conn, """
        SELECT  id, entity_type, entity_id, insight_type,
                metric_name, period, first_seen_at, last_seen_at,
                seen_count,
                COALESCE(status, 'new') AS status,
                COALESCE(consecutive_periods, 1) AS consecutive_periods,
                last_severity
        FROM    internal.pg_insight_history
        WHERE   client_id = %s
          AND   last_seen_at >= NOW() - INTERVAL '30 days'
    """, (client_id,))
    log.info(f"[DATA]   insight_history: {len(bundle.insight_history)} rows")

    # ── 6. Dimension lookups ───────────────────────────────────────────────
    for table, id_col, name_col, target in [
        ("data.dim_channel",     "channel_id",     "channel_name",   "dim_channels"),
        ("data.dim_user",        "user_id",        "user_name",      "dim_users"),
        ("data.dim_input_type",  "input_type_id",  "type_name",      "dim_input_types"),
        ("data.dim_output_type", "output_type_id", "type_name",      "dim_output_types"),
        ("data.dim_language",    "language_id",     "language_name",  "dim_languages"),
        ("data.dim_team",        "team_id",        "team_name",      "dim_teams"),
    ]:
        rows = _fetch(conn, f"SELECT {id_col}, {name_col} FROM {table}")
        setattr(bundle, target, {r[id_col]: r[name_col] for r in rows})

    log.info(f"[DATA] Hydration complete — {_total_rows(bundle)} total rows")
    return bundle


def _total_rows(b: HydratedDataBundle) -> int:
    return (
        len(b.monthly_kpis) + len(b.channel_health)
        + len(b.user_performance) + len(b.fact_sample)
        + len(b.insight_history)
    )
