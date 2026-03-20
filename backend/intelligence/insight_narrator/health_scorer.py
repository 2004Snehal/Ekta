"""
Phase 6 — Entity Health Scorer.

Computes a 0-100 health score for each channel (and fleet-wide pulse score).
Components:
  - publish_rate_score (40%) — vs fleet median
  - activity_score (30%) — MoM consistency, penalize gaps
  - trend_score (20%) — direction of last 3 months
  - dq_score (10%) — % complete records for this entity

Grades: A(80+) B(60-79) C(40-59) D(<40)
"""

import logging
from collections import defaultdict
from intelligence.insight_narrator.schemas import EntityHealthScore, FlaggedMetric
from intelligence.insight_narrator.data_loader import HydratedDataBundle

log = logging.getLogger("narrator.health")


def score_entity_health(
    bundle: HydratedDataBundle,
    signals: list[FlaggedMetric],
) -> tuple[list[EntityHealthScore], int]:
    """
    Returns:
      - scores: per-channel EntityHealthScore list
      - pulse: fleet-wide 0-100 pulse score
    """

    scores: list[EntityHealthScore] = []

    # Build signal counts per entity
    signal_counts: dict[str, int] = defaultdict(int)
    signal_top: dict[str, str] = {}       # entity_id → top signal title/action
    signal_top_sev: dict[str, str] = {}   # entity_id → severity of top signal
    severity_rank = {"high": 3, "medium": 2, "low": 1}

    for sig in signals:
        key = sig.entity_id
        signal_counts[key] += 1
        if key not in signal_top or severity_rank.get(sig.severity, 0) > severity_rank.get(signal_top_sev.get(key, "low"), 0):
            signal_top[key] = sig.suggested_action or sig.metric_name
            signal_top_sev[key] = sig.severity

    # Fleet-level stats for normalization
    fleet_rates = [float(ch.get("publish_rate_pct", 0) or 0) for ch in bundle.channel_health]
    fleet_median = sorted(fleet_rates)[len(fleet_rates) // 2] if fleet_rates else 50

    # Build monthly volumes per channel for consistency scoring
    channel_months = _build_channel_monthly(bundle)

    # DQ per channel
    channel_dq = _build_channel_dq(bundle)

    for ch in bundle.channel_health:
        ch_id = str(ch.get("channel_id"))
        ch_name = ch.get("channel_name", ch_id)
        rate = float(ch.get("publish_rate_pct", 0) or 0)

        # Component 1: publish_rate_score (40%)
        pr_score = min(100, rate / max(fleet_median, 1) * 50 + 25)

        # Component 2: activity_score (30%)
        monthly = channel_months.get(int(ch.get("channel_id", 0)), [])
        act_score = _activity_consistency(monthly)

        # Component 3: trend_score (20%)
        trend_score = _trend_direction(monthly)

        # Component 4: dq_score (10%)
        dq = channel_dq.get(int(ch.get("channel_id", 0)), 100)

        # Weighted composite
        total = int(pr_score * 0.4 + act_score * 0.3 + trend_score * 0.2 + dq * 0.1)
        total = max(0, min(100, total))

        grade = "A" if total >= 80 else "B" if total >= 60 else "C" if total >= 40 else "D"

        scores.append(EntityHealthScore(
            entity_type="channel",
            entity_id=ch_id,
            entity_label=ch_name,
            score=total,
            grade=grade,
            components={
                "publish_rate": round(pr_score),
                "activity": round(act_score),
                "trend": round(trend_score),
                "data_quality": round(dq),
            },
            signal_count=signal_counts.get(ch_id, 0),
            top_signal=signal_top.get(ch_id),
        ))

    # Sort by score descending
    scores.sort(key=lambda s: s.score, reverse=True)

    # Fleet pulse = weighted average of channel scores
    if scores:
        pulse = int(sum(s.score for s in scores) / len(scores))
    else:
        pulse = 50

    log.info(f"[HEALTH] {len(scores)} entities scored, pulse={pulse}")
    return scores, pulse


def _build_channel_monthly(bundle: HydratedDataBundle) -> dict[int, list[float]]:
    """Build {channel_id: [month1_count, month2_count, ...]} sorted chronologically."""
    monthly: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in bundle.monthly_kpis:
        ch_id = row.get("channel_id")
        if ch_id is None:
            continue
        month = row.get("month", "")
        monthly[ch_id][month] += float(row.get("created_count", 0) or 0)

    result = {}
    for ch_id, by_month in monthly.items():
        sorted_vals = [v for _, v in sorted(by_month.items())]
        result[ch_id] = sorted_vals

    return result


def _activity_consistency(monthly_values: list[float]) -> float:
    """Score 0-100 based on MoM consistency. Penalize gaps and volatility."""
    if not monthly_values or len(monthly_values) < 2:
        return 50

    # Check for zero months
    zero_months = sum(1 for v in monthly_values if v == 0)
    if zero_months > 0:
        return max(0, 50 - zero_months * 20)

    # Coefficient of variation (lower = more consistent = higher score)
    mean = sum(monthly_values) / len(monthly_values)
    if mean == 0:
        return 0
    variance = sum((v - mean) ** 2 for v in monthly_values) / len(monthly_values)
    cv = (variance ** 0.5) / mean

    # CV of 0 → 100, CV of 1.0 → 20
    return max(0, min(100, int(100 - cv * 80)))


def _trend_direction(monthly_values: list[float]) -> float:
    """Score 0-100 based on trend of last 3 months. Up = good."""
    if len(monthly_values) < 3:
        return 50  # neutral

    last3 = monthly_values[-3:]
    if last3[0] == 0:
        return 50

    # Simple: compare last vs first of 3-month window
    change = (last3[-1] - last3[0]) / abs(last3[0]) * 100

    if change > 20:
        return 90
    elif change > 5:
        return 70
    elif change > -5:
        return 50
    elif change > -20:
        return 30
    else:
        return 10


def _build_channel_dq(bundle: HydratedDataBundle) -> dict[int, float]:
    """Build {channel_id: dq_score_0_100} from fact_sample."""
    from collections import Counter

    channel_total: Counter = Counter()
    channel_nulls: Counter = Counter()

    check_fields = ["team_id", "platform_id", "input_type_id", "output_type_id"]

    for row in bundle.fact_sample:
        ch_id = row.get("channel_id")
        if ch_id is None:
            continue
        channel_total[ch_id] += 1
        for f in check_fields:
            if row.get(f) is None:
                channel_nulls[ch_id] += 1

    result = {}
    for ch_id, total in channel_total.items():
        nulls = channel_nulls.get(ch_id, 0)
        max_nulls = total * len(check_fields)
        if max_nulls > 0:
            completeness = (1 - nulls / max_nulls) * 100
        else:
            completeness = 100
        result[ch_id] = round(completeness, 1)

    return result
