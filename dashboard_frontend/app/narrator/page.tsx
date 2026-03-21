'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Newspaper, RefreshCw, AlertCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { useProfile } from '@/lib/profiles';
import type { NarratorResponseV2, InsightCardData, EntityHealthScore, DQScorecard, DQPeriodScore } from '@/types/narrator';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '');
const CLIENT_ID = 1;
const CACHE_KEY = `narrator-insights-${CLIENT_ID}`;
const CACHE_TTL = 5 * 60 * 1000;

function readNarratorCache(): NarratorResponseV2 | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const { ts, data } = JSON.parse(raw) as { ts: number; data: NarratorResponseV2 };
    return Date.now() - ts > CACHE_TTL ? null : data;
  } catch { return null; }
}

function writeNarratorCache(data: NarratorResponseV2) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data })); }
  catch { /* quota */ }
}

type LoadState = 'idle' | 'loading' | 'refreshing' | 'error';

function formatRelativeTime(iso: string): string {
  const dt = new Date(iso);
  const diffMs = Date.now() - dt.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1)  return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24)  return `${diffHrs}h ago`;
  return `${Math.floor(diffHrs / 24)}d ago`;
}

// ── Merge all signal arrays into one flat feed ──────────────────────────────
function mergeAllSignals(data: NarratorResponseV2): InsightCardData[] {
  return [
    ...(data.flagged_metrics ?? []),
    ...(data.consecutive_trends ?? []),
    ...(data.cross_dimension ?? []),
    ...(data.milestones ?? []),
    ...(data.funnel_gaps ?? []),
    ...(data.operational_risks ?? []),
    ...(data.stalled_content ?? []),
    ...(data.dq_issues ?? []),
  ];
}

// ── Sort: severity (high→med→low) then |delta_pct| descending ────────────────
const SEV_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

function sortSignals(signals: InsightCardData[]): InsightCardData[] {
  return [...signals].sort((a, b) => {
    const sevDiff = (SEV_ORDER[a.severity] ?? 2) - (SEV_ORDER[b.severity] ?? 2);
    if (sevDiff !== 0) return sevDiff;
    return Math.abs(b.delta_pct) - Math.abs(a.delta_pct);
  });
}

// ── Severity border style ─────────────────────────────────────────────────────
function severityBorder(sev: string): string {
  if (sev === 'high')   return '4px solid var(--signal)';
  if (sev === 'medium') return '3px solid var(--warn)';
  return '1px solid var(--wire-hi)';
}

// ── Grade color ───────────────────────────────────────────────────────────────
function gradeColor(grade: string): string {
  if (grade === 'A') return 'var(--ok)';
  if (grade === 'B') return 'var(--ok)';
  if (grade === 'C') return 'var(--warn)';
  return 'var(--signal)';
}

// ── Signal category label ─────────────────────────────────────────────────────
const CATEGORY_LABELS: Record<string, string> = {
  anomaly: 'Anomaly', trend: 'Trend', comparison: 'Cross-dim',
  milestone: 'Milestone', operational: 'Pipeline', data_quality: 'DQ',
};

// ── SOURCE → CATEGORY mapping for filter chips ────────────────────────────────
function insightCategory(card: InsightCardData): string {
  if (card.category === 'data_quality' || card.insight_source === 'dq') return 'DQ';
  if (card.category === 'operational' || card.insight_source === 'funnel' || card.insight_source === 'op_risk' || card.insight_source === 'stalled') return 'Pipeline';
  if (card.category === 'anomaly' || card.insight_source === 'anomaly') return 'Anomaly';
  if (card.category === 'trend' || card.insight_source === 'consecutive') return 'Trend';
  if (card.category === 'comparison' || card.insight_source === 'cross_dim') return 'Cross-dim';
  if (card.category === 'milestone' || card.insight_source === 'milestone') return 'Milestone';
  return 'Other';
}

// ── NLQ navigation URL ────────────────────────────────────────────────────────
function nlqUrl(query: string): string {
  return `/nlq?q=${encodeURIComponent(query)}`;
}

export default function NarratorPage() {
  const router = useRouter();
  const { profileDef } = useProfile();
  const [data,       setData]       = useState<NarratorResponseV2 | null>(() => {
    if (typeof window === 'undefined') return null;
    return readNarratorCache();
  });
  const [loadState,  setLoadState]  = useState<LoadState>(() => {
    if (typeof window === 'undefined') return 'loading';
    return readNarratorCache() ? 'idle' : 'loading';
  });
  const [errorMsg,   setErrorMsg]   = useState('');
  const [triggerMsg, setTriggerMsg] = useState('');

  // Filter state
  const [severityFilter, setSeverityFilter] = useState<'all' | 'high' | 'medium' | 'low'>('all');
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [entityFilter,   setEntityFilter]   = useState<string | null>(null);
  const [expandedIds,      setExpandedIds]      = useState<Set<string>>(new Set());
  const [periodExpanded,   setPeriodExpanded]   = useState(false);
  const [dqExpanded,       setDqExpanded]       = useState(false);

  const fetchInsights = useCallback(async (isRefresh = false) => {
    const cached = readNarratorCache();
    if (cached && !isRefresh) {
      setData(cached);
      setLoadState('idle');
      // still re-fetch in background to stay fresh
    } else {
      setLoadState(isRefresh ? 'refreshing' : 'loading');
    }
    setErrorMsg('');
    try {
      const res = await fetch(
        `${API_BASE}/narrator/insights?client_id=${CLIENT_ID}`,
        { cache: 'no-store' },
      );
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const json = await res.json() as NarratorResponseV2;
      writeNarratorCache(json);
      setData(json);
    } catch (err) {
      if (!data) {
        setErrorMsg(err instanceof Error ? err.message : 'Failed to load insights');
      }
    } finally {
      setLoadState('idle');
    }
  }, [data]);

  useEffect(() => { fetchInsights(); }, [fetchInsights]);

  async function triggerRun() {
    setTriggerMsg('');
    try {
      const profile = profileDef?.key;
      const res = await fetch(
        `${API_BASE}/narrator/run?client_id=${CLIENT_ID}${profile ? `&profile=${profile}` : ''}`,
        { method: 'POST' },
      );
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      setTriggerMsg('Pipeline queued — refresh in a moment.');
    } catch (err) {
      setTriggerMsg(err instanceof Error ? err.message : 'Failed to trigger run');
    }
  }

  function toggleExpand(id: string) {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleEntityFilter(label: string) {
    setEntityFilter(prev => prev === label ? null : label);
  }

  const isLoading = loadState === 'loading';

  // ── Compute filtered signals ──────────────────────────────────────────────
  const allSignals = data ? sortSignals(mergeAllSignals(data)) : [];

  const filteredSignals = allSignals.filter(card => {
    if (severityFilter !== 'all' && card.severity !== severityFilter) return false;
    if (categoryFilter && insightCategory(card) !== categoryFilter) return false;
    if (entityFilter && card.entity_id !== entityFilter && (card as any).entity_label !== entityFilter) return false;
    return true;
  });

  const entityHealth = data?.entity_health ?? [];

  // Period summary and resolved for a footer section
  const resolved = data?.resolved ?? [];

  return (
    <div className="min-h-screen" style={{ background: 'var(--void)' }}>

      {/* ── Page header ── */}
      <div className="flex items-start justify-between gap-4 px-8 pt-8 pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'var(--signal-dim)' }}>
            <Newspaper className="w-5 h-5" style={{ color: 'var(--signal)' }} />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Intelligence Hub</h1>
            <p className="text-sm" style={{ color: 'var(--on-mid)' }}>
              Proactive fleet intelligence · {profileDef?.displayName ?? 'Default'}
              {data && <> · Generated {formatRelativeTime(data.generated_at)}</>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchInsights(true)}
            disabled={loadState !== 'idle'}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors disabled:opacity-50"
            style={{ borderColor: 'var(--wire)', color: 'var(--on-mid)' }}
          >
            <RefreshCw className={`w-4 h-4 ${loadState === 'refreshing' ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={triggerRun}
            disabled={loadState !== 'idle'}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            style={{ background: 'var(--signal)', color: 'var(--on)' }}
          >
            Run Now
          </button>
        </div>
      </div>

      {triggerMsg && (
        <div className="mx-8 mb-4">
          <p className="text-sm px-4 py-2 rounded-lg border" style={{ color: 'var(--on-mid)', background: 'var(--surface)', borderColor: 'var(--wire)' }}>
            {triggerMsg}
          </p>
        </div>
      )}

      {/* ── Loading skeleton ── */}
      {isLoading && (
        <div className="px-8 space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 rounded-lg animate-pulse" style={{ background: 'var(--surface)' }} />
          ))}
        </div>
      )}

      {/* ── Error ── */}
      {!isLoading && errorMsg && (
        <div className="mx-8 flex items-center gap-3 p-4 rounded-lg border" style={{ borderColor: 'rgba(229,0,26,0.3)', background: 'rgba(229,0,26,0.05)', color: 'var(--signal)' }}>
          <AlertCircle className="w-5 h-5 shrink-0" />
          <p className="text-sm">{errorMsg}</p>
        </div>
      )}

      {/* ── Main content ── */}
      {!isLoading && !errorMsg && data && (
        <div className="px-8 pb-8 space-y-6">

          {/* ═══ PULSE HEADER BAR ══════════════════════════════════════════ */}
          <div
            className="flex items-center gap-6 px-5 py-4 rounded-lg"
            style={{ background: 'var(--surface)', border: '1px solid var(--wire)' }}
          >
            {/* Score */}
            <div style={{ flexShrink: 0 }}>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '2rem',
                fontWeight: 700,
                color: 'var(--on)',
                lineHeight: 1,
              }}>
                {data.pulse_score ?? '—'}
              </div>
              <div style={{
                fontFamily: 'var(--font-condensed)',
                fontSize: '0.55rem',
                fontWeight: 700,
                letterSpacing: '0.14em',
                color: 'var(--on-low)',
                textTransform: 'uppercase',
                marginTop: '2px',
              }}>
                Pulse
              </div>
            </div>

            {/* Delta */}
            {data.pulse_delta != null && (
              <div style={{ flexShrink: 0 }}>
                <span style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  color: data.pulse_delta >= 0 ? 'var(--ok)' : 'var(--signal)',
                }}>
                  {data.pulse_delta >= 0 ? '▲' : '▼'} {Math.abs(data.pulse_delta)} pts
                </span>
              </div>
            )}

            {/* Vertical divider */}
            <div style={{ width: '1px', height: '40px', background: 'var(--wire)', flexShrink: 0 }} />

            {/* Digest */}
            {data.digest && (
              <p style={{
                fontFamily: 'var(--font-sans)',
                fontSize: '0.8rem',
                color: 'var(--on-mid)',
                lineHeight: 1.5,
                flex: 1,
              }}>
                {data.digest}
              </p>
            )}

            {/* Summary counts */}
            {Object.keys(data.summary_counts ?? {}).length > 0 && (
              <div className="flex gap-3 flex-wrap" style={{ flexShrink: 0 }}>
                {Object.entries(data.summary_counts ?? {}).map(([tab, count]) => (
                  <div key={tab} style={{ textAlign: 'center' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.1rem', fontWeight: 700, color: 'var(--on)' }}>
                      {count}
                    </div>
                    <div style={{
                      fontFamily: 'var(--font-condensed)',
                      fontSize: '0.5rem',
                      fontWeight: 700,
                      letterSpacing: '0.12em',
                      color: 'var(--on-low)',
                      textTransform: 'uppercase',
                    }}>
                      {tab === 'dq' ? 'DQ' : tab.replace(/_/g, ' ')}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ═══ ENTITY HEALTH CHIPS ════════════════════════════════════════ */}
          {entityHealth.length > 0 && (
            <div
              className="flex gap-2 overflow-x-auto"
              style={{ scrollbarWidth: 'none', paddingBottom: '4px' }}
            >
              {entityHealth.map((eh) => {
                const label = (eh as any).entity_label ?? eh.entity_id;
                const isActive = entityFilter === label;
                return (
                  <button
                    key={eh.entity_id}
                    onClick={() => toggleEntityFilter(label)}
                    style={{
                      flexShrink: 0,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      padding: '4px 10px',
                      background: isActive ? 'var(--surface-raise)' : 'var(--surface)',
                      border: `1px solid ${isActive ? gradeColor(eh.grade) : 'var(--wire)'}`,
                      cursor: 'pointer',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.65rem',
                      color: 'var(--on)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <span>{label}</span>
                    <span style={{
                      fontFamily: 'var(--font-condensed)',
                      fontSize: '0.6rem',
                      fontWeight: 700,
                      color: gradeColor(eh.grade),
                    }}>
                      {eh.grade}
                      {(eh.grade === 'C' || eh.grade === 'D') ? '●' : ''}
                    </span>
                  </button>
                );
              })}
              {entityFilter && (
                <button
                  onClick={() => setEntityFilter(null)}
                  style={{
                    flexShrink: 0,
                    padding: '4px 10px',
                    background: 'none',
                    border: '1px solid var(--wire)',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.6rem',
                    color: 'var(--on-low)',
                  }}
                >
                  Clear ×
                </button>
              )}
            </div>
          )}

          {/* ═══ FILTER BAR ═════════════════════════════════════════════════ */}
          <div
            className="flex flex-wrap items-center gap-3"
            style={{ borderBottom: '1px solid var(--wire)', paddingBottom: '12px' }}
          >
            {/* Severity pills */}
            <div className="flex items-center gap-1">
              {(['all', 'high', 'medium', 'low'] as const).map((sev) => (
                <button
                  key={sev}
                  onClick={() => setSeverityFilter(sev)}
                  style={{
                    padding: '3px 10px',
                    fontFamily: 'var(--font-condensed)',
                    fontSize: '0.6rem',
                    fontWeight: 700,
                    letterSpacing: '0.12em',
                    textTransform: 'uppercase',
                    background: severityFilter === sev ? 'var(--surface-raise)' : 'none',
                    border: `1px solid ${severityFilter === sev ? 'var(--wire-hi)' : 'var(--wire)'}`,
                    cursor: 'pointer',
                    color: severityFilter === sev ? 'var(--on)' : 'var(--on-low)',
                  }}
                >
                  {sev === 'all' ? '● All' : sev === 'high' ? '● High' : sev === 'medium' ? '● Med' : '● Low'}
                </button>
              ))}
            </div>

            <div style={{ width: '1px', height: '20px', background: 'var(--wire)' }} />

            {/* Category chips */}
            {['Anomaly', 'Trend', 'Pipeline', 'DQ', 'Milestone', 'Cross-dim'].map((cat) => (
              <button
                key={cat}
                onClick={() => setCategoryFilter(prev => prev === cat ? null : cat)}
                style={{
                  padding: '3px 10px',
                  fontFamily: 'var(--font-condensed)',
                  fontSize: '0.6rem',
                  fontWeight: 700,
                  letterSpacing: '0.12em',
                  textTransform: 'uppercase',
                  background: categoryFilter === cat ? 'var(--surface-raise)' : 'none',
                  border: `1px solid ${categoryFilter === cat ? 'var(--wire-hi)' : 'var(--wire)'}`,
                  cursor: 'pointer',
                  color: categoryFilter === cat ? 'var(--on)' : 'var(--on-low)',
                }}
              >
                {cat}
              </button>
            ))}

            {/* Signal count */}
            <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
              {filteredSignals.length} signal{filteredSignals.length !== 1 ? 's' : ''}
            </span>
          </div>

          {/* ═══ SIGNAL FEED ════════════════════════════════════════════════ */}
          {filteredSignals.length === 0 ? (
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--on-low)' }}>
              — no signals match active filters
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {filteredSignals.map((card) => {
                const isExpanded = expandedIds.has(card.id);
                const entityLabel = (card as any).entity_label ?? card.entity_id;
                const cat = CATEGORY_LABELS[card.category] ?? card.category;
                const delta = card.delta_pct;

                return (
                  <div
                    key={card.id}
                    style={{
                      borderLeft: severityBorder(card.severity),
                      borderBottom: '1px solid var(--wire)',
                      padding: '12px 16px',
                      paddingLeft: card.severity === 'high' ? '12px' : card.severity === 'medium' ? '13px' : '15px',
                    }}
                  >
                    {/* ── Card header row ── */}
                    <div className="flex items-start justify-between gap-4">
                      <div style={{ flex: 1, minWidth: 0 }}>
                        {/* Entity + metric line */}
                        <div className="flex items-center gap-2 mb-1">
                          <span style={{
                            fontFamily: 'var(--font-condensed)',
                            fontSize: '0.55rem',
                            fontWeight: 700,
                            letterSpacing: '0.14em',
                            color: card.severity === 'high' ? 'var(--signal)' : card.severity === 'medium' ? 'var(--warn)' : 'var(--on-low)',
                            textTransform: 'uppercase',
                            flexShrink: 0,
                          }}>
                            {card.severity}
                          </span>
                          <span style={{
                            fontFamily: 'var(--font-condensed)',
                            fontSize: '0.55rem',
                            letterSpacing: '0.1em',
                            color: 'var(--on-low)',
                            textTransform: 'uppercase',
                          }}>
                            {cat}
                          </span>
                        </div>
                        <h3 style={{
                          fontFamily: 'var(--font-sans)',
                          fontSize: '0.85rem',
                          fontWeight: 500,
                          color: 'var(--on)',
                          lineHeight: 1.3,
                          margin: 0,
                        }}>
                          {entityLabel} · {card.metric_name.replace(/_/g, ' ')}
                        </h3>
                        <p style={{
                          fontFamily: 'var(--font-sans)',
                          fontSize: '0.72rem',
                          color: 'var(--on-mid)',
                          lineHeight: 1.4,
                          marginTop: '4px',
                          marginBottom: 0,
                        }}>
                          {card.title}
                        </p>
                      </div>

                      {/* Delta + expand */}
                      <div className="flex items-center gap-3" style={{ flexShrink: 0 }}>
                        {delta != null && (
                          <span style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '1rem',
                            fontWeight: 700,
                            color: delta >= 0 ? 'var(--ok)' : 'var(--signal)',
                          }}>
                            {delta >= 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(4)}%
                          </span>
                        )}
                      </div>
                    </div>

                    {/* ── Expand/collapse controls ── */}
                    <div className="flex items-center gap-4 mt-2">
                      <button
                        onClick={() => toggleExpand(card.id)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '3px',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.6rem',
                          color: 'var(--on-low)',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: 0,
                        }}
                      >
                        {isExpanded
                          ? <><ChevronDown className="w-3 h-3" /> collapse</>
                          : <><ChevronRight className="w-3 h-3" /> expand</>
                        }
                      </button>

                      {card.nlq_query && (
                        <button
                          onClick={() => router.push(nlqUrl(card.nlq_query!))}
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.6rem',
                            color: 'var(--uplink)',
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            padding: 0,
                          }}
                        >
                          Explore in NLQ →
                        </button>
                      )}
                    </div>

                    {/* ── Expanded body ── */}
                    {isExpanded && (
                      <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--wire)' }}>
                        <p style={{
                          fontFamily: 'var(--font-sans)',
                          fontSize: '0.75rem',
                          color: 'var(--on-mid)',
                          lineHeight: 1.55,
                          marginBottom: '8px',
                        }}>
                          {card.body}
                        </p>

                        {card.suggested_action && (
                          <p style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.65rem',
                            color: 'var(--signal)',
                            letterSpacing: '0.02em',
                            marginBottom: '8px',
                          }}>
                            → {card.suggested_action}
                          </p>
                        )}

                        {card.root_cause_hint && (
                          <p style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.62rem',
                            color: 'var(--on-low)',
                            marginBottom: '8px',
                          }}>
                            Root cause: {card.root_cause_hint}
                          </p>
                        )}

                        {/* Metrics row */}
                        <div className="flex gap-4 flex-wrap">
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
                            Current: <span style={{ color: 'var(--on)' }}>{card.current_value?.toFixed(4)}</span>
                          </span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
                            Baseline: <span style={{ color: 'var(--on)' }}>{card.reference_value?.toFixed(4)}</span>
                          </span>
                          {card.consecutive_periods && card.consecutive_periods > 1 && (
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
                              Consecutive: <span style={{ color: 'var(--on)' }}>{card.consecutive_periods} periods</span>
                            </span>
                          )}
                          {card.confidence && (
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
                              Confidence: <span style={{ color: 'var(--on)' }}>{card.confidence}</span>
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* ═══ RESOLVED / PERIOD SUMMARY (collapsible footer section) ════ */}
          {(resolved.length > 0 || data.period_summary) && (
            <div style={{ border: '1px solid var(--wire)' }}>
              <button
                onClick={() => setPeriodExpanded(p => !p)}
                className="flex items-center justify-between w-full px-4 py-3"
                style={{
                  background: 'var(--surface)',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--on-low)',
                }}
              >
                <span style={{
                  fontFamily: 'var(--font-condensed)',
                  fontSize: '0.6rem',
                  fontWeight: 700,
                  letterSpacing: '0.14em',
                  textTransform: 'uppercase',
                  color: 'var(--on-low)',
                }}>
                  Period Summary {resolved.length > 0 && `· ${resolved.length} resolved`}
                </span>
                {periodExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
              </button>

              {periodExpanded && (
                <div style={{ padding: '16px', borderTop: '1px solid var(--wire)' }}>
                  {/* Period metrics comparison */}
                  {data.period_summary?.metrics && data.period_summary.metrics.length > 0 && (
                    <div style={{ marginBottom: '16px' }}>
                      <p style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.14em', color: 'var(--on-low)', textTransform: 'uppercase', marginBottom: '8px' }}>
                        {data.period_summary.current_period} vs {data.period_summary.previous_period}
                      </p>
                      <div className="flex gap-4 flex-wrap">
                        {data.period_summary.metrics.map((m) => (
                          <div key={m.metric_name} style={{ minWidth: '100px' }}>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.55rem', color: 'var(--on-low)', marginBottom: '2px' }}>
                              {m.metric_label}
                            </div>
                            <div style={{
                              fontFamily: 'var(--font-mono)',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              color: m.direction === 'improved' ? 'var(--ok)' : m.direction === 'declined' ? 'var(--signal)' : 'var(--on-low)',
                            }}>
                              {m.delta_pct > 0 ? '▲' : m.delta_pct < 0 ? '▼' : '—'} {Math.abs(m.delta_pct).toFixed(4)}%
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Resolved signals */}
                  {resolved.length > 0 && (
                    <div>
                      <p style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.14em', color: 'var(--on-low)', textTransform: 'uppercase', marginBottom: '8px' }}>
                        Recently Resolved ({resolved.length})
                      </p>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        {resolved.map((card) => (
                          <div key={card.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0' }}>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--ok)' }}>✓</span>
                            <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', color: 'var(--on-mid)' }}>{card.title}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ═══ DATA GOVERNANCE SCORECARD ══════════════════════════════════ */}
          {data.dq_scorecard && (
            <div style={{ border: '1px solid var(--wire)' }}>
              <button
                onClick={() => setDqExpanded(p => !p)}
                className="flex items-center justify-between w-full px-4 py-3"
                style={{
                  background: 'var(--surface)',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <div className="flex items-center gap-4">
                  <span style={{
                    fontFamily: 'var(--font-condensed)',
                    fontSize: '0.6rem',
                    fontWeight: 700,
                    letterSpacing: '0.14em',
                    textTransform: 'uppercase',
                    color: 'var(--on-low)',
                  }}>
                    Data Governance
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    color: 'var(--on)',
                  }}>
                    DQ {data.dq_scorecard.overall_score}
                    {data.dq_scorecard.delta_vs_last != null && (
                      <span style={{
                        fontSize: '0.65rem',
                        color: (data.dq_scorecard.delta_vs_last ?? 0) >= 0 ? 'var(--ok)' : 'var(--signal)',
                        marginLeft: '6px',
                      }}>
                        {(data.dq_scorecard.delta_vs_last ?? 0) >= 0 ? '▲' : '▼'}{Math.abs(data.dq_scorecard.delta_vs_last ?? 0)}
                      </span>
                    )}
                  </span>
                </div>
                {dqExpanded ? <ChevronDown className="w-3 h-3" style={{ color: 'var(--on-low)' }} /> : <ChevronRight className="w-3 h-3" style={{ color: 'var(--on-low)' }} />}
              </button>

              {dqExpanded && (
                <div style={{ padding: '16px', borderTop: '1px solid var(--wire)' }}>
                  {/* Field completeness bars */}
                  <p style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.14em', color: 'var(--on-low)', textTransform: 'uppercase', marginBottom: '12px' }}>
                    Field Completeness
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {data.dq_scorecard.fields.slice(0, 8).map((f) => (
                      <div key={f.field_name}>
                        <div className="flex items-center justify-between mb-1">
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-mid)' }}>
                            {f.field_name.replace(/_/g, ' ')}
                          </span>
                          <span style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.6rem',
                            color: f.pct_complete >= 90 ? 'var(--ok)' : f.pct_complete >= 70 ? 'var(--warn)' : 'var(--signal)',
                          }}>
                            {f.pct_complete.toFixed(4)}%
                          </span>
                        </div>
                        <div style={{ height: '3px', background: 'var(--surface-raise)', borderRadius: '1px' }}>
                          <div style={{
                            height: '100%',
                            width: `${f.pct_complete}%`,
                            background: f.pct_complete >= 90 ? 'var(--ok)' : f.pct_complete >= 70 ? 'var(--warn)' : 'var(--signal)',
                            borderRadius: '1px',
                          }} />
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* 6-month DQ trend */}
                  {data.dq_trend && data.dq_trend.length > 0 && (
                    <div style={{ marginTop: '16px' }}>
                      <p style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.14em', color: 'var(--on-low)', textTransform: 'uppercase', marginBottom: '8px' }}>
                        DQ Trend
                      </p>
                      <div className="flex items-end gap-2">
                        {data.dq_trend.slice(-6).map((pt) => (
                          <div key={pt.period} style={{ flex: 1, textAlign: 'center' }}>
                            <div style={{
                              height: `${Math.round((pt.score / 100) * 40)}px`,
                              background: pt.score >= 80 ? 'var(--ok)' : pt.score >= 60 ? 'var(--warn)' : 'var(--signal)',
                              minHeight: '3px',
                              marginBottom: '4px',
                            }} />
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.5rem', color: 'var(--on-low)' }}>
                              {pt.period.slice(-3)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

        </div>
      )}
    </div>
  );
}
