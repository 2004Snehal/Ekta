// ── Filter state ──────────────────────────────────────────────────────────────

export interface Filters {
  client_id: number
  channel_id: number | null
  date_from: string | null  // ISO date string or null
  date_to: string | null
}

// ── Filter options (from /filters/options) ───────────────────────────────────

export interface ChannelOption {
  id: number
  name: string
  code: string
}

export interface InputTypeOption {
  id: number
  name: string
  category: string
}

export interface LanguageOption {
  id: number
  code: string
  name: string
}

export interface FilterOptions {
  channels: ChannelOption[]
  input_types: InputTypeOption[]
  languages: LanguageOption[]
  date_range: { min: string | null; max: string | null }
}

// ── KPI totals (from /kpis/totals) ───────────────────────────────────────────

export interface KpiTotals {
  total_uploads: number
  total_outputs: number
  total_published: number
  publish_rate_pct: number
}

// ── Monthly summary row (from /kpis/summary) ─────────────────────────────────

export interface SummaryRow {
  month: string
  channel_id: number
  channel_code: string
  channel_name: string
  input_type_id: number | null
  input_type: string | null
  output_type_id: number | null
  output_type: string | null
  language_id: number | null
  language_code: string | null
  created_count: number
  published_count: number
  total_uploaded_secs: number
  total_created_secs: number
  total_published_secs: number
  publish_rate_pct: number
}

// ── Channel health (from /channels/health) ───────────────────────────────────

export interface ChannelHealth {
  channel_id: number
  channel_name: string
  channel_code: string
  primary_language: string
  total_created: number
  total_published: number
  publish_rate_pct: number
  active_users: number
  last_activity: string | null
}

// ── User performance (from /users/performance) ───────────────────────────────

export interface UserPerformance {
  user_id: number
  user_name: string
  role: string
  is_bot: boolean
  channel_id: number
  channel_name: string
  channel_code: string
  created_count: number
  published_count: number
  publish_rate_pct: number
  total_uploaded_duration_secs: number
  total_created_duration_secs: number
}

// ── Insight (from /insights/) ────────────────────────────────────────────────

export interface Insight {
  insight_id: number
  insight_type: string
  severity: string
  title: string
  body: string
  dimensions: Record<string, unknown> | null
  metric_value: number | null
  baseline_value: number | null
  delta_pct: number | null
  generated_at: string
  is_read: boolean
}

// ── NLQ result (from /nlq/query) ─────────────────────────────────────────────

export interface NLQResult {
  question: string
  answer?: string
  sql: string | null
  chart_type: 'bar' | 'line' | 'pie' | 'table' | 'stacked_bar'
  title: string
  x: string
  y: string
  description: string
  data: Record<string, unknown>[]
  columns: string[]
  row_count: number
  error?: string
}
