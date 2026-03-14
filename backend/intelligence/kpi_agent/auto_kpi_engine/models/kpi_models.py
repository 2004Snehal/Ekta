"""
Pydantic models shared across the Auto-KPI Engine.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
# Schema models
# ------------------------------------------------------------------ #

class ColumnInfo(BaseModel):
    name: str
    dtype: str
    sample_values: List[Any] = Field(default_factory=list)
    null_rate: float = 0.0
    unique_count: int = 0


class TableSchema(BaseModel):
    table_name: str
    columns: List[ColumnInfo] = Field(default_factory=list)
    row_count: int = 0
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list)


# ------------------------------------------------------------------ #
# Relationship models
# ------------------------------------------------------------------ #

class TableRelationship(BaseModel):
    left_table: str
    right_table: str
    left_column: str
    right_column: str
    relationship_type: str = "inferred"          # "fk" | "name_match" | "inferred"
    confidence: float = 1.0


# ------------------------------------------------------------------ #
# Column statistics
# ------------------------------------------------------------------ #

class ColumnStats(BaseModel):
    table: str
    column: str
    dtype: str
    row_count: int = 0
    null_rate: float = 0.0
    unique_count: int = 0
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    entropy: Optional[float] = None
    top_values: List[Any] = Field(default_factory=list)


# ------------------------------------------------------------------ #
# KPI models
# ------------------------------------------------------------------ #

class CandidateKPI(BaseModel):
    id: str
    name: str
    description: str
    template: str                                # e.g. "conversion_rate"
    formula: str                                 # human-readable formula
    tables: List[str] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    sql: Optional[str] = None
    confidence: float = 0.0
    requires_join: bool = False
    group_id: int = 0                            # which table group


class ComputedKPI(BaseModel):
    kpi_id: str
    value: Any = None
    error: Optional[str] = None
    sql_used: Optional[str] = None


class EvaluatedKPI(BaseModel):
    kpi_id: str
    name: str
    value: Any = None
    variance_score: float = 0.0
    usefulness_score: float = 0.0
    passed: bool = False
    rejection_reason: Optional[str] = None


class KPIInsight(BaseModel):
    kpi_id: str
    kpi_name: str
    value: Any = None
    insight: str = ""
