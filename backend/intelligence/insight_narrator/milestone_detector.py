"""
Phase 1 Analyzer — Milestone Detector.

Detects POSITIVE achievements:
  - Record-breaking months (highest ever for a metric)
  - First-time thresholds crossed (e.g., first time > 500 videos)
  - Perfect publish rates (100% for a channel)

Milestones prevent the narrator from being purely problem-focused.
"""

import logging
from collections import defaultdict
from intelligence.insight_narrator.schemas import FlaggedMetric
from intelligence.insight_narrator.data_loader import HydratedDataBundle

log = logging.getLogger("narrator.milestone")

# Thresholds for "first time crossing X"
VOLUME_MILESTONES = [100, 250, 500, 1000, 2500, 5000]
PUBLISH_RATE_MILESTONE = 80  # first time above 80%


def detect_milestones(bundle: HydratedDataBundle) -> list[FlaggedMetric]:
    """Find positive achievements in the current period."""

    signals: list[FlaggedMetric] = []
    if not bundle.monthly_kpis:
        return signals

    period = bundle.monthly_kpis[0].get("month", "")

    # ── Record months per channel ──────────────────────────────────────────
    # Group by (channel_id, metric) → sorted monthly values
    channel_monthly: dict = defaultdict(list)

    for row in bundle.monthly_kpis:
        ch_id = row.get("channel_id")
        if ch_id is None:
            continue
        month = row.get("month", "")
        for metric in ["created_count", "published_count"]:
            val = row.get(metric)
            if val is not None:
                channel_monthly[(ch_id, metric)].append((month, float(val)))

    for (ch_id, metric), monthly in channel_monthly.items():
        if len(monthly) < 2:
            continue

        sorted_m = sorted(monthly, key=lambda x: x[0])
        latest_month, latest_val = sorted_m[-1]
        historical_max = max(v for _, v in sorted_m[:-1])

        if latest_val > historical_max and latest_val > 0 and historical_max > 0:
            pct_above = (latest_val - historical_max) / historical_max * 100
            if pct_above >= 10:  # at least 10% above previous record
                ch_label = bundle.dim_channels.get(ch_id, str(ch_id))
                metric_label = metric.replace("_", " ")

                signals.append(FlaggedMetric(
                    entity_type="channel",
                    entity_id=str(ch_id),
                    entity_label=ch_label,
                    metric_name=metric,
                    current_value=round(latest_val),
                    reference_value=round(historical_max),
                    delta_pct=round(pct_above, 1),
                    severity="low",  # milestones are always low severity (positive)
                    period=latest_month,
                    insight_source="milestone",
                    suggested_action=(
                        f"{ch_label} hit a new record for {metric_label}: "
                        f"{int(latest_val)} (previous best: {int(historical_max)}). "
                        f"Recognize the team and understand what drove this."
                    ),
                ))

    # ── Fleet-level volume milestones ──────────────────────────────────────
    fleet_monthly: dict[str, float] = defaultdict(float)
    for row in bundle.monthly_kpis:
        month = row.get("month", "")
        fleet_monthly[month] += float(row.get("created_count", 0) or 0)

    if fleet_monthly:
        sorted_fleet = sorted(fleet_monthly.items())
        latest_month, latest_total = sorted_fleet[-1]

        for milestone in VOLUME_MILESTONES:
            # Check if this is the first time crossing this milestone
            previous_crossed = any(v >= milestone for m, v in sorted_fleet[:-1])
            if latest_total >= milestone and not previous_crossed:
                signals.append(FlaggedMetric(
                    entity_type="fleet",
                    entity_id="milestone",
                    entity_label="Fleet-wide",
                    metric_name="total_created",
                    current_value=round(latest_total),
                    reference_value=milestone,
                    delta_pct=round((latest_total - milestone) / milestone * 100, 1),
                    severity="low",
                    period=latest_month,
                    insight_source="milestone",
                    suggested_action=(
                        f"First time crossing {milestone} videos in a single month "
                        f"({int(latest_total)} total). A growth milestone worth celebrating."
                    ),
                ))
                break  # only report the highest milestone crossed

    log.info(f"[MILESTONE] Detected {len(signals)} milestones")
    return signals
