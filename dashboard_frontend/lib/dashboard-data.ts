/**
 * dashboard-data.ts
 *
 * Client-side data layer for the Analytics Dashboard.
 * Handles filtering, KPI computation, chart building, mock data, and state management.
 */

import type {
  DashboardDateRange,
  DashboardFilterField,
  DashboardFilters,
  DashboardInsight,
  DashboardKPI,
  DashboardKpiDetail,
  DashboardKpiId,
  DashboardRecord,
  DashboardStatePayload,
  FilterOption,
} from '@/types/dashboard';
import type { UniversalChartSpec } from '@/types/chart';

// ── Constants ──────────────────────────────────────────────────────────────────

const RANGE_DAYS: Record<DashboardDateRange, number> = {
  'last-7-days':  7,
  'last-30-days': 30,
  'last-90-days': 90,
  'all-time':     Infinity,
};

export const DEFAULT_FILTERS: DashboardFilters = {
  dateRange:    'last-30-days',
  client_type:  '',
  client:       '',
  channel:      '',
  user:         '',
  language:     '',
  type:         '',
  platform:     '',
  extraFilters: [],
};

const KNOWN_FILTER_FIELDS: DashboardFilterField[] = [
  { key: 'client_type',    label: 'Client Type',    defaultVisible: true  },
  { key: 'channel',        label: 'Channel',        defaultVisible: true  },
  { key: 'user',           label: 'User',           defaultVisible: true  },
  { key: 'language',       label: 'Language',       defaultVisible: true  },
  { key: 'type',           label: 'Type',           defaultVisible: true  },
  { key: 'platform',       label: 'Platform',       defaultVisible: true  },
  { key: 'workflow',       label: 'Workflow',       defaultVisible: false },
  { key: 'publisher',      label: 'Publisher',      defaultVisible: false },
  { key: 'content_bucket', label: 'Content Bucket', defaultVisible: false },
  { key: 'status',         label: 'Status',         defaultVisible: false },
];

// ── Range helpers ──────────────────────────────────────────────────────────────

export function supportsRange(
  loadedRange: DashboardDateRange | null,
  requestedRange: DashboardDateRange,
): boolean {
  if (!loadedRange) return false;
  return RANGE_DAYS[loadedRange] >= RANGE_DAYS[requestedRange];
}

export function getDisplayRangeLabel(range: DashboardDateRange): string {
  switch (range) {
    case 'last-7-days':  return 'Last 7 days';
    case 'last-30-days': return 'Last 30 days';
    case 'last-90-days': return 'Last 90 days';
    case 'all-time':     return 'All time';
  }
}

function getDateCutoff(range: DashboardDateRange): Date | null {
  if (range === 'all-time') return null;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - RANGE_DAYS[range]);
  cutoff.setHours(0, 0, 0, 0);
  return cutoff;
}

// ── Filter helpers ─────────────────────────────────────────────────────────────

export function normalizeFilterFields(
  records: DashboardRecord[],
  filterFields?: DashboardFilterField[],
): DashboardFilterField[] {
  if (filterFields && filterFields.length > 0) return filterFields;
  return KNOWN_FILTER_FIELDS.filter((f) =>
    records.some((r) => r[f.key] != null && r[f.key] !== ''),
  );
}

export function getFilterOptions(records: DashboardRecord[], key: string): FilterOption[] {
  const counts = new Map<string, number>();
  for (const r of records) {
    const val = String(r[key] ?? '');
    if (val) counts.set(val, (counts.get(val) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([value, count]) => ({ value, label: value, count }));
}

export function filterDashboardRecords(
  records: DashboardRecord[],
  filters: DashboardFilters,
  opts?: { ignoreField?: string },
): DashboardRecord[] {
  const cutoff = getDateCutoff(filters.dateRange);

  return records.filter((r) => {
    if (cutoff) {
      const d = new Date(r.date);
      if (isNaN(d.getTime()) || d < cutoff) return false;
    }

    const simple: Array<[keyof DashboardFilters, string]> = [
      ['client_type', 'client_type'],
      ['channel', 'channel'],
      ['user', 'user'],
      ['language', 'language'],
      ['type', 'type'],
      ['platform', 'platform'],
    ];

    for (const [fk, rk] of simple) {
      if (opts?.ignoreField === rk) continue;
      const v = filters[fk] as string;
      if (v && v !== 'all' && r[rk] !== v) return false;
    }

    for (const ef of filters.extraFilters) {
      if (opts?.ignoreField === ef.field) continue;
      if (ef.value && ef.value !== 'all' && String(r[ef.field] ?? '') !== ef.value) return false;
    }

    return true;
  });
}

// ── Mock data ──────────────────────────────────────────────────────────────────

const MOCK_CHANNELS  = ['Channel Alpha', 'Channel Beta', 'Channel Gamma', 'Channel Delta', 'Channel Epsilon'];
const MOCK_USERS     = ['User A', 'User B', 'User C', 'User D', 'User E'];
const MOCK_LANGUAGES = ['lang-1', 'lang-2', 'lang-3', 'lang-4'];
const MOCK_TYPES     = ['bulletin', 'interview', 'special report', 'panel', 'feature'];
const MOCK_PLATFORMS = ['Platform X', 'Platform Y', 'Platform Z', 'Platform W', 'Platform V'];

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

export function createMockDashboardRecords(range: DashboardDateRange): DashboardRecord[] {
  const days = range === 'all-time' ? 90 : RANGE_DAYS[range];
  const records: DashboardRecord[] = [];
  const now = new Date();

  for (let i = 0; i < days; i++) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().split('T')[0]!;
    const perDay = 3 + Math.floor(Math.random() * 5);

    for (let j = 0; j < perDay; j++) {
      const uploaded  = 1 + Math.floor(Math.random() * 4);
      const processed = uploaded;
      const published = Math.floor(Math.random() * (processed + 1));

      records.push({
        date:           dateStr,
        client:         'Frammer Demo',
        channel:        pick(MOCK_CHANNELS),
        user:           pick(MOCK_USERS),
        language:       pick(MOCK_LANGUAGES),
        type:           pick(MOCK_TYPES),
        platform:       pick(MOCK_PLATFORMS),
        workflow:       Math.random() > 0.3 ? 'auto' : 'manual',
        publisher:      'system',
        content_bucket: 'news',
        status:         published > 0 ? 'published' : 'created',
        uploadedVideos:   uploaded,
        processedVideos:  processed,
        publishedVideos:  published,
        promotedVideos:   Math.floor(Math.random() * 2),
        engagement:       Math.floor(Math.random() * 50000),
        avgDurationSeconds: 30 + Math.floor(Math.random() * 270),
      });
    }
  }

  return records;
}

// ── KPI builders ──────────────────────────────────────────────────────────────

function sum(records: DashboardRecord[], key: keyof DashboardRecord): number {
  return records.reduce((s, r) => s + ((r[key] as number) ?? 0), 0);
}

function formatDuration(secs: number): string {
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function publishRate(records: DashboardRecord[]): number {
  const proc = sum(records, 'processedVideos');
  const pub  = sum(records, 'publishedVideos');
  return proc > 0 ? Math.round((pub / proc) * 100) : 0;
}

export function buildDashboardKpis(
  allRecords: DashboardRecord[],
  filteredRecords: DashboardRecord[],
  filters: DashboardFilters,
): DashboardKPI[] {
  const uploaded  = sum(filteredRecords, 'uploadedVideos');
  const processed = sum(filteredRecords, 'processedVideos');
  const published = sum(filteredRecords, 'publishedVideos');
  const rate      = publishRate(filteredRecords);
  const totalDur  = sum(filteredRecords, 'avgDurationSeconds');
  const avgDur    = filteredRecords.length > 0 ? Math.round(totalDur / filteredRecords.length) : 0;

  const allUploaded  = sum(allRecords, 'uploadedVideos');
  const baseChange   = allUploaded > 0 ? Math.round(((uploaded - allUploaded * 0.5) / (allUploaded * 0.5)) * 100) : 0;
  const timeframe    = getDisplayRangeLabel(filters.dateRange);

  return [
    { id: 'uploaded_videos',  title: 'Uploaded Videos',  value: uploaded.toLocaleString(),  change: baseChange,                    timeframe, iconKey: 'video'    },
    { id: 'processed_videos', title: 'Processed Videos', value: processed.toLocaleString(), change: Math.round(baseChange * 0.9),  timeframe, iconKey: 'zap'      },
    { id: 'published_videos', title: 'Published Videos', value: published.toLocaleString(), change: Math.round(baseChange * 1.1),  timeframe, iconKey: 'trending' },
    { id: 'publish_rate',     title: 'Publish Rate',     value: `${rate}%`,                 change: Math.round(baseChange * 0.5),  timeframe, iconKey: 'bar'      },
    { id: 'average_duration', title: 'Avg Duration',     value: formatDuration(avgDur),      change: 0,                             timeframe, iconKey: 'bar'      },
  ];
}

// ── KPI detail builders ────────────────────────────────────────────────────────

export function buildDashboardKpiDetails(
  _allRecords: DashboardRecord[],
  filteredRecords: DashboardRecord[],
  _filters: DashboardFilters,
): Record<DashboardKpiId, DashboardKpiDetail> {
  const byChannel = groupBy(filteredRecords, 'channel');
  const byUser    = groupBy(filteredRecords, 'user');
  const byType    = groupBy(filteredRecords, 'type');

  const channelRows = Object.entries(byChannel).map(([channel, recs]) => ({
    channel,
    uploaded:   sum(recs, 'uploadedVideos'),
    processed:  sum(recs, 'processedVideos'),
    published:  sum(recs, 'publishedVideos'),
    publish_rate: `${publishRate(recs)}%`,
  })).sort((a, b) => b.uploaded - a.uploaded);

  const userRows = Object.entries(byUser).map(([user, recs]) => ({
    user,
    processed:    sum(recs, 'processedVideos'),
    published:    sum(recs, 'publishedVideos'),
    publish_rate: `${publishRate(recs)}%`,
  })).sort((a, b) => b.processed - a.processed);

  const typeRows = Object.entries(byType).map(([type, recs]) => ({
    type,
    count:        sum(recs, 'processedVideos'),
    published:    sum(recs, 'publishedVideos'),
    publish_rate: `${publishRate(recs)}%`,
  })).sort((a, b) => b.count - a.count);

  const totalUploaded  = sum(filteredRecords, 'uploadedVideos');
  const totalProcessed = sum(filteredRecords, 'processedVideos');
  const totalPublished = sum(filteredRecords, 'publishedVideos');
  const rate           = publishRate(filteredRecords);

  const channelBarChart: UniversalChartSpec = {
    chart_type: 'bar',
    title: 'By Channel',
    axes:  { x: { field: 'channel' }, y: { field: 'uploaded' } },
    data:  channelRows,
  };

  const userBarChart: UniversalChartSpec = {
    chart_type: 'bar',
    title: 'By User',
    axes:  { x: { field: 'user' }, y: { field: 'processed' } },
    data:  userRows,
  };

  const typeBarChart: UniversalChartSpec = {
    chart_type: 'bar',
    title: 'By Content Type',
    axes:  { x: { field: 'type' }, y: { field: 'count' } },
    data:  typeRows,
  };

  const ratePieChart: UniversalChartSpec = {
    chart_type: 'pie',
    title:      'Published vs Unpublished',
    category:   'status',
    value:      'count',
    data: [
      { status: 'Published',   count: totalPublished },
      { status: 'Unpublished', count: totalProcessed - totalPublished },
    ],
  };

  return {
    uploaded_videos: {
      kpiId: 'uploaded_videos',
      title: 'Uploaded Videos',
      subtitle: 'Source video uploads breakdown',
      description: 'Total source videos uploaded in the selected period, broken down by channel and user.',
      stats: [
        { label: 'Total Uploads',  value: totalUploaded.toLocaleString() },
        { label: 'Channels',       value: Object.keys(byChannel).length.toString() },
        { label: 'Active Users',   value: Object.keys(byUser).length.toString() },
      ],
      charts: [channelBarChart, userBarChart],
      tableTitle: 'Uploads by Channel',
      table: channelRows,
    },

    processed_videos: {
      kpiId: 'processed_videos',
      title: 'Processed Videos',
      subtitle: 'Processing pipeline performance',
      description: 'Videos processed through the pipeline in the selected period.',
      stats: [
        { label: 'Total Processed', value: totalProcessed.toLocaleString() },
        { label: 'By Channel',      value: Object.keys(byChannel).length.toString() },
        { label: 'Content Types',   value: Object.keys(byType).length.toString() },
      ],
      charts: [channelBarChart, typeBarChart],
      tableTitle: 'Processing by Channel',
      table: channelRows,
    },

    published_videos: {
      kpiId: 'published_videos',
      title: 'Published Videos',
      subtitle: 'Publishing output across channels',
      description: 'Videos that made it to publication in the selected period.',
      stats: [
        { label: 'Total Published', value: totalPublished.toLocaleString() },
        { label: 'Top Channel',     value: channelRows[0]?.channel ?? '—' },
        { label: 'Top User',        value: userRows[0]?.user ?? '—' },
      ],
      charts: [channelBarChart, userBarChart],
      tableTitle: 'Published by Channel',
      table: channelRows,
    },

    publish_rate: {
      kpiId: 'publish_rate',
      title: 'Publish Rate',
      subtitle: 'Percentage of processed videos published',
      description: 'Publish rate = published / processed × 100. Higher is better.',
      stats: [
        { label: 'Overall Rate',   value: `${rate}%` },
        { label: 'Best Channel',   value: channelRows.sort((a, b) => parseInt(b.publish_rate) - parseInt(a.publish_rate))[0]?.channel ?? '—' },
        { label: 'Worst Channel',  value: channelRows[channelRows.length - 1]?.channel ?? '—' },
      ],
      charts: [ratePieChart, channelBarChart],
      tableTitle: 'Publish Rate by Channel',
      table: channelRows.map((r) => ({ channel: r.channel, publish_rate: r.publish_rate, published: r.published, processed: r.processed })),
    },

    average_duration: {
      kpiId: 'average_duration',
      title: 'Average Duration',
      subtitle: 'Average video duration in the selected period',
      description: 'Average duration of source videos processed by channel and type.',
      stats: [
        { label: 'Overall Avg',  value: formatDuration(filteredRecords.length > 0 ? Math.round(sum(filteredRecords, 'avgDurationSeconds') / filteredRecords.length) : 0) },
        { label: 'Total Videos', value: totalProcessed.toLocaleString() },
        { label: 'Content Types', value: Object.keys(byType).length.toString() },
      ],
      charts: [typeBarChart, channelBarChart],
      tableTitle: 'Duration by Content Type',
      table: typeRows,
    },
  };
}

// ── Chart builders ─────────────────────────────────────────────────────────────

export function buildDashboardCharts(records: DashboardRecord[]): UniversalChartSpec[] {
  const byChannel = groupBy(records, 'channel');
  const byLang    = groupBy(records, 'language');
  const byType    = groupBy(records, 'type');

  const channelData = Object.entries(byChannel).map(([channel, recs]) => ({
    channel,
    uploaded:  sum(recs, 'uploadedVideos'),
    processed: sum(recs, 'processedVideos'),
    published: sum(recs, 'publishedVideos'),
  })).sort((a, b) => b.uploaded - a.uploaded);

  // Daily trend — group by date
  const dateMap = new Map<string, { uploaded: number; published: number }>();
  for (const r of records) {
    const existing = dateMap.get(r.date) ?? { uploaded: 0, published: 0 };
    dateMap.set(r.date, {
      uploaded:  existing.uploaded  + r.uploadedVideos,
      published: existing.published + r.publishedVideos,
    });
  }
  const trendData = Array.from(dateMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, vals]) => ({ date: date.slice(5), ...vals }));

  const langData = Object.entries(byLang).map(([language, recs]) => ({
    language,
    count: sum(recs, 'uploadedVideos'),
  })).sort((a, b) => b.count - a.count);

  const typeData = Object.entries(byType).map(([type, recs]) => ({
    type,
    count: sum(recs, 'processedVideos'),
  })).sort((a, b) => b.count - a.count);

  return [
    {
      chart_type:  'bar',
      title:       'Videos by Channel',
      description: 'Uploaded, processed and published counts per channel',
      axes:        { x: { field: 'channel', label: 'Channel' }, y: { field: 'uploaded', label: 'Count' } },
      data:        channelData,
    },
    {
      chart_type:  'line',
      title:       'Daily Upload Trend',
      description: 'Uploaded and published videos over time',
      axes:        { x: { field: 'date', label: 'Date' }, y: { field: 'uploaded', label: 'Videos' } },
      data:        trendData,
    },
    {
      chart_type:  'pie',
      title:       'Language Distribution',
      description: 'Share of content by language',
      category:    'language',
      value:       'count',
      data:        langData,
    },
    {
      chart_type:  'bar',
      title:       'Content by Type',
      description: 'Processed video count by input type',
      axes:        { x: { field: 'type', label: 'Type' }, y: { field: 'count', label: 'Count' } },
      data:        typeData,
    },
  ];
}

// ── Insight builders ───────────────────────────────────────────────────────────

export function buildDashboardInsights(
  records: DashboardRecord[],
  _filterFields: DashboardFilterField[],
): DashboardInsight[] {
  if (records.length === 0) return [];

  const insights: DashboardInsight[] = [];

  const byChannel = groupBy(records, 'channel');
  const ranked = Object.entries(byChannel)
    .map(([ch, recs]) => ({ ch, pub: sum(recs, 'publishedVideos'), proc: sum(recs, 'processedVideos') }))
    .sort((a, b) => b.pub - a.pub);

  if (ranked[0]) {
    const top  = ranked[0];
    const rate = top.proc > 0 ? Math.round((top.pub / top.proc) * 100) : 0;
    insights.push({
      title:       `${top.ch} leads in published content`,
      description: `${top.ch} published ${top.pub.toLocaleString()} videos with a ${rate}% publish rate in the selected period.`,
      actionable:  false,
    });
  }

  const byLang    = groupBy(records, 'language');
  const total     = sum(records, 'uploadedVideos');
  const topLang   = Object.entries(byLang)
    .map(([lang, recs]) => ({ lang, count: sum(recs, 'uploadedVideos') }))
    .sort((a, b) => b.count - a.count)[0];

  if (topLang && total > 0) {
    const pct = Math.round((topLang.count / total) * 100);
    insights.push({
      title:       `${topLang.lang.toUpperCase()} content dominates uploads`,
      description: `${pct}% of all uploaded videos are in ${topLang.lang}. Consider expanding language coverage for wider reach.`,
      actionable:  true,
    });
  }

  const totalProcessed = sum(records, 'processedVideos');
  const totalPublished = sum(records, 'publishedVideos');
  const rate           = publishRate(records);

  if (rate < 50) {
    insights.push({
      title:       `Publish rate below 50% — action needed`,
      description: `Only ${rate}% of processed videos were published. Review QC pipeline or channel-level blockers.`,
      actionable:  true,
    });
  } else {
    insights.push({
      title:       `Healthy publish rate at ${rate}%`,
      description: `${totalPublished.toLocaleString()} of ${totalProcessed.toLocaleString()} processed videos reached publication — above the 50% benchmark.`,
      actionable:  false,
    });
  }

  const byUser  = groupBy(records, 'user');
  const topUser = Object.entries(byUser)
    .map(([user, recs]) => ({ user, count: sum(recs, 'processedVideos') }))
    .sort((a, b) => b.count - a.count)[0];

  if (topUser) {
    insights.push({
      title:       `${topUser.user} is the most active editor`,
      description: `${topUser.user} processed ${topUser.count.toLocaleString()} videos — the highest individual contribution this period.`,
      actionable:  false,
    });
  }

  return insights;
}

// ── State management ───────────────────────────────────────────────────────────

export function createDashboardState(
  userId: string,
  filters: DashboardFilters,
  filtersExpanded: boolean,
  loadedRange: DashboardDateRange,
  selectedKpiId?: DashboardKpiId,
): DashboardStatePayload {
  return {
    userId,
    version:        1,
    filters,
    filtersExpanded,
    loadedRange,
    selectedKpiId,
    updatedAt: new Date().toISOString(),
  };
}

// ── Internal utils ─────────────────────────────────────────────────────────────

function groupBy(records: DashboardRecord[], key: string): Record<string, DashboardRecord[]> {
  const result: Record<string, DashboardRecord[]> = {};
  for (const r of records) {
    const k = String(r[key] ?? 'Unknown');
    (result[k] ??= []).push(r);
  }
  return result;
}
