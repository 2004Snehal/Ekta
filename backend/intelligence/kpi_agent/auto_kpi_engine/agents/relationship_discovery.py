"""
Relationship Discovery Agent
Detects JOIN-able relationships between tables using:
  1. Explicit foreign key metadata (if available)
  2. Column name matching heuristics
  3. LLM-assisted relationship inference (fallback)
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from models.kpi_models import TableRelationship, TableSchema
from graph.state import KPIState
from llm.prompts import render_relationship_prompt

logger = logging.getLogger(__name__)

# Columns with these names are common FK / PK patterns
_ID_SUFFIX_RE = re.compile(r"(.+)_id$", re.IGNORECASE)
_PRIMARY_KEY_NAMES = {"id", "pk", "key"}


def _schema_summary(schema: Dict[str, TableSchema]) -> str:
    """Build a text summary of the schema for the LLM prompt."""
    lines = []
    for tname, tschema in schema.items():
        cols = ", ".join(f"{c.name} ({c.dtype})" for c in tschema.columns)
        lines.append(f"  {tname}: [{cols}]")
    return "\n".join(lines)


def _name_match_relationships(schema: Dict[str, TableSchema]) -> List[TableRelationship]:
    """
    Rule-based: if a column 'X_id' exists in table A and table B has a column 'id' or 'X_id',
    infer a relationship.
    """
    # Build index: column_name → {table}
    col_to_tables: Dict[str, Set[str]] = defaultdict(set)
    for tname, tschema in schema.items():
        for col in tschema.columns:
            col_to_tables[col.name.lower()].add(tname)

    rels: List[TableRelationship] = []

    for tname, tschema in schema.items():
        for col in tschema.columns:
            match = _ID_SUFFIX_RE.match(col.name)
            if not match:
                continue
            prefix = match.group(1).lower()

            # Look for a table named <prefix> or <prefix>s that has an "id" or same column
            candidate_tables = [
                other for other in schema
                if other.lower() in (prefix, prefix + "s", prefix + "es") and other != tname
            ]

            for candidate in candidate_tables:
                candidate_cols = {c.name.lower() for c in schema[candidate].columns}
                right_col = "id" if "id" in candidate_cols else col.name.lower() if col.name.lower() in candidate_cols else None
                if right_col:
                    rels.append(TableRelationship(
                        left_table=tname,
                        right_table=candidate,
                        left_column=col.name,
                        right_column=right_col,
                        relationship_type="name_match",
                        confidence=0.85,
                    ))
                    logger.debug("Name-match rel: %s.%s → %s.%s", tname, col.name, candidate, right_col)

            # Also match across tables that share the exact same column name (e.g. user_id in orders + payments)
            if col.name.lower() in col_to_tables:
                sharers = col_to_tables[col.name.lower()] - {tname}
                for other in sharers:
                    if other != tname:
                        rels.append(TableRelationship(
                            left_table=tname,
                            right_table=other,
                            left_column=col.name,
                            right_column=col.name,
                            relationship_type="name_match",
                            confidence=0.75,
                        ))

    return rels


def _deduplicate(rels: List[TableRelationship]) -> List[TableRelationship]:
    """Remove duplicate relationships (same pair of tables / columns)."""
    seen: Set[Tuple[str, str, str, str]] = set()
    unique: List[TableRelationship] = []
    for r in rels:
        key = (
            min(r.left_table, r.right_table),
            max(r.left_table, r.right_table),
            min(r.left_column, r.right_column),
            max(r.left_column, r.right_column),
        )
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _build_adjacency(rels: List[TableRelationship]) -> Dict[str, List[str]]:
    adj: Dict[str, List[str]] = defaultdict(list)
    for r in rels:
        adj[r.left_table].append(r.right_table)
        adj[r.right_table].append(r.left_table)
    return dict(adj)


def _llm_relationships(schema: Dict[str, TableSchema], llm) -> List[TableRelationship]:
    """Use LLM for any additional relationship inference."""
    prompt = render_relationship_prompt(_schema_summary(schema))
    try:
        response = llm.generate(prompt, temperature=0.0)
        # Extract JSON array
        json_match = re.search(r"\[.*\]", response, re.DOTALL)
        if not json_match:
            return []
        items = json.loads(json_match.group())
        rels = []
        for item in items:
            try:
                rels.append(TableRelationship(
                    left_table=item["left_table"],
                    right_table=item["right_table"],
                    left_column=item["left_column"],
                    right_column=item["right_column"],
                    relationship_type="inferred",
                    confidence=float(item.get("confidence", 0.7)),
                ))
            except Exception as exc:
                logger.warning("LLM relationship parse error: %s | item=%s", exc, item)
        return rels
    except Exception as exc:
        logger.error("LLM relationship discovery failed: %s", exc)
        return []


def relationship_discovery(state: KPIState) -> KPIState:
    """
    LangGraph node: discover relationships between tables.

    Reads:
        state["schema"]
        state["llm_service"]

    Writes:
        state["relationships"]
        state["relationship_graph"]
    """
    schema: Dict[str, TableSchema] = state.get("schema", {})
    errors: List[str] = state.get("errors", [])

    if not schema:
        state["relationships"] = []
        state["relationship_graph"] = {}
        return state

    # Step 1: name-match heuristics
    rels = _name_match_relationships(schema)
    logger.info("Name-match relationships found: %d", len(rels))

    # Step 2: LLM-assisted inference (only if we have an LLM service)
    llm = state.get("llm_service")
    if llm and len(schema) > 1:
        llm_rels = _llm_relationships(schema, llm)
        logger.info("LLM relationships found: %d", len(llm_rels))
        rels.extend(llm_rels)

    rels = _deduplicate(rels)
    adj = _build_adjacency(rels)

    state["relationships"] = rels
    state["relationship_graph"] = adj
    state["errors"] = errors

    logger.info(
        "Relationship discovery complete: %d relationships across tables %s",
        len(rels),
        list(schema.keys()),
    )
    return state
