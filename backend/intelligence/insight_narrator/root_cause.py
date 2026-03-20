"""
Root Cause Decomposition.

When a metric anomaly is detected, automatically find which dimension
drove the change. Inspired by Amplitude's root cause analysis.

Example output: "80% of the publish_rate drop came from Summary Videos output type"
"""

import logging
from collections import defaultdict
from intelligence.insight_narrator.data_loader import HydratedDataBundle

log = logging.getLogger("narrator.root_cause")


def decompose_root_cause(
    bundle: HydratedDataBundle,
    entity_type: str,
    entity_id: str,
    metric_name: str,
) -> list[dict]:
    """
    For a flagged metric on a specific entity, find which sub-dimension
    contributed most to the anomaly.

    Returns list of {dimension, driver_label, driver_id, contribution_pct, value}
    sorted by |contribution_pct| descending.
    """

    if entity_type != "channel":
        return []  # only decompose channel-level anomalies for now

    channel_id = int(entity_id) if entity_id.isdigit() else None
    if channel_id is None:
        return []

    breakdowns = []

    # Decompose by output_type
    by_ot = _breakdown_by_dim(
        bundle.fact_sample, channel_id,
        group_dim="output_type_id", metric_name=metric_name,
        label_lookup=bundle.dim_output_types,
        dim_name="output_type",
    )
    breakdowns.extend(by_ot)

    # Decompose by user
    by_user = _breakdown_by_dim(
        bundle.fact_sample, channel_id,
        group_dim="user_id", metric_name=metric_name,
        label_lookup=bundle.dim_users,
        dim_name="user",
    )
    breakdowns.extend(by_user)

    # Decompose by language
    by_lang = _breakdown_by_dim(
        bundle.fact_sample, channel_id,
        group_dim="language_id", metric_name=metric_name,
        label_lookup=bundle.dim_languages,
        dim_name="language",
    )
    breakdowns.extend(by_lang)

    # Sort by contribution descending, return top 3
    breakdowns.sort(key=lambda x: abs(x.get("contribution_pct", 0)), reverse=True)
    return breakdowns[:3]


def _breakdown_by_dim(
    fact_sample: list[dict],
    channel_id: int,
    group_dim: str,
    metric_name: str,
    label_lookup: dict,
    dim_name: str,
) -> list[dict]:
    """Group fact_sample by a dimension and compute metric contribution."""

    # Filter to this channel
    channel_rows = [r for r in fact_sample if r.get("channel_id") == channel_id]
    if not channel_rows:
        return []

    # Group by dimension
    groups: dict[any, dict] = defaultdict(lambda: {"total": 0, "published": 0})

    for row in channel_rows:
        dim_val = row.get(group_dim)
        if dim_val is None:
            dim_val = "unknown"
        groups[dim_val]["total"] += 1
        if row.get("published_flag"):
            groups[dim_val]["published"] += 1

    total_all = sum(g["total"] for g in groups.values())
    published_all = sum(g["published"] for g in groups.values())

    if total_all == 0:
        return []

    results = []
    for dim_val, counts in groups.items():
        if counts["total"] < 3:
            continue

        if metric_name == "publish_rate":
            group_rate = counts["published"] / counts["total"] * 100
            fleet_rate = published_all / total_all * 100 if total_all > 0 else 0
            # Contribution: how much this group drags down (or up) the overall rate
            weight = counts["total"] / total_all
            contribution = weight * (group_rate - fleet_rate)

            label = label_lookup.get(dim_val, str(dim_val))
            results.append({
                "dimension": dim_name,
                "driver_label": label,
                "driver_id": str(dim_val),
                "contribution_pct": round(contribution, 1),
                "value": round(group_rate, 1),
                "count": counts["total"],
            })
        elif metric_name in ("output_count", "created_count"):
            weight = counts["total"] / total_all * 100
            label = label_lookup.get(dim_val, str(dim_val))
            results.append({
                "dimension": dim_name,
                "driver_label": label,
                "driver_id": str(dim_val),
                "contribution_pct": round(weight, 1),
                "value": counts["total"],
                "count": counts["total"],
            })

    return results
