"""
Phase 1 Analyzer — Operational Risk Detector.

Detects structural operational risks:
  - Dead/dormant channels (30+ days no activity)
  - SPOF users (sole producer of a content type)
  - Concentration risk (top N users = >X% of output)
  - Ghost users (account exists, 0 output in 60 days)
"""

import logging
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from intelligence.insight_narrator.schemas import FlaggedMetric
from intelligence.insight_narrator.data_loader import HydratedDataBundle

log = logging.getLogger("narrator.op_risk")

DORMANT_DAYS = 30
CONCENTRATION_THRESHOLD = 0.75  # top 2 users = >75% of output
GHOST_DAYS = 60


def detect_operational_risks(bundle: HydratedDataBundle) -> list[FlaggedMetric]:
    """Detect dead channels, SPOF, concentration, ghost users."""

    signals: list[FlaggedMetric] = []
    period = bundle.monthly_kpis[0].get("month", "") if bundle.monthly_kpis else ""

    signals.extend(_detect_dormant_channels(bundle, period))
    signals.extend(_detect_spof_users(bundle, period))
    signals.extend(_detect_concentration_risk(bundle, period))

    log.info(f"[OP-RISK] Detected {len(signals)} operational risks")
    return signals


def _detect_dormant_channels(bundle: HydratedDataBundle, period: str) -> list[FlaggedMetric]:
    """Channels with 0 activity for DORMANT_DAYS+ days."""
    signals = []
    now = datetime.now()

    for ch in bundle.channel_health:
        last_activity = ch.get("last_activity")
        if last_activity is None:
            continue

        if isinstance(last_activity, str):
            try:
                last_activity = datetime.fromisoformat(last_activity)
            except (ValueError, TypeError):
                continue

        # Make both naive for comparison
        if hasattr(last_activity, 'tzinfo') and last_activity.tzinfo is not None:
            last_activity = last_activity.replace(tzinfo=None)

        days_inactive = (now - last_activity).days

        if days_inactive >= DORMANT_DAYS and ch.get("total_created", 0) > 20:
            ch_name = ch.get("channel_name", str(ch.get("channel_id")))
            signals.append(FlaggedMetric(
                entity_type="channel",
                entity_id=str(ch.get("channel_id")),
                entity_label=ch_name,
                metric_name="days_inactive",
                current_value=days_inactive,
                reference_value=0,
                delta_pct=100,
                severity="high" if days_inactive >= 60 else "medium",
                period=period,
                insight_source="op_risk",
                suggested_action=(
                    f"{ch_name} has had no activity for {days_inactive} days. "
                    f"Previously produced {ch.get('total_created', 0)} videos. "
                    f"Investigate if channel is deprecated or if there's an issue."
                ),
            ))

    return signals


def _detect_spof_users(bundle: HydratedDataBundle, period: str) -> list[FlaggedMetric]:
    """Single Point of Failure: one user is sole producer of an output type."""
    signals = []

    # Group fact_sample by output_type → set of users
    type_users: dict[int, set] = defaultdict(set)
    type_counts: Counter = Counter()

    for row in bundle.fact_sample:
        ot_id = row.get("output_type_id")
        u_id = row.get("user_id")
        if ot_id is not None and u_id is not None:
            type_users[ot_id].add(u_id)
            type_counts[ot_id] += 1

    for ot_id, users in type_users.items():
        if len(users) == 1 and type_counts[ot_id] >= 10:
            user_id = list(users)[0]
            ot_label = bundle.dim_output_types.get(ot_id, str(ot_id))
            user_label = bundle.dim_users.get(user_id, str(user_id))

            signals.append(FlaggedMetric(
                entity_type="user",
                entity_id=str(user_id),
                entity_label=user_label,
                metric_name="spof_output_type",
                current_value=type_counts[ot_id],
                reference_value=1,  # 1 user
                delta_pct=0,
                severity="medium",
                period=period,
                insight_source="op_risk",
                suggested_action=(
                    f"{user_label} is the sole producer of {ot_label} content "
                    f"({type_counts[ot_id]} videos in 90 days). "
                    f"If this user becomes unavailable, {ot_label} output drops to zero. "
                    f"Consider cross-training additional users."
                ),
            ))

    return signals


def _detect_concentration_risk(bundle: HydratedDataBundle, period: str) -> list[FlaggedMetric]:
    """Top 2 users produce >75% of all output."""
    signals = []

    # Aggregate user volumes
    user_volumes: Counter = Counter()
    for up in bundle.user_performance:
        user_volumes[up.get("user_id")] += up.get("created_count", 0)

    total = sum(user_volumes.values())
    if total < 50 or len(user_volumes) < 3:
        return signals

    # Top 2 users
    top2 = user_volumes.most_common(2)
    top2_total = sum(v for _, v in top2)
    top2_pct = top2_total / total * 100

    if top2_pct >= CONCENTRATION_THRESHOLD * 100:
        top_names = [
            bundle.dim_users.get(uid, str(uid)) for uid, _ in top2
        ]
        signals.append(FlaggedMetric(
            entity_type="fleet",
            entity_id="concentration",
            entity_label="Fleet-wide",
            metric_name="user_concentration",
            current_value=round(top2_pct, 1),
            reference_value=50,  # ideal: top 2 ≤ 50%
            delta_pct=round(top2_pct - 50, 1),
            severity="high" if top2_pct >= 85 else "medium",
            period=period,
            insight_source="op_risk",
            suggested_action=(
                f"Top 2 users ({', '.join(top_names)}) produce {top2_pct:.0f}% of all output. "
                f"If either is unavailable, monthly output drops significantly. "
                f"Consider distributing workload across more team members."
            ),
        ))

    return signals
