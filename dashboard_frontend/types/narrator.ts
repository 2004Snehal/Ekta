/**
 * Narrator v2 — TypeScript types matching backend schemas.py
 */

// ── Insight Card (v2 extended) ──────────────────────────────────────────────

export type InsightCategory =
  | 'anomaly' | 'trend' | 'comparison' | 'milestone'
  | 'operational' | 'data_quality';

export type InsightSeverity = 'high' | 'medium' | 'low';

export type EntityType =
  | 'channel' | 'user' | 'language' | 'input_type'
  | 'output_type' | 'team' | 'fleet';

export type InsightStatus = 'new' | 'ongoing' | 'worsening' | 'resolved';

export type TabDestination = 'pulse' | 'watchlist' | 'pipeline' | 'data_governance';

export interface RootCauseDriver {
  dimension: string;
  driver: string;
  contribution_pct: number;
}

export interface InsightCardData {
  id: string;
  title: string;
  body: string;
  category: InsightCategory;
  severity: InsightSeverity;
  metric_name: string;
  entity_type: EntityType;
  entity_id: string;
  current_value: number;
  reference_value: number;
  delta_pct: number;
  period: string;
  confidence: 'statistical' | 'contextual';
  root_cause_hint?: string | null;
  // v2
  status: InsightStatus;
  suggested_action?: string | null;
  insight_source: string;
  tab_destination: TabDestination;
  consecutive_periods?: number | null;
  root_cause_breakdown?: RootCauseDriver[] | null;
  actionability_score?: number | null;
  nlq_query?: string | null;
}

// ── Entity Health ───────────────────────────────────────────────────────────

export type HealthGrade = 'A' | 'B' | 'C' | 'D';

export interface EntityHealthScore {
  entity_type: string;
  entity_id: string;
  entity_label: string;
  score: number;
  grade: HealthGrade;
  components: Record<string, number>;
  delta_vs_last?: number | null;
  signal_count: number;
  top_signal?: string | null;
}

// ── Publishing Funnel ───────────────────────────────────────────────────────

export interface FunnelStage {
  stage: string;
  count: number;
  duration_hours: number;
  pct_of_uploaded: number;
}

export interface FunnelByEntity {
  entity_label: string;
  entity_id: string;
  uploaded: number;
  processed: number;
  published: number;
  publish_rate: number;
  gap: number;
  status: 'critical' | 'watch' | 'healthy';
}

export interface FunnelSummary {
  stages: FunnelStage[];
  by_channel: FunnelByEntity[];
  total_gap: number;
  fleet_publish_rate: number;
}

// ── Data Quality ────────────────────────────────────────────────────────────

export interface FieldCompleteness {
  field_name: string;
  total_rows: number;
  non_null_count: number;
  null_count: number;
  pct_complete: number;
  unknown_count: number;
  trend: 'improving' | 'stable' | 'declining';
}

export interface DQScorecard {
  overall_score: number;
  total_rows: number;
  fields: FieldCompleteness[];
  duplicate_video_ids: number;
  invalid_publish_urls: number;
  delta_vs_last?: number | null;
}

export interface DQPeriodScore {
  period: string;
  score: number;
  total_rows: number;
  pct_complete: number;
}

// ── Period Summary ──────────────────────────────────────────────────────────

export interface MetricComparison {
  metric_name: string;
  metric_label: string;
  current_value: number;
  previous_value: number;
  delta_pct: number;
  direction: 'improved' | 'declined' | 'stable';
}

export interface PeriodSummary {
  current_period: string;
  previous_period: string;
  metrics: MetricComparison[];
  improved_count: number;
  declined_count: number;
  stable_count: number;
}

// ── Narrator Response V2 ────────────────────────────────────────────────────

export interface NarratorResponseV2 {
  client_id: number;
  period: string;
  generated_at: string;
  data_as_of: string;

  // Pulse
  pulse_score: number;
  pulse_delta?: number | null;
  digest?: string | null;
  period_summary?: PeriodSummary | null;
  entity_health: EntityHealthScore[];
  top_signals: InsightCardData[];
  follow_ups: InsightCardData[];
  resolved: InsightCardData[];
  summary_counts: Record<string, number>;

  // Watchlist & Patterns
  flagged_metrics: InsightCardData[];
  consecutive_trends: InsightCardData[];
  cross_dimension: InsightCardData[];
  milestones: InsightCardData[];

  // Pipeline & Operations
  funnel?: FunnelSummary | null;
  funnel_gaps: InsightCardData[];
  operational_risks: InsightCardData[];
  stalled_content: InsightCardData[];

  // Data Governance
  dq_scorecard?: DQScorecard | null;
  dq_trend: DQPeriodScore[];
  dq_issues: InsightCardData[];

  // Dashboard integration
  kpi_insights: InsightCardData[];
  dashboard_banner: InsightCardData[];

  // History context
  last_resolved: InsightCardData[];
  checks_run: string[];

  // Backward compat
  insights: InsightCardData[];
}
