/**
 * Fallback KPIs shown when AI KPI generation returns 0 results after 2 retries.
 * Full data including expand_page — displayed exactly like AI-generated KPIs.
 * NOT saved to DB.
 */

export interface FallbackExpandStatQuery {
  sql: string;
  label: string;
}

export interface FallbackExpandChartConfig {
  sql: string;
  axes: { x: { field: string; label: string }; y: { field: string; label: string } };
  title: string;
  chart_type: 'line' | 'bar';
}

export interface FallbackExpandPage {
  value_range: string;
  interpretation: string;
  high_value_means: string;
  low_value_means: string;
  stat_queries: FallbackExpandStatQuery[];
  chart_configs: FallbackExpandChartConfig[];
}

export interface FallbackKPI {
  id: string;
  name: string;
  description: string;
  formula: string;
  sql_expression: string;
  columns_used: string[];
  tables_used: string[];
  category: string;
  unit: string;
  current_value: number | string;
  usefulness_score: number | null;
  source: string;
  expand_page: FallbackExpandPage;
}

export const FALLBACK_KPIS: FallbackKPI[] = [
  {
    id: 'fallback-kpi-1',
    name: 'Viral Share Rate',
    description:
      'Measures the percentage of published videos that exceed a defined virality threshold (e.g., 100K views), indicating breakout success among published content',
    formula:
      '(Count(Distinct Video_ID where Views > 100000) / Count(Distinct Video_ID where Published = 1)) * 100',
    sql_expression:
      "SELECT ( COUNT(DISTINCT CASE WHEN views > 100000 THEN video_id END)::DOUBLE PRECISION / NULLIF(COUNT(DISTINCT CASE WHEN published = 1 THEN video_id END), 0) ) * 100 AS value FROM data.shortened_filtered_data",
    columns_used: ['views', 'video_id', 'published', 'output_type'],
    tables_used: ['data.shortened_filtered_data'],
    category: 'Editorial and Production Teams',
    unit: 'percentage',
    current_value: 13.4007585335019,
    usefulness_score: null,
    source: 'agent',
    expand_page: {
      value_range: '0% to 100% (higher means more published content achieving viral reach)',
      interpretation:
        'This KPI measures how often published content achieves viral performance, focusing only on content that actually made it to distribution.',
      high_value_means:
        'High values indicate strong performance where a significant portion of published content achieves viral reach.',
      low_value_means:
        'Low values indicate that few published videos reach high engagement thresholds, suggesting improvement opportunities in content strategy or distribution.',
      stat_queries: [
        {
          sql: 'SELECT COUNT(DISTINCT video_id) AS value FROM data.shortened_filtered_data WHERE published = 1',
          label: 'Total Published Videos',
        },
        {
          sql: 'SELECT COUNT(DISTINCT video_id) AS value FROM data.shortened_filtered_data WHERE views > 100000',
          label: 'Viral Videos (>100K views)',
        },
        {
          sql: 'SELECT COUNT(DISTINCT video_id) AS value FROM data.shortened_filtered_data WHERE views > 100000 AND published = 1',
          label: 'Published Viral Videos',
        },
      ],
      chart_configs: [
        {
          sql: "SELECT DATE(TO_TIMESTAMP(uploaded_at, 'YYYY-MM-DD')) AS upload_date, ( COUNT(DISTINCT CASE WHEN views > 100000 THEN video_id END)::DOUBLE PRECISION / NULLIF(COUNT(DISTINCT CASE WHEN published = 1 THEN video_id END), 0) ) * 100 AS viral_rate FROM data.shortened_filtered_data WHERE uploaded_at IS NOT NULL GROUP BY upload_date ORDER BY upload_date ASC",
          axes: { x: { field: 'upload_date', label: 'Date' }, y: { field: 'viral_rate', label: 'Viral Share (%)' } },
          title: 'Viral Share Rate Over Time (Published Only)',
          chart_type: 'line',
        },
        {
          sql: "SELECT output_type, ( COUNT(DISTINCT CASE WHEN views > 100000 THEN video_id END)::DOUBLE PRECISION / NULLIF(COUNT(DISTINCT CASE WHEN published = 1 THEN video_id END), 0) ) * 100 AS viral_rate FROM data.shortened_filtered_data WHERE output_type IS NOT NULL GROUP BY output_type ORDER BY viral_rate DESC",
          axes: { x: { field: 'output_type', label: 'Output Type' }, y: { field: 'viral_rate', label: 'Viral Share (%)' } },
          title: 'Viral Share Rate by Output Type (Published Only)',
          chart_type: 'bar',
        },
      ],
    },
  },
  {
    id: 'fallback-kpi-2',
    name: 'Engagement Velocity Index',
    description:
      'Measures how many views are generated per second of published content, indicating content efficiency and audience engagement speed',
    formula: 'Sum(Views) / Sum(Published_Duration in seconds)',
    sql_expression:
      "SELECT ( COALESCE(SUM(views), 0) / NULLIF(SUM(EXTRACT(EPOCH FROM published_duration::interval)), 0) ) AS value FROM data.shortened_filtered_data WHERE views IS NOT NULL OR published_duration IS NOT NULL",
    columns_used: ['views', 'published_duration'],
    tables_used: ['data.shortened_filtered_data'],
    category: 'Editorial and Production Teams',
    unit: 'ratio',
    current_value: 188.054065687427,
    usefulness_score: null,
    source: 'agent',
    expand_page: {
      value_range: '0 to ∞ (higher means more engagement per second of content)',
      interpretation:
        'This KPI evaluates how efficiently published content generates views relative to its duration, reflecting audience engagement intensity.',
      high_value_means:
        'High velocity suggests strong audience engagement, effective content strategy, and efficient use of viewer attention.',
      low_value_means:
        'Low velocity indicates content is not generating sufficient engagement per unit time, suggesting weak audience resonance or distribution.',
      stat_queries: [
        {
          sql: 'SELECT COALESCE(SUM(views), 0) AS value FROM data.shortened_filtered_data WHERE views IS NOT NULL',
          label: 'Total Views',
        },
        {
          sql: "SELECT SUM(EXTRACT(EPOCH FROM published_duration::interval)) AS value FROM data.shortened_filtered_data WHERE published_duration IS NOT NULL",
          label: 'Total Published Duration (seconds)',
        },
      ],
      chart_configs: [
        {
          sql: "SELECT DATE(TO_TIMESTAMP(uploaded_at, 'YYYY-MM-DD')) AS upload_date, ( COALESCE(SUM(views), 0) / NULLIF(SUM(EXTRACT(EPOCH FROM published_duration::interval)), 0) ) AS engagement_velocity FROM data.shortened_filtered_data WHERE uploaded_at IS NOT NULL GROUP BY upload_date ORDER BY upload_date ASC",
          axes: { x: { field: 'upload_date', label: 'Date' }, y: { field: 'engagement_velocity', label: 'Views per Second' } },
          title: 'Engagement Velocity Trend Over Time',
          chart_type: 'line',
        },
        {
          sql: "SELECT output_type, ( COALESCE(SUM(views), 0) / NULLIF(SUM(EXTRACT(EPOCH FROM published_duration::interval)), 0) ) AS engagement_velocity FROM data.shortened_filtered_data WHERE output_type IS NOT NULL GROUP BY output_type ORDER BY engagement_velocity DESC",
          axes: { x: { field: 'output_type', label: 'Output Type' }, y: { field: 'engagement_velocity', label: 'Views per Second' } },
          title: 'Engagement Velocity by Output Type',
          chart_type: 'bar',
        },
      ],
    },
  },
];
