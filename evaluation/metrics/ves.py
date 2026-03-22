"""Valid Efficiency Score (VES) — BIRD execution-time variant and static heuristic."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evaluation.pipelines.base import EvalResult


# ---------------------------------------------------------------------------
# BIRD VES (execution-time based)
# ---------------------------------------------------------------------------


def ves_bird(
    pred_rows: list[dict],
    gold_rows: list[dict],
    pred_time_ms: float,
    gold_time_ms: float,
) -> float:
    """Compute BIRD's Valid Efficiency Score for a single query.

    Formula:
      Vi  = 1 if result sets match (order-insensitive), else 0
      Ri  = min(gold_time_ms / pred_time_ms, 1.0)  — efficiency ratio capped at 1
      VES = Vi * Ri

    Returns 0.0 when pred_time_ms == 0 or the result sets do not match.
    """
    if pred_time_ms == 0:
        return 0.0

    # Import here to avoid a module-level circular dependency at runtime.
    from evaluation.metrics.ex_accuracy import ex_score  # noqa: PLC0415

    v_i = ex_score(pred_rows, gold_rows)
    if v_i == 0.0:
        return 0.0

    r_i = min(gold_time_ms / pred_time_ms, 1.0)
    return v_i * r_i


def compute_ves_bird(results: list["EvalResult"]) -> float:
    """Compute the mean BIRD VES across all results.

    Each EvalResult must have a ``gold_exec_time_ms`` attribute set by the runner.
    Results where the attribute is missing or None are skipped.

    Returns the mean VES as a float rounded to 4 decimal places.
    """
    scores: list[float] = []
    for r in results:
        gold_time_ms = getattr(r, "gold_exec_time_ms", None)
        if gold_time_ms is None:
            continue
        score = ves_bird(
            pred_rows=r.rows or [],
            gold_rows=r.gold_rows or [],
            pred_time_ms=r.latency_ms,
            gold_time_ms=gold_time_ms,
        )
        scores.append(score)

    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 4)


# ---------------------------------------------------------------------------
# Static heuristic VES (for own / production queries without gold SQL)
# ---------------------------------------------------------------------------


def ves_static(sql: str) -> float:
    """Heuristic VES for queries where no gold SQL is available.

    Starts at 1.0 and applies the following deductions:
      -0.25  SELECT * used
      -0.20  fact_created_videos queried for aggregates when only
             GROUP BY / COUNT / SUM are present (should use mv_ views instead)
      -0.15  No LIMIT clause on a non-aggregate query
      -0.10  No client_id filter on fact_created_videos
      -0.10  Cartesian join detected (JOIN keyword without a following ON clause)

    Score is floored at 0.0.  All checks are regex-based on the SQL string.
    """
    score = 1.0
    sql_upper = sql.upper()

    # -0.25 — SELECT * used
    if re.search(r"SELECT\s+\*", sql_upper):
        score -= 0.25

    # -0.20 — fact_created_videos used for aggregates instead of mv_ views.
    #         Triggers when fact_created_videos is referenced AND at least one
    #         aggregate keyword (GROUP BY, COUNT, SUM) is present.
    if re.search(r"\bFACT_CREATED_VIDEOS\b", sql_upper) and re.search(
        r"\b(GROUP\s+BY|COUNT\s*\(|SUM\s*\()\b", sql_upper
    ):
        score -= 0.20

    # -0.15 — No LIMIT clause on a non-aggregate query.
    #         Treat query as aggregate if it contains GROUP BY, COUNT, SUM, AVG, MIN, MAX.
    is_aggregate = bool(
        re.search(
            r"\b(GROUP\s+BY|COUNT\s*\(|SUM\s*\(|AVG\s*\(|MIN\s*\(|MAX\s*\()\b",
            sql_upper,
        )
    )
    if not is_aggregate and not re.search(r"\bLIMIT\b", sql_upper):
        score -= 0.15

    # -0.10 — No client_id filter on fact_created_videos.
    if re.search(r"\bFACT_CREATED_VIDEOS\b", sql_upper) and not re.search(
        r"\bCLIENT_ID\b", sql_upper
    ):
        score -= 0.10

    # -0.10 — Cartesian join: JOIN keyword present but no ON clause follows.
    #         Detects patterns like "JOIN table" with no "ON" anywhere after the join.
    if re.search(r"\bJOIN\b", sql_upper) and not re.search(r"\bON\b", sql_upper):
        score -= 0.10

    return round(max(score, 0.0), 4)


def compute_ves_static(results: list["EvalResult"]) -> dict:
    """Run ves_static on each result's sql field and aggregate.

    Returns a dict with:
      - mean_ves:    Average heuristic VES across all results.
      - scores:      List of per-query VES floats (same order as results).
      - n_perfect:   Count of queries with score == 1.0.
      - n_penalised: Count of queries with score < 1.0.
    """
    scores: list[float] = []
    for r in results:
        sql = r.sql or ""
        scores.append(ves_static(sql))

    n_total = len(scores)
    mean_ves = round(sum(scores) / n_total, 4) if n_total else 0.0
    n_perfect = sum(1 for s in scores if s == 1.0)
    n_penalised = n_total - n_perfect

    return {
        "mean_ves": mean_ves,
        "scores": scores,
        "n_perfect": n_perfect,
        "n_penalised": n_penalised,
    }
