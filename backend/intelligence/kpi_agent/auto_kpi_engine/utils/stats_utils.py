"""
Statistical utility functions for the stats extractor and KPI evaluator.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ================================================================== #
# Basic descriptive statistics
# ================================================================== #

def safe_mean(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    return sum(vals) / len(vals) if vals else None


def safe_std(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if len(vals) < 2:
        return None
    mu = sum(vals) / len(vals)
    variance = sum((x - mu) ** 2 for x in vals) / (len(vals) - 1)
    return math.sqrt(variance)


def safe_variance(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if len(vals) < 2:
        return None
    mu = sum(vals) / len(vals)
    return sum((x - mu) ** 2 for x in vals) / (len(vals) - 1)


def safe_min(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    return min(vals) if vals else None


def safe_max(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    return max(vals) if vals else None


# ================================================================== #
# Entropy (Shannon)
# ================================================================== #

def entropy(values: Sequence[Any]) -> float:
    """
    Compute Shannon entropy (base-2) of a sequence of values.
    High entropy ≈ uniform distribution; low entropy ≈ concentrated.
    """
    n = len(values)
    if n == 0:
        return 0.0
    counts = Counter(values)
    result = 0.0
    for count in counts.values():
        if count > 0:
            p = count / n
            result -= p * math.log2(p)
    return result


# ================================================================== #
# Correlation
# ================================================================== #

def pearson_correlation(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    """
    Compute Pearson correlation coefficient between two equal-length sequences.
    Returns None if computation is not possible.
    """
    paired = [
        (a, b) for a, b in zip(x, y)
        if a is not None and b is not None and not math.isnan(a) and not math.isnan(b)
    ]
    n = len(paired)
    if n < 2:
        return None
    xs = [p[0] for p in paired]
    ys = [p[1] for p in paired]
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in paired)
    denom = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
    if denom == 0:
        return None
    return num / denom


def correlation_matrix(series_dict: Dict[str, List[float]]) -> Dict[Tuple[str, str], Optional[float]]:
    """
    Compute pairwise Pearson correlations for all pairs in *series_dict*.

    Returns a dict keyed by (kpi_id_a, kpi_id_b) → correlation.
    """
    keys = list(series_dict.keys())
    result: Dict[Tuple[str, str], Optional[float]] = {}
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            result[(a, b)] = pearson_correlation(series_dict[a], series_dict[b])
    return result


# ================================================================== #
# Null / unique utilities
# ================================================================== #

def null_rate(values: Sequence[Any]) -> float:
    """Fraction of None values in the sequence."""
    n = len(values)
    if n == 0:
        return 0.0
    return sum(1 for v in values if v is None) / n


def unique_count(values: Sequence[Any]) -> int:
    return len(set(v for v in values if v is not None))
