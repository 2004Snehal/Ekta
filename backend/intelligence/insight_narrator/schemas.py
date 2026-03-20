"""
Pydantic schemas for the Insight Narrator pipeline.

FlaggedMetric   — internal pre-LLM statistical detection output
InsightCard     — canonical unit surfaced to the frontend
NarratorResponseV2 — full pipeline response, organized by tab destination
Supporting models: EntityHealthScore, FunnelSummary, DQScorecard, PeriodSummary
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid


# ── Pre-LLM: statistical detector output ─────────────────────────────────────

class FlaggedMetric(BaseModel):
    """A single metric anomaly detected statistically BEFORE any LLM call."""

    entity_type: Literal["channel", "user", "language", "input_type", "output_type", "team", "fleet"]
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

    # ── v2 extensions (all have defaults, fully backward-compatible) ──
    insight_source: str = "anomaly"        # anomaly|funnel|cross_dim|consecutive|milestone|op_risk|dq
    consecutive_periods: Optional[int] = None  # for consecutive trends
    dimensions: Optional[list[str]] = None     # for cross-dim: ["channel","language"]
    suggested_action: Optional[str] = None
    status: str = "new"                    # new|ongoing|worsening|resolved
    root_cause_breakdown: Optional[list[dict]] = None  # [{dimension, driver, contribution_pct}]
    actionability_score: Optional[float] = None  # 0-100 composite: severity × recoverability × scope
    tab_destination: Optional[str] = None


# ── Post-LLM: narrator output ────────────────────────────────────────────────

class InsightCard(BaseModel):
    """A single insight card returned to the frontend."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    body: str
    category: Literal["anomaly", "trend", "comparison", "milestone", "operational", "data_quality"]
    severity: Literal["high", "medium", "low"]
    metric_name: str
    entity_type: Literal["channel", "user", "language", "input_type", "output_type", "team", "fleet"]
    entity_id: str
    current_value: float
    reference_value: float
    delta_pct: float
    period: str                            # YYYY-MM
    confidence: Literal["statistical", "contextual"] = "statistical"
    root_cause_hint: Optional[str] = None

    # ── v2 extensions ──
    status: str = "new"                    # new|ongoing|worsening|resolved
    suggested_action: Optional[str] = None
    insight_source: str = "anomaly"
    tab_destination: str = "watchlist"     # pulse|watchlist|pipeline|data_governance
    consecutive_periods: Optional[int] = None
    root_cause_breakdown: Optional[list[dict]] = None
    actionability_score: Optional[float] = None
    nlq_query: Optional[str] = None        # pre-filled NLQ question for "Explore in NLQ" link


# ═══════════════════════════════════════════════════════════════════════════════
# v2 models — narrator intelligence hub
# ═══════════════════════════════════════════════════════════════════════════════

# ── Entity Health ─────────────────────────────────────────────────────────────

class EntityHealthScore(BaseModel):
    """Health score for a single entity (channel, user, etc.)."""

    entity_type: str                       # "channel" | "user"
    entity_id: str
    entity_label: str
    score: int                             # 0-100
    grade: Literal["A", "B", "C", "D"]    # A(80+) B(60-79) C(40-59) D(<40)
    components: dict = {}                  # {"publish_rate": 85, "activity": 70, "trend": 60, "dq": 90}
    delta_vs_last: Optional[int] = None    # score change vs previous period
    signal_count: int = 0                  # how many signals flagged for this entity
    top_signal: Optional[str] = None       # title of highest-severity signal


# ── Publishing Funnel ─────────────────────────────────────────────────────────

class FunnelStage(BaseModel):
    """One stage of the publishing funnel."""

    stage: str                             # "uploaded" | "processed" | "published"
    count: int
    duration_hours: float = 0.0
    pct_of_uploaded: float                 # relative to first stage


class FunnelByEntity(BaseModel):
    """Funnel breakdown for a single entity."""

    entity_label: str
    entity_id: str
    uploaded: int
    processed: int
    published: int
    publish_rate: float                    # published / uploaded * 100
    gap: int                               # uploaded - published
    status: Literal["critical", "watch", "healthy"]


class FunnelSummary(BaseModel):
    """Fleet-level funnel data (always populated)."""

    stages: list[FunnelStage]
    by_channel: list[FunnelByEntity] = []
    total_gap: int = 0                     # fleet-wide uploaded - published
    fleet_publish_rate: float = 0.0


# ── Data Quality ──────────────────────────────────────────────────────────────

class FieldCompleteness(BaseModel):
    """Completeness stats for a single field."""

    field_name: str
    total_rows: int
    non_null_count: int
    null_count: int
    pct_complete: float                    # 0-100
    unknown_count: int = 0                 # records with "Unknown" / "unknown" value
    trend: Literal["improving", "stable", "declining"] = "stable"


class DQScorecard(BaseModel):
    """Data quality scorecard (always populated)."""

    overall_score: int                     # 0-100
    total_rows: int
    fields: list[FieldCompleteness]
    duplicate_video_ids: int = 0
    invalid_publish_urls: int = 0
    delta_vs_last: Optional[int] = None    # score change vs previous period


class DQPeriodScore(BaseModel):
    """DQ score for a single period (for trend chart)."""

    period: str                            # YYYY-MM
    score: int                             # 0-100
    total_rows: int
    pct_complete: float


# ── Period Comparison ─────────────────────────────────────────────────────────

class MetricComparison(BaseModel):
    """Single metric comparison: current vs previous period."""

    metric_name: str
    metric_label: str
    current_value: float
    previous_value: float
    delta_pct: float
    direction: Literal["improved", "declined", "stable"]


class PeriodSummary(BaseModel):
    """Period-over-period summary for Pulse tab."""

    current_period: str
    previous_period: str
    metrics: list[MetricComparison] = []
    improved_count: int = 0
    declined_count: int = 0
    stable_count: int = 0


# ── Narrator Response V2 ─────────────────────────────────────────────────────

class NarratorResponseV2(BaseModel):
    """
    Full response for the Intelligence Hub (narrator v2).
    Organized by tab destination. Always-present fields ensure no tab is empty.
    """

    client_id: int
    period: str
    generated_at: str
    data_as_of: str

    # ── Pulse tab (always has content) ──
    pulse_score: int = 0                   # 0-100 overall health
    pulse_delta: Optional[int] = None      # vs last period
    digest: Optional[str] = None
    period_summary: Optional[PeriodSummary] = None
    entity_health: list[EntityHealthScore] = []
    top_signals: list[InsightCard] = []    # top 5 across all tabs
    follow_ups: list[InsightCard] = []     # ongoing/worsening from previous periods
    resolved: list[InsightCard] = []
    summary_counts: dict = {}              # {"watchlist": 3, "pipeline": 1, "dq": 2}

    # ── Watchlist & Patterns tab ──
    flagged_metrics: list[InsightCard] = []       # current-period detections
    consecutive_trends: list[InsightCard] = []    # 3+ months same direction
    cross_dimension: list[InsightCard] = []       # surprising dim-pair patterns
    milestones: list[InsightCard] = []            # positive achievements

    # ── Pipeline & Operations tab ──
    funnel: Optional[FunnelSummary] = None        # always populated
    funnel_gaps: list[InsightCard] = []
    operational_risks: list[InsightCard] = []     # dead channels, SPOF, concentration
    stalled_content: list[InsightCard] = []       # processed but unpublished

    # ── Data Governance tab ──
    dq_scorecard: Optional[DQScorecard] = None    # always populated
    dq_trend: list[DQPeriodScore] = []            # 6-month history
    dq_issues: list[InsightCard] = []

    # ── Dashboard integration layer ──
    kpi_insights: list[InsightCard] = []          # for SparkKPI dots
    dashboard_banner: list[InsightCard] = []      # top 3 for InsightBanner

    # ── History context (for empty states) ──
    last_resolved: list[InsightCard] = []         # most recent resolved items
    checks_run: list[str] = []                    # "7 analyzers executed, 342 signals evaluated"

    # ── Backward compat ──
    insights: list[InsightCard] = []              # flattened list (all cards)
