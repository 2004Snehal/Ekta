'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { SparkKPI } from '@/components/SparkKPI';
import { KPIDetailModal } from '@/components/KPIDetailModal';
import { ChartRenderer } from '@/components/ChartRenderer';
import { Filters } from '@/components/Filters';
import { IntelligencePanel } from '@/components/IntelligencePanel';
import { WorkspacePanel } from '@/components/WorkspacePanel';
import {
  buildDashboardCharts,
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
import { buildDrillUrl } from '@/lib/drill-down';
import type {
  DashboardDatasetResponse,
  DashboardDateRange,
  DashboardFilters,
  DashboardKpiId,
  DashboardRecord,
  DashboardStatePayload,
} from '@/types/dashboard';

const API          = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
const USER_ID      = process.env.NEXT_PUBLIC_DASHBOARD_USER_ID ?? 'demo-user';
const STORAGE_KEY  = `dashboard-state:${USER_ID}`;

const DEFAULT_VISIBLE_KPI_IDS: string[] = [
  'uploaded_videos', 'processed_videos', 'published_videos', 'publish_rate', 'average_duration',
];

const BUILTIN_CHART_NAMES = [
  'Videos by Channel', 'Daily Upload Trend', 'Language Distribution', 'Content by Type',
];

interface CtxMenu { x: number; y: number; type: 'kpi' | 'graph'; targetId: string }
interface RegistryKpi { id: string; name: string; current_value: unknown; unit?: string; }
interface NLQPinnedGraph { id: string; title: string; chart_type: string; x: string; y: string; data: Record<string, unknown>[]; sql?: string | null; description?: string | null; }

function uid() { return Math.random().toString(36).slice(2); }

type ShareStatus = 'idle' | 'saving' | 'copied';

function getRequiredDataRange(range: DashboardDateRange): DashboardDateRange {
  return range; // fetch exactly what's needed; supportsRange handles cache reuse
}

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
  const router     = useRouter();
  const apiBaseUrl = API;

  // Core state
  const [filters, setFilters]               = useState<DashboardFilters>(DEFAULT_FILTERS);
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const [allRecords, setAllRecords]         = useState<DashboardRecord[]>([]);
  const [loadedRange, setLoadedRange]       = useState<DashboardDateRange | null>(null);
  const [filterFields, setFilterFields]     = useState(() => normalizeFilterFields(createMockDashboardRecords('last-90-days')));
  const [dataSource, setDataSource]         = useState<'live' | 'mock'>('mock');
  const [isLoading, setIsLoading]           = useState(true);
  const [selectedKpiId, setSelectedKpiId]   = useState<DashboardKpiId | null>(null);
  const [stateReady, setStateReady]         = useState(false);
  const [shareStatus, setShareStatus]       = useState<ShareStatus>('idle');
  const lastSavedState = useRef('');

  // Narrator
  const [kpiInsightMap, setKpiInsightMap] = useState<Record<string, 'high' | 'medium' | 'low'>>({});
  const [narratorData, setNarratorData]   = useState<{ digest?: string | null; dashboard_banner?: unknown[] } | null>(null);
  const [periodDeltas, setPeriodDeltas]   = useState<Record<string, number>>({});

  // Workspace / customisation
  const [visibleKpiIds, setVisibleKpiIds]             = useState<string[]>(DEFAULT_VISIBLE_KPI_IDS);
  const [visibleGraphIndices, setVisibleGraphIndices] = useState<number[]>([0, 1, 2, 3]);
  const [showWorkspace, setShowWorkspace]             = useState(false);
  const [registryKpiMap, setRegistryKpiMap]           = useState<Record<string, RegistryKpi>>({});

  // KPI picker
  const [showKpiPicker, setShowKpiPicker]     = useState(false);
  const [allRegistryKpis, setAllRegistryKpis] = useState<RegistryKpi[]>([]);
  const [kpiPickerLoading, setKpiPickerLoading] = useState(false);

  // Context menu
  const [ctxMenu, setCtxMenu] = useState<CtxMenu | null>(null);

  // NLQ pinned graphs + ordering
  const [nlqGraphs, setNlqGraphs]       = useState<NLQPinnedGraph[]>([]);
  const [graphOrder, setGraphOrder]     = useState<string[]>([]);
  const [pinsInitialized, setPinsInitialized] = useState(false);

  /* ── Narrator insights ───────────────────────────────── */
  useEffect(() => {
    if (!apiBaseUrl) return;
    fetch(`${apiBaseUrl}/narrator/insights?client_id=1`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        setNarratorData(data);
        const kpiIns = data.kpi_insights ?? [];
        const kpiMap: Record<string, 'high' | 'medium' | 'low'> = {};
        for (const ins of kpiIns) {
          const key = ins.metric_name;
          if (key && (!kpiMap[key] || ins.severity === 'high' || (ins.severity === 'medium' && kpiMap[key] === 'low')))
            kpiMap[key] = ins.severity;
        }
        setKpiInsightMap(kpiMap);
      })
      .catch(() => {});
  }, [apiBaseUrl]);

  /* ── Period deltas ───────────────────────────────────── */
  useEffect(() => {
    if (!apiBaseUrl) return;
    fetch(`${apiBaseUrl}/analytics/period-compare?client_id=1&period=month`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data?.deltas) return;
        setPeriodDeltas({
          uploaded_videos: data.deltas.count_pct ?? 0,
          processed_videos: data.deltas.count_pct ?? 0,
          published_videos: data.deltas.published_pct ?? 0,
          publish_rate: data.deltas.publish_rate_delta ?? 0,
          average_duration: data.deltas.duration_pct ?? 0,
        });
      })
      .catch(() => {});
  }, [apiBaseUrl]);

  /* ── Close context menu on outside click ────────────── */
  useEffect(() => {
    if (!ctxMenu) return;
    const h = () => setCtxMenu(null);
    window.addEventListener('click', h);
    return () => window.removeEventListener('click', h);
  }, [ctxMenu]);

  /* ── Load pinned KPIs + NLQ graphs from localStorage (once) ─────────── */
  useEffect(() => {
    if (!stateReady || pinsInitialized) return;
    // Pinned registry KPIs (starred in KPI Lab)
    try {
      const pinned = JSON.parse(localStorage.getItem('dashboard_pinned_kpis') ?? '[]') as string[];
      if (pinned.length > 0) {
        setVisibleKpiIds(prev => {
          const toAdd = pinned.filter(id => !prev.includes(id));
          if (toAdd.length === 0) return prev;
          toAdd.forEach(id => {
            if (!apiBaseUrl) return;
            fetch(`${apiBaseUrl}/kpi-lab/registry/${id}`)
              .then(r => r.ok ? r.json() : null)
              .then(k => { if (k) setRegistryKpiMap(p => ({ ...p, [id]: k as RegistryKpi })); })
              .catch(() => {});
          });
          return [...prev, ...toAdd];
        });
      }
    } catch { /* ignore */ }
    // Pinned NLQ graphs (starred in Query page)
    try {
      const nlq = JSON.parse(localStorage.getItem('dashboard_nlq_graphs') ?? '[]') as NLQPinnedGraph[];
      if (nlq.length > 0) setNlqGraphs(nlq);
    } catch { /* ignore */ }
    // Saved graph order
    try {
      const order = JSON.parse(localStorage.getItem('dashboard_graph_order') ?? '[]') as string[];
      if (order.length > 0) setGraphOrder(order);
    } catch { /* ignore */ }
    setPinsInitialized(true);
  }, [stateReady, pinsInitialized, apiBaseUrl]);

  /* ── Keep graphOrder in sync with visible items ──────── */
  useEffect(() => {
    const wanted = [
      ...visibleGraphIndices.map(i => `builtin_${i}`),
      ...nlqGraphs.map(g => `nlq_${g.id}`),
    ];
    setGraphOrder(prev => {
      const filtered = prev.filter(id => wanted.includes(id));
      const added    = wanted.filter(id => !filtered.includes(id));
      return [...filtered, ...added];
    });
  }, [visibleGraphIndices, nlqGraphs]);

  /* ── Sync pinned KPIs to localStorage ───────────────── */
  useEffect(() => {
    if (!pinsInitialized) return;
    const registryIds = visibleKpiIds.filter(id => !DEFAULT_VISIBLE_KPI_IDS.includes(id));
    localStorage.setItem('dashboard_pinned_kpis', JSON.stringify(registryIds));
  }, [visibleKpiIds, pinsInitialized]);

  /* ── Sync NLQ graphs to localStorage ────────────────── */
  useEffect(() => {
    if (!pinsInitialized) return;
    localStorage.setItem('dashboard_nlq_graphs', JSON.stringify(nlqGraphs));
  }, [nlqGraphs, pinsInitialized]);

  /* ── Sync graph order to localStorage ───────────────── */
  useEffect(() => {
    if (!pinsInitialized || graphOrder.length === 0) return;
    localStorage.setItem('dashboard_graph_order', JSON.stringify(graphOrder));
  }, [graphOrder, pinsInitialized]);

  /* ── Share ───────────────────────────────────────────── */
  async function handleShare() {
    if (!apiBaseUrl || shareStatus !== 'idle') return;
    setShareStatus('saving');
    try {
      const payload = createDashboardState(USER_ID, filters, filtersExpanded, loadedRange ?? 'last-90-days', selectedKpiId ?? undefined);
      const res = await fetch(`${apiBaseUrl}/dashboard/state`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error();
      const { state_id } = await res.json() as { state_id: string };
      await navigator.clipboard.writeText(`${window.location.origin}/dashboard?state=${state_id}`);
      setShareStatus('copied');
      setTimeout(() => setShareStatus('idle'), 2500);
    } catch { setShareStatus('idle'); }
  }

  /* ── Hydration ───────────────────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    const hydrate = async () => {
      let restored: DashboardStatePayload | null = null;
      if (typeof window !== 'undefined' && apiBaseUrl) {
        const params = new URLSearchParams(window.location.search);
        const stateId     = params.get('state');
        const loadDashId  = params.get('load_dashboard');

        if (stateId) {
          try {
            const res = await fetch(`${apiBaseUrl}/dashboard/state/${stateId}`, { cache: 'no-store' });
            if (res.ok) { restored = await res.json() as DashboardStatePayload; if (!cancelled) {} }
          } catch { /* fallthrough */ }
        }

        if (loadDashId && !cancelled) {
          try {
            const res = await fetch(`${apiBaseUrl}/workspace/dashboards/${loadDashId}`, { cache: 'no-store' });
            if (res.ok) {
              const d = await res.json() as { visible_kpi_ids: string[]; graphs: Array<Record<string, unknown>> };
              const indices = d.graphs.filter(g => g['source'] === 'builtin' && typeof g['index'] === 'number').map(g => g['index'] as number);
              const nlqGs: NLQPinnedGraph[] = d.graphs
                .filter(g => g['source'] === 'nlq')
                .map(g => ({ id: String(g['id'] ?? uid()), title: String(g['title'] ?? 'NLQ Graph'), chart_type: String(g['chart_type'] ?? 'bar'), x: String(g['x'] ?? ''), y: String(g['y'] ?? ''), data: (g['data'] as Record<string, unknown>[]) ?? [], sql: g['sql'] as string | null, description: g['description'] as string | null }));
              if (d.visible_kpi_ids.length > 0) setVisibleKpiIds(d.visible_kpi_ids);
              if (indices.length > 0) setVisibleGraphIndices(indices);
              if (nlqGs.length > 0) { setNlqGraphs(nlqGs); localStorage.setItem('dashboard_nlq_graphs', JSON.stringify(nlqGs)); }
            }
          } catch { /* ignore */ }
        }
      }
      if (!restored && typeof window !== 'undefined') {
        const local = window.localStorage.getItem(STORAGE_KEY);
        if (local) {
          try { restored = JSON.parse(local) as DashboardStatePayload; }
          catch { window.localStorage.removeItem(STORAGE_KEY); }
        }
      }
      if (!restored && apiBaseUrl) {
        try {
          const res = await fetch(`${apiBaseUrl}/dashboard/state?user_id=${encodeURIComponent(USER_ID)}`, { cache: 'no-store' });
          if (res.ok) {
            const p = await res.json() as DashboardStatePayload | { state?: DashboardStatePayload };
            restored = 'state' in p && p.state ? p.state : (p as DashboardStatePayload);
          }
        } catch { /* no remote state */ }
      }
      if (!cancelled && restored) {
        setFilters({ ...DEFAULT_FILTERS, ...restored.filters, extraFilters: (restored.filters?.extraFilters ?? []).filter(ef => ef.value && ef.value !== 'all') });
        setFiltersExpanded(restored.filtersExpanded);
        setSelectedKpiId(restored.selectedKpiId ?? null);
      }
      if (!cancelled) setStateReady(true);
    };
    void hydrate();
    return () => { cancelled = true; };
  }, [apiBaseUrl]);

  /* ── Data load ───────────────────────────────────────── */
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
          if (!res.ok) throw new Error();
          const payload = await res.json() as DashboardDatasetResponse;
          if (!cancelled) { setAllRecords(payload.records ?? []); setFilterFields(normalizeFilterFields(payload.records ?? [], payload.filter_fields)); setLoadedRange(payload.requested_range ?? reqRange); setDataSource('live'); setIsLoading(false); }
          return;
        } catch { if (!cancelled) setDataSource('mock'); }
      }
      const mock = createMockDashboardRecords(reqRange);
      if (!cancelled) { setAllRecords(mock); setFilterFields(normalizeFilterFields(mock)); setLoadedRange(reqRange); setIsLoading(false); }
    };
    void load();
    return () => { cancelled = true; };
  }, [allRecords.length, apiBaseUrl, filters.dateRange, loadedRange, stateReady]);

  /* ── State persistence — localStorage only ───────────── */
  useEffect(() => {
    if (!stateReady || !loadedRange) return;
    const next = createDashboardState(USER_ID, filters, filtersExpanded, loadedRange, selectedKpiId ?? undefined);
    const ser  = JSON.stringify(next);
    if (ser === lastSavedState.current) return;
    lastSavedState.current = ser;
    if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, ser);
    // NOT auto-saved to API — use Workspace to save dashboards explicitly
  }, [filters, filtersExpanded, loadedRange, selectedKpiId, stateReady]);

  /* ── KPI picker ──────────────────────────────────────── */
  async function openKpiPicker() {
    setShowKpiPicker(true);
    if (allRegistryKpis.length > 0 || !apiBaseUrl) return;
    setKpiPickerLoading(true);
    try {
      const res = await fetch(`${apiBaseUrl}/kpi-lab/registry`);
      if (res.ok) { const d = await res.json() as { kpis: RegistryKpi[] }; setAllRegistryKpis(d.kpis ?? []); }
    } catch { /* ignore */ }
    setKpiPickerLoading(false);
  }

  function addKpiFromRegistry(kpi: RegistryKpi) {
    if (visibleKpiIds.includes(kpi.id)) return;
    setRegistryKpiMap(prev => ({ ...prev, [kpi.id]: kpi }));
    setVisibleKpiIds(prev => [...prev, kpi.id]);
  }

  /* ── Load saved workspace dashboard ─────────────────── */
  function handleLoadDashboard(kpiIds: string[], graphIndices: number[], nlqGs: NLQPinnedGraph[] = []) {
    setVisibleKpiIds(kpiIds.length > 0 ? kpiIds : DEFAULT_VISIBLE_KPI_IDS);
    setVisibleGraphIndices(graphIndices.length > 0 ? graphIndices : [0, 1, 2, 3]);
    setNlqGraphs(nlqGs);
    localStorage.setItem('dashboard_nlq_graphs', JSON.stringify(nlqGs));
    // Reset order so it rebuilds from new state
    setGraphOrder([]);
    const registryIds = kpiIds.filter(id => !DEFAULT_VISIBLE_KPI_IDS.includes(id));
    registryIds.forEach(id => {
      if (registryKpiMap[id] || !apiBaseUrl) return;
      fetch(`${apiBaseUrl}/kpi-lab/registry/${id}`).then(r => r.ok ? r.json() : null).then(k => { if (k) setRegistryKpiMap(prev => ({ ...prev, [id]: k as RegistryKpi })); }).catch(() => {});
    });
  }

  /* ── Move graph up/down ──────────────────────────────── */
  function moveGraph(gid: string, dir: -1 | 1) {
    setGraphOrder(prev => {
      const idx = prev.indexOf(gid);
      if (idx === -1) return prev;
      const newIdx = idx + dir;
      if (newIdx < 0 || newIdx >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[newIdx]] = [next[newIdx], next[idx]];
      return next;
    });
  }

  /* ── Derived data ────────────────────────────────────── */
  const filteredRecords = useMemo(() => filterDashboardRecords(allRecords, filters), [allRecords, filters]);
  const filterOptions   = useMemo(() =>
    Object.fromEntries(filterFields.map(f => [f.key, getFilterOptions(filterDashboardRecords(allRecords, filters, { ignoreField: f.key }), f.key)])),
    [allRecords, filterFields, filters]);
  const kpis         = useMemo(() => buildDashboardKpis(allRecords, filteredRecords, filters), [allRecords, filteredRecords, filters]);
  const kpiDetails   = useMemo(() => buildDashboardKpiDetails(allRecords, filteredRecords, filters), [allRecords, filteredRecords, filters]);
  const charts       = useMemo(() => buildDashboardCharts(filteredRecords), [filteredRecords]);
  const selectedKpiDetail = selectedKpiId ? kpiDetails[selectedKpiId] ?? null : null;
  const dataReady    = !isLoading && filteredRecords.length > 0;

  const sparklines = useMemo(() => ({
    uploaded_videos:  buildSparkline(filteredRecords, 'uploadedVideos'),
    processed_videos: buildSparkline(filteredRecords, 'processedVideos'),
    published_videos: buildSparkline(filteredRecords, 'publishedVideos'),
    publish_rate:     buildSparkline(filteredRecords, 'publishedVideos'),
    average_duration: [] as number[],
  }), [filteredRecords]);

  const enrichedCharts = useMemo(() => charts.map((chart, idx) => {
    const enriched = { ...chart };
    if (idx < 2) {
      enriched.refLinks = [{ label: 'View in Usage', href: '/dashboard/usage?from=summary' }];
    } else {
      const xKey = chart.axes?.x?.field ?? chart.x ?? chart.category ?? '';
      if (xKey) enriched.drillDown = { dimensionKey: xKey, targetPage: '/dashboard/analysis', targetParam: 'dim1' };
      enriched.refLinks = [{ label: 'See Funnel', href: buildDrillUrl('/dashboard/funnel', { group_by: xKey || 'channel', from: 'summary' }) }];
    }
    return enriched;
  }), [charts]);

  const visibleBuiltinKpis   = useMemo(() => kpis.filter(k => visibleKpiIds.includes(k.id)), [kpis, visibleKpiIds]);
  const visibleRegistryKpis  = useMemo(() => visibleKpiIds.filter(id => !DEFAULT_VISIBLE_KPI_IDS.includes(id)).map(id => registryKpiMap[id]).filter((k): k is RegistryKpi => !!k), [visibleKpiIds, registryKpiMap]);
  const hiddenChartIndices   = useMemo(() => [0, 1, 2, 3].filter(i => !visibleGraphIndices.includes(i)), [visibleGraphIndices]);

  const handleChartClick = useCallback((dimensionKey: string, value: string) => {
    router.push(buildDrillUrl('/dashboard/analysis', { dim1: dimensionKey, filter: { [dimensionKey]: value }, from: 'summary' }));
  }, [router]);

  const mono: React.CSSProperties = { fontFamily: 'var(--font-mono)' };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--void)' }}>

      {/* Workspace panel */}
      <WorkspacePanel isOpen={showWorkspace} onClose={() => setShowWorkspace(false)}
        apiBaseUrl={apiBaseUrl} currentUserId={USER_ID}
        visibleKpiIds={visibleKpiIds} visibleGraphIndices={visibleGraphIndices}
        nlqGraphs={nlqGraphs}
        onLoadDashboard={handleLoadDashboard} />

      {/* Context menu */}
      {ctxMenu && (
        <div onClick={e => e.stopPropagation()} style={{
          position: 'fixed', left: ctxMenu.x, top: ctxMenu.y, background: 'var(--surface-raise)',
          border: '1px solid var(--wire-hi)', zIndex: 2000, borderRadius: '2px', minWidth: '160px',
          boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
        }}>
          <button
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-hi)'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ''; }}
            onClick={() => {
              if (ctxMenu.type === 'kpi') {
                setVisibleKpiIds(prev => prev.filter(id => id !== ctxMenu.targetId));
                if (selectedKpiId === ctxMenu.targetId) setSelectedKpiId(null);
              } else {
                const gid = ctxMenu.targetId;
                if (gid.startsWith('builtin_')) {
                  const idx = parseInt(gid.slice(8));
                  setVisibleGraphIndices(prev => prev.filter(i => i !== idx));
                } else if (gid.startsWith('nlq_')) {
                  const id = gid.slice(4);
                  setNlqGraphs(prev => prev.filter(g => g.id !== id));
                }
              }
              setCtxMenu(null);
            }}
            style={{ width: '100%', padding: '8px 14px', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--on)', textAlign: 'left', ...mono, fontSize: '0.65rem', display: 'block' }}
          >
            Remove from Dashboard
          </button>
        </div>
      )}

      {/* KPI Picker */}
      {showKpiPicker && (
        <>
          <div onClick={() => setShowKpiPicker(false)} style={{ position: 'fixed', inset: 0, zIndex: 998, background: 'rgba(0,0,0,0.4)' }} />
          <div style={{
            position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
            background: 'var(--surface)', border: '1px solid var(--wire)', zIndex: 999,
            width: '380px', maxHeight: '480px', display: 'flex', flexDirection: 'column', borderRadius: '2px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid var(--wire)' }}>
              <span style={{ ...mono, fontSize: '0.65rem', letterSpacing: '0.12em', color: 'var(--on-mid)', textTransform: 'uppercase' }}>Add KPI from Registry</span>
              <button onClick={() => setShowKpiPicker(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--on-mid)', ...mono, fontSize: '0.8rem' }}>✕</button>
            </div>
            <div style={{ overflowY: 'auto', flex: 1 }}>
              {kpiPickerLoading && <p style={{ padding: '12px 16px', fontSize: '0.75rem', color: 'var(--on-low)' }}>Loading registry…</p>}
              {!kpiPickerLoading && allRegistryKpis.length === 0 && <p style={{ padding: '12px 16px', fontSize: '0.75rem', color: 'var(--on-low)' }}>No KPIs in registry. Create one in KPI Lab.</p>}
              {allRegistryKpis.map(kpi => {
                const already = visibleKpiIds.includes(kpi.id);
                return (
                  <div key={kpi.id} onClick={() => { if (!already) { addKpiFromRegistry(kpi); setShowKpiPicker(false); } }}
                    style={{ padding: '9px 16px', cursor: already ? 'default' : 'pointer', opacity: already ? 0.45 : 1, borderBottom: '1px solid var(--wire)' }}
                    onMouseEnter={e => { if (!already) (e.currentTarget as HTMLElement).style.background = 'var(--surface-hi)'; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ''; }}>
                    <div style={{ fontSize: '0.82rem', color: 'var(--on)', marginBottom: '2px' }}>{kpi.name}</div>
                    <div style={{ ...mono, fontSize: '0.55rem', color: 'var(--on-low)' }}>
                      {kpi.current_value != null ? `${String(kpi.current_value)}${kpi.unit ? ' ' + kpi.unit : ''}` : 'no value'}{already ? ' · already on dashboard' : ''}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* Filter strip */}
      <div className="sticky top-11 z-40" style={{ background: 'var(--void)' }}>
        <Filters filters={filters} filterFields={filterFields} filterOptions={filterOptions}
          isExpanded={filtersExpanded} onExpandedChange={setFiltersExpanded} onApply={setFilters} />
      </div>

      {/* KPI strip */}
      <div className="flex" style={{ borderBottom: '1px solid var(--wire)' }}>
        {isLoading ? (
          <div className="flex-1 px-6 py-8"><div className="scan-loader" /></div>
        ) : (
          <>
            {visibleBuiltinKpis.map((kpi, i) => (
              <div key={kpi.id} className="flex" style={{ flex: 1 }}
                onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, type: 'kpi', targetId: kpi.id }); }}
                title="Right-click to remove">
                {i > 0 && <div className="wire-v" />}
                <SparkKPI title={kpi.title} value={kpi.value}
                  delta={periodDeltas[kpi.id] ?? kpi.change ?? null}
                  sparkData={sparklines[kpi.id as keyof typeof sparklines] ?? []}
                  active={selectedKpiId === kpi.id}
                  onClick={() => setSelectedKpiId(kpi.id === selectedKpiId ? null : kpi.id)}
                  insightSeverity={kpiInsightMap[kpi.id] ?? null} />
              </div>
            ))}
            {visibleRegistryKpis.map(kpi => (
              <div key={kpi.id} className="flex" style={{ flex: 1 }}
                onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, type: 'kpi', targetId: kpi.id }); }}
                title="Right-click to remove">
                <div className="wire-v" />
                <SparkKPI title={kpi.name} value={kpi.current_value != null ? String(kpi.current_value) : '—'} insightSeverity={null} />
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', padding: '0 10px', flexShrink: 0 }}>
              <button onClick={() => void openKpiPicker()} title="Add a KPI from the registry"
                style={{ background: 'none', border: '1px dashed var(--wire-hi)', cursor: 'pointer', color: 'var(--on-low)', padding: '4px 8px', borderRadius: '2px', ...mono, fontSize: '0.55rem', letterSpacing: '0.12em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
                + KPI
              </button>
            </div>
          </>
        )}
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-4 px-6 py-1.5 flex-wrap" style={{ borderBottom: '1px solid var(--wire)' }}>
        <span style={{ ...mono, fontSize: '0.6rem', color: 'var(--on-low)' }}>USER:{USER_ID}</span>
        <span style={{ color: 'var(--wire-mid)', fontSize: '0.55rem' }}>·</span>
        <span style={{ ...mono, fontSize: '0.6rem', color: dataSource === 'live' ? 'var(--ok)' : 'var(--on-low)' }}>{dataSource === 'live' ? 'LIVE' : 'MOCK'}</span>
        <span style={{ color: 'var(--wire-mid)', fontSize: '0.55rem' }}>·</span>
        <span style={{ ...mono, fontSize: '0.6rem', color: 'var(--on-low)' }}>{filteredRecords.length.toLocaleString()} ROWS</span>
        <span style={{ color: 'var(--wire-mid)', fontSize: '0.55rem' }}>·</span>
        <span style={{ ...mono, fontSize: '0.6rem', color: 'var(--on-low)' }}>{getDisplayRangeLabel(filters.dateRange).toUpperCase()}</span>
        <div className="flex-1" />
        {apiBaseUrl && (
          <span className="action-text" onClick={() => void handleShare()}
            style={{ color: shareStatus === 'copied' ? 'var(--ok)' : shareStatus === 'saving' ? 'var(--warn)' : undefined }}>
            {shareStatus === 'copied' ? 'COPIED ✓' : shareStatus === 'saving' ? 'SAVING…' : 'SHARE ↗'}
          </span>
        )}
        <span className="action-text" onClick={() => setShowWorkspace(true)}>WORKSPACE ↗</span>
      </div>

      {/* Empty state */}
      {!isLoading && filteredRecords.length === 0 && (
        <div className="px-6 py-12">
          <p style={{ ...mono, fontSize: '0.75rem', color: 'var(--on-low)' }}>— no rows match active filters. clear filters to repopulate.</p>
        </div>
      )}

      {/* Main content */}
      {!isLoading && filteredRecords.length > 0 && (
        <div className="flex" style={{ minHeight: '600px' }}>

          {/* Charts (65%) */}
          <div style={{ flex: '0 0 65%', borderRight: '1px solid var(--wire)', padding: '24px 28px' }}>

            {/* Hidden built-in chart restore buttons */}
            {hiddenChartIndices.length > 0 && (
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '20px' }}>
                {hiddenChartIndices.map(idx => (
                  <button key={idx} onClick={() => setVisibleGraphIndices(prev => [...prev, idx].sort((a, b) => a - b))}
                    style={{ border: '1px dashed var(--wire-hi)', background: 'none', cursor: 'pointer', color: 'var(--on-low)', padding: '4px 10px', borderRadius: '2px', ...mono, fontSize: '0.55rem', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                    + {BUILTIN_CHART_NAMES[idx]}
                  </button>
                ))}
              </div>
            )}

            {/* Charts — ordered by graphOrder, supports up/down reposition */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
              {(graphOrder.length === 0 ? visibleGraphIndices.map(i => `builtin_${i}`) : graphOrder).map((gid, pos, arr) => {
                const moveBtnStyle: React.CSSProperties = { background: 'none', border: '1px solid var(--wire)', cursor: 'pointer', color: 'var(--on-low)', padding: '1px 5px', borderRadius: '2px', ...mono, fontSize: '0.6rem', lineHeight: 1.4 };
                const moveControls = (
                  <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end', marginBottom: '4px' }}>
                    <button onClick={() => moveGraph(gid, -1)} disabled={pos === 0} title="Move up" style={{ ...moveBtnStyle, opacity: pos === 0 ? 0.3 : 1 }}>▲</button>
                    <button onClick={() => moveGraph(gid, 1)} disabled={pos === arr.length - 1} title="Move down" style={{ ...moveBtnStyle, opacity: pos === arr.length - 1 ? 0.3 : 1 }}>▼</button>
                  </div>
                );

                if (gid.startsWith('builtin_')) {
                  const idx = parseInt(gid.slice(8));
                  const chart = enrichedCharts[idx];
                  if (!chart) return null;
                  return (
                    <div key={gid}>
                      {moveControls}
                      <div onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, type: 'graph', targetId: gid }); }} title="Right-click to remove">
                        <ChartRenderer chart={chart} onElementClick={handleChartClick} />
                      </div>
                    </div>
                  );
                }

                // NLQ graph
                const id = gid.slice(4);
                const nlqG = nlqGraphs.find(g => g.id === id);
                if (!nlqG) return null;
                const spec = { chart_type: nlqG.chart_type as 'bar' | 'line' | 'pie' | 'scatter' | 'stacked_bar' | 'table', title: nlqG.title, description: nlqG.description ?? undefined, x: nlqG.x, y: nlqG.y, data: nlqG.data };
                return (
                  <div key={gid}>
                    {moveControls}
                    <div onContextMenu={e => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, type: 'graph', targetId: gid }); }} title="Right-click to remove">
                      <div style={{ ...mono, fontSize: '0.5rem', color: 'var(--on-low)', marginBottom: '4px', letterSpacing: '0.1em', textTransform: 'uppercase' }}>From NLQ ·</div>
                      <ChartRenderer chart={spec} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Intelligence panel (35%) */}
          <div style={{ flex: '0 0 35%', padding: '24px 24px', position: 'sticky', top: '88px', alignSelf: 'flex-start', maxHeight: 'calc(100vh - 88px)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <IntelligencePanel apiBaseUrl={apiBaseUrl} filters={filters} kpis={kpis}
              selectedKpiId={selectedKpiId} dataReady={dataReady} narratorData={narratorData} />
          </div>
        </div>
      )}

      <KPIDetailModal open={Boolean(selectedKpiId && selectedKpiDetail)} detail={selectedKpiDetail}
        onOpenChange={open => { if (!open) setSelectedKpiId(null); }} />
    </div>
  );
}
