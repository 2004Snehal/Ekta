"""
SQL Builder Agent
Converts candidate KPI formulas into validated SQL queries.
Uses the LLM to generate SQL but never allows LLM-invented JOIN conditions.
All JOIN conditions must come from the discovered relationship graph.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from models.kpi_models import CandidateKPI, TableRelationship
from graph.state import KPIState
from llm.prompts import render_sql_builder_prompt
from utils.sql_validator import validate_with_explain

logger = logging.getLogger(__name__)


def _relationships_summary(
    kpi: CandidateKPI,
    relationships: List[TableRelationship],
) -> str:
    """Filter relationships relevant to this KPI and format for prompt."""
    kpi_tables = set(kpi.tables)
    relevant = [
        r for r in relationships
        if r.left_table in kpi_tables and r.right_table in kpi_tables
    ]
    if not relevant:
        return "None (no joins allowed)"
    lines = [
        f"  {r.left_table}.{r.left_column} = {r.right_table}.{r.right_column} "
        f"(type={r.relationship_type}, confidence={r.confidence:.2f})"
        for r in relevant
    ]
    return "\n".join(lines)


def _build_sql_from_formula(formula: str, kpi: CandidateKPI) -> Optional[str]:
    """
    Simple rule-based SQL wrapping for fallback KPIs whose formula is
    already in the form '<AGG> FROM <table>'.
    """
    # Match patterns like: AVG(col) FROM table or COUNT(*) FROM table
    pattern = re.compile(
        r"^(SELECT\s+)?(?P<agg>.+?)\s+FROM\s+(?P<table>\w+)\s*(?:WHERE\s+(?P<where>.+))?$",
        re.IGNORECASE,
    )
    m = pattern.match(formula.strip())
    if m:
        agg = m.group("agg").strip()
        table = m.group("table").strip()
        where_clause = m.group("where") or ""
        sql = f'SELECT {agg} AS kpi_value FROM "{table}"'
        if where_clause:
            sql += f" WHERE {where_clause}"
        return sql
    return None


def sql_builder(state: KPIState) -> KPIState:
    """
    LangGraph node: convert KPI formulas to validated SQL.

    Reads:
        state["candidate_kpis"]
        state["relationships"]
        state["db_adapter"]
        state["llm_service"]
        state["dialect"]

    Writes:
        state["candidate_kpis"]  (with sql field populated)
    """
    candidate_kpis: List[CandidateKPI] = state.get("candidate_kpis", [])
    relationships: List[TableRelationship] = state.get("relationships", [])
    db = state["db_adapter"]
    llm = state.get("llm_service")
    dialect: str = state.get("dialect", "duckdb")
    errors: List[str] = state.get("errors", [])

    updated_kpis: List[CandidateKPI] = []

    for kpi in candidate_kpis:
        sql: Optional[str] = None

        # ---- Attempt 1: rule-based formula → SQL ----
        sql = _build_sql_from_formula(kpi.formula, kpi)

        # ---- Attempt 2: LLM-assisted SQL generation ----
        if sql is None and llm:
            rel_summary = _relationships_summary(kpi, relationships)
            prompt = render_sql_builder_prompt(
                kpi_name=kpi.name,
                formula=kpi.formula,
                tables=kpi.tables,
                columns=kpi.columns,
                requires_join=kpi.requires_join,
                relationships=rel_summary,
                dialect=dialect,
            )
            try:
                raw_sql = llm.generate(prompt, temperature=0.0, max_tokens=512)
                # Strip markdown code fences if present
                raw_sql = re.sub(r"```(?:sql)?|```", "", raw_sql, flags=re.IGNORECASE).strip()
                sql = raw_sql if raw_sql.upper().startswith("SELECT") else None
            except Exception as exc:
                msg = f"sql_builder LLM error for KPI '{kpi.name}': {exc}"
                logger.error(msg)
                errors.append(msg)

        # ---- Validate SQL via EXPLAIN ----
        if sql:
            valid, reason = validate_with_explain(db, sql)
            if not valid:
                logger.warning(
                    "SQL validation failed for KPI '%s': %s | sql=%s", kpi.name, reason, sql[:150]
                )
                errors.append(f"SQL invalid for {kpi.name}: {reason}")
                sql = None

        kpi = kpi.model_copy(update={"sql": sql})
        updated_kpis.append(kpi)

        if sql:
            logger.debug("SQL built for KPI '%s': %s", kpi.name, sql[:100])
        else:
            logger.warning("No SQL for KPI '%s' — will skip execution", kpi.name)

    state["candidate_kpis"] = updated_kpis
    state["errors"] = errors
    logger.info(
        "SQL builder: %d/%d KPIs have valid SQL",
        sum(1 for k in updated_kpis if k.sql),
        len(updated_kpis),
    )
    return state
