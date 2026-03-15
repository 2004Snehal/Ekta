"""
Statistical anomaly detector — Step 2 of the Insight Narrator pipeline.

Pulls aggregated metrics from materialized views, applies z-score / IQR /
MoM-delta detection, and returns a ranked list of FlaggedMetric objects.

The LLM never sees raw tables — only this pre-flagged, pre-scored output.
"""

from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np

from intelligence.insight_narrator.schemas import FlaggedMetric

logger = logging.getLogger(__name__)

# ── Thresholds (all configurable) ────────────────────────────────────────────

ZSCORE_HIGH   = 2.5
ZSCORE_MED    = 1.5
ZSCORE_LOW    = 1.0

MOM_HIGH      = 40.0   # % absolute change
MOM_MED       = 25.0
MOM_LOW       = 15.0

IQR_MULTIPLIER = 1.5


# ── Severity assignment (Python-owned, NOT the LLM) ──────────────────────────

def _severity_from_stats(
    zscore: Optional[float],
    mom_delta_pct: float,
) -> Optional[str]:
    """
    Returns 'high' | 'medium' | 'low' | None (not anomalous enough).
    zscore magnitude and MoM delta are both considered; worst wins.
    """
    severity = None
    abs_mom = abs(mom_delta_pct)
    abs_z   = abs(zscore) if zscore is not None else 0.0

    if abs_z >= ZSCORE_HIGH or abs_mom >= MOM_HIGH:
        severity = "high"
    elif abs_z >= ZSCORE_MED or abs_mom >= MOM_MED:
        severity = "medium"
    elif abs_z >= ZSCORE_LOW or abs_mom >= MOM_LOW:
        severity = "low"

    return severity


def _zscore_for_series(series: list[float], current: float) -> Optional[float]:
    """Z-score of current value relative to the series (baseline months)."""
    if len(series) < 2:
        return None
    arr = np.array(series, dtype=float)
    std = arr.std()
    if std == 0:
        return None
    return float((current - arr.mean()) / std)


def _iqr_flag(series: list[float], current: float) -> bool:
    """Returns True if current is an IQR outlier relative to series."""
    if len(series) < 3:
        return False
    arr = np.array(series, dtype=float)
    q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
    iqr = q3 - q1
    return current < q1 - IQR_MULTIPLIER * iqr or current > q3 + IQR_MULTIPLIER * iqr


# ── Data pull ─────────────────────────────────────────────────────────────────

def _pull_channel_monthly(conn, client_id: int, months_back: int = 4) -> list[dict]:
    """
    Pull per-channel monthly aggregates for the last N months.
    Aggregates across input_type / output_type / language.
    """
    cutoff = (date.today().replace(day=1) - timedelta(days=months_back * 31)).replace(day=1)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            m.channel_id,
            dc.channel_name,
            dc.channel_code,
            m.month,
            SUM(m.created_count)    AS output_count,
            SUM(m.published_count)  AS published_count,
            ROUND(
                SUM(m.published_count)::NUMERIC / NULLIF(SUM(m.created_count), 0) * 100,
                2
            ) AS publish_rate,
            AVG(
                CASE WHEN m.total_created_duration_secs > 0 AND m.created_count > 0
                     THEN m.total_created_duration_secs::FLOAT / m.created_count
                END
            ) AS avg_duration_secs
        FROM mv_monthly_kpis m
        JOIN dim_channel dc ON dc.channel_id = m.channel_id
        WHERE m.client_id = %s
          AND m.month >= %s
        GROUP BY m.channel_id, dc.channel_name, dc.channel_code, m.month
        ORDER BY m.channel_id, m.month
        """,
        (client_id, cutoff),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _pull_upload_counts(conn, client_id: int, months_back: int = 4) -> list[dict]:
    """
    Pull per-channel monthly distinct source-video upload counts.
    (mv_monthly_kpis stores output count; upload count needs fact table.)
    """
    cutoff = (date.today().replace(day=1) - timedelta(days=months_back * 31)).replace(day=1)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            channel_id,
            date_trunc('month', uploaded_at) AS month,
            COUNT(DISTINCT video_id)          AS upload_count
        FROM fact_created_videos
        WHERE client_id = %s
          AND uploaded_at >= %s
        GROUP BY channel_id, date_trunc('month', uploaded_at)
        ORDER BY channel_id, month
        """,
        (client_id, cutoff),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _pull_user_monthly(conn, client_id: int, months_back: int = 4) -> list[dict]:
    """Pull per-user monthly output counts from mv_user_performance (all-time)."""
    cutoff = (date.today().replace(day=1) - timedelta(days=months_back * 31)).replace(day=1)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            f.user_id,
            du.user_name,
            dc.channel_code,
            date_trunc('month', f.uploaded_at) AS month,
            COUNT(*)                             AS output_count,
            COUNT(*) FILTER (WHERE f.published_flag) AS published_count
        FROM fact_created_videos f
        JOIN dim_user    du ON du.user_id    = f.user_id
        JOIN dim_channel dc ON dc.channel_id = f.channel_id
        WHERE f.client_id = %s
          AND f.uploaded_at >= %s
          AND du.is_bot = FALSE
        GROUP BY f.user_id, du.user_name, dc.channel_code, date_trunc('month', f.uploaded_at)
        ORDER BY f.user_id, month
        """,
        (client_id, cutoff),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ── Detection helpers ─────────────────────────────────────────────────────────

def _detect_metric_anomaly(
    entity_type: str,
    entity_id: str,
    entity_label: str,
    metric_name: str,
    current: float,
    baseline_series: list[float],
    period: str,
    history_months: int,
    use_zscore: bool = True,
) -> Optional[FlaggedMetric]:
    """
    Core detection logic for a single metric on a single entity.
    Returns a FlaggedMetric if anomalous, else None.
    """
    if not baseline_series or current is None:
        return None

    reference = float(np.mean(baseline_series))
    if reference == 0:
        return None

    mom_delta = (current - reference) / reference * 100.0
    zscore    = _zscore_for_series(baseline_series, current) if use_zscore else None
    iqr_out   = _iqr_flag(baseline_series, current)

    # Severity from stats (IQR outlier bumps severity if z-score is borderline)
    severity = _severity_from_stats(zscore, mom_delta)
    if severity is None and iqr_out:
        severity = "low"
    if severity is None:
        return None

    return FlaggedMetric(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        metric_name=metric_name,
        current_value=round(current, 4),
        reference_value=round(reference, 4),
        delta_pct=round(mom_delta, 2),
        zscore=round(zscore, 3) if zscore is not None else None,
        severity=severity,
        period=period,
        history_months=history_months,
    )


# ── Public entry point ────────────────────────────────────────────────────────

def detect_anomalies(conn, client_id: int) -> list[FlaggedMetric]:
    """
    Run full statistical detection pipeline.
    Returns a list of FlaggedMetric objects, sorted severity-desc, delta-desc.
    """
    flagged: list[FlaggedMetric] = []

    channel_rows  = _pull_channel_monthly(conn, client_id)
    upload_rows   = _pull_upload_counts(conn, client_id)
    user_rows     = _pull_user_monthly(conn, client_id)

    if not channel_rows:
        logger.info("detector: no channel data for client %s", client_id)
        return []

    # ── Identify current period (most recent month in data) ──────────────────
    all_months = sorted({r["month"] for r in channel_rows}, reverse=True)
    if not all_months:
        return []
    current_month = all_months[0]
    period_str    = current_month.strftime("%Y-%m")

    # ── Build upload lookup: {(channel_id, month): upload_count} ─────────────
    upload_lookup: dict[tuple, int] = {}
    for r in upload_rows:
        key = (r["channel_id"], r["month"])
        upload_lookup[key] = int(r["upload_count"] or 0)

    # ── Per-channel detection ─────────────────────────────────────────────────
    # Group rows by channel_id
    channel_groups: dict[int, list[dict]] = {}
    for r in channel_rows:
        channel_groups.setdefault(r["channel_id"], []).append(r)

    for ch_id, rows in channel_groups.items():
        rows_sorted = sorted(rows, key=lambda x: x["month"])
        current_row = next((r for r in rows_sorted if r["month"] == current_month), None)
        if current_row is None:
            continue
        baseline_rows = [r for r in rows_sorted if r["month"] != current_month]
        if not baseline_rows:
            continue

        label = current_row.get("channel_name") or current_row.get("channel_code") or str(ch_id)
        code  = current_row.get("channel_code") or str(ch_id)
        history_months = len(baseline_rows)

        # Metrics: publish_rate (IQR — skewed), output_count (IQR), avg_duration (z-score)
        for metric, use_z in [
            ("publish_rate",      False),
            ("output_count",      False),
            ("avg_duration_secs", True),
        ]:
            current_val = current_row.get(metric)
            baseline    = [r.get(metric) for r in baseline_rows if r.get(metric) is not None]
            if current_val is None or not baseline:
                continue
            fm = _detect_metric_anomaly(
                entity_type="channel",
                entity_id=code,
                entity_label=label,
                metric_name=metric,
                current=float(current_val),
                baseline_series=[float(v) for v in baseline],
                period=period_str,
                history_months=history_months,
                use_zscore=use_z,
            )
            if fm:
                flagged.append(fm)

        # Upload count from fact table
        current_uploads  = upload_lookup.get((ch_id, current_month))
        baseline_uploads = [upload_lookup.get((ch_id, r["month"])) for r in baseline_rows]
        baseline_uploads = [v for v in baseline_uploads if v is not None]
        if current_uploads is not None and baseline_uploads:
            fm = _detect_metric_anomaly(
                entity_type="channel",
                entity_id=code,
                entity_label=label,
                metric_name="upload_count",
                current=float(current_uploads),
                baseline_series=[float(v) for v in baseline_uploads],
                period=period_str,
                history_months=len(baseline_uploads),
                use_zscore=False,
            )
            if fm:
                flagged.append(fm)

    # ── Per-user detection ────────────────────────────────────────────────────
    user_groups: dict[int, list[dict]] = {}
    for r in user_rows:
        user_groups.setdefault(r["user_id"], []).append(r)

    for uid, rows in user_groups.items():
        rows_sorted   = sorted(rows, key=lambda x: x["month"])
        current_row   = next((r for r in rows_sorted if r["month"] == current_month), None)
        baseline_rows = [r for r in rows_sorted if r["month"] != current_month]
        if current_row is None or not baseline_rows:
            continue

        label = current_row.get("user_name") or str(uid)

        for metric in ["output_count"]:
            current_val = current_row.get(metric)
            baseline    = [r.get(metric) for r in baseline_rows if r.get(metric) is not None]
            if current_val is None or not baseline:
                continue
            fm = _detect_metric_anomaly(
                entity_type="user",
                entity_id=label,
                entity_label=label,
                metric_name=metric,
                current=float(current_val),
                baseline_series=[float(v) for v in baseline],
                period=period_str,
                history_months=len(baseline),
                use_zscore=False,
            )
            if fm:
                flagged.append(fm)

    # ── Rank: high severity first, then by absolute delta ────────────────────
    severity_order = {"high": 0, "medium": 1, "low": 2}
    flagged.sort(key=lambda x: (severity_order[x.severity], -abs(x.delta_pct)))

    logger.info(
        "detector: client %s — %d anomalies flagged for period %s",
        client_id, len(flagged), period_str,
    )
    return flagged
