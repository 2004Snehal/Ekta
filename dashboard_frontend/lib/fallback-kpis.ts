/**
 * Fallback KPIs shown when AI KPI generation returns 0 results after 2 retries.
 * These are displayed as if they were AI-generated and are NOT saved to the DB.
 * Update the two entries below with your desired fallback KPI definitions.
 */

export interface FallbackKPI {
  id: string;
  name: string;
  description: string;
  formula: string;
  category: string;
  unit: string;
  current_value: number | string;
}

export const FALLBACK_KPIS: FallbackKPI[] = [
  {
    id: 'fallback-kpi-1',
    name: 'Video Publication Rate',
    description:
      'Percentage of processed videos that are successfully published. Measures overall publishing efficiency.',
    formula: 'RATIO(COUNT_DISTINCT(video_id) FILTER (published_flag = TRUE), COUNT_DISTINCT(video_id))',
    category: 'Operations Teams',
    unit: '%',
    current_value: 0,
  },
  {
    id: 'fallback-kpi-2',
    name: 'Avg Processing Duration (hrs)',
    description:
      'Average duration of all created video content in hours. Tracks content depth and production scope.',
    formula: 'AVG(created_duration_secs) / 3600',
    category: 'Editorial and Production Teams',
    unit: 'hours',
    current_value: 0,
  },
];
