"""
Phase 1 Analyzer — Publishing Funnel Analyzer.

Detects chronic publish-rate gaps at channel level and output-type level.
Also builds the FunnelSummary (always-populated data for the Pipeline tab).
"""

import logging
from intelligence.insight_narrator.schemas import (
    FlaggedMetric, FunnelSummary, FunnelStage, FunnelByEntity,
)
from intelligence.insight_narrator.data_loader import HydratedDataBundle

log = logging.getLogger("narrator.funnel")

# Channels with publish_rate below this vs fleet median get flagged
GAP_THRESHOLD_PP = 15  # percentage points below fleet median


def analyze_funnel(bundle: HydratedDataBundle) -> tuple[list[FlaggedMetric], FunnelSummary]:
    """
    Returns:
      - signals: FlaggedMetric[] for channels with chronic low publish rate
      - summary: FunnelSummary (always populated, for the Pipeline tab viz)
    """
    signals: list[FlaggedMetric] = []

    # ── Build fleet-level funnel ───────────────────────────────────────────
    total_uploaded = sum(r.get("total_created", 0) for r in bundle.channel_health)
    total_published = sum(r.get("total_published", 0) for r in bundle.channel_health)
    # Use total_created as proxy for processed (Frammer processes all uploads)
    total_processed = total_uploaded

    fleet_rate = (total_published / total_uploaded * 100) if total_uploaded > 0 else 0

    stages = [
        FunnelStage(stage="uploaded", count=total_uploaded,
                    pct_of_uploaded=100.0),
        FunnelStage(stage="processed", count=total_processed,
                    pct_of_uploaded=round(total_processed / max(total_uploaded, 1) * 100, 1)),
        FunnelStage(stage="published", count=total_published,
                    pct_of_uploaded=round(total_published / max(total_uploaded, 1) * 100, 1)),
    ]

    # ── Per-channel funnel breakdown ───────────────────────────────────────
    by_channel: list[FunnelByEntity] = []

    for ch in bundle.channel_health:
        uploaded = ch.get("total_created", 0)
        published = ch.get("total_published", 0)
        rate = ch.get("publish_rate_pct", 0) or 0
        gap = uploaded - published

        if uploaded < 10:
            continue  # skip low-volume channels

        status = "critical" if rate < fleet_rate - GAP_THRESHOLD_PP else (
            "watch" if rate < fleet_rate else "healthy"
        )

        by_channel.append(FunnelByEntity(
            entity_label=ch.get("channel_name", str(ch.get("channel_id"))),
            entity_id=str(ch.get("channel_id")),
            uploaded=uploaded,
            processed=uploaded,  # proxy
            published=published,
            publish_rate=round(rate, 1),
            gap=gap,
            status=status,
        ))

        # Flag channels with chronic gaps
        if status == "critical":
            signals.append(FlaggedMetric(
                entity_type="channel",
                entity_id=str(ch.get("channel_id")),
                entity_label=ch.get("channel_name", ""),
                metric_name="publish_rate",
                current_value=round(rate, 1),
                reference_value=round(fleet_rate, 1),
                delta_pct=round(rate - fleet_rate, 1),
                severity="high" if rate < fleet_rate * 0.5 else "medium",
                period=bundle.monthly_kpis[0].get("month", "") if bundle.monthly_kpis else "",
                insight_source="funnel",
                suggested_action=(
                    f"{ch.get('channel_name', '')} publishes only {rate:.0f}% vs "
                    f"fleet avg {fleet_rate:.0f}%. "
                    f"Gap of {gap} unpublished videos. Investigate editorial bottleneck."
                ),
            ))

    # Sort by gap descending
    by_channel.sort(key=lambda x: x.gap, reverse=True)

    summary = FunnelSummary(
        stages=stages,
        by_channel=by_channel,
        total_gap=total_uploaded - total_published,
        fleet_publish_rate=round(fleet_rate, 1),
    )

    log.info(f"[FUNNEL] Fleet rate: {fleet_rate:.1f}%, {len(signals)} gap signals")
    return signals, summary
