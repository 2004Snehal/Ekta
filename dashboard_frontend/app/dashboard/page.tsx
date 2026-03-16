'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { SparkKPI } from '@/components/SparkKPI';
import { KPIDetailModal } from '@/components/KPIDetailModal';
import { ChartRenderer } from '@/components/ChartRenderer';
import { Filters } from '@/components/Filters';
import { InsightPanel } from '@/components/InsightPanel';
import { InsightBanner } from '@/components/InsightBanner';
import { RecommendationsPanel } from '@/components/RecommendationsPanel';
import {
  buildDashboardCharts,
  buildDashboardInsights,
  buildDashboardKpiDetails,
  buildDashboardKpis,
  createDashboardState,
  createMockDashboardRecords,
  DEFAULT_FILTERS,
  getDisplayRangeLabel,
  getFilterOptions,
  normalizeFilterFields,
  filterDashboardRecords,
  supportsRange,
} from '@/lib/dashboard-data';
import type {
  DashboardDatasetResponse,
  DashboardDateRange,
  DashboardFilters,
  DashboardKpiId,
  DashboardRecord,
  DashboardStatePayload,
} from '@/types/dashboard';

const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
const USER_ID    = process.env.NEXT_PUBLIC_DASHBOARD_USER_ID ?? 'demo-user';
const STORAGE_KEY = `dashboard-state:${USER_ID}`;

type ShareStatus = 'idle' | 'saving' | 'copied';

function getRequiredDataRange(range: DashboardDateRange): DashboardDateRange {
  return range === 'all-time' ? 'all-time' : 'last-90-days';
}

/** Build a simple 12-point sparkline from filtered records bucketed by the last N periods */
function buildSparkline(records: DashboardRecord[], key: 'uploadedVideos' | 'processedVideos' | 'publishedVideos', buckets = 12): number[] {
  if (records.length === 0) return [];
  const sorted = [...records].sort((a, b) => a.date.localeCompare(b.date));
  const chunkSize = Math.ceil(sorted.length / buckets);
  const result: number[] = [];
  for (let i = 0; i < sorted.length; i += chunkSize) {
    const chunk = sorted.slice(i, i + chunkSize);
    result.push(chunk.reduce((s, r) => s + ((r[key] as number) ?? 0), 0));
  }
  return result;
}

export default function Dashboard() {
  const apiBaseUrl = API;
  const [filters, setFilters]         = useState<DashboardFilters>(DEFAULT_FILTERS);
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const [allRecords, setAllRecords]   = useState<DashboardRecord[]>([]);
  const [loadedRange, setLoadedRange] = useState<DashboardDateRange | null>(null);
  const [filterFields, setFilterFields] = useState(() => normalizeFilterFields(createMockDashboardRecords('last-90-days')));
  const [dataSource, setDataSource]   = useState<'live' | 'mock'>('mock');
  const [stateSource, setStateSource] = useState<'api' | 'local'>('local');
  const [isLoading, setIsLoading]     = useState(true);
  const [selectedKpiId, setSelectedKpiId] = useState<DashboardKpiId | null>(null);
  const [stateReady, setStateReady]   = useState(false);
  const [shareStatus, setShareStatus] = useState<ShareStatus>('idle');
  const lastSavedState = useRef('');

  // New: narrator insights for InsightBanner
  const [narratorInsights, setNarratorInsights] = useState<{ title: string; severity: 'high' | 'medium' | 'low'; body?: string }[]>([]);

  // New: period comparison data for delta values on SparkKPIs
  const [periodDeltas, setPeriodDeltas] = useState<Record<string, number>>({});

  /* ── Fetch narrator insights ─────────────────────────────── */
  useEffect(() => {
    if (!apiBaseUrl) return;
    fetch(`${apiBaseUrl}/narrator/insights?client_id=1`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        const raw = Array.isArray(data) ? data : (data.insights ?? []);
        setNarratorInsights(raw.slice(0, 3).map((ins: any) => ({
          title: ins.title ?? ins.headline ?? String(ins),
          severity: ins.severity ?? ins.priority ?? 'medium',
          body: ins.body ?? ins.description ?? undefined,
        })));
      })
      .catch(() => {});
  }, [apiBaseUrl]);

  /* ── Fetch period deltas for SparkKPI ────────────────────── */
  useEffect(() => {
    if (!apiBaseUrl) return;
    fetch(`${apiBaseUrl}/analytics/period-compare?client_id=1&period=month`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data?.deltas) return;
        setPeriodDeltas({
          uploaded_videos:  data.deltas.count_pct ?? 0,
          processed_videos: data.deltas.count_pct ?? 0,
          published_videos: data.deltas.published_pct ?? 0,
          publish_rate:     data.deltas.publish_rate_delta ?? 0,
          average_duration: data.deltas.duration_pct ?? 0,
        });
      })
      .catch(() => {});
  }, [apiBaseUrl]);

  /* ── Share ──────────────────────────────────────────── */
  async function handleShare() {
    if (!apiBaseUrl || shareStatus !== 'idle') return;
    setShareStatus('saving');
    try {
      const payload = createDashboardState(USER_ID, filters, filtersExpanded, loadedRange ?? 'last-90-days', selectedKpiId ?? undefined);
      const res = await fetch(`${apiBaseUrl}/dashboard/state`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('save failed');
      const { state_id } = await res.json() as { state_id: string };
      await navigator.clipboard.writeText(`${window.location.origin}/dashboard?state=${state_id}`);
      setShareStatus('copied');
      setTimeout(() => setShareStatus('idle'), 2500);
    } catch { setShareStatus('idle'); }
  }

  /* ── State hydration ────────────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    const hydrate = async () => {
      let restored: DashboardStatePayload | null = null;

      if (typeof window !== 'undefined' && apiBaseUrl) {
        const stateId = new URLSearchParams(window.location.search).get('state');
        if (stateId) {
          try {
            const res = await fetch(`${apiBaseUrl}/dashboard/state/${stateId}`, { cache: 'no-store' });
            if (res.ok) { restored = await res.json() as DashboardStatePayload; if (!cancelled) setStateSource('api'); }
          } catch { /* fallthrough */ }
        }
      }

      if (!restored && typeof window !== 'undefined') {
        const local = window.localStorage.getItem(STORAGE_KEY);
        if (local) {
          try { restored = JSON.parse(local) as DashboardStatePayload; if (!cancelled) setStateSource('local'); }
          catch { window.localStorage.removeItem(STORAGE_KEY); }
        }
      }

      if (!restored && apiBaseUrl) {
        try {
          const res = await fetch(`${apiBaseUrl}/dashboard/state?user_id=${encodeURIComponent(USER_ID)}`, { cache: 'no-store' });
          if (res.ok) {
            const p = await res.json() as DashboardStatePayload | { state?: DashboardStatePayload };
            restored = 'state' in p && p.state ? p.state : (p as DashboardStatePayload);
            if (!cancelled) setStateSource('api');
          }
        } catch { /* no remote state */ }
      }

      if (!cancelled && restored) {
        const restoredFilters = {
          ...DEFAULT_FILTERS,
          ...restored.filters,
          extraFilters: (restored.filters?.extraFilters ?? []).filter((ef) => ef.value && ef.value !== 'all'),
        };
        setFilters(restoredFilters);
        setFiltersExpanded(restored.filtersExpanded);
        setSelectedKpiId(restored.selectedKpiId ?? null);
      }
      if (!cancelled) setStateReady(true);
    };
    void hydrate();
    return () => { cancelled = true; };
  }, [apiBaseUrl]);

  /* ── Data load ──────────────────────────────────────── */
  useEffect(() => {
    if (!stateReady) return;
    const reqRange = getRequiredDataRange(filters.dateRange);
    if (supportsRange(loadedRange, reqRange) && allRecords.length > 0) return;

    let cancelled = false;
    const load = async () => {
      setIsLoading(true);
      if (apiBaseUrl) {
        try {
          const res = await fetch(`${apiBaseUrl}/dashboard?user_id=${encodeURIComponent(USER_ID)}&date_range=${encodeURIComponent(reqRange)}`, { cache: 'no-store' });
          if (!res.ok) throw new Error('failed');
          const payload = await res.json() as DashboardDatasetResponse;
          if (!cancelled) {
            setAllRecords(payload.records ?? []);
            setFilterFields(normalizeFilterFields(payload.records ?? [], payload.filter_fields));
            setLoadedRange(payload.requested_range ?? reqRange);
            setDataSource('live');
            setIsLoading(false);
          }
          return;
        } catch { if (!cancelled) setDataSource('mock'); }
      }
      const mock = createMockDashboardRecords(reqRange);
      if (!cancelled) { setAllRecords(mock); setFilterFields(normalizeFilterFields(mock)); setLoadedRange(reqRange); setIsLoading(false); }
    };
    void load();
    return () => { cancelled = true; };
  }, [allRecords.length, apiBaseUrl, filters.dateRange, loadedRange, stateReady]);

  /* ── State persistence ──────────────────────────────── */
  useEffect(() => {
    if (!stateReady || !loadedRange) return;
    const next = createDashboardState(USER_ID, filters, filtersExpanded, loadedRange, selectedKpiId ?? undefined);
    const ser  = JSON.stringify(next);
    if (ser === lastSavedState.current) return;
    lastSavedState.current = ser;
    if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, ser);
    if (apiBaseUrl) void fetch(`${apiBaseUrl}/dashboard/state`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: ser }).catch(() => undefined);
  }, [apiBaseUrl, filters, filtersExpanded, loadedRange, selectedKpiId, stateReady]);

  /* ── Derived data ───────────────────────────────────── */
  const filteredRecords = useMemo(() => filterDashboardRecords(allRecords, filters), [allRecords, filters]);
  const filterOptions   = useMemo(() =>
    Object.fromEntries(filterFields.map((f) => [f.key, getFilterOptions(filterDashboardRecords(allRecords, filters, { ignoreField: f.key }), f.key)])),
    [allRecords, filterFields, filters]);
  const kpis            = useMemo(() => buildDashboardKpis(allRecords, filteredRecords, filters), [allRecords, filteredRecords, filters]);
  const kpiDetails      = useMemo(() => buildDashboardKpiDetails(allRecords, filteredRecords, filters), [allRecords, filteredRecords, filters]);
  const charts          = useMemo(() => buildDashboardCharts(filteredRecords), [filteredRecords]);
  const insights        = useMemo(() => buildDashboardInsights(filteredRecords, filterFields), [filteredRecords, filterFields]);
  const selectedKpiDetail = selectedKpiId ? kpiDetails[selectedKpiId] ?? null : null;
  const dataReady       = !isLoading && filteredRecords.length > 0;

  // Build sparklines per KPI from filtered records
  const sparklines = useMemo(() => ({
    uploaded_videos:  buildSparkline(filteredRecords, 'uploadedVideos'),
    processed_videos: buildSparkline(filteredRecords, 'processedVideos'),
    published_videos: buildSparkline(filteredRecords, 'publishedVideos'),
    publish_rate:     buildSparkline(filteredRecords, 'publishedVideos'),
    average_duration: [],
  }), [filteredRecords]);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--void)' }}>

      {/* ── Filter strip (sticky) ──────────────────────── */}
      <div className="sticky top-11 z-40" style={{ background: 'var(--void)' }}>
        <Filters
          filters={filters}
          filterFields={filterFields}
          filterOptions={filterOptions}
          isExpanded={filtersExpanded}
          onExpandedChange={setFiltersExpanded}
          onApply={setFilters}
        />
      </div>

      {/* ── KPI strip ─────────────────────────────────── */}
      <div
        className="flex"
        style={{ borderBottom: '1px solid var(--wire)' }}
      >
        {isLoading ? (
          <div className="flex-1 px-6 py-8">
            <div className="scan-loader" />
          </div>
        ) : (
          kpis.map((kpi, i) => (
            <div key={kpi.id} className="flex" style={{ flex: 1 }}>
              {i > 0 && <div className="wire-v" />}
              <SparkKPI
                title={kpi.title}
                value={kpi.value}
                delta={periodDeltas[kpi.id] ?? kpi.change ?? null}
                sparkData={sparklines[kpi.id] ?? []}
                active={selectedKpiId === kpi.id}
                onClick={() => setSelectedKpiId(kpi.id === selectedKpiId ? null : kpi.id)}
              />
            </div>
          ))
        )}
      </div>

      {/* ── Status bar ────────────────────────────────── */}
      <div
        className="flex items-center gap-4 px-6 py-1.5 flex-wrap"
        style={{ borderBottom: '1px solid var(--wire)' }}
      >
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
          USER:{USER_ID}
        </span>
        <span style={{ color: 'var(--wire-mid)', fontSize: '0.55rem' }}>·</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: dataSource === 'live' ? 'var(--ok)' : 'var(--on-low)' }}>
          {dataSource === 'live' ? 'LIVE' : 'MOCK'}
        </span>
        <span style={{ color: 'var(--wire-mid)', fontSize: '0.55rem' }}>·</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
          {filteredRecords.length.toLocaleString()} ROWS
        </span>
        <span style={{ color: 'var(--wire-mid)', fontSize: '0.55rem' }}>·</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
          {getDisplayRangeLabel(filters.dateRange).toUpperCase()}
        </span>

        <div className="flex-1" />

        {apiBaseUrl && (
          <span
            className="action-text"
            onClick={() => void handleShare()}
            style={{ color: shareStatus === 'copied' ? 'var(--ok)' : shareStatus === 'saving' ? 'var(--warn)' : undefined }}
          >
            {shareStatus === 'copied' ? 'COPIED ✓' : shareStatus === 'saving' ? 'SAVING…' : 'SHARE ↗'}
          </span>
        )}
      </div>

      {/* ── Main content ──────────────────────────────── */}
      {!isLoading && filteredRecords.length === 0 && (
        <div className="px-6 py-12">
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--on-low)' }}>
            — no rows match active filters. clear filters to repopulate.
          </p>
        </div>
      )}

      {!isLoading && filteredRecords.length > 0 && (
        <div className="flex" style={{ minHeight: '600px' }}>

          {/* Left: charts (65%) */}
          <div style={{ flex: '0 0 65%', borderRight: '1px solid var(--wire)', padding: '24px 28px' }}>

            {/* Section: Trends */}
            <div style={{ marginBottom: '32px' }}>
              {charts.slice(0, 2).map((chart, i) => (
                <div key={i} style={{ marginBottom: i === 0 ? '32px' : '0' }}>
                  <ChartRenderer chart={chart} />
                </div>
              ))}
            </div>

            <div className="wire-h" style={{ marginBottom: '32px' }} />

            {/* Section: Distribution */}
            <div
              className="grid"
              style={{ gridTemplateColumns: '1fr 1fr', gap: '28px' }}
            >
              {charts.slice(2, 4).map((chart, i) => (
                <ChartRenderer key={i + 2} chart={chart} />
              ))}
            </div>

            {insights.length > 0 && (
              <>
                <div className="wire-h" style={{ margin: '32px 0 24px' }} />
                <div
                  className="grid"
                  style={{ gridTemplateColumns: '1fr 1fr', gap: '28px' }}
                >
                  <InsightPanel insights={insights.slice(0, 2)} label="Insights" />
                  {insights.length > 2 && (
                    <InsightPanel insights={insights.slice(2, 4)} label="More Insights" />
                  )}
                </div>
              </>
            )}
          </div>

          {/* Right: InsightBanner + recommendations (35%) */}
          <div style={{ flex: '0 0 35%', padding: '24px 24px', position: 'sticky', top: '88px', alignSelf: 'flex-start', maxHeight: 'calc(100vh - 88px)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

            {/* InsightBanner at top of right column */}
            {narratorInsights.length > 0 && (
              <div style={{ marginBottom: '16px', flexShrink: 0 }}>
                <InsightBanner insights={narratorInsights} />
              </div>
            )}

            <RecommendationsPanel
              apiBaseUrl={apiBaseUrl}
              filters={filters}
              kpis={kpis}
              selectedKpiId={selectedKpiId}
              dataReady={dataReady}
            />
          </div>
        </div>
      )}

      {/* ── KPI detail modal ──────────────────────────── */}
      <KPIDetailModal
        open={Boolean(selectedKpiId && selectedKpiDetail)}
        detail={selectedKpiDetail}
        onOpenChange={(open) => { if (!open) setSelectedKpiId(null); }}
      />
    </div>
  );
}
