"""
LangGraph shared state for the Auto-KPI pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict

from models.kpi_models import (
    CandidateKPI,
    ColumnStats,
    ComputedKPI,
    EvaluatedKPI,
    KPIInsight,
    TableRelationship,
    TableSchema,
)


class KPIState(TypedDict, total=False):
    """
    Shared mutable state passed between every node in the LangGraph pipeline.

    Each agent reads from and writes to this dict.
    Fields are optional (total=False) so agents can add fields progressively.
    """

    # ------------------------------------------------------------------ #
    # Input
    # ------------------------------------------------------------------ #
    db_adapter: Any                         # DBAdapter instance injected at startup
    llm_service: Any                        # LLMService instance injected at startup
    dialect: str                            # "duckdb" | "clickhouse"

    # ------------------------------------------------------------------ #
    # Schema Reader output
    # ------------------------------------------------------------------ #
    schema: Dict[str, TableSchema]          # table_name → TableSchema

    # ------------------------------------------------------------------ #
    # Relationship Discovery output
    # ------------------------------------------------------------------ #
    relationships: List[TableRelationship]
    relationship_graph: Dict[str, List[str]]  # adjacency list: table → [connected tables]

    # ------------------------------------------------------------------ #
    # Table Grouping output
    # ------------------------------------------------------------------ #
    table_groups: List[List[str]]           # list of connected components

    # ------------------------------------------------------------------ #
    # Statistics Extractor output
    # ------------------------------------------------------------------ #
    column_stats: List[ColumnStats]

    # ------------------------------------------------------------------ #
    # KPI Generator output
    # ------------------------------------------------------------------ #
    candidate_kpis: List[CandidateKPI]

    # ------------------------------------------------------------------ #
    # SQL Builder output (KPIs enriched with SQL)
    # ------------------------------------------------------------------ #
    # candidate_kpis updated in-place with sql field

    # ------------------------------------------------------------------ #
    # Query Executor output
    # ------------------------------------------------------------------ #
    computed_values: Dict[str, ComputedKPI]   # kpi_id → ComputedKPI

    # ------------------------------------------------------------------ #
    # KPI Evaluator output
    # ------------------------------------------------------------------ #
    evaluation_scores: Dict[str, EvaluatedKPI]
    good_kpis: List[EvaluatedKPI]

    # ------------------------------------------------------------------ #
    # Insight Generator output
    # ------------------------------------------------------------------ #
    insights: List[KPIInsight]

    # ------------------------------------------------------------------ #
    # Pipeline metadata
    # ------------------------------------------------------------------ #
    errors: List[str]                       # non-fatal errors collected during run
    run_id: str                             # unique ID for this pipeline run
