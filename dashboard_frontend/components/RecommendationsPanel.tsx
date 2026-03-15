'use client';

import { useEffect, useRef, useState } from 'react';
import { Lightbulb, RefreshCw } from 'lucide-react';
import type { DashboardFilters, DashboardKPI, DashboardKpiId } from '@/types/dashboard';

// ── Types ─────────────────────────────────────────────────────────────────────

type UserRole = 'ops_lead' | 'editor' | 'exec';

type Rec = {
  title: string;
  action: string;
  rationale: string;
  priority: 'high' | 'medium' | 'low';
  scope: string;
  supporting_metrics: Record<string, unknown>;
};

type RecResponse = {
  recommendations: Rec[];
  context_view: string;
  entity_name: string;
  generated_at: string;
  cached: boolean;
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<UserRole, string> = {
  ops_lead: 'Ops Lead',
  editor:   'Editor',
  exec:     'Executive',
};

const KPI_TO_METRIC: Partial<Record<DashboardKpiId, string>> = {
  publish_rate:      'publish_rate_pct',
  processed_videos:  'created_count',
  published_videos:  'published_count',
};

const PRIORITY_CARD: Record<string, string> = {
  high:   'border-red-500/40 bg-red-500/5',
  medium: 'border-yellow-500/40 bg-yellow-500/5',
  low:    'border-green-500/40 bg-green-500/5',
};

const PRIORITY_BADGE: Record<string, string> = {
  high:   'bg-red-500/20 text-red-400',
  medium: 'bg-yellow-500/20 text-yellow-400',
  low:    'bg-green-500/20 text-green-400',
};

function buildContext(
  filters: DashboardFilters,
  kpis: DashboardKPI[],
  selectedKpiId: DashboardKpiId | null,
  userRole: UserRole,
) {
  const channelFilter = filters.channel && filters.channel !== 'all' ? filters.channel : null;
  const userFilter    = filters.user    && filters.user    !== 'all' ? filters.user    : null;

  let view        = 'executive_summary';
  let entityType  = 'network';
  let entityName  = 'All Channels';

  if (channelFilter) {
    view       = 'channel_detail';
    entityType = 'channel';
    entityName = channelFilter;
  } else if (userFilter) {
    view       = 'user_detail';
    entityType = 'user';
    entityName = userFilter;
  }

  const focusKpiId  = selectedKpiId ?? 'publish_rate';
  const metricName  = KPI_TO_METRIC[focusKpiId] ?? 'publish_rate_pct';
  const focusedKpi  = kpis.find((k) => k.id === focusKpiId);
  const rawValue    = focusedKpi?.value;
  const currentValue =
    typeof rawValue === 'number'
      ? rawValue
      : typeof rawValue === 'string'
      ? parseFloat(rawValue.replace(/[^0-9.-]/g, '')) || null
      : null;

  return {
    client_id:       1,
    view,
    entity_type:     entityType,
    entity_id:       null,
    entity_name:     entityName,
    metric_in_focus: metricName,
    current_value:   currentValue,
    time_range:      null,
    user_role:       userRole,
  };
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  apiBaseUrl: string;
  filters: DashboardFilters;
  kpis: DashboardKPI[];
  selectedKpiId: DashboardKpiId | null;
  dataReady: boolean; // only fetch once dashboard data is loaded
}

export function RecommendationsPanel({ apiBaseUrl, filters, kpis, selectedKpiId, dataReady }: Props) {
  const [userRole, setUserRole] = useState<UserRole>('ops_lead');
  const [recs,     setRecs]     = useState<RecResponse | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function fetchRecs(role: UserRole) {
    if (!apiBaseUrl || !dataReady) return;
    setLoading(true);
    setError(null);
    try {
      const body = buildContext(filters, kpis, selectedKpiId, role);
      const res = await fetch(`${apiBaseUrl}/recommendations/contextual`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`${res.status} — ${await res.text()}`);
      setRecs(await res.json() as RecResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load recommendations');
    } finally {
      setLoading(false);
    }
  }

  // Auto-fetch when filters/kpis/data readiness changes (debounced)
  useEffect(() => {
    if (!dataReady) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => void fetchRecs(userRole), 600);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, kpis, selectedKpiId, dataReady]);

  function handleRoleChange(role: UserRole) {
    setUserRole(role);
    void fetchRecs(role);
  }

  return (
    <div className="bg-card border border-border rounded-lg p-6">

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-primary/10 rounded-lg flex items-center justify-center shrink-0">
            <Lightbulb className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-foreground">AI Recommendations</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Context-aware actions based on current view
              {recs && !loading && (
                <span className="ml-2">
                  · <span className="text-foreground">{recs.entity_name}</span>
                  {recs.cached && <span className="ml-1 text-muted-foreground/60">(cached)</span>}
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Role selector */}
          <div className="flex rounded-lg border border-border overflow-hidden text-xs">
            {(Object.keys(ROLE_LABELS) as UserRole[]).map((role) => (
              <button
                key={role}
                onClick={() => handleRoleChange(role)}
                className={`px-3 py-1.5 transition-colors ${
                  userRole === role
                    ? 'bg-primary text-primary-foreground font-medium'
                    : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                }`}
              >
                {ROLE_LABELS[role]}
              </button>
            ))}
          </div>

          <button
            onClick={() => void fetchRecs(userRole)}
            disabled={loading}
            className="p-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-20 rounded-lg bg-secondary/30 animate-pulse" />
          ))}
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
          {error}
        </p>
      )}

      {/* Empty / not ready */}
      {!loading && !error && !recs && (
        <p className="text-sm text-muted-foreground text-center py-6">
          Recommendations load automatically once the dashboard data is ready.
        </p>
      )}

      {/* Recommendations */}
      {!loading && !error && recs && (
        <div className="space-y-3">
          {recs.recommendations.map((rec, i) => (
            <div
              key={i}
              className={`rounded-lg border p-4 ${PRIORITY_CARD[rec.priority] ?? 'border-border'}`}
            >
              <div className="flex items-start justify-between gap-3 mb-1.5">
                <span className="text-sm font-semibold text-foreground leading-snug">{rec.title}</span>
                <span className={`shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full ${PRIORITY_BADGE[rec.priority] ?? ''}`}>
                  {rec.priority}
                </span>
              </div>

              <p className="text-xs font-medium text-primary mb-1.5">→ {rec.action}</p>
              <p className="text-xs text-muted-foreground leading-relaxed mb-2">{rec.rationale}</p>

              {Object.keys(rec.supporting_metrics).length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(rec.supporting_metrics).map(([k, v]) => (
                    <span key={k} className="text-[10px] bg-secondary/60 rounded px-2 py-0.5 text-muted-foreground">
                      {k.replace(/_/g, ' ')}: <span className="text-foreground font-medium">{String(v)}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
