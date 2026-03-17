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

const PRIORITY_CONFIG: Record<string, { color: string; bg: string; border: string; dot: string }> = {
  high:   { color: 'var(--signal)', bg: 'rgba(196, 85, 58, 0.05)',   border: 'rgba(196, 85, 58, 0.2)',  dot: '#C4553A' },
  medium: { color: 'var(--warn)',   bg: 'rgba(198, 139, 44, 0.05)',  border: 'rgba(198, 139, 44, 0.2)', dot: '#C68B2C' },
  low:    { color: 'var(--ok)',     bg: 'rgba(91, 138, 114, 0.05)',  border: 'rgba(91, 138, 114, 0.2)', dot: '#5B8A72' },
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.1rem', fontWeight: 700, color: 'var(--on)', lineHeight: 1.2, marginBottom: '3px' }}>
            Recommendations
          </h2>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.65rem', color: 'var(--on-low)', letterSpacing: '0.03em' }}>
            Context-aware · {profileDef.displayName}
          </p>
        </div>
        <button
          onClick={() => void fetchRecs(profile)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: 'var(--surface-raise)',
            border: '1px solid var(--wire)',
            borderRadius: '20px',
            cursor: 'pointer',
            color: loading ? 'var(--signal)' : 'var(--on-mid)',
            fontFamily: 'var(--font-sans)',
            fontSize: '0.72rem',
            fontWeight: 600,
            padding: '5px 12px',
            transition: 'all 0.2s',
          }}
        >
          <span style={{ display: 'inline-block', animation: loading ? 'spin 1s linear infinite' : 'none' }}>↻</span>
          {loading ? 'Loading' : 'Refresh'}
        </button>
      </div>

      {/* Context pill + entity */}
      {recs && !loading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px', flexWrap: 'wrap' }}>
          <span style={{
            fontFamily: 'var(--font-sans)',
            fontSize: '0.65rem',
            fontWeight: 700,
            color: 'var(--signal)',
            background: 'var(--signal-dim)',
            padding: '3px 10px',
            borderRadius: '20px',
            border: '1px solid rgba(196, 85, 58, 0.15)',
            letterSpacing: '0.04em',
          }}>
            {recs.context_view.replace(/_/g, ' ')}
          </span>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', color: 'var(--on-low)' }}>
            {recs.entity_name}
          </span>
          {recs.cached && (
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.62rem', color: 'var(--on-low)', background: 'var(--surface-raise)', padding: '2px 8px', borderRadius: '10px' }}>
              cached
            </span>
          )}
        </div>
      )}

      <div style={{ height: '1px', background: 'var(--wire)', marginBottom: '14px', flexShrink: 0 }} />

      {/* Loading skeleton */}
      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {[...Array(3)].map((_, i) => (
            <div key={i} style={{
              borderRadius: '12px',
              border: '1px solid var(--wire)',
              background: 'var(--surface)',
              padding: '14px',
              opacity: 1 - i * 0.2,
            }}>
              <div className="scan-loader" style={{ marginBottom: '10px' }} />
              <div style={{ height: '9px', background: 'var(--surface-raise)', width: '55%', marginBottom: '8px', borderRadius: '4px' }} />
              <div style={{ height: '7px', background: 'var(--surface-hi)', width: '80%', borderRadius: '4px' }} />
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div style={{
          borderRadius: '10px',
          border: '1px solid rgba(196, 85, 58, 0.25)',
          background: 'rgba(196, 85, 58, 0.04)',
          padding: '12px 14px',
        }}>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.75rem', color: 'var(--signal)' }}>
            {error}
          </p>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && !recs && (
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.82rem', color: 'var(--on-low)', fontStyle: 'italic' }}>
          Awaiting dashboard data…
        </p>
      )}

      {/* Recommendation cards */}
      {!loading && !error && recs && (
        <div style={{ flex: 1, overflowY: 'auto', scrollbarWidth: 'thin', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {recs.recommendations.map((rec, i) => {
            const cfg = PRIORITY_CONFIG[rec.priority] ?? PRIORITY_CONFIG.low;
            return (
              <div
                key={i}
                style={{
                  borderRadius: '12px',
                  border: `1px solid ${cfg.border}`,
                  background: cfg.bg,
                  padding: '14px 16px',
                  animation: 'fade-up 0.35s ease-out both',
                  animationDelay: `${i * 0.08}s`,
                }}
              >
                {/* Priority badge + title */}
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', marginBottom: '8px' }}>
                  <span style={{
                    flexShrink: 0,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '0.62rem',
                    fontWeight: 700,
                    letterSpacing: '0.07em',
                    textTransform: 'uppercase',
                    color: cfg.color,
                    background: 'rgba(255,255,255,0.7)',
                    padding: '2px 8px',
                    borderRadius: '20px',
                    border: `1px solid ${cfg.border}`,
                    marginTop: '2px',
                  }}>
                    <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: cfg.dot, flexShrink: 0 }} />
                    {rec.priority}
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-sans)',
                    fontSize: '0.84rem',
                    fontWeight: 700,
                    color: 'var(--on)',
                    lineHeight: 1.3,
                  }}>
                    {rec.title}
                  </span>
                </div>

                {/* Action */}
                <p style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  color: cfg.color,
                  marginBottom: '6px',
                  lineHeight: 1.4,
                }}>
                  → {rec.action}
                </p>

                {/* Rationale */}
                <p style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: '0.73rem',
                  color: 'var(--on-mid)',
                  lineHeight: 1.55,
                  marginBottom: Object.keys(rec.supporting_metrics).length > 0 ? '10px' : 0,
                }}>
                  {rec.rationale}
                </p>

                {/* Supporting metrics */}
                {Object.keys(rec.supporting_metrics).length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                    {Object.entries(rec.supporting_metrics).map(([k, v]) => (
                      <span key={k} style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.62rem',
                        background: 'rgba(255,255,255,0.8)',
                        border: '1px solid var(--wire)',
                        color: 'var(--on-low)',
                        padding: '2px 7px',
                        borderRadius: '6px',
                      }}>
                        {k.replace(/_/g, ' ')}: <span style={{ color: 'var(--on)', fontWeight: 600 }}>{String(v)}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
