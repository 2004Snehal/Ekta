"""
Pydantic schemas for the Insight Narrator output.

InsightCard is the canonical unit surfaced to users.
FlaggedMetric is the internal pre-LLM representation
produced by the statistical detector.
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid


# ── Pre-LLM: statistical detector output ─────────────────────────────────────

class FlaggedMetric(BaseModel):
    """A single metric anomaly detected statistically BEFORE any LLM call."""

    entity_type: Literal["channel", "user", "language", "input_type"]
    entity_id: str                         # channel_code, user_name, etc.
    entity_label: str                      # human-readable name
    metric_name: str                       # publish_rate | output_count | upload_count | output_multiplier | avg_duration_secs
    current_value: float
    reference_value: float                 # 3-month rolling average
    delta_pct: float                       # (current - reference) / reference * 100
    zscore: Optional[float] = None
    severity: Literal["high", "medium", "low"]
    period: str                            # YYYY-MM
    history_months: int = 3               # how many months of data underpins baseline


# ── Post-LLM: narrator output ─────────────────────────────────────────────────

class InsightCard(BaseModel):
    """A single insight card returned to the frontend."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    body: str
    category: Literal["anomaly", "trend", "comparison", "milestone"]
    severity: Literal["high", "medium", "low"]
    metric_name: str
    entity_type: Literal["channel", "user", "language", "input_type"]
    entity_id: str
    current_value: float
    reference_value: float
    delta_pct: float
    period: str                            # YYYY-MM
    confidence: Literal["statistical", "contextual"] = "statistical"
    root_cause_hint: Optional[str] = None


class NarratorResponse(BaseModel):
    """Top-level response returned by the narrator pipeline."""

    client_id: int
    period: str                            # YYYY-MM of the most recent month analysed
    generated_at: str                      # ISO datetime
    data_as_of: str                        # ISO date — most recent month in dataset
    digest: Optional[str] = None           # one-paragraph weekly digest
    insights: list[InsightCard] = []
