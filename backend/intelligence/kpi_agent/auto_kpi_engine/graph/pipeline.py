"""
LangGraph pipeline definition for the Auto-KPI Discovery Engine.

The pipeline is a directed graph of agent nodes connected in sequence.
Each node is a Python function that receives and returns KPIState.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from langgraph.graph import START, END, StateGraph

from graph.state import KPIState
from agents.schema_reader import schema_reader
from agents.relationship_discovery import relationship_discovery
from agents.table_grouping import table_grouping
from agents.stats_extractor import stats_extractor
from agents.kpi_generator import kpi_generator
from agents.sql_builder import sql_builder
from agents.query_executor import query_executor
from agents.kpi_evaluator import kpi_evaluator
from agents.insight_generator import insight_generator


# ================================================================== #
# Graph construction
# ================================================================== #

def build_pipeline() -> Any:
    """
    Construct and compile the LangGraph StateGraph for KPI discovery.

    Returns a compiled graph that can be invoked with an initial KPIState.
    """
    graph = StateGraph(KPIState)

    # Register nodes
    graph.add_node("schema_reader", schema_reader)
    graph.add_node("relationship_discovery", relationship_discovery)
    graph.add_node("table_grouping", table_grouping)
    graph.add_node("stats_extractor", stats_extractor)
    graph.add_node("kpi_generator", kpi_generator)
    graph.add_node("sql_builder", sql_builder)
    graph.add_node("query_executor", query_executor)
    graph.add_node("kpi_evaluator", kpi_evaluator)
    graph.add_node("insight_generator", insight_generator)

    # Define edges (linear pipeline)
    graph.add_edge(START, "schema_reader")
    graph.add_edge("schema_reader", "relationship_discovery")
    graph.add_edge("relationship_discovery", "table_grouping")
    graph.add_edge("table_grouping", "stats_extractor")
    graph.add_edge("stats_extractor", "kpi_generator")
    graph.add_edge("kpi_generator", "sql_builder")
    graph.add_edge("sql_builder", "query_executor")
    graph.add_edge("query_executor", "kpi_evaluator")
    graph.add_edge("kpi_evaluator", "insight_generator")
    graph.add_edge("insight_generator", END)

    return graph.compile()


# ================================================================== #
# Pipeline runner helpers
# ================================================================== #

def run_pipeline(
    db_adapter: Any,
    llm_service: Optional[Any] = None,
    dialect: str = "duckdb",
) -> KPIState:
    """
    Convenience function: build the pipeline and run it end-to-end.

    Parameters
    ----------
    db_adapter:
        A connected DBAdapter instance (DuckDB, ClickHouse, etc.).
    llm_service:
        An LLMService instance.  If None, fallback rule-based logic is used.
    dialect:
        SQL dialect hint ("duckdb" or "clickhouse").

    Returns
    -------
    Final KPIState after the full pipeline completes.
    """
    pipeline = build_pipeline()

    initial_state: KPIState = {
        "db_adapter": db_adapter,
        "llm_service": llm_service,
        "dialect": dialect,
        "run_id": str(uuid.uuid4()),
        "errors": [],
    }

    final_state = pipeline.invoke(initial_state)
    return final_state


def run_partial_pipeline(
    db_adapter: Any,
    llm_service: Optional[Any],
    stop_after: str,
    dialect: str = "duckdb",
) -> KPIState:
    """
    Run the pipeline and stop after a named node.
    Useful for the individual API endpoints (/schema, /kpi/generate, etc.).

    stop_after must be one of:
        schema_reader | relationship_discovery | table_grouping |
        stats_extractor | kpi_generator | sql_builder |
        query_executor | kpi_evaluator | insight_generator
    """
    pipeline = build_pipeline()

    initial_state: KPIState = {
        "db_adapter": db_adapter,
        "llm_service": llm_service,
        "dialect": dialect,
        "run_id": str(uuid.uuid4()),
        "errors": [],
    }

    # LangGraph supports streaming; collect states until the target node
    final_state: KPIState = initial_state  # type: ignore[assignment]
    for state_snapshot in pipeline.stream(initial_state):
        # state_snapshot is a dict {node_name: state_after_node}
        for node_name, node_state in state_snapshot.items():
            final_state = node_state
            if node_name == stop_after:
                return final_state

    return final_state
