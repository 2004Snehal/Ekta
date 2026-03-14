"""
Table Grouping Agent
Uses connected-components analysis on the relationship graph to form
independent KPI discovery groups.

Independent tables (no relationships) each become their own group.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set

from graph.state import KPIState

logger = logging.getLogger(__name__)


def _connected_components(
    tables: List[str], adjacency: Dict[str, List[str]]
) -> List[List[str]]:
    """
    BFS/DFS connected components over the undirected relationship graph.
    Every table must appear in exactly one component, even if isolated.
    """
    visited: Set[str] = set()
    components: List[List[str]] = []

    for table in tables:
        if table in visited:
            continue
        # BFS
        component: List[str] = []
        queue = [table]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in adjacency.get(node, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(sorted(component))

    return components


def table_grouping(state: KPIState) -> KPIState:
    """
    LangGraph node: group tables into connected components.

    Reads:
        state["schema"]
        state["relationship_graph"]

    Writes:
        state["table_groups"]
    """
    schema = state.get("schema", {})
    adjacency: Dict[str, List[str]] = state.get("relationship_graph", {})
    errors: List[str] = state.get("errors", [])

    all_tables = list(schema.keys())

    if not all_tables:
        state["table_groups"] = []
        state["errors"] = errors
        return state

    groups = _connected_components(all_tables, adjacency)

    state["table_groups"] = groups
    state["errors"] = errors

    logger.info(
        "Table grouping: %d groups from %d tables — %s",
        len(groups),
        len(all_tables),
        groups,
    )
    return state
