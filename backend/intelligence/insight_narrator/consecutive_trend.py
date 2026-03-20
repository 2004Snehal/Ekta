"""
Phase 1 Analyzer — Consecutive Trend Detector.

Finds metrics that have moved in the SAME direction for 3+ consecutive months,
even if each individual month's change is below the anomaly threshold.
"""

import logging
from collections import defaultdict
from intelligence.insight_narrator.schemas import FlaggedMetric
from intelligence.insight_narrator.data_loader import HydratedDataBundle

log = logging.getLogger("narrator.consecutive_trend")

MIN_CONSECUTIVE = 3  # months in same direction to flag


def detect_consecutive_trends(bundle: HydratedDataBundle) -> list[FlaggedMetric]:
    """Detect 3+ month directional trends across entities and metrics."""

    signals: list[FlaggedMetric] = []

    # Group monthly_kpis by entity
    entity_series = _build_entity_series(bundle)

    for (entity_type, entity_id, metric), monthly_values in entity_series.items():
        if len(monthly_values) < MIN_CONSECUTIVE + 1:
            continue

        # Sort by month ascending
        sorted_months = sorted(monthly_values.items())
        values = [v for _, v in sorted_months]
        months = [m for m, _ in sorted_months]

        # Count consecutive direction
        direction = None
        streak = 0
        for i in range(1, len(values)):
            if values[i] is None or values[i - 1] is None:
                direction = None
                streak = 0
                continue

            if values[i - 1] == 0:
                direction = None
                streak = 0
                continue

            delta = values[i] - values[i - 1]
            current_dir = "up" if delta > 0 else ("down" if delta < 0 else None)

            if current_dir is None:
                direction = None
                streak = 0
                continue

            if current_dir == direction:
                streak += 1
            else:
                direction = current_dir
                streak = 1

        if streak >= MIN_CONSECUTIVE and direction is not None:
            current = values[-1] or 0
            reference = values[-(streak + 1)] if len(values) > streak else values[0]
            reference = reference or 1

            total_delta = ((current - reference) / abs(reference) * 100) if reference != 0 else 0

            # Severity based on streak length and total delta
            severity = _trend_severity(streak, abs(total_delta))

            entity_label = _resolve_label(bundle, entity_type, entity_id)

            signals.append(FlaggedMetric(
                entity_type=entity_type,
                entity_id=str(entity_id),
                entity_label=entity_label,
                metric_name=metric,
                current_value=round(current, 2),
                reference_value=round(reference, 2),
                delta_pct=round(total_delta, 1),
                severity=severity,
                period=months[-1],
                history_months=len(values),
                insight_source="consecutive",
                consecutive_periods=streak,
                suggested_action=_suggest_action(entity_label, metric, direction, streak),
            ))

    log.info(f"[TREND] Detected {len(signals)} consecutive trends")
    return signals


def _build_entity_series(bundle: HydratedDataBundle) -> dict:
    """Build {(entity_type, entity_id, metric): {month: value}} from monthly_kpis."""
    series = defaultdict(dict)

    for row in bundle.monthly_kpis:
        month = row.get("month")

        # Channel-level metrics
        ch_id = row.get("channel_id")
        if ch_id:
            for metric in ["created_count", "published_count", "publish_rate_pct"]:
                val = row.get(metric)
                if val is not None:
                    key = ("channel", ch_id, metric)
                    if month not in series[key]:
                        series[key][month] = 0
                    series[key][month] += float(val)

        # Output type metrics (aggregate across channels)
        ot_id = row.get("output_type_id")
        if ot_id:
            for metric in ["created_count", "published_count"]:
                val = row.get(metric)
                if val is not None:
                    key = ("output_type", ot_id, metric)
                    if month not in series[key]:
                        series[key][month] = 0
                    series[key][month] += float(val)

        # Language metrics
        lang_id = row.get("language_id")
        if lang_id:
            for metric in ["created_count", "published_count"]:
                val = row.get(metric)
                if val is not None:
                    key = ("language", lang_id, metric)
                    if month not in series[key]:
                        series[key][month] = 0
                    series[key][month] += float(val)

    return series


def _trend_severity(streak: int, total_delta_abs: float) -> str:
    if streak >= 5 or total_delta_abs >= 40:
        return "high"
    if streak >= 4 or total_delta_abs >= 25:
        return "medium"
    return "low"


def _resolve_label(bundle: HydratedDataBundle, entity_type: str, entity_id) -> str:
    lookup = {
        "channel": bundle.dim_channels,
        "user": bundle.dim_users,
        "output_type": bundle.dim_output_types,
        "input_type": bundle.dim_input_types,
        "language": bundle.dim_languages,
        "team": bundle.dim_teams,
    }
    return lookup.get(entity_type, {}).get(entity_id, str(entity_id))


def _suggest_action(label: str, metric: str, direction: str, streak: int) -> str:
    verb = "declining" if direction == "down" else "growing"
    return (
        f"{label}'s {metric.replace('_', ' ')} has been {verb} for "
        f"{streak} consecutive months. Review underlying drivers."
    )
