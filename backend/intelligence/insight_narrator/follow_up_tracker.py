"""
Phase 3 — Follow-Up Tracker.

Replaces the simple deduplicator with temporal awareness.
Tags each signal with status: new | ongoing | worsening | resolved.
Also generates "resolved" signals for previously-flagged issues that recovered.
"""

import logging
from intelligence.insight_narrator.schemas import FlaggedMetric
from intelligence.insight_narrator.data_loader import HydratedDataBundle

log = logging.getLogger("narrator.follow_up")

# Suppress ongoing signals if unchanged for < 7 days
SUPPRESS_UNCHANGED_DAYS = 7


def track_follow_ups(
    signals: list[FlaggedMetric],
    bundle: HydratedDataBundle,
) -> tuple[list[FlaggedMetric], list[FlaggedMetric]]:
    """
    Returns:
      - tagged_signals: input signals with status field updated
      - resolved_signals: new FlaggedMetric(status="resolved") for recovered issues
    """

    history = bundle.insight_history
    history_keys = {}
    for h in history:
        key = (
            h.get("entity_type"),
            h.get("entity_id"),
            h.get("metric_name"),
        )
        history_keys[key] = h

    tagged: list[FlaggedMetric] = []
    seen_keys: set[tuple] = set()

    for sig in signals:
        key = (sig.entity_type, sig.entity_id, sig.metric_name)
        seen_keys.add(key)

        prev = history_keys.get(key)

        if prev is None:
            # Brand new signal
            sig.status = "new"
            tagged.append(sig)
        else:
            prev_severity = prev.get("last_severity", "low")
            severity_order = {"high": 3, "medium": 2, "low": 1}
            current_rank = severity_order.get(sig.severity, 0)
            prev_rank = severity_order.get(prev_severity, 0)

            if current_rank > prev_rank:
                sig.status = "worsening"
                sig.consecutive_periods = prev.get("consecutive_periods", 1) + 1
                tagged.append(sig)
            else:
                # Ongoing — same or lower severity
                sig.status = "ongoing"
                sig.consecutive_periods = prev.get("consecutive_periods", 1) + 1

                # Suppress if unchanged and seen recently
                days_since = _days_since_last_seen(prev)
                if days_since < SUPPRESS_UNCHANGED_DAYS and current_rank <= prev_rank:
                    continue  # suppress

                tagged.append(sig)

    # ── Generate resolved signals ──────────────────────────────────────────
    resolved: list[FlaggedMetric] = []
    for key, hist in history_keys.items():
        if key not in seen_keys:
            # Was in history but NOT in current signals → resolved
            entity_type, entity_id, metric_name = key
            resolved.append(FlaggedMetric(
                entity_type=entity_type,
                entity_id=str(entity_id),
                entity_label=str(entity_id),  # will be enriched by narrator
                metric_name=metric_name,
                current_value=0,
                reference_value=0,
                delta_pct=0,
                severity="low",
                period=bundle.monthly_kpis[0].get("month", "") if bundle.monthly_kpis else "",
                insight_source=hist.get("insight_type", "anomaly"),
                status="resolved",
                consecutive_periods=hist.get("consecutive_periods", 1),
            ))

    log.info(
        f"[FOLLOW-UP] {len(tagged)} active ({_count_by_status(tagged)}), "
        f"{len(resolved)} resolved"
    )
    return tagged, resolved


def _days_since_last_seen(hist: dict) -> int:
    from datetime import datetime
    last = hist.get("last_seen_at")
    if last is None:
        return 999
    if isinstance(last, str):
        try:
            last = datetime.fromisoformat(last)
        except (ValueError, TypeError):
            return 999
    if hasattr(last, 'tzinfo') and last.tzinfo is not None:
        last = last.replace(tzinfo=None)
    return (datetime.now() - last).days


def _count_by_status(signals: list[FlaggedMetric]) -> str:
    counts = {}
    for s in signals:
        counts[s.status] = counts.get(s.status, 0) + 1
    return ", ".join(f"{k}={v}" for k, v in counts.items())
