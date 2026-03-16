'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import type { DashboardFilters, DashboardKPI, DashboardKpiId } from '@/types/dashboard';
import { useProfile, type ProfileKey } from '@/lib/profiles';

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

const KPI_TO_METRIC: Partial<Record<DashboardKpiId, string>> = {
  publish_rate:     'publish_rate_pct',
  processed_videos: 'created_count',
  published_videos: 'published_count',
};

const PRIORITY_COLOR: Record<string, string> = {
  high:   'var(--signal)',
  medium: 'var(--warn)',
  low:    'var(--ok)',
};

function getViewFromPathname(pathname: string): string {
  if (pathname === '/dashboard') return 'executive_summary';
  if (pathname.startsWith('/dashboard/usage')) return 'trend_view';
  if (pathname.startsWith('/dashboard/analysis')) return 'channel_detail';
  if (pathname.startsWith('/dashboard/funnel')) return 'content_mix';
  return 'executive_summary';
}

function buildContext(filters: DashboardFilters, kpis: DashboardKPI[], selectedKpiId: DashboardKpiId | null, userRole: ProfileKey, pathname: string) {
  const channelFilter = filters.channel && filters.channel !== 'all' ? filters.channel : null;
  const userFilter    = filters.user    && filters.user    !== 'all' ? filters.user    : null;

  let view = getViewFromPathname(pathname), entityType = 'network', entityName = 'All Channels';
  if (channelFilter) { view = 'channel_detail'; entityType = 'channel'; entityName = channelFilter; }
  else if (userFilter) { view = 'user_detail'; entityType = 'user'; entityName = userFilter; }

  const focusKpiId   = selectedKpiId ?? 'publish_rate';
  const metricName   = KPI_TO_METRIC[focusKpiId] ?? 'publish_rate_pct';
  const focusedKpi   = kpis.find((k) => k.id === focusKpiId);
  const rawValue     = focusedKpi?.value;
  const currentValue = typeof rawValue === 'number' ? rawValue
    : typeof rawValue === 'string' ? parseFloat(rawValue.replace(/[^0-9.-]/g, '')) || null
    : null;

  return { client_id: 1, view, entity_type: entityType, entity_id: null, entity_name: entityName,
           metric_in_focus: metricName, current_value: currentValue, time_range: null, user_role: userRole };
}

interface Props {
  apiBaseUrl: string;
  filters: DashboardFilters;
  kpis: DashboardKPI[];
  selectedKpiId: DashboardKpiId | null;
  dataReady: boolean;
}

export function RecommendationsPanel({ apiBaseUrl, filters, kpis, selectedKpiId, dataReady }: Props) {
  const { profile, profileDef } = useProfile();
  const pathname = usePathname();
  const [recs,    setRecs]    = useState<RecResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function fetchRecs(role: ProfileKey) {
    if (!apiBaseUrl || !dataReady) return;
    setLoading(true);
    setError(null);
    try {
      const body = buildContext(filters, kpis, selectedKpiId, role, pathname);
      const res  = await fetch(`${apiBaseUrl}/recommendations/contextual`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setRecs(await res.json() as RecResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!dataReady) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => void fetchRecs(profile), 600);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, kpis, selectedKpiId, dataReady, profile, pathname]);

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <span className="section-id">Recommendations</span>
        <span
          className="action-text"
          onClick={() => void fetchRecs(profile)}
          style={{ color: loading ? 'var(--signal)' : undefined }}
        >
          {loading ? <span className="spin-anim">↻</span> : '↻'}
        </span>
      </div>

      {/* Profile context display */}
      <div className="flex items-center gap-2 mb-4">
        <span
          style={{
            fontFamily: 'var(--font-condensed)',
            fontSize: '0.6rem',
            fontWeight: 700,
            letterSpacing: '0.14em',
            color: 'var(--on)',
            paddingBottom: '1px',
            borderBottom: '1px solid var(--signal)',
          }}
        >
          {profileDef.displayName.toUpperCase()}
        </span>
        {recs && !loading && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.55rem',
              color: 'var(--on-low)',
              marginLeft: 'auto',
            }}
          >
            {recs.entity_name}
          </span>
        )}
      </div>

      <div className="wire-h" style={{ marginBottom: '12px' }} />

      {/* Loading skeleton — scan lines */}
      {loading && (
        <div className="flex flex-col gap-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} style={{ animationDelay: `${i * 0.1}s` }}>
              <div className="scan-loader" style={{ animationDelay: `${i * 0.15}s`, marginBottom: '8px' }} />
              <div style={{ height: '8px', background: 'var(--surface-raise)', width: '60%', marginBottom: '4px' }} />
              <div style={{ height: '6px', background: 'var(--surface-hi)', width: '80%' }} />
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div style={{ borderLeft: '2px solid var(--signal)', paddingLeft: '10px' }}>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--signal)' }}>
            ERR: {error}
          </p>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && !recs && (
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--on-low)' }}>
          — awaiting dashboard data
        </p>
      )}

      {/* Recommendation rows */}
      {!loading && !error && recs && (
        <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: 'thin' }}>
          {recs.recommendations.map((rec, i) => (
            <div key={i} className="rec-row" style={{ animationDelay: `${i * 0.08}s` }}>
              {/* Priority bar */}
              <div
                className="rec-bar"
                style={{ background: PRIORITY_COLOR[rec.priority] ?? 'var(--wire-hi)' }}
              />

              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Priority label + title */}
                <div className="flex items-baseline gap-2 mb-1">
                  <span
                    style={{
                      fontFamily: 'var(--font-condensed)',
                      fontSize: '0.55rem',
                      fontWeight: 700,
                      letterSpacing: '0.18em',
                      color: PRIORITY_COLOR[rec.priority] ?? 'var(--on-low)',
                    }}
                  >
                    {rec.priority.toUpperCase()}
                  </span>
                  <span
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontSize: '0.75rem',
                      fontWeight: 500,
                      color: 'var(--on)',
                      lineHeight: 1.3,
                    }}
                  >
                    {rec.title}
                  </span>
                </div>

                {/* Action */}
                <p
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.65rem',
                    color: 'var(--signal)',
                    marginBottom: '4px',
                    letterSpacing: '0.02em',
                  }}
                >
                  → {rec.action}
                </p>

                {/* Rationale */}
                <p
                  style={{
                    fontSize: '0.7rem',
                    color: 'var(--on-mid)',
                    lineHeight: 1.45,
                    marginBottom: '6px',
                  }}
                >
                  {rec.rationale}
                </p>

                {/* Supporting metrics chips */}
                {Object.keys(rec.supporting_metrics).length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(rec.supporting_metrics).map(([k, v]) => (
                      <span
                        key={k}
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.55rem',
                          background: 'var(--surface-raise)',
                          color: 'var(--on-mid)',
                          padding: '1px 5px',
                          letterSpacing: '0.04em',
                        }}
                      >
                        {k.replace(/_/g, ' ')}: <span style={{ color: 'var(--on)' }}>{String(v)}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
