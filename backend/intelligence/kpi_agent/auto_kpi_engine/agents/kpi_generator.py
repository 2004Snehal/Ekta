"""
KPI Generator Agent
Generates candidate KPIs per table group using a template-first, LLM-assisted approach.
Works for both independent tables and related (join-able) table groups.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List

from models.kpi_models import CandidateKPI, ColumnStats, TableSchema
from graph.state import KPIState
from kpi_templates.ratio_templates import RATIO_TEMPLATES
from kpi_templates.growth_templates import GROWTH_TEMPLATES
from kpi_templates.distribution_templates import DISTRIBUTION_TEMPLATES
from llm.prompts import render_kpi_generation_prompt

logger = logging.getLogger(__name__)

ALL_TEMPLATES: List[Dict[str, Any]] = RATIO_TEMPLATES + GROWTH_TEMPLATES + DISTRIBUTION_TEMPLATES

_TEMPLATE_SUMMARY = "\n".join(
    f"  - {t['name']}: {t['description']}" for t in ALL_TEMPLATES
)


def _schema_detail_for_group(
    tables: List[str], schema: Dict[str, TableSchema]
) -> str:
    lines = []
    for t in tables:
        ts = schema.get(t)
        if not ts:
            continue
        cols = ", ".join(f"{c.name} ({c.dtype})" for c in ts.columns)
        lines.append(f"  {t} ({ts.row_count} rows): [{cols}]")
    return "\n".join(lines) if lines else "No schema available."


def _stats_summary_for_group(
    tables: List[str], column_stats: List[ColumnStats]
) -> str:
    lines = []
    for stat in column_stats:
        if stat.table not in tables:
            continue
        parts = [f"{stat.table}.{stat.column} ({stat.dtype})"]
        if stat.mean is not None:
            parts.append(f"mean={stat.mean:.2f}")
        if stat.null_rate > 0:
            parts.append(f"null_rate={stat.null_rate:.1%}")
        parts.append(f"unique={stat.unique_count}")
        if stat.entropy is not None:
            parts.append(f"entropy={stat.entropy:.2f}")
        lines.append("  " + ", ".join(parts))
    return "\n".join(lines) if lines else "No stats available."


def _parse_llm_kpis(response: str, group_id: int, tables: List[str]) -> List[CandidateKPI]:
    """Extract a JSON array of KPI dicts from the LLM response."""
    json_match = re.search(r"\[.*\]", response, re.DOTALL)
    if not json_match:
        logger.warning("KPI generator: no JSON array in LLM response")
        return []

    items = json.loads(json_match.group())
    result = []
    for item in items:
        try:
            # Ensure tables referenced by LLM actually exist in the group
            kpi_tables = [t for t in item.get("tables", tables) if t in tables]
            if not kpi_tables:
                kpi_tables = tables

            kpi = CandidateKPI(
                id=str(uuid.uuid4()),
                name=item["name"],
                description=item.get("description", ""),
                template=item.get("template", "custom"),
                formula=item.get("formula", ""),
                tables=kpi_tables,
                columns=item.get("columns", []),
                confidence=float(item.get("confidence", 0.7)),
                requires_join=bool(item.get("requires_join", False)),
                group_id=group_id,
            )
            result.append(kpi)
        except Exception as exc:
            logger.warning("KPI parse error: %s | item=%s", exc, item)
    return result


def kpi_generator(state: KPIState) -> KPIState:
    """
    LangGraph node: generate candidate KPIs for every table group.

    Reads:
        state["schema"]
        state["table_groups"]
        state["column_stats"]
        state["relationship_graph"]
        state["llm_service"]

    Writes:
        state["candidate_kpis"]
    """
    schema: Dict[str, TableSchema] = state.get("schema", {})
    table_groups: List[List[str]] = state.get("table_groups", [])
    column_stats: List[ColumnStats] = state.get("column_stats", [])
    relationship_graph: Dict[str, List[str]] = state.get("relationship_graph", {})
    llm = state.get("llm_service")
    errors: List[str] = state.get("errors", [])

    # If no groups provided, treat each table independently
    if not table_groups:
        table_groups = [[t] for t in schema.keys()]

    all_kpis: List[CandidateKPI] = []

    for group_id, group_tables in enumerate(table_groups):
        logger.info("KPI generation for group %d: %s", group_id, group_tables)

        schema_detail = _schema_detail_for_group(group_tables, schema)
        stats_summary = _stats_summary_for_group(group_tables, column_stats)
        has_relations = any(t in relationship_graph for t in group_tables)

        # Number of KPIs to request scales with group size
        n_kpis = max(3, min(8, 3 * len(group_tables)))

        prompt = render_kpi_generation_prompt(
            tables=group_tables,
            schema_detail=schema_detail,
            stats_summary=stats_summary,
            templates=_TEMPLATE_SUMMARY,
            n_kpis=n_kpis,
        )

        if llm:
            try:
                response = llm.generate(prompt, temperature=0.3, max_tokens=2048)
                kpis = _parse_llm_kpis(response, group_id, group_tables)
                logger.info("Group %d: LLM generated %d KPIs", group_id, len(kpis))
                all_kpis.extend(kpis)
            except Exception as exc:
                msg = f"kpi_generator group {group_id}: LLM failed – {exc}"
                logger.error(msg)
                errors.append(msg)
                # Fallback: create basic count KPIs per table
                all_kpis.extend(_fallback_kpis(group_tables, schema, group_id))
        else:
            # No LLM — pure template fallback
            all_kpis.extend(_fallback_kpis(group_tables, schema, group_id))

    state["candidate_kpis"] = all_kpis
    state["errors"] = errors
    logger.info("KPI generator: total %d candidate KPIs", len(all_kpis))
    return state


def _fallback_kpis(
    tables: List[str], schema: Dict[str, TableSchema], group_id: int
) -> List[CandidateKPI]:
    """
    Generate basic fallback KPIs without an LLM.
    Creates a row_count and unique-value KPI for each table.
    """
    kpis = []
    for table in tables:
        ts = schema.get(table)
        if not ts:
            continue
        kpis.append(CandidateKPI(
            id=str(uuid.uuid4()),
            name=f"{table}_row_count",
            description=f"Total number of rows in {table}",
            template="unique_count",
            formula=f"COUNT(*) FROM {table}",
            tables=[table],
            columns=[],
            confidence=0.9,
            requires_join=False,
            group_id=group_id,
        ))
        # Add numeric column averages
        for col in ts.columns:
            if any(t in col.dtype.upper() for t in ["INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"]):
                kpis.append(CandidateKPI(
                    id=str(uuid.uuid4()),
                    name=f"avg_{table}_{col.name}",
                    description=f"Average {col.name} in {table}",
                    template="average_value",
                    formula=f"AVG({col.name}) FROM {table}",
                    tables=[table],
                    columns=[col.name],
                    confidence=0.8,
                    requires_join=False,
                    group_id=group_id,
                ))
    return kpis
