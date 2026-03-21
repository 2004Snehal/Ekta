/**
 * Fallback KPIs shown when AI KPI generation returns 0 results after 2 retries.
 * These are displayed as if they were AI-generated and are NOT saved to the DB.
 *
 * TODO: Replace FALLBACK_KPI_2 with your second KPI once provided.
 */

export interface FallbackKPI {
  id: string;
  name: string;
  description: string;
  formula: string;
  sql?: string;
  category: string;
  unit: string;
  current_value: number | string;
  usefulness_score?: number;
}

export const FALLBACK_KPIS: FallbackKPI[] = [
  {
    id: 'fallback-kpi-1',
    name: 'Engagement Velocity Index',
    description:
      'Measures how many views are generated per second of published content, indicating content efficiency and audience engagement speed',
    formula: 'Sum(Views) / Sum(Published_Duration in seconds)',
    sql: `SELECT (
  COALESCE(SUM(views), 0) /
  NULLIF(SUM(EXTRACT(EPOCH FROM published_duration::interval)), 0)
) AS value
FROM data.shortened_filtered_data
WHERE views IS NOT NULL OR published_duration IS NOT NULL`,
    category: 'Editorial and Production Teams',
    unit: 'ratio',
    current_value: 188.054065687427,
    usefulness_score: 8,
  },
  // ── SECOND FALLBACK KPI ──────────────────────────────────────────────────────
  // TODO: replace this placeholder with your actual second fallback KPI
  {
    id: 'fallback-kpi-2',
    name: 'Video Publication Rate',
    description:
      'Percentage of processed videos that are successfully published. Measures overall publishing efficiency across all channels.',
    formula: 'RATIO(COUNT_DISTINCT(video_id) FILTER (published_flag = TRUE), COUNT_DISTINCT(video_id))',
    sql: `SELECT
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE published_flag = TRUE)
    / NULLIF(COUNT(*), 0),
    4
  ) AS value
FROM data.fact_created_videos`,
    category: 'Operations Teams',
    unit: '%',
    current_value: 0,
    usefulness_score: 8,
  },
];
