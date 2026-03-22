"""Self-healing and execution success metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evaluation.pipelines.base import EvalResult


def compute_esr(results: list["EvalResult"]) -> float:
    """Compute the Execution Success Rate (ESR).

    ESR is the percentage of queries where ``success=True``, expressed as a
    float in the range [0.0, 1.0].  Returns 0.0 for an empty result list.
    """
    if not results:
        return 0.0
    n_success = sum(1 for r in results if r.success)
    return round(n_success / len(results), 4)


def compute_healing_efficiency(results: list["EvalResult"]) -> dict:
    """Compute healing efficiency among queries that required healing.

    A query "needed healing" when ``first_shot_success=False``.

    Returns a dict with:
      - healing_efficiency:  Fraction of healed-attempted queries that
                             eventually succeeded (float 0–1, or None when
                             no healing was attempted).
      - n_healed_attempted:  Number of queries where healing was triggered.
      - n_healed_succeeded:  Number of those that succeeded after healing.
    """
    n_healed_attempted = sum(1 for r in results if not r.first_shot_success)
    n_healed_succeeded = sum(
        1 for r in results if not r.first_shot_success and r.success
    )

    if n_healed_attempted == 0:
        healing_efficiency = None
    else:
        healing_efficiency = round(n_healed_succeeded / n_healed_attempted, 4)

    return {
        "healing_efficiency": healing_efficiency,
        "n_healed_attempted": n_healed_attempted,
        "n_healed_succeeded": n_healed_succeeded,
    }


def compute_healing_metrics(results: list["EvalResult"]) -> dict:
    """Combine ESR and healing efficiency metrics into a single dict.

    Merges the output of :func:`compute_esr` and
    :func:`compute_healing_efficiency`.

    Returns a dict with:
      - esr:                 Execution Success Rate across all results.
      - healing_efficiency:  See :func:`compute_healing_efficiency`.
      - n_healed_attempted:  See :func:`compute_healing_efficiency`.
      - n_healed_succeeded:  See :func:`compute_healing_efficiency`.
      - n_total:             Total number of results.
    """
    healing = compute_healing_efficiency(results)
    return {
        "esr": compute_esr(results),
        "n_total": len(results),
        **healing,
    }
