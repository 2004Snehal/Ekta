"""Execution Accuracy (EX) metrics for BIRD dataset evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evaluation.pipelines.base import EvalResult


def _norm_val(v):
    """Normalise a single cell value for comparison."""
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, str):
        return v.strip().lower()
    return v


def normalise_rows(rows: list[dict]) -> list[tuple]:
    """Sort rows and convert to hashable tuples for set comparison.

    BIRD-standard: compares **values only**, ignoring column names.
    This avoids false negatives when predicted SQL uses different aliases
    (e.g. ``AS ratio`` vs the raw expression ``SUM(...)/SUM(...)``).

    Values within each row are sorted by their string representation so
    that column ordering differences are neutralised.  Floats are rounded
    to 4 dp; strings are lowercased and stripped.
    """
    normalised = []
    for row in rows:
        vals = tuple(sorted((_norm_val(v) for v in row.values()), key=lambda x: str(x)))
        normalised.append(vals)
    return sorted(normalised, key=lambda t: str(t))


def ex_score(pred_rows: list[dict], gold_rows: list[dict]) -> float:
    """Return 1.0 if result sets match (order-insensitive), 0.0 otherwise.

    Comparison is performed on normalised, sorted row tuples so that row
    ordering and minor float precision differences do not cause false negatives.
    """
    if normalise_rows(pred_rows) == normalise_rows(gold_rows):
        return 1.0
    return 0.0


def compute_ex_metrics(results: list["EvalResult"]) -> dict:
    """Compute Execution Accuracy metrics for a list of BIRD EvalResults.

    Metrics computed:
      - ex:             Overall EX using the final sql/rows after any healing.
      - first_shot_ex:  EX restricted to queries that succeeded on the first
                        attempt (first_shot_success=True) AND whose rows match
                        the gold rows.
      - healed_ex:      EX among queries that required healing
                        (first_shot_success=False).  Numerator counts those
                        that eventually succeeded and whose final rows match gold.
      - n_total:        Total number of results evaluated.
      - n_ex_pass:      Queries whose final rows match gold.
      - n_first_shot_pass: Queries that were first-shot successes with gold match.

    Returns a dict containing all of the above fields.
    """
    n_total = len(results)
    n_ex_pass = 0
    n_first_shot_pass = 0
    n_healed_attempted = 0
    n_healed_gold_match = 0

    for r in results:
        gold = r.gold_rows or []
        pred = r.rows or []

        # Overall EX: did the final execution produce the correct result?
        if r.success and ex_score(pred, gold) == 1.0:
            n_ex_pass += 1

        # First-shot EX: no healing was needed AND result is correct.
        if r.first_shot_success and ex_score(pred, gold) == 1.0:
            n_first_shot_pass += 1

        # Healed queries: any healing was attempted (error-based or result-aware).
        if r.heal_attempts > 0:
            n_healed_attempted += 1
            if r.success and ex_score(pred, gold) == 1.0:
                n_healed_gold_match += 1

    ex = n_ex_pass / n_total if n_total else 0.0
    first_shot_ex = n_first_shot_pass / n_total if n_total else 0.0
    healed_ex = (
        n_healed_gold_match / n_healed_attempted if n_healed_attempted else 0.0
    )

    return {
        "ex": round(ex, 4),
        "first_shot_ex": round(first_shot_ex, 4),
        "healed_ex": round(healed_ex, 4),
        "n_total": n_total,
        "n_ex_pass": n_ex_pass,
        "n_first_shot_pass": n_first_shot_pass,
    }
