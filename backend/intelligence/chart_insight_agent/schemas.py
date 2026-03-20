"""
Pydantic schemas for the Chart Insight Agent.

ChartInsightRequest  — sent by the frontend on hover.
ChartInsightResponse — returned to the frontend for display.
"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel


class ChartInsightRequest(BaseModel):
    """Payload sent by the frontend when a user hovers over a chart."""

    chart_title: str
    chart_type: str                          # line | bar | pie | scatter | stacked_bar
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    data: list[dict[str, Any]]              # exactly what is rendered in the chart
    user_role: Optional[str] = None


class ChartInsightResponse(BaseModel):
    """Insight output returned to the frontend."""

    summary: str                             # one-sentence headline
    insights: list[str]                      # 3–5 plain-English bullet points


class ChartDescriptionRequest(BaseModel):
    """Metadata needed to describe what a chart depicts (no data required)."""

    chart_title: str
    chart_type: str
    x_label: Optional[str] = None
    y_label: Optional[str] = None


class ChartDescriptionResponse(BaseModel):
    """Static description of what a chart is and what it measures."""

    description: str
