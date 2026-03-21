'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import type { DashboardFilters, DashboardKPI, DashboardKpiId } from '@/types/dashboard';
import { useProfile, PROFILES, type ProfileKey } from '@/lib/profiles';

interface InsightAlert {
  title: string;
  severity: 'high' | 'medium' | 'low';
  body?: string;
  metric_name?: string;
  entity_type?: string;
  delta_pct?: number;
}

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

const SEVERITY_DOT: Record<string, string> = {
  high:   'var(--signal)',
  medium: 'var(--warn)',
  low:    'var(--ok)',
};

const PRIORITY_COLOR: Record<string, string> = {
  high:   'var(--signal)',
  medium: 'var(--warn)',
  low:    'var(--ok)',
};

const KPI_TO_METRIC: Partial<Record<DashboardKpiId, string>> = {
  publish_rate:     'publish_rate_pct',
  processed_videos: 'created_count',
  published_videos: 'published_count',
};

function getViewFromPathname(pathname: string): string {
  if (pathname === '/dashboard') return 'executive_summary';
  if (pathname.startsWith('/dashboard/usage')) return 'trend_view';
  if (pathname.startsWith('/dashboard/analysis')) return 'channel_detail';
  if (pathname.startsWith('/dashboard/funnel')) return 'content_mix';
  return 'executive_summary';
}

function buildContext(
  filters: DashboardFilters,
  kpis: DashboardKPI[],
  selectedKpiId: DashboardKpiId | null,
  userRole: ProfileKey,
  pathname: string,
) {
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

  return {
    client_id: 1, view, entity_type: entityType, entity_id: null, entity_name: entityName,
    metric_in_focus: metricName, current_value: currentValue, time_range: null, user_role: userRole,
  };
}

export interface IntelligencePanelProps {
  apiBaseUrl: string;
  filters: DashboardFilters;
  kpis: DashboardKPI[];
  selectedKpiId: DashboardKpiId | null;
  dataReady: boolean;
  narratorData: { digest?: string | null; dashboard_banner?: InsightAlert[] } | null;
}

export function IntelligencePanel({
  apiBaseUrl,
  filters,
  kpis,
  selectedKpiId,
  dataReady,
  narratorData,
}: IntelligencePanelProps) {
  const { profile, profileDef, setProfile } = useProfile();
  const pathname = usePathname();
  const [recs,    setRecs]    = useState<RecResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [roleMenuOpen, setRoleMenuOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const signals = (narratorData?.dashboard_banner ?? []).slice(0, 5) as InsightAlert[];

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

  function handleRoleSelect(key: ProfileKey) {
    setProfile(key);
    setRoleMenuOpen(false);
  }

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 0 }}>

      {/* ── Panel header ── */}
      <div className="flex items-center justify-between" style={{ marginBottom: '12px' }}>
        <span className="section-id">Intelligence</span>
        <span
          className="action-text"
          onClick={() => void fetchRecs(profile)}
          style={{ color: loading ? 'var(--signal)' : undefined }}
        >
          {loading ? <span className="spin-anim">↻</span> : '↻'}
        </span>
      </div>

      {/* ── Digest line ── */}
      {narratorData?.digest && (
        <p style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.65rem',
          color: 'var(--on-mid)',
          lineHeight: 1.5,
          marginBottom: '12px',
          letterSpacing: '0.02em',
        }}>
          {narratorData.digest}
        </p>
      )}

      <div className="wire-h" style={{ marginBottom: '12px' }} />

      {/* ── Signals section ── */}
      {signals.length > 0 && (
        <>
          <div className="flex items-center justify-between" style={{ marginBottom: '8px' }}>
            <span style={{
              fontFamily: 'var(--font-condensed)',
              fontSize: '0.55rem',
              fontWeight: 700,
              letterSpacing: '0.14em',
              color: 'var(--on-low)',
              textTransform: 'uppercase',
            }}>
              Signals
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '8px' }}>
            {signals.map((sig, i) => {
              const dotColor = SEVERITY_DOT[sig.severity] ?? 'var(--on-low)';
              const delta = sig.delta_pct;
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '5px 0' }}>
                  {/* Severity dot */}
                  <span style={{
                    width: '6px', height: '6px', borderRadius: '50%',
                    background: dotColor, flexShrink: 0,
                  }} />
                  {/* Entity + metric */}
                  <span style={{
                    fontFamily: 'var(--font-sans)',
                    fontSize: '0.7rem',
                    color: 'var(--on)',
                    flex: 1,
                    lineHeight: 1.3,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {sig.title}
                  </span>
                  {/* Delta badge */}
                  {delta != null && (
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.6rem',
                      fontWeight: 700,
                      color: delta >= 0 ? 'var(--ok)' : 'var(--signal)',
                      flexShrink: 0,
                    }}>
                      {delta >= 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(0)}%
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          <div style={{ marginBottom: '12px' }}>
            <Link
              href="/narrator"
              style={{
                fontFamily: 'var(--font-condensed)',
                fontSize: '0.55rem',
                fontWeight: 700,
                letterSpacing: '0.14em',
                color: 'var(--on-low)',
                textDecoration: 'none',
                textTransform: 'uppercase',
              }}
            >
              View Full Report →
            </Link>
          </div>

          <div className="wire-h" style={{ marginBottom: '12px' }} />
        </>
      )}

      {/* ── Actions header with inline role selector ── */}
      <div className="flex items-center gap-2" style={{ marginBottom: '12px', position: 'relative', zIndex: 10 }}>
        <span style={{
          fontFamily: 'var(--font-condensed)',
          fontSize: '0.55rem',
          fontWeight: 700,
          letterSpacing: '0.14em',
          color: 'var(--on-low)',
          textTransform: 'uppercase',
        }}>
          Actions for
        </span>
        <button
          onClick={() => setRoleMenuOpen((p) => !p)}
          style={{
            fontFamily: 'var(--font-condensed)',
            fontSize: '0.55rem',
            fontWeight: 700,
            letterSpacing: '0.14em',
            color: 'var(--on)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '1px 4px',
            borderBottom: '1px solid var(--signal)',
            textTransform: 'uppercase',
          }}
        >
          {profileDef.displayName.toUpperCase()} ▾
        </button>

        {/* Role dropdown */}
        {roleMenuOpen && (
          <div style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            zIndex: 50,
            background: 'var(--surface)',
            border: '1px solid var(--wire)',
            minWidth: '180px',
            marginTop: '4px',
          }}>
            {(Object.keys(PROFILES) as ProfileKey[]).map((key) => (
              <button
                key={key}
                onClick={() => handleRoleSelect(key)}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '8px 12px',
                  fontFamily: 'var(--font-condensed)',
                  fontSize: '0.6rem',
                  fontWeight: key === profile ? 700 : 400,
                  letterSpacing: '0.12em',
                  color: key === profile ? 'var(--on)' : 'var(--on-mid)',
                  background: key === profile ? 'var(--surface-raise)' : 'none',
                  border: 'none',
                  cursor: 'pointer',
                  textTransform: 'uppercase',
                }}
              >
                {PROFILES[key].displayName}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Recommendation rows ── */}
      <div className="wire-h" style={{ marginBottom: '12px' }} />

      {loading && (
        <div className="flex flex-col gap-3">
          {[...Array(3)].map((_, i) => (
            <div key={i}>
              <div className="scan-loader" style={{ animationDelay: `${i * 0.15}s`, marginBottom: '8px' }} />
              <div style={{ height: '8px', background: 'var(--surface-raise)', width: '60%', marginBottom: '4px' }} />
              <div style={{ height: '6px', background: 'var(--surface-hi)', width: '80%' }} />
            </div>
          ))}
        </div>
      )}

      {!loading && error && (
        <div style={{ borderLeft: '2px solid var(--signal)', paddingLeft: '10px' }}>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--signal)' }}>
            ERR: {error}
          </p>
        </div>
      )}

      {!loading && !error && !recs && (
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--on-low)' }}>
          — awaiting dashboard data
        </p>
      )}

      {!loading && !error && recs && (
        <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: 'thin', minHeight: 0, paddingRight: '8px' }}>
          {recs.recommendations.map((rec, i) => (
            <div key={i} className="rec-row" style={{ animationDelay: `${i * 0.08}s` }}>
              <div
                className="rec-bar"
                style={{ background: PRIORITY_COLOR[rec.priority] ?? 'var(--wire-hi)' }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="flex items-baseline gap-2 mb-1">
                  <span style={{
                    fontFamily: 'var(--font-sans)',
                    fontSize: '0.75rem',
                    fontWeight: 500,
                    color: 'var(--on)',
                    lineHeight: 1.3,
                  }}>
                    {rec.title}
                  </span>
                </div>
                <p style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.65rem',
                  color: 'var(--signal)',
                  marginBottom: '4px',
                  letterSpacing: '0.02em',
                }}>
                  → {rec.action}
                </p>
                <p style={{
                  fontSize: '0.7rem',
                  color: 'var(--on-mid)',
                  lineHeight: 1.45,
                }}>
                  {rec.rationale}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
