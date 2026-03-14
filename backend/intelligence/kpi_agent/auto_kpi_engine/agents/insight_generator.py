"""
Insight Generator Agent
Converts good KPI values into human-readable business insights using the LLM.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from models.kpi_models import CandidateKPI, EvaluatedKPI, KPIInsight
from graph.state import KPIState
from llm.prompts import render_insight_prompt

logger = logging.getLogger(__name__)


def _context_summary(
    good_kpis: List[EvaluatedKPI],
    exclude_id: str,
) -> str:
    lines = []
    for ev in good_kpis:
        if ev.kpi_id == exclude_id:
            continue
        lines.append(f"  {ev.name}: {ev.value}")
    return "\n".join(lines[:5]) if lines else ""


def insight_generator(state: KPIState) -> KPIState:
    """
    LangGraph node: generate business insights for each good KPI.

    Reads:
        state["good_kpis"]
        state["candidate_kpis"]
        state["llm_service"]

    Writes:
        state["insights"]
    """
    good_kpis: List[EvaluatedKPI] = state.get("good_kpis", [])
    candidate_kpis: List[CandidateKPI] = state.get("candidate_kpis", [])
    llm = state.get("llm_service")
    errors: List[str] = state.get("errors", [])

    # Build a lookup of candidate KPI metadata
    kpi_meta: Dict[str, CandidateKPI] = {k.id: k for k in candidate_kpis}

    insights: List[KPIInsight] = []

    for ev in good_kpis:
        meta = kpi_meta.get(ev.kpi_id)
        formula = meta.formula if meta else ev.name
        context = _context_summary(good_kpis, ev.kpi_id)

        if llm:
            prompt = render_insight_prompt(
                kpi_name=ev.name,
                formula=formula,
                value=ev.value,
                context=context,
            )
            try:
                insight_text = llm.generate(prompt, temperature=0.4, max_tokens=256)
            except Exception as exc:
                msg = f"insight_generator: LLM failed for '{ev.name}': {exc}"
                logger.error(msg)
                errors.append(msg)
                insight_text = _fallback_insight(ev)
        else:
            insight_text = _fallback_insight(ev)

        insights.append(KPIInsight(
            kpi_id=ev.kpi_id,
            kpi_name=ev.name,
            value=ev.value,
            insight=insight_text,
        ))

    state["insights"] = insights
    state["errors"] = errors
    logger.info("Insight generator: produced %d insights", len(insights))
    return state


def _fallback_insight(ev: EvaluatedKPI) -> str:
    """Generate a simple template-based insight when LLM is unavailable."""
    return f"The metric '{ev.name}' has a computed value of {ev.value}."
