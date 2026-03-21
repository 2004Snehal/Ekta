/**
 * Fallback KPIs shown when AI KPI generation returns 0 results after 2 retries.
 * These are displayed as if AI-generated and are NOT saved to the DB.
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
    name: 'Viral Share Rate',
    description:
      'Measures the percentage of published videos that exceed a defined virality threshold (e.g., 100K views), indicating breakout success among published content',
    formula: '(Count(Distinct Video_ID where Views > 100000) / Count(Distinct Video_ID where Published = 1)) * 100',
    sql: `SELECT (
  COUNT(DISTINCT CASE WHEN views > 100000 THEN video_id END)::DOUBLE PRECISION
  / NULLIF(COUNT(DISTINCT CASE WHEN published = 1 THEN video_id END), 0)
) * 100 AS value
FROM data.shortened_filtered_data`,
    category: 'Editorial and Production Teams',
    unit: 'percentage',
    current_value: 13.4007585335019,
    usefulness_score: 8,
  },
  {
    id: 'fallback-kpi-2',
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
];
