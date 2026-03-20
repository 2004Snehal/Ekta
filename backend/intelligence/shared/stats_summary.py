"""
stats_summary.py — shared statistical summarizer for LLM data formatting.

Replaces raw row dumps with compact statistical summaries before any LLM call.
Used by: recommendation/engine.py, chart_insight_agent/agent.py

Auto-detects data shape:
  - Numeric columns  → min, max, mean, std, total
  - Categorical cols → unique count + top value distribution
  - Time series      → first, last, peak, trough, trend direction + change %
  - Always appends   → top N rows by primary metric (and bottom 2 if n > cap)
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any


def summarize_rows(
    rows: list[dict],
    label: str = "",
    row_cap: int = 5,
) -> str:
    """
    Convert a list of DB row dicts into a compact statistical summary string
    suitable for LLM consumption.

    Args:
        rows:    list of row dicts (from DB query or chart data)
        label:   section heading prepended to output
        row_cap: max number of sample rows to show

    Returns:
        Multi-line string ready to be included in an LLM prompt.
    """
    if not rows:
        return f"### {label}\n(no data)\n" if label else "(no data)\n"

    n = len(rows)
    keys = list(rows[0].keys())

    # ── Classify columns ──────────────────────────────────────────────────────
    numeric_cols: list[str] = []
    cat_cols: list[str] = []
    date_cols: list[str] = []

    for k in keys:
        sample = [r[k] for r in rows[:20] if r.get(k) is not None]
        if not sample:
            continue
        if isinstance(sample[0], (int, float)):
            numeric_cols.append(k)
        elif isinstance(sample[0], str):
            # Heuristic: YYYY-MM or YYYY-MM-DD
            if all(len(str(v)) <= 10 and "-" in str(v) for v in sample[:5]):
                date_cols.append(k)
            else:
                cat_cols.append(k)

    lines: list[str] = []
    lines.append(f"### {label} ({n} rows)" if label else f"({n} rows)")

    # ── Numeric stats ─────────────────────────────────────────────────────────
    for col in numeric_cols:
        vals = [float(r[col]) for r in rows if r.get(col) is not None]
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        std = (
            math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
            if len(vals) > 1
            else 0.0
        )
        lines.append(
            f"  {col}: min={min(vals):.2f}  max={max(vals):.2f}  "
            f"mean={mean:.2f}  std={std:.2f}  total={sum(vals):.2f}"
        )

    # ── Categorical stats ─────────────────────────────────────────────────────
    for col in cat_cols:
        counts = Counter(str(r[col]) for r in rows if r.get(col) is not None)
        top = counts.most_common(5)
        lines.append(
            f"  {col} (unique={len(counts)}): "
            + ", ".join(f"{v}×{c}" for v, c in top)
        )

    # ── Time-series summary (when date + numeric cols co-exist) ───────────────
    if date_cols and numeric_cols:
        date_col = date_cols[0]
        val_col = numeric_cols[0]
        pairs = [
            (r[date_col], float(r[val_col]))
            for r in rows
            if r.get(date_col) is not None and r.get(val_col) is not None
        ]
        if len(pairs) >= 2:
            pairs.sort(key=lambda x: str(x[0]))
            first_p, last_p = pairs[0], pairs[-1]
            peak_p = max(pairs, key=lambda x: x[1])
            trough_p = min(pairs, key=lambda x: x[1])
            trend = (
                "↑" if last_p[1] > first_p[1]
                else "↓" if last_p[1] < first_p[1]
                else "→"
            )
            change_pct = (
                (last_p[1] - first_p[1]) / first_p[1] * 100
                if first_p[1] != 0
                else 0.0
            )
            lines.append(
                f"  trend({val_col}): {trend} {change_pct:+.1f}%  "
                f"first={first_p[0]}:{first_p[1]:.2f}  "
                f"last={last_p[0]}:{last_p[1]:.2f}  "
                f"peak={peak_p[0]}:{peak_p[1]:.2f}  "
                f"trough={trough_p[0]}:{trough_p[1]:.2f}"
            )

    # ── Top N sample rows ─────────────────────────────────────────────────────
    # Columns shown per row: up to 2 categorical + 1 date + 3 numeric
    show_cols = [*cat_cols[:2], *date_cols[:1], *numeric_cols[:3]]
    if not show_cols:
        show_cols = keys[:5]

    if numeric_cols:
        primary = numeric_cols[0]
        top_rows = sorted(
            rows, key=lambda r: r.get(primary) or 0, reverse=True
        )[:row_cap]
        lines.append(f"  top {len(top_rows)} by {primary}:")
    else:
        top_rows = rows[:row_cap]
        lines.append(f"  sample ({len(top_rows)}):")

    for r in top_rows:
        parts = [f"{k}={r[k]}" for k in show_cols if r.get(k) is not None]
        lines.append("    " + "  ".join(parts))

    # Bottom 2 (only useful when there's a numeric ranking)
    if n > row_cap and numeric_cols:
        primary = numeric_cols[0]
        bottom_rows = sorted(
            rows, key=lambda r: r.get(primary) or 0
        )[:2]
        lines.append(f"  bottom 2 by {primary}:")
        for r in bottom_rows:
            parts = [f"{k}={r[k]}" for k in show_cols if r.get(k) is not None]
            lines.append("    " + "  ".join(parts))

    return "\n".join(lines) + "\n"
