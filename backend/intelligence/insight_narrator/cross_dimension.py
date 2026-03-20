"""
Phase 1 Analyzer — Cross-Dimension Pattern Detector.

Finds surprising patterns across dimension pairs using entropy-based scoring.
Example: "Hindi × Reels: 0 output despite high demand elsewhere"
Example: "Channel Alpha × Interviews: 3x fleet average — heavy specialization"
"""

import logging
import math
from collections import defaultdict, Counter
from intelligence.insight_narrator.schemas import FlaggedMetric
from intelligence.insight_narrator.data_loader import HydratedDataBundle

log = logging.getLogger("narrator.cross_dim")

# Dimension pairs to analyze
DIM_PAIRS = [
    ("channel_id", "output_type_id"),  # what content types each channel produces
    ("channel_id", "language_id"),      # language distribution per channel
    ("channel_id", "input_type_id"),    # input content specialization
    ("user_id", "output_type_id"),      # user-type specialization (SPOF detection)
]

MAX_PATTERNS = 5  # return top N most surprising patterns


def detect_cross_dimension_patterns(bundle: HydratedDataBundle) -> list[FlaggedMetric]:
    """Find surprising cross-dimensional patterns in the fact_sample."""

    if not bundle.fact_sample:
        return []

    all_patterns: list[dict] = []

    for dim1, dim2 in DIM_PAIRS:
        patterns = _analyze_pair(bundle, dim1, dim2)
        all_patterns.extend(patterns)

    # Rank by surprise_score descending, take top N
    all_patterns.sort(key=lambda x: x["surprise_score"], reverse=True)
    top = all_patterns[:MAX_PATTERNS]

    signals = []
    for p in top:
        signals.append(FlaggedMetric(
            entity_type=p["dim1_type"],
            entity_id=str(p["dim1_value"]),
            entity_label=p["dim1_label"],
            metric_name=p["metric"],
            current_value=p["actual"],
            reference_value=p["expected"],
            delta_pct=p["delta_pct"],
            severity=_pattern_severity(p["surprise_score"]),
            period=bundle.monthly_kpis[0].get("month", "") if bundle.monthly_kpis else "",
            insight_source="cross_dim",
            dimensions=[p["dim1_type"], p["dim2_type"]],
            suggested_action=p["narrative"],
        ))

    log.info(f"[CROSS-DIM] Detected {len(signals)} cross-dimension patterns")
    return signals


def _analyze_pair(bundle: HydratedDataBundle, dim1: str, dim2: str) -> list[dict]:
    """Analyze a single dimension pair for surprising distributions."""

    # Build contingency: {dim1_val: {dim2_val: count}}
    contingency: dict[any, Counter] = defaultdict(Counter)
    dim2_totals: Counter = Counter()

    for row in bundle.fact_sample:
        d1 = row.get(dim1)
        d2 = row.get(dim2)
        if d1 is None or d2 is None:
            continue
        contingency[d1][d2] += 1
        dim2_totals[d2] += 1

    if not contingency or not dim2_totals:
        return []

    total = sum(dim2_totals.values())
    # Expected proportion of each dim2 value
    dim2_expected = {k: v / total for k, v in dim2_totals.items()}

    patterns = []
    dim1_type = dim1.replace("_id", "")
    dim2_type = dim2.replace("_id", "")

    for d1_val, d2_counts in contingency.items():
        d1_total = sum(d2_counts.values())
        if d1_total < 5:
            continue  # skip low-volume entities

        for d2_val, actual_count in d2_counts.items():
            actual_pct = actual_count / d1_total
            expected_pct = dim2_expected.get(d2_val, 0)

            if expected_pct < 0.01:
                continue  # skip very rare dim2 values

            # Surprise = KL divergence contribution (point-wise)
            if actual_pct > 0 and expected_pct > 0:
                surprise = actual_pct * math.log(actual_pct / expected_pct)
            else:
                surprise = 0

            # Also detect ZEROS — dimension gaps
            if actual_count == 0 and expected_pct > 0.1:
                surprise = expected_pct * 2  # boost zero-gaps

            if abs(surprise) < 0.05:
                continue

            delta_pct = ((actual_pct - expected_pct) / expected_pct * 100) if expected_pct > 0 else 0

            d1_label = _resolve(bundle, dim1_type, d1_val)
            d2_label = _resolve(bundle, dim2_type, d2_val)

            if actual_count == 0:
                narrative = (
                    f"{d1_label} produces 0 {d2_label} content, but "
                    f"{d2_label} accounts for {expected_pct*100:.0f}% of fleet output. "
                    f"Consider piloting {d2_label} for {d1_label}."
                )
                metric = f"zero_{dim2_type}_gap"
            elif actual_pct > expected_pct * 2:
                narrative = (
                    f"{d1_label} over-indexes on {d2_label} at {actual_pct*100:.0f}% "
                    f"vs fleet avg {expected_pct*100:.0f}%. Strong specialization."
                )
                metric = f"{dim2_type}_concentration"
            elif actual_pct < expected_pct * 0.5:
                narrative = (
                    f"{d1_label} under-indexes on {d2_label} at {actual_pct*100:.0f}% "
                    f"vs fleet avg {expected_pct*100:.0f}%. Potential expansion opportunity."
                )
                metric = f"{dim2_type}_underindex"
            else:
                continue

            patterns.append({
                "dim1_type": dim1_type,
                "dim1_value": d1_val,
                "dim1_label": d1_label,
                "dim2_type": dim2_type,
                "dim2_value": d2_val,
                "dim2_label": d2_label,
                "actual": round(actual_pct * 100, 1),
                "expected": round(expected_pct * 100, 1),
                "delta_pct": round(delta_pct, 1),
                "surprise_score": abs(surprise),
                "metric": metric,
                "narrative": narrative,
            })

    return patterns


def _resolve(bundle: HydratedDataBundle, dim_type: str, dim_id) -> str:
    lookup = {
        "channel": bundle.dim_channels,
        "user": bundle.dim_users,
        "output_type": bundle.dim_output_types,
        "input_type": bundle.dim_input_types,
        "language": bundle.dim_languages,
        "team": bundle.dim_teams,
    }
    return lookup.get(dim_type, {}).get(dim_id, str(dim_id))


def _pattern_severity(surprise: float) -> str:
    if surprise >= 0.5:
        return "high"
    if surprise >= 0.2:
        return "medium"
    return "low"
