"""Latency statistics for NLQ evaluation results."""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evaluation.pipelines.base import EvalResult


def compute_latency_percentiles(results: list["EvalResult"]) -> dict:
    """Compute latency statistics from result.latency_ms values.

    Returns a dict with:
      - p50:     50th-percentile latency in ms (rounded to 1 dp).
      - p95:     95th-percentile latency in ms (rounded to 1 dp).
      - mean:    Arithmetic mean latency in ms (rounded to 1 dp).
      - min:     Minimum latency in ms (rounded to 1 dp).
      - max:     Maximum latency in ms (rounded to 1 dp).
      - n_total: Number of results included.

    Uses ``statistics.quantiles`` for p50 / p95 calculations.
    Returns zero-filled dict if the result list is empty.
    """
    if not results:
        return {"p50": 0.0, "p95": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0, "n_total": 0}

    latencies = [r.latency_ms for r in results]
    n_total = len(latencies)

    mean_val = round(statistics.mean(latencies), 1)
    min_val = round(min(latencies), 1)
    max_val = round(max(latencies), 1)

    if n_total == 1:
        # quantiles requires at least 2 data points for n=100
        p50 = round(latencies[0], 1)
        p95 = round(latencies[0], 1)
    else:
        # statistics.quantiles returns (n-1) cut points for n quantiles.
        # For percentiles we use n=100; index 49 → p50, index 94 → p95.
        quantile_points = statistics.quantiles(latencies, n=100)
        p50 = round(quantile_points[49], 1)
        p95 = round(quantile_points[94], 1)

    return {
        "p50": p50,
        "p95": p95,
        "mean": mean_val,
        "min": min_val,
        "max": max_val,
        "n_total": n_total,
    }


def compute_latency_by_complexity(results: list["EvalResult"]) -> dict:
    """Group results by complexity level and return p50 latency per group.

    Checks each result for a ``complexity`` attribute.  Results lacking the
    attribute are silently skipped.  If no results carry the attribute, an
    empty dict is returned.

    Returns a dict mapping complexity level (as a string) to p50 latency in ms
    (rounded to 1 dp).
    """
    groups: dict[str, list[float]] = {}

    for r in results:
        complexity = getattr(r, "complexity", None)
        if complexity is None:
            continue
        key = str(complexity)
        groups.setdefault(key, []).append(r.latency_ms)

    if not groups:
        return {}

    p50_by_complexity: dict[str, float] = {}
    for level, latencies in groups.items():
        if len(latencies) == 1:
            p50_by_complexity[level] = round(latencies[0], 1)
        else:
            quantile_points = statistics.quantiles(latencies, n=100)
            p50_by_complexity[level] = round(quantile_points[49], 1)

    return p50_by_complexity
