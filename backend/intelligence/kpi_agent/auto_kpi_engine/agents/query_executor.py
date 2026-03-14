"""
Query Executor Agent
Runs validated SQL for each KPI and stores the computed values.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from models.kpi_models import CandidateKPI, ComputedKPI
from graph.state import KPIState

logger = logging.getLogger(__name__)


def _extract_scalar(rows: List[Dict[str, Any]]) -> Any:
    """
    Extract a single scalar from a query result.
    Handles both single-cell and multi-row results.
    """
    if not rows:
        return None

    # Single row, single column → scalar KPI
    if len(rows) == 1 and len(rows[0]) == 1:
        return list(rows[0].values())[0]

    # Multi-row result → return as list of dicts (for distribution KPIs)
    if len(rows) <= 50:
        return rows

    # Large result: return row count as a proxy
    return len(rows)


def query_executor(state: KPIState) -> KPIState:
    """
    LangGraph node: execute SQL for each candidate KPI.

    Reads:
        state["candidate_kpis"]
        state["db_adapter"]

    Writes:
        state["computed_values"]
    """
    candidate_kpis: List[CandidateKPI] = state.get("candidate_kpis", [])
    db = state["db_adapter"]
    errors: List[str] = state.get("errors", [])

    computed: Dict[str, ComputedKPI] = {}
    skipped = 0
    executed = 0
    failed = 0

    for kpi in candidate_kpis:
        if not kpi.sql:
            skipped += 1
            computed[kpi.id] = ComputedKPI(
                kpi_id=kpi.id,
                value=None,
                error="No SQL available",
                sql_used=None,
            )
            continue

        try:
            rows = db.execute(kpi.sql)
            value = _extract_scalar(rows)
            computed[kpi.id] = ComputedKPI(
                kpi_id=kpi.id,
                value=value,
                error=None,
                sql_used=kpi.sql,
            )
            executed += 1
            logger.debug("Executed KPI '%s' → %s", kpi.name, str(value)[:60])
        except Exception as exc:
            msg = f"query_executor: error running KPI '{kpi.name}': {exc}"
            logger.error(msg)
            errors.append(msg)
            failed += 1
            computed[kpi.id] = ComputedKPI(
                kpi_id=kpi.id,
                value=None,
                error=str(exc),
                sql_used=kpi.sql,
            )

    state["computed_values"] = computed
    state["errors"] = errors
    logger.info(
        "Query executor: executed=%d, skipped=%d, failed=%d",
        executed, skipped, failed,
    )
    return state
