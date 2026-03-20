"""
Phase 2 — Entity Synthesizer.

Groups signals by (entity_type, entity_id). If 3+ signals target the same
entity, creates a SynthesisBundle so the LLM produces one combined card
instead of 3 separate ones.
"""

import logging
from collections import defaultdict
from intelligence.insight_narrator.schemas import FlaggedMetric

log = logging.getLogger("narrator.synthesizer")

SYNTHESIS_THRESHOLD = 3  # signals per entity to trigger synthesis


def synthesize_entities(
    all_signals: list[FlaggedMetric],
) -> tuple[list[FlaggedMetric], list[dict]]:
    """
    Returns:
      - singles: signals that don't need synthesis (pass through)
      - bundles: [{entity_type, entity_id, entity_label, signals: [...]}]
                 for entities with 3+ signals
    """

    grouped: dict[tuple, list[FlaggedMetric]] = defaultdict(list)

    for sig in all_signals:
        key = (sig.entity_type, sig.entity_id)
        grouped[key].append(sig)

    singles: list[FlaggedMetric] = []
    bundles: list[dict] = []

    for (etype, eid), sigs in grouped.items():
        if len(sigs) >= SYNTHESIS_THRESHOLD:
            # Use highest severity label
            best_label = sigs[0].entity_label
            bundles.append({
                "entity_type": etype,
                "entity_id": eid,
                "entity_label": best_label,
                "signals": sigs,
                "signal_count": len(sigs),
                "max_severity": _max_severity(sigs),
            })
        else:
            singles.extend(sigs)

    log.info(
        f"[SYNTH] {len(singles)} singles, {len(bundles)} synthesis bundles "
        f"({sum(b['signal_count'] for b in bundles)} signals bundled)"
    )
    return singles, bundles


def _max_severity(sigs: list[FlaggedMetric]) -> str:
    order = {"high": 3, "medium": 2, "low": 1}
    return max(sigs, key=lambda s: order.get(s.severity, 0)).severity
