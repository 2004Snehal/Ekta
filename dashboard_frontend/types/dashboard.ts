import type { UniversalChartSpec } from '@/types/chart';

export type DashboardDateRange = 'last-7-days' | 'last-30-days' | 'last-90-days' | 'all-time';

export type DashboardKpiId =
  | 'uploaded_videos'
  | 'processed_videos'
  | 'published_videos'
  | 'publish_rate'
  | 'average_duration';

export interface DashboardRecord extends Record<string, string | number | null> {
  date: string;
  client: string;
  channel: string;
  user: string;
  language: string;
  type: string;
  platform: string;
  workflow: string;
  publisher: string;
  content_bucket: string;
  status: string;
  videoId?: string;
  videoTitle?: string;
  uploadedVideos: number;
  processedVideos: number;
  publishedVideos: number;
  promotedVideos: number;
  engagement: number;
  avgDurationSeconds: number;
}

export interface DynamicDashboardFilter {
  id: string;
  field: string;
  value: string;
}

export interface DashboardFilters {
  dateRange: DashboardDateRange;
  client: string;
  channel: string;
  user: string;
  language: string;
  type: string;
  platform: string;
  extraFilters: DynamicDashboardFilter[];
}

export interface FilterOption {
  value: string;
  label: string;
  count?: number;
}

export interface DashboardFilterField {
  key: string;
  label: string;
  defaultVisible?: boolean;
}

export interface DashboardKPI {
  id: DashboardKpiId;
  title: string;
  value: string | number;
  change: number;
  timeframe: string;
  iconKey: 'video' | 'zap' | 'trending' | 'bar';
}

export interface DashboardKpiStat {
  label: string;
  value: string;
}

export interface DashboardKpiDetail {
  kpiId: DashboardKpiId;
  title: string;
  subtitle: string;
  description: string;
  stats: DashboardKpiStat[];
  charts: UniversalChartSpec[];
  tableTitle: string;
  table: Record<string, unknown>[];
}

export interface DashboardInsight {
  title: string;
  description: string;
  actionable?: boolean;
}

export interface DashboardStatePayload {
  userId: string;
  version: number;
  filters: DashboardFilters;
  filtersExpanded: boolean;
  loadedRange: DashboardDateRange;
  selectedKpiId?: DashboardKpiId;
  updatedAt?: string;
}

export interface DashboardDatasetResponse {
  user_id: string;
  requested_range: DashboardDateRange;
  data_window: {
    start_date: string;
    end_date: string;
    coverage_days: number;
  };
  records: DashboardRecord[];
  filter_fields?: DashboardFilterField[];
}

export interface DashboardKpiDetailResponse {
  user_id: string;
  kpi_id: DashboardKpiId;
  detail: DashboardKpiDetail;
}