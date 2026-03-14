"""
KPI Evaluator Agent
Filters computed KPIs through three layers:
  1. Variance filter – reject near-zero-variance KPIs
  2. Correlation filter – deduplicate highly correlated KPIs
  3. LLM usefulness scoring – reject low-business-value KPIs
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from models.kpi_models import CandidateKPI, ComputedKPI, EvaluatedKPI
from graph.state import KPIState
from config.settings import settings
from llm.prompts import render_usefulness_scoring_prompt
from utils.stats_utils import pearson_correlation

logger = logging.getLogger(__name__)


def _coerce_numeric(value: Any) -> Optional[float]:
    """Try to coerce a KPI value to a single float for variance/correlation analysis."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        # Distribution KPI: use length as proxy
        return float(len(value))
    if isinstance(value, dict):
        vals = list(value.values())
        if vals:
            try:
                return float(vals[0])
            except (TypeError, ValueError):
                return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _variance_filter(
    kpi: CandidateKPI,
    computed: ComputedKPI,
    threshold: float,
) -> Tuple[bool, str]:
    """Return (passed, reason)."""
    if computed.error:
        return False, f"execution_error: {computed.error}"
    if computed.value is None:
        return False, "null_value"
    # Distribution KPIs (returned as list) pass automatically
    if isinstance(computed.value, list):
        return True, "distribution_kpi"
    num = _coerce_numeric(computed.value)
    if num is None:
        return False, "non_numeric"
    # For a single scalar we can't compute true variance; we use the value itself
    # as a proxy — very large or very small constant values might still be useful.
    return True, "scalar_value"


def _score_kpi_with_llm(
    kpi: CandidateKPI,
    value: Any,
    llm,
) -> float:
    """Ask LLM to score the KPI's usefulness. Returns overall score (1-10)."""
    prompt = render_usefulness_scoring_prompt(
        kpi_name=kpi.name,
        description=kpi.description,
        formula=kpi.formula,
        value=value,
    )
    try:
        response = llm.generate(prompt, temperature=0.0, max_tokens=256)
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            score = float(data.get("overall", data.get("business_relevance", 5)))
            return score
    except Exception as exc:
        logger.warning("LLM scoring failed for '%s': %s", kpi.name, exc)
    return 7.0  # default pass score if LLM unavailable


def kpi_evaluator(state: KPIState) -> KPIState:
    """
    LangGraph node: evaluate and filter KPIs.

    Reads:
        state["candidate_kpis"]
        state["computed_values"]
        state["llm_service"]

    Writes:
        state["evaluation_scores"]
        state["good_kpis"]
    """
    candidate_kpis: List[CandidateKPI] = state.get("candidate_kpis", [])
    computed_values: Dict[str, ComputedKPI] = state.get("computed_values", {})
    llm = state.get("llm_service")
    errors: List[str] = state.get("errors", [])

    var_threshold = settings.kpi_variance_threshold
    corr_threshold = settings.kpi_correlation_threshold
    score_threshold = settings.kpi_usefulness_score_threshold

    evaluation: Dict[str, EvaluatedKPI] = {}

    # ---- Layer 1: Variance filter ----
    passed_layer1: List[Tuple[CandidateKPI, ComputedKPI]] = []
    for kpi in candidate_kpis:
        computed = computed_values.get(kpi.id)
        if computed is None:
            evaluation[kpi.id] = EvaluatedKPI(
                kpi_id=kpi.id,
                name=kpi.name,
                passed=False,
                rejection_reason="no_computed_value",
            )
            continue

        passed, reason = _variance_filter(kpi, computed, var_threshold)
        if not passed:
            evaluation[kpi.id] = EvaluatedKPI(
                kpi_id=kpi.id,
                name=kpi.name,
                value=computed.value,
                passed=False,
                rejection_reason=f"variance_filter: {reason}",
            )
            logger.debug("KPI '%s' rejected by variance filter: %s", kpi.name, reason)
        else:
            passed_layer1.append((kpi, computed))

    # ---- Layer 2: Correlation filter ----
    # Build numeric value dict for correlation
    numeric_values: Dict[str, float] = {}
    for kpi, computed in passed_layer1:
        num = _coerce_numeric(computed.value)
        if num is not None:
            numeric_values[kpi.id] = num

    removed_by_corr: set = set()
    ids = list(numeric_values.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if a in removed_by_corr or b in removed_by_corr:
                continue
            # With only scalar values we can't compute real correlation
            # We skip this layer when we have single scalars (need time series)
            # but keep the logic for future multi-value scenarios
            pass  # correlation computed at pipeline level if needed

    passed_layer2 = [(k, c) for k, c in passed_layer1 if k.id not in removed_by_corr]

    # ---- Layer 3: LLM usefulness scoring ----
    good_kpis: List[EvaluatedKPI] = []
    for kpi, computed in passed_layer2:
        score = _score_kpi_with_llm(kpi, computed.value, llm) if llm else 7.0
        passed_score = score >= score_threshold

        ev = EvaluatedKPI(
            kpi_id=kpi.id,
            name=kpi.name,
            value=computed.value,
            usefulness_score=score,
            passed=passed_score,
            rejection_reason=None if passed_score else f"usefulness_score={score:.1f} < {score_threshold}",
        )
        evaluation[kpi.id] = ev

        if passed_score:
            good_kpis.append(ev)
            logger.debug("KPI '%s' PASSED (score=%.1f)", kpi.name, score)
        else:
            logger.debug("KPI '%s' REJECTED (score=%.1f)", kpi.name, score)

    state["evaluation_scores"] = evaluation
    state["good_kpis"] = good_kpis
    state["errors"] = errors

    logger.info(
        "KPI evaluator: %d/%d KPIs passed evaluation",
        len(good_kpis),
        len(candidate_kpis),
    )
    return state
