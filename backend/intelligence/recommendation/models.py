"""
Pydantic models for the context-aware recommendation agent.
"""

from __future__ import annotations
from pydantic import BaseModel


class DashboardContext(BaseModel):
    client_id: int
    view: str
    # "channel_detail" | "user_detail" | "content_mix" | "executive_summary" | "trend_view"
    entity_type: str
    # "channel" | "user" | "input_type" | "output_type" | "network"
    entity_id: int | None = None
    # nullable for executive_summary
    entity_name: str
    metric_in_focus: str = "publish_rate_pct"
    # "publish_rate_pct" | "created_count" | "published_count" | "output_multiplier"
    current_value: float | None = None
    time_range: str | None = None
    # "2024-11" | null for all-time
    user_role: str = "operations"
    # "founder" | "client_success" | "operations" | "editorial" | "tech_product"
    # Legacy keys still accepted: "exec" → "founder", "ops_lead" → "operations", "editor" → "editorial"


class ExpandedContext(BaseModel):
    """Internal model — not exposed via API. Holds 4 query result sets."""
    entity_profile: list[dict]
    peer_comparison: list[dict]
    related_actors: list[dict]
    benchmark: list[dict]


class Recommendation(BaseModel):
    title: str
    action: str
    rationale: str
    priority: str           # "high" | "medium" | "low"
    scope: str              # "channel" | "user" | "content" | "network"
    supporting_metrics: dict


class RecommendationResponse(BaseModel):
    recommendations: list[Recommendation]
    context_view: str
    entity_name: str
    generated_at: str
    cached: bool = False
