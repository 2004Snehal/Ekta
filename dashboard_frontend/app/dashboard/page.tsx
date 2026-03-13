'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { KPICard } from '@/components/KPICard';
import { KPIDetailModal } from '@/components/KPIDetailModal';
import { ChartRenderer } from '@/components/ChartRenderer';
import { Filters } from '@/components/Filters';
import { InsightPanel } from '@/components/InsightPanel';
import { BarChart3, Video, Zap, TrendingUp, Share2, Check, Loader2 } from 'lucide-react';
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

const USER_ID = process.env.NEXT_PUBLIC_DASHBOARD_USER_ID ?? 'demo-user';
const STORAGE_KEY = `dashboard-state:${USER_ID}`;

type ShareStatus = 'idle' | 'saving' | 'copied';

function getRequiredDataRange(range: DashboardDateRange): DashboardDateRange {
  return range === 'all-time' ? 'all-time' : 'last-90-days';
}

function resolveDashboardIcon(iconKey: string) {
  switch (iconKey) {
    case 'video':
      return <Video className="w-5 h-5" />;
    case 'zap':
      return <Zap className="w-5 h-5" />;
    case 'trending':
      return <TrendingUp className="w-5 h-5" />;
    default:
      return <BarChart3 className="w-5 h-5" />;
  }
}

export default function Dashboard() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS);
  const [filtersExpanded, setFiltersExpanded] = useState(true);
  const [allRecords, setAllRecords] = useState<DashboardRecord[]>([]);
  const [loadedRange, setLoadedRange] = useState<DashboardDateRange | null>(null);
  const [filterFields, setFilterFields] = useState(() => normalizeFilterFields(createMockDashboardRecords('last-90-days')));
  const [dataSource, setDataSource] = useState<'live' | 'mock'>('mock');
  const [stateSource, setStateSource] = useState<'api' | 'local'>('local');
  const [isLoading, setIsLoading] = useState(true);
  const [selectedKpiId, setSelectedKpiId] = useState<DashboardKpiId | null>(null);
  const [stateReady, setStateReady] = useState(false);
  const [shareStatus, setShareStatus] = useState<ShareStatus>('idle');
  const lastSavedState = useRef('');

  async function handleShare() {
    if (!apiBaseUrl || shareStatus !== 'idle') return;
    setShareStatus('saving');
    try {
      const payload = createDashboardState(USER_ID, filters, filtersExpanded, loadedRange ?? 'last-90-days', selectedKpiId ?? undefined);
      const res = await fetch(`${apiBaseUrl}/dashboard/state`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('save failed');
      const { state_id } = await res.json() as { state_id: string };
      const url = `${window.location.origin}/dashboard?state=${state_id}`;
      await navigator.clipboard.writeText(url);
      setShareStatus('copied');
      setTimeout(() => setShareStatus('idle'), 2500);
    } catch {
      setShareStatus('idle');
    }
  }

  useEffect(() => {
    let isCancelled = false;

    const hydrateState = async () => {
      let restoredState: DashboardStatePayload | null = null;

      // 1. Check URL for a shared state_id (?state=<uuid>)
      if (typeof window !== 'undefined' && apiBaseUrl) {
        const urlParams = new URLSearchParams(window.location.search);
        const sharedStateId = urlParams.get('state');
        if (sharedStateId) {
          try {
            const res = await fetch(`${apiBaseUrl}/dashboard/state/${sharedStateId}`, { cache: 'no-store' });
            if (res.ok) {
              const payload = await res.json() as DashboardStatePayload;
              restoredState = payload;
              if (!isCancelled) setStateSource('api');
            }
          } catch { /* fall through */ }
        }
      }

      // 2. Fallback: localStorage
      if (!restoredState && typeof window !== 'undefined') {
        const localState = window.localStorage.getItem(STORAGE_KEY);
        if (localState) {
          try {
            restoredState = JSON.parse(localState) as DashboardStatePayload;
            if (!isCancelled) setStateSource('local');
          } catch {
            window.localStorage.removeItem(STORAGE_KEY);
          }
        }
      }

      // 3. Fallback: user state from API
      if (!restoredState && apiBaseUrl) {
        try {
          const response = await fetch(`${apiBaseUrl}/dashboard/state?user_id=${encodeURIComponent(USER_ID)}`, {
            cache: 'no-store',
          });
          if (response.ok) {
            const payload = (await response.json()) as DashboardStatePayload | { state?: DashboardStatePayload };
            restoredState = 'state' in payload && payload.state ? payload.state : (payload as DashboardStatePayload);
            if (!isCancelled) setStateSource('api');
          }
        } catch { /* no remote state */ }
      }

      if (!isCancelled && restoredState) {
        setFilters({ ...DEFAULT_FILTERS, ...restoredState.filters });
        setFiltersExpanded(restoredState.filtersExpanded);
        setSelectedKpiId(restoredState.selectedKpiId ?? null);
      }

      if (!isCancelled) {
        setStateReady(true);
      }
    };

    void hydrateState();

    return () => {
      isCancelled = true;
    };
  }, [apiBaseUrl]);

  useEffect(() => {
    if (!stateReady) {
      return;
    }

    const requestedRange = getRequiredDataRange(filters.dateRange);
    if (supportsRange(loadedRange, requestedRange) && allRecords.length > 0) {
      return;
    }

    let isCancelled = false;

    const loadDashboardData = async () => {
      setIsLoading(true);

      if (apiBaseUrl) {
        try {
          const response = await fetch(
            `${apiBaseUrl}/dashboard?user_id=${encodeURIComponent(USER_ID)}&date_range=${encodeURIComponent(requestedRange)}`,
            { cache: 'no-store' }
          );

          if (!response.ok) {
            throw new Error('Dashboard request failed');
          }

          const payload = (await response.json()) as DashboardDatasetResponse;
          if (!isCancelled) {
            setAllRecords(payload.records ?? []);
            setFilterFields(normalizeFilterFields(payload.records ?? [], payload.filter_fields));
            setLoadedRange(payload.requested_range ?? requestedRange);
            setDataSource('live');
            setIsLoading(false);
          }
          return;
        } catch {
          if (!isCancelled) {
            setDataSource('mock');
          }
        }
      }

      const mockRecords = createMockDashboardRecords(requestedRange);
      if (!isCancelled) {
        setAllRecords(mockRecords);
        setFilterFields(normalizeFilterFields(mockRecords));
        setLoadedRange(requestedRange);
        setIsLoading(false);
      }
    };

    void loadDashboardData();

    return () => {
      isCancelled = true;
    };
  }, [allRecords.length, apiBaseUrl, filters.dateRange, loadedRange, stateReady]);

  useEffect(() => {
    if (!stateReady || !loadedRange) {
      return;
    }

    const nextState = createDashboardState(USER_ID, filters, filtersExpanded, loadedRange, selectedKpiId ?? undefined);
    const serialized = JSON.stringify(nextState);

    if (serialized === lastSavedState.current) {
      return;
    }

    lastSavedState.current = serialized;

    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, serialized);
    }

    if (apiBaseUrl) {
      void fetch(`${apiBaseUrl}/dashboard/state`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: serialized,
      }).catch(() => undefined);
    }
  }, [apiBaseUrl, filters, filtersExpanded, loadedRange, selectedKpiId, stateReady]);

  const filteredRecords = useMemo(() => filterDashboardRecords(allRecords, filters), [allRecords, filters]);

  const filterOptions = useMemo(
    () =>
      Object.fromEntries(
        filterFields.map((field) => [field.key, getFilterOptions(filterDashboardRecords(allRecords, filters, { ignoreField: field.key }), field.key)])
      ),
    [allRecords, filterFields, filters]
  );

  const kpis = useMemo(() => buildDashboardKpis(allRecords, filteredRecords, filters), [allRecords, filteredRecords, filters]);
  const kpiDetails = useMemo(() => buildDashboardKpiDetails(allRecords, filteredRecords, filters), [allRecords, filteredRecords, filters]);
  const charts = useMemo(() => buildDashboardCharts(filteredRecords), [filteredRecords]);
  const insights = useMemo(() => buildDashboardInsights(filteredRecords, filterFields), [filteredRecords, filterFields]);
  const selectedKpiDetail = selectedKpiId ? kpiDetails[selectedKpiId] ?? null : null;
  const loadedRangeLabel = loadedRange ? getDisplayRangeLabel(loadedRange) : 'Loading';

  return (
    <div className="p-8 min-h-screen">
      <div className="mb-8 flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="text-4xl font-bold text-foreground mb-2">Analytics Dashboard</h1>
          <p className="text-muted-foreground">Client-side filters are applied on the loaded dataset, so narrower ranges reuse cached data instead of recalling the backend.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span className="rounded-full border border-border px-3 py-1">User: {USER_ID}</span>
          <span className="rounded-full border border-border px-3 py-1">Dataset: {dataSource === 'live' ? 'Backend' : 'Mock fallback'}</span>
          <span className="rounded-full border border-border px-3 py-1">Loaded window: {loadedRangeLabel}</span>
          <span className="rounded-full border border-border px-3 py-1">State: {stateSource === 'api' ? 'Synced API' : 'Local cache'}</span>
          <span className="rounded-full border border-border px-3 py-1">Rows in view: {filteredRecords.length.toLocaleString()}</span>
          {apiBaseUrl && (
            <button
              onClick={() => void handleShare()}
              disabled={shareStatus !== 'idle'}
              className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1 hover:border-primary/60 hover:text-foreground transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {shareStatus === 'saving' ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : shareStatus === 'copied' ? (
                <Check className="w-3.5 h-3.5 text-green-400" />
              ) : (
                <Share2 className="w-3.5 h-3.5" />
              )}
              {shareStatus === 'copied' ? 'Link copied!' : shareStatus === 'saving' ? 'Saving…' : 'Share'}
            </button>
          )}
        </div>
      </div>

      <Filters
        filters={filters}
        filterFields={filterFields}
        filterOptions={filterOptions}
        isExpanded={filtersExpanded}
        onExpandedChange={setFiltersExpanded}
        onApply={setFilters}
      />

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        {kpis.map((kpi) => (
          <KPICard
            key={kpi.id}
            title={kpi.title}
            value={kpi.value}
            change={kpi.change}
            timeframe={kpi.timeframe}
            icon={resolveDashboardIcon(kpi.iconKey)}
            onClick={() => setSelectedKpiId(kpi.id)}
          />
        ))}
      </div>

      {isLoading ? (
        <div className="bg-card border border-border rounded-lg p-8 text-muted-foreground">Loading dashboard dataset...</div>
      ) : filteredRecords.length ? (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {charts.slice(0, 2).map((chart, idx) => (
              <ChartRenderer key={idx} chart={chart} />
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {charts.slice(2, 4).map((chart, idx) => (
              <ChartRenderer key={idx + 2} chart={chart} />
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <InsightPanel insights={insights.slice(0, 2)} />
            <InsightPanel insights={insights.slice(2, 4)} />
          </div>
        </>
      ) : (
        <div className="bg-card border border-border rounded-lg p-8 text-muted-foreground">
          No dashboard rows match the active filters. Reset filters or remove one of the added filters to repopulate the view.
        </div>
      )}

      <KPIDetailModal
        open={Boolean(selectedKpiId && selectedKpiDetail)}
        detail={selectedKpiDetail}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedKpiId(null);
          }
        }}
      />
    </div>
  );
}
