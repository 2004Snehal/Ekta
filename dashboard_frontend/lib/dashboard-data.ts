import type { UniversalChartSpec } from '@/types/chart';
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

export const DEFAULT_FILTER_FIELDS: DashboardFilterField[] = [
  { key: 'client', label: 'Client', defaultVisible: true },
  { key: 'channel', label: 'Channel', defaultVisible: true },
  { key: 'user', label: 'User', defaultVisible: true },
  { key: 'language', label: 'Language', defaultVisible: true },
  { key: 'type', label: 'Type', defaultVisible: true },
  { key: 'platform', label: 'Platform', defaultVisible: true },
  { key: 'workflow', label: 'Workflow' },
  { key: 'publisher', label: 'Publisher' },
  { key: 'content_bucket', label: 'Content Bucket' },
  { key: 'status', label: 'Status' },
];

export const DEFAULT_FILTERS: DashboardFilters = {
  dateRange: 'last-90-days',
  client: 'all',
  channel: 'all',
  user: 'all',
  language: 'all',
  type: 'all',
  platform: 'all',
  extraFilters: [],
};

const DIMENSION_FIELDS = new Set(DEFAULT_FILTER_FIELDS.map((field) => field.key));

const DATE_RANGE_IN_DAYS: Record<DashboardDateRange, number> = {
  'last-7-days': 7,
  'last-30-days': 30,
  'last-90-days': 90,
  'all-time': Number.POSITIVE_INFINITY,
};

function titleCase(input: string): string {
  return input
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function toDateValue(value: string): number {
  return new Date(`${value}T00:00:00`).getTime();
}

function clampPercentChange(current: number, previous: number): number {
  if (previous === 0) {
    return current === 0 ? 0 : 100;
  }

  return Math.round(((current - previous) / previous) * 100);
}

function sumBy(records: DashboardRecord[], field: keyof DashboardRecord): number {
  return records.reduce((total, record) => total + Number(record[field] ?? 0), 0);
}

function avgBy(records: DashboardRecord[], field: keyof DashboardRecord): number {
  if (!records.length) {
    return 0;
  }

  return sumBy(records, field) / records.length;
}

function groupAndAggregate(
  records: DashboardRecord[],
  key: keyof DashboardRecord,
  metric: keyof DashboardRecord,
  outputKey: string
): Record<string, unknown>[] {
  const grouped = new Map<string, number>();

  for (const record of records) {
    const label = String(record[key] ?? 'Unknown');
    grouped.set(label, (grouped.get(label) ?? 0) + Number(record[metric] ?? 0));
  }

  return Array.from(grouped.entries())
    .map(([label, value]) => ({ [String(key)]: label, [outputKey]: value }))
    .sort((left, right) => Number(right[outputKey]) - Number(left[outputKey]));
}

function getDateBounds(records: DashboardRecord[]): { minDate: string; maxDate: string } {
  if (!records.length) {
    return { minDate: '', maxDate: '' };
  }

  return records.reduce(
    (bounds, record) => ({
      minDate: !bounds.minDate || record.date < bounds.minDate ? record.date : bounds.minDate,
      maxDate: !bounds.maxDate || record.date > bounds.maxDate ? record.date : bounds.maxDate,
    }),
    { minDate: '', maxDate: '' }
  );
}

function getRangeWindow(records: DashboardRecord[], range: DashboardDateRange): { start: number; end: number } | null {
  if (!records.length || range === 'all-time') {
    return null;
  }

  const { maxDate } = getDateBounds(records);
  const end = toDateValue(maxDate);
  const days = DATE_RANGE_IN_DAYS[range];
  const start = end - (days - 1) * 24 * 60 * 60 * 1000;

  return { start, end };
}

function applyValueFilter(record: DashboardRecord, field: string, value: string): boolean {
  return value === 'all' || String(record[field] ?? '') === value;
}

export function getRangeCoverage(range: DashboardDateRange): number {
  return DATE_RANGE_IN_DAYS[range];
}

export function createDashboardState(
  userId: string,
  filters: DashboardFilters,
  filtersExpanded: boolean,
  loadedRange: DashboardDateRange,
  selectedKpiId?: DashboardKpiId,
  stateId?: string,
): DashboardStatePayload {
  return {
    ...(stateId ? { stateId } : {}),
    userId,
    version: 1,
    filters,
    filtersExpanded,
    loadedRange,
    selectedKpiId,
    updatedAt: new Date().toISOString(),
  };
}

export function getFieldLabel(field: string, filterFields?: DashboardFilterField[]): string {
  return filterFields?.find((candidate) => candidate.key === field)?.label ?? titleCase(field);
}

export function normalizeFilterFields(records: DashboardRecord[], backendFields?: DashboardFilterField[]): DashboardFilterField[] {
  const merged = new Map<string, DashboardFilterField>();

  for (const field of DEFAULT_FILTER_FIELDS) {
    merged.set(field.key, field);
  }

  for (const field of backendFields ?? []) {
    merged.set(field.key, {
      key: field.key,
      label: field.label || titleCase(field.key),
      defaultVisible: merged.get(field.key)?.defaultVisible ?? field.defaultVisible,
    });
  }

  if (records.length) {
    for (const key of Object.keys(records[0])) {
      const sample = records[0][key];
      if (typeof sample === 'string' && key !== 'date') {
        merged.set(key, {
          key,
          label: merged.get(key)?.label ?? titleCase(key),
          defaultVisible: merged.get(key)?.defaultVisible,
        });
      }
    }
  }

  return Array.from(merged.values()).sort((left, right) => {
    const leftRank = left.defaultVisible ? 0 : 1;
    const rightRank = right.defaultVisible ? 0 : 1;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return left.label.localeCompare(right.label);
  });
}

export function createMockDashboardRecords(range: DashboardDateRange = 'last-90-days'): DashboardRecord[] {
  const days = range === 'all-time' ? 180 : Math.min(getRangeCoverage(range), 90);
  const clients = ['Frammer AI', 'Client North', 'Client South'];
  const channels = ['YouTube', 'Instagram', 'TikTok', 'LinkedIn'];
  const users = ['Sneha', 'Aarav', 'Meera', 'Vikram'];
  const languages = ['English', 'Hindi', 'Tamil', 'Marathi'];
  const types = ['Short-form', 'Long-form', 'Live', 'Explainer'];
  const platforms = ['Mobile App', 'Web Studio', 'OTT', 'Broadcast'];
  const workflows = ['Auto', 'Assisted', 'Manual'];
  const publishers = ['Internal', 'Agency'];
  const buckets = ['News', 'Education', 'Entertainment'];
  const statuses = ['Uploaded', 'Processed', 'Published'];
  const today = new Date('2026-03-14T00:00:00');
  const records: DashboardRecord[] = [];

  for (let dayOffset = days - 1; dayOffset >= 0; dayOffset -= 1) {
    const currentDate = new Date(today);
    currentDate.setDate(today.getDate() - dayOffset);
    const date = currentDate.toISOString().slice(0, 10);

    for (let slot = 0; slot < 6; slot += 1) {
      const seed = (days - dayOffset) * 17 + slot * 11;
      const channelWeight = slot % channels.length;
      const processedVideos = 24 + (seed % 14) * 3 + channelWeight * 6;
      const uploadedVideos = processedVideos + 6 + (seed % 5);
      const publishedVideos = Math.max(processedVideos - ((seed + slot) % 7), 8);
      const promotedVideos = Math.max(Math.round(publishedVideos * (0.42 + (slot % 3) * 0.08)), 4);
      const engagement = publishedVideos * (165 + (seed % 8) * 21);

      records.push({
        date,
        client: clients[seed % clients.length],
        channel: channels[(seed + slot) % channels.length],
        user: users[(seed + 2 * slot) % users.length],
        language: languages[(seed + dayOffset) % languages.length],
        type: types[(seed + 1) % types.length],
        platform: platforms[(seed + 3) % platforms.length],
        workflow: workflows[(seed + 2) % workflows.length],
        publisher: publishers[(seed + 4) % publishers.length],
        content_bucket: buckets[(seed + 5) % buckets.length],
        status: statuses[(seed + 6) % statuses.length],
        videoId: `vid-${date.replace(/-/g, '')}-${slot + 1}`,
        videoTitle: `${channels[(seed + slot) % channels.length]} Clip ${slot + 1}`,
        uploadedVideos,
        processedVideos,
        publishedVideos,
        promotedVideos,
        engagement,
        avgDurationSeconds: 45 + (seed % 7) * 15,
      });
    }
  }

  return records;
}

export function filterDashboardRecords(
  records: DashboardRecord[],
  filters: DashboardFilters,
  options?: { ignoreField?: string }
): DashboardRecord[] {
  const window = getRangeWindow(records, filters.dateRange);

  return records.filter((record) => {
    if (window) {
      const recordTime = toDateValue(record.date);
      if (recordTime < window.start || recordTime > window.end) {
        return false;
      }
    }

    if (options?.ignoreField !== 'client' && !applyValueFilter(record, 'client', filters.client)) {
      return false;
    }
    if (options?.ignoreField !== 'channel' && !applyValueFilter(record, 'channel', filters.channel)) {
      return false;
    }
    if (options?.ignoreField !== 'user' && !applyValueFilter(record, 'user', filters.user)) {
      return false;
    }
    if (options?.ignoreField !== 'language' && !applyValueFilter(record, 'language', filters.language)) {
      return false;
    }
    if (options?.ignoreField !== 'type' && !applyValueFilter(record, 'type', filters.type)) {
      return false;
    }
    if (options?.ignoreField !== 'platform' && !applyValueFilter(record, 'platform', filters.platform)) {
      return false;
    }

    for (const extraFilter of filters.extraFilters) {
      if (extraFilter.field === options?.ignoreField) {
        continue;
      }

      if (!applyValueFilter(record, extraFilter.field, extraFilter.value)) {
        return false;
      }
    }

    return true;
  });
}

export function getFilterOptions(records: DashboardRecord[], field: string): FilterOption[] {
  const grouped = new Map<string, number>();

  for (const record of records) {
    const value = String(record[field] ?? 'Unknown');
    grouped.set(value, (grouped.get(value) ?? 0) + 1);
  }

  return [
    { value: 'all', label: 'All' },
    ...Array.from(grouped.entries())
      .sort((left, right) => left[0].localeCompare(right[0]))
      .map(([value, count]) => ({ value, label: value, count })),
  ];
}

export function buildDashboardKpis(allRecords: DashboardRecord[], filteredRecords: DashboardRecord[], filters: DashboardFilters): DashboardKPI[] {
  const filteredWithoutDate = filterDashboardRecords(allRecords, { ...filters, dateRange: 'all-time' });
  const window = getRangeWindow(filteredWithoutDate, filters.dateRange === 'all-time' ? 'last-30-days' : filters.dateRange);

  let previousWindowRecords: DashboardRecord[] = [];
  if (window) {
    const duration = window.end - window.start;
    const previousStart = window.start - duration - 24 * 60 * 60 * 1000;
    const previousEnd = window.start - 24 * 60 * 60 * 1000;
    previousWindowRecords = filteredWithoutDate.filter((record) => {
      const value = toDateValue(record.date);
      return value >= previousStart && value <= previousEnd;
    });
  }

  const timeframe = filters.dateRange === 'all-time' ? 'vs previous 30 days' : 'vs previous period';

  const uploaded = sumBy(filteredRecords, 'uploadedVideos');
  const processed = sumBy(filteredRecords, 'processedVideos');
  const published = sumBy(filteredRecords, 'publishedVideos');
  const publishRate = uploaded === 0 ? 0 : Math.round((published / uploaded) * 100);

  const previousUploaded = sumBy(previousWindowRecords, 'uploadedVideos');
  const previousProcessed = sumBy(previousWindowRecords, 'processedVideos');
  const previousPublished = sumBy(previousWindowRecords, 'publishedVideos');
  const previousPublishRate = previousUploaded === 0 ? 0 : Math.round((previousPublished / previousUploaded) * 100);

  const averageDuration = Math.round(avgBy(filteredRecords, 'avgDurationSeconds'));
  const previousAverageDuration = Math.round(avgBy(previousWindowRecords, 'avgDurationSeconds'));

  return [
    {
      id: 'uploaded_videos',
      title: 'Uploaded Videos',
      value: uploaded.toLocaleString(),
      change: clampPercentChange(uploaded, previousUploaded),
      timeframe,
      iconKey: 'video',
    },
    {
      id: 'processed_videos',
      title: 'Processed Videos',
      value: processed.toLocaleString(),
      change: clampPercentChange(processed, previousProcessed),
      timeframe,
      iconKey: 'zap',
    },
    {
      id: 'published_videos',
      title: 'Published Videos',
      value: published.toLocaleString(),
      change: clampPercentChange(published, previousPublished),
      timeframe,
      iconKey: 'trending',
    },
    {
      id: 'publish_rate',
      title: 'Publish Rate',
      value: `${publishRate}%`,
      change: clampPercentChange(publishRate, previousPublishRate),
      timeframe,
      iconKey: 'bar',
    },
    {
      id: 'average_duration',
      title: 'Average Duration',
      value: `${averageDuration}s`,
      change: clampPercentChange(averageDuration, previousAverageDuration),
      timeframe,
      iconKey: 'video',
    },
  ];
}

export function buildDashboardCharts(records: DashboardRecord[]): UniversalChartSpec[] {
  const trendByDate = records
    .reduce<Map<string, { processed: number; uploaded: number; published: number }>>((grouped, record) => {
      const current = grouped.get(record.date) ?? { processed: 0, uploaded: 0, published: 0 };
      current.processed += Number(record.processedVideos ?? 0);
      current.uploaded += Number(record.uploadedVideos ?? 0);
      current.published += Number(record.publishedVideos ?? 0);
      grouped.set(record.date, current);
      return grouped;
    }, new Map())
    .entries();

  const trendData = Array.from(trendByDate)
    .map(([date, totals]) => ({ date, processed: totals.processed, uploaded: totals.uploaded, published: totals.published }))
    .sort((left, right) => left.date.localeCompare(right.date));

  const channelData = records
    .reduce<Map<string, { videos: number; engagement: number }>>((grouped, record) => {
      const key = String(record.channel ?? 'Unknown');
      const current = grouped.get(key) ?? { videos: 0, engagement: 0 };
      current.videos += Number(record.publishedVideos ?? 0);
      current.engagement += Number(record.engagement ?? 0);
      grouped.set(key, current);
      return grouped;
    }, new Map())
    .entries();

  const channelChartData = Array.from(channelData)
    .map(([channel, totals]) => ({ channel, videos: totals.videos, engagement: totals.engagement }))
    .sort((left, right) => right.videos - left.videos);

  const languageData = groupAndAggregate(records, 'language', 'publishedVideos', 'videos');
  const stackedPlatformData = records.map((record) => ({
    platform: record.platform,
    type: record.type,
    videos: record.publishedVideos,
  }));

  return [
    {
      chart_type: 'line',
      title: 'Processing Trend',
      description: 'Uploaded, processed, and published video volume across the active time window.',
      axes: {
        x: { field: 'date', label: 'Date' },
        y: { field: 'processed', label: 'Processed Videos' },
      },
      data: trendData,
      x: 'date',
      y: 'processed',
      yAxis: 'processed',
    },
    {
      chart_type: 'bar',
      title: 'Channel Performance',
      description: 'Published videos aggregated by channel after local filter application.',
      axes: {
        x: { field: 'channel', label: 'Channel' },
        y: { field: 'videos', label: 'Published Videos' },
      },
      data: channelChartData,
      x: 'channel',
      y: 'videos',
      yAxis: 'videos',
    },
    {
      chart_type: 'pie',
      title: 'Language Distribution',
      description: 'Published volume share by content language in the current result set.',
      category: 'language',
      value: 'videos',
      data: languageData,
      x: 'language',
      y: 'videos',
      yAxis: 'videos',
    },
    {
      chart_type: 'stacked_bar',
      title: 'Platform x Type Mix',
      description: 'Type mix per platform, rendered locally from the loaded dataset.',
      axes: {
        x: { field: 'platform', label: 'Platform' },
        y: { field: 'videos', label: 'Published Videos' },
      },
      group_by: 'type',
      data: stackedPlatformData,
      x: 'platform',
      y: 'videos',
      yAxis: 'videos',
    },
  ];
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs.toString().padStart(2, '0')}s`;
}

function buildMetricTrendData(records: DashboardRecord[], metric: keyof DashboardRecord, outputKey: string): Record<string, unknown>[] {
  return Array.from(
    records
      .reduce<Map<string, number>>((grouped, record) => {
        grouped.set(record.date, (grouped.get(record.date) ?? 0) + Number(record[metric] ?? 0));
        return grouped;
      }, new Map())
      .entries()
  )
    .map(([date, value]) => ({ date, [outputKey]: value }))
    .sort((left, right) => String(left.date).localeCompare(String(right.date)));
}

function buildTopRecordsTable(records: DashboardRecord[], metric: keyof DashboardRecord, metricLabel: string): Record<string, unknown>[] {
  return [...records]
    .sort((left, right) => Number(right[metric] ?? 0) - Number(left[metric] ?? 0))
    .slice(0, 10)
    .map((record) => ({
      date: record.date,
      video: record.videoTitle ?? record.videoId ?? 'Unknown',
      channel: record.channel,
      user: record.user,
      language: record.language,
      value: Number(record[metric] ?? 0),
      metric: metricLabel,
    }));
}

function buildPublishRateByChannel(records: DashboardRecord[]): Record<string, unknown>[] {
  return Array.from(
    records
      .reduce<Map<string, { uploaded: number; published: number }>>((grouped, record) => {
        const key = String(record.channel ?? 'Unknown');
        const current = grouped.get(key) ?? { uploaded: 0, published: 0 };
        current.uploaded += Number(record.uploadedVideos ?? 0);
        current.published += Number(record.publishedVideos ?? 0);
        grouped.set(key, current);
        return grouped;
      }, new Map())
      .entries()
  )
    .map(([channel, totals]) => ({
      channel,
      uploaded: totals.uploaded,
      published: totals.published,
      publish_rate: totals.uploaded === 0 ? 0 : Math.round((totals.published / totals.uploaded) * 100),
    }))
    .sort((left, right) => Number(right.publish_rate) - Number(left.publish_rate))
    .slice(0, 10);
}

export function buildDashboardKpiDetails(
  allRecords: DashboardRecord[],
  filteredRecords: DashboardRecord[],
  filters: DashboardFilters
): Record<DashboardKpiId, DashboardKpiDetail> {
  const rangeLabel = getDisplayRangeLabel(filters.dateRange);
  const uploadedTotal = sumBy(filteredRecords, 'uploadedVideos');
  const processedTotal = sumBy(filteredRecords, 'processedVideos');
  const publishedTotal = sumBy(filteredRecords, 'publishedVideos');
  const averageDuration = Math.round(avgBy(filteredRecords, 'avgDurationSeconds'));
  const publishRate = uploadedTotal === 0 ? 0 : Math.round((publishedTotal / uploadedTotal) * 100);

  const baseSubtitle = `Current selection: ${rangeLabel}. Rows: ${filteredRecords.length.toLocaleString()} from a cached ${allRecords.length.toLocaleString()} record set.`;

  const details: Record<DashboardKpiId, DashboardKpiDetail> = {
    uploaded_videos: {
      kpiId: 'uploaded_videos',
      title: 'Uploaded Videos Breakdown',
      subtitle: baseSubtitle,
      description: 'Shows how uploaded volume is distributed by date and channel after applying client-side filters.',
      stats: [
        { label: 'Uploaded Total', value: uploadedTotal.toLocaleString() },
        { label: 'Avg/Day', value: Math.round(uploadedTotal / Math.max(1, filteredRecords.length)).toLocaleString() },
      ],
      charts: [
        {
          chart_type: 'line',
          title: 'Uploaded Trend',
          axes: { x: { field: 'date', label: 'Date' }, y: { field: 'uploaded', label: 'Uploaded' } },
          data: buildMetricTrendData(filteredRecords, 'uploadedVideos', 'uploaded'),
        },
        {
          chart_type: 'bar',
          title: 'Top Channels by Uploads',
          axes: { x: { field: 'channel', label: 'Channel' }, y: { field: 'uploaded', label: 'Uploaded' } },
          data: groupAndAggregate(filteredRecords, 'channel', 'uploadedVideos', 'uploaded').slice(0, 10),
        },
      ],
      tableTitle: 'Top 10 Upload-heavy Records',
      table: buildTopRecordsTable(filteredRecords, 'uploadedVideos', 'Uploaded Videos'),
    },
    processed_videos: {
      kpiId: 'processed_videos',
      title: 'Processed Videos Breakdown',
      subtitle: baseSubtitle,
      description: 'Shows processed volume progression and the strongest channels in the active filtered slice.',
      stats: [
        { label: 'Processed Total', value: processedTotal.toLocaleString() },
        { label: 'Processing Efficiency', value: `${uploadedTotal === 0 ? 0 : Math.round((processedTotal / uploadedTotal) * 100)}%` },
      ],
      charts: [
        {
          chart_type: 'line',
          title: 'Processed Trend',
          axes: { x: { field: 'date', label: 'Date' }, y: { field: 'processed', label: 'Processed' } },
          data: buildMetricTrendData(filteredRecords, 'processedVideos', 'processed'),
        },
        {
          chart_type: 'bar',
          title: 'Top Channels by Processed Volume',
          axes: { x: { field: 'channel', label: 'Channel' }, y: { field: 'processed', label: 'Processed' } },
          data: groupAndAggregate(filteredRecords, 'channel', 'processedVideos', 'processed').slice(0, 10),
        },
      ],
      tableTitle: 'Top 10 Processed-heavy Records',
      table: buildTopRecordsTable(filteredRecords, 'processedVideos', 'Processed Videos'),
    },
    published_videos: {
      kpiId: 'published_videos',
      title: 'Published Videos Breakdown',
      subtitle: baseSubtitle,
      description: 'Shows publishing output trend and where publishing concentration is highest.',
      stats: [
        { label: 'Published Total', value: publishedTotal.toLocaleString() },
        { label: 'Publish Share', value: `${uploadedTotal === 0 ? 0 : Math.round((publishedTotal / uploadedTotal) * 100)}% of uploads` },
      ],
      charts: [
        {
          chart_type: 'line',
          title: 'Published Trend',
          axes: { x: { field: 'date', label: 'Date' }, y: { field: 'published', label: 'Published' } },
          data: buildMetricTrendData(filteredRecords, 'publishedVideos', 'published'),
        },
        {
          chart_type: 'pie',
          title: 'Published Mix by Language',
          category: 'language',
          value: 'published',
          data: groupAndAggregate(filteredRecords, 'language', 'publishedVideos', 'published').slice(0, 10),
        },
      ],
      tableTitle: 'Top 10 Published-heavy Records',
      table: buildTopRecordsTable(filteredRecords, 'publishedVideos', 'Published Videos'),
    },
    publish_rate: {
      kpiId: 'publish_rate',
      title: 'Publish Rate Diagnostics',
      subtitle: baseSubtitle,
      description: 'Compares publish rate by channel and daily movement to explain changes in the headline publish rate KPI.',
      stats: [
        { label: 'Publish Rate', value: `${publishRate}%` },
        { label: 'Uploaded', value: uploadedTotal.toLocaleString() },
        { label: 'Published', value: publishedTotal.toLocaleString() },
      ],
      charts: [
        {
          chart_type: 'bar',
          title: 'Publish Rate by Channel',
          axes: { x: { field: 'channel', label: 'Channel' }, y: { field: 'publish_rate', label: 'Publish Rate %' } },
          data: buildPublishRateByChannel(filteredRecords),
        },
        {
          chart_type: 'line',
          title: 'Daily Publish Rate',
          axes: { x: { field: 'date', label: 'Date' }, y: { field: 'publish_rate', label: 'Publish Rate %' } },
          data: Array.from(
            filteredRecords
              .reduce<Map<string, { uploaded: number; published: number }>>((grouped, record) => {
                const current = grouped.get(record.date) ?? { uploaded: 0, published: 0 };
                current.uploaded += Number(record.uploadedVideos ?? 0);
                current.published += Number(record.publishedVideos ?? 0);
                grouped.set(record.date, current);
                return grouped;
              }, new Map())
              .entries()
          )
            .map(([date, totals]) => ({
              date,
              publish_rate: totals.uploaded === 0 ? 0 : Math.round((totals.published / totals.uploaded) * 100),
            }))
            .sort((left, right) => String(left.date).localeCompare(String(right.date))),
        },
      ],
      tableTitle: 'Top Channels by Publish Rate',
      table: buildPublishRateByChannel(filteredRecords),
    },
    average_duration: {
      kpiId: 'average_duration',
      title: 'Average Duration Detail',
      subtitle: baseSubtitle,
      description: 'Expands the average duration KPI into longest videos, language mix, and per-channel duration distribution.',
      stats: [
        { label: 'Average Duration', value: formatDuration(averageDuration) },
        {
          label: 'Max Duration',
          value: formatDuration(Math.max(...filteredRecords.map((record) => Number(record.avgDurationSeconds ?? 0)), 0)),
        },
      ],
      charts: [
        {
          chart_type: 'bar',
          title: 'Top 10 Longest Videos',
          axes: { x: { field: 'video', label: 'Video' }, y: { field: 'duration', label: 'Duration (s)' } },
          data: [...filteredRecords]
            .sort((left, right) => Number(right.avgDurationSeconds ?? 0) - Number(left.avgDurationSeconds ?? 0))
            .slice(0, 10)
            .map((record) => ({ video: record.videoTitle ?? record.videoId ?? 'Unknown', duration: record.avgDurationSeconds })),
        },
        {
          chart_type: 'bar',
          title: 'Average Duration by Channel',
          axes: { x: { field: 'channel', label: 'Channel' }, y: { field: 'avg_duration', label: 'Avg Duration (s)' } },
          data: Array.from(
            filteredRecords
              .reduce<Map<string, { total: number; count: number }>>((grouped, record) => {
                const key = String(record.channel ?? 'Unknown');
                const current = grouped.get(key) ?? { total: 0, count: 0 };
                current.total += Number(record.avgDurationSeconds ?? 0);
                current.count += 1;
                grouped.set(key, current);
                return grouped;
              }, new Map())
              .entries()
          )
            .map(([channel, stats]) => ({ channel, avg_duration: Math.round(stats.total / Math.max(1, stats.count)) }))
            .sort((left, right) => Number(right.avg_duration) - Number(left.avg_duration))
            .slice(0, 10),
        },
      ],
      tableTitle: 'Top 10 Longest Videos',
      table: [...filteredRecords]
        .sort((left, right) => Number(right.avgDurationSeconds ?? 0) - Number(left.avgDurationSeconds ?? 0))
        .slice(0, 10)
        .map((record) => ({
          date: record.date,
          video: record.videoTitle ?? record.videoId ?? 'Unknown',
          channel: record.channel,
          user: record.user,
          language: record.language,
          duration_seconds: record.avgDurationSeconds,
          duration_readable: formatDuration(Number(record.avgDurationSeconds ?? 0)),
        })),
    },
  };

  return details;
}

export function buildDashboardInsights(records: DashboardRecord[], filterFields: DashboardFilterField[]): DashboardInsight[] {
  if (!records.length) {
    return [
      {
        title: 'No matching records',
        description: 'The selected filter combination removed every row. Reset one or more filters to restore dashboard output.',
        actionable: true,
      },
    ];
  }

  const topChannel = groupAndAggregate(records, 'channel', 'publishedVideos', 'videos')[0];
  const topLanguage = groupAndAggregate(records, 'language', 'publishedVideos', 'videos')[0];
  const topUser = groupAndAggregate(records, 'user', 'publishedVideos', 'videos')[0];
  const averageDuration = Math.round(avgBy(records, 'avgDurationSeconds'));

  return [
    {
      title: 'Top Channel',
      description: `${String(topChannel?.channel ?? 'Unknown')} leads the current view with ${Number(topChannel?.videos ?? 0).toLocaleString()} published videos.`,
      actionable: true,
    },
    {
      title: 'Language Opportunity',
      description: `${String(topLanguage?.language ?? 'Unknown')} is the leading language in this slice, making it the best candidate for deeper segmentation with an added filter.`,
      actionable: true,
    },
    {
      title: 'User Contribution',
      description: `${String(topUser?.user ?? 'Unknown')} is driving the highest published output in the current filtered dataset.`,
      actionable: false,
    },
    {
      title: 'Average Duration',
      description: `Videos in the current view average ${averageDuration} seconds. Add ${getFieldLabel('workflow', filterFields)} or ${getFieldLabel('publisher', filterFields)} as extra filters to inspect operational differences.`,
      actionable: true,
    },
  ];
}

export function getDisplayRangeLabel(range: DashboardDateRange): string {
  switch (range) {
    case 'last-7-days':
      return 'Last 7 days';
    case 'last-30-days':
      return 'Last 30 days';
    case 'last-90-days':
      return 'Last 90 days';
    default:
      return 'All time';
  }
}

export function supportsRange(loadedRange: DashboardDateRange | null, requestedRange: DashboardDateRange): boolean {
  if (!loadedRange) {
    return false;
  }

  return getRangeCoverage(loadedRange) >= getRangeCoverage(requestedRange);
}

export function getFilterFieldCandidates(filterFields: DashboardFilterField[]): DashboardFilterField[] {
  return filterFields.filter((field) => field.key !== 'date' && DIMENSION_FIELDS.has(field.key));
}