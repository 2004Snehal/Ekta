"""
Pydantic response models for the NLQ API.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LidaInsight(BaseModel):
    title: str
    chart_spec: Dict[str, Any] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    question: str = Field("", description="Original natural language question")
    sql: str = Field(description="Generated SQL query")
    description: str = Field("", description="Natural language answer / description")
    chart_type: Optional[str] = Field(None, description="Suggested chart type")
    x: Optional[str] = Field(None, description="X-axis column name")
    y: Optional[str] = Field(None, description="Y-axis column name")
    title: Optional[str] = Field(None, description="Chart / result title")
    data: List[Dict[str, Any]] = Field(
        default_factory=list, description="Raw query result rows"
    )
    columns: List[str] = Field(default_factory=list, description="Column names in result")
    row_count: int = Field(0, description="Number of rows returned")
    insights: List[LidaInsight] = Field(
        default_factory=list, description="LIDA-generated insights (explore=true only)"
    )
    processing_time_ms: float = Field(0.0, description="Total end-to-end processing time in milliseconds")


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
