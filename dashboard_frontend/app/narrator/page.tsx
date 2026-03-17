'use client';

import { useCallback, useEffect, useState } from 'react';
import { Newspaper, RefreshCw, AlertCircle, Clock } from 'lucide-react';
import { useProfile } from '@/lib/profiles';
import { InsightCard } from '@/components/InsightCard';
import type { InsightCardData } from '@/components/InsightCard';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '');
const CLIENT_ID = 1;

interface NarratorPayload {
  client_id: number;
  period: string;
  generated_at: string;
  data_as_of: string;
  digest?: string | null;
  insights: InsightCardData[];
}

type LoadState = 'idle' | 'loading' | 'refreshing' | 'error';

function SeveritySummary({ insights }: { insights: InsightCardData[] }) {
  const high   = insights.filter(i => i.severity === 'high').length;
  const medium = insights.filter(i => i.severity === 'medium').length;
  const low    = insights.filter(i => i.severity === 'low').length;

  return (
    <div className="flex gap-2">
      {high > 0 && (
        <span style={{
          fontSize: '0.72rem', fontWeight: 700, padding: '3px 10px', borderRadius: '20px',
          background: 'rgba(196, 85, 58, 0.1)', color: 'var(--signal)',
          fontFamily: 'var(--font-sans)',
        }}>
          {high} high
        </span>
      )}
      {medium > 0 && (
        <span style={{
          fontSize: '0.72rem', fontWeight: 700, padding: '3px 10px', borderRadius: '20px',
          background: 'rgba(198, 139, 44, 0.1)', color: 'var(--warn)',
          fontFamily: 'var(--font-sans)',
        }}>
          {medium} medium
        </span>
      )}
      {low > 0 && (
        <span style={{
          fontSize: '0.72rem', fontWeight: 700, padding: '3px 10px', borderRadius: '20px',
          background: 'rgba(91, 126, 161, 0.1)', color: 'var(--uplink)',
          fontFamily: 'var(--font-sans)',
        }}>
          {low} low
        </span>
      )}
    </div>
  );
}

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

export default function NarratorPage() {
  const { profileDef } = useProfile();
  const [data,        setData]        = useState<NarratorPayload | null>(null);
  const [loadState,   setLoadState]   = useState<LoadState>('idle');
  const [errorMsg,    setErrorMsg]    = useState<string>('');
  const [triggerMsg,  setTriggerMsg]  = useState<string>('');

  const fetchInsights = useCallback(async (isRefresh = false) => {
    setLoadState(isRefresh ? 'refreshing' : 'loading');
    setErrorMsg('');
    try {
      const res = await fetch(
        `${API_BASE}/narrator/insights?client_id=${CLIENT_ID}`,
        { cache: 'no-store' },
      );
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const json = await res.json();
      const payload: NarratorPayload = json.insights ? json : json;
      setData(payload);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load insights');
    } finally {
      setLoadState('idle');
    }
  }, []);

  useEffect(() => { fetchInsights(); }, [fetchInsights]);

  async function triggerRun() {
    setTriggerMsg('');
    try {
      const res = await fetch(
        `${API_BASE}/narrator/run?client_id=${CLIENT_ID}`,
        { method: 'POST' },
      );
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      setTriggerMsg('Pipeline queued — refresh in a moment.');
    } catch (err) {
      setTriggerMsg(err instanceof Error ? err.message : 'Failed to trigger run');
    }
  }

  const isLoading = loadState === 'loading';
  const insights  = data?.insights ?? [];

  return (
    <div style={{ minHeight: '100vh', background: 'var(--void)', padding: '32px' }}>

      {/* Page header */}
      <div className="flex items-start justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          <div style={{
            width: '44px', height: '44px',
            background: 'var(--signal-dim)',
            borderRadius: '14px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Newspaper style={{ width: '20px', height: '20px', color: 'var(--signal)' }} />
          </div>
          <div>
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.6rem', fontWeight: 700, color: 'var(--on)', marginBottom: '2px' }}>
              Insight Narrator
            </h1>
            <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-mid)' }}>
              Automatically surfaced anomalies, trends & milestones · {profileDef.displayName}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchInsights(true)}
            disabled={loadState !== 'idle'}
            style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '8px 16px',
              borderRadius: '10px',
              border: '1px solid var(--wire)',
              background: 'var(--surface)',
              color: 'var(--on-mid)',
              fontFamily: 'var(--font-sans)',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
              opacity: loadState !== 'idle' ? 0.5 : 1,
              transition: 'all 0.2s',
            }}
          >
            <RefreshCw style={{ width: '14px', height: '14px', animation: loadState === 'refreshing' ? 'spin 1s linear infinite' : 'none' }} />
            Refresh
          </button>
          <button
            onClick={triggerRun}
            disabled={loadState !== 'idle'}
            style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '8px 18px',
              borderRadius: '10px',
              border: 'none',
              background: 'var(--signal)',
              color: '#fff',
              fontFamily: 'var(--font-sans)',
              fontSize: '0.82rem',
              fontWeight: 700,
              cursor: 'pointer',
              opacity: loadState !== 'idle' ? 0.5 : 1,
              transition: 'opacity 0.2s',
            }}
          >
            Run Now
          </button>
        </div>
      </div>

      {triggerMsg && (
        <div style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '0.82rem',
          color: 'var(--on-mid)',
          background: 'var(--surface)',
          border: '1px solid var(--wire)',
          borderRadius: '10px',
          padding: '10px 16px',
          marginBottom: '24px',
        }}>
          {triggerMsg}
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {[...Array(3)].map((_, i) => (
            <div key={i} style={{
              height: '120px',
              borderRadius: '16px',
              background: 'var(--surface)',
              border: '1px solid var(--wire)',
              opacity: 0.6,
            }} />
          ))}
        </div>
      )}

      {/* Error */}
      {!isLoading && errorMsg && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '12px',
          padding: '16px 20px',
          borderRadius: '12px',
          border: '1px solid rgba(196, 85, 58, 0.3)',
          background: 'rgba(196, 85, 58, 0.06)',
          color: 'var(--signal)',
          fontFamily: 'var(--font-sans)',
          fontSize: '0.85rem',
        }}>
          <AlertCircle style={{ width: '18px', height: '18px', flexShrink: 0 }} />
          <p>{errorMsg}</p>
        </div>
      )}

      {/* Content */}
      {!isLoading && !errorMsg && data && (
        <>
          {/* Meta bar */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            flexWrap: 'wrap', gap: '12px',
            padding: '14px 18px',
            borderRadius: '12px',
            background: 'var(--surface)',
            border: '1px solid var(--wire)',
            marginBottom: '24px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--on-mid)', fontFamily: 'var(--font-sans)', fontSize: '0.82rem' }}>
              <Clock style={{ width: '14px', height: '14px' }} />
              Generated {formatRelativeTime(data.generated_at)} · Period: {data.period}
            </div>
            <SeveritySummary insights={insights} />
          </div>

          {/* Weekly digest card */}
          {data.digest && (
            <div style={{
              padding: '16px 20px',
              borderRadius: '12px',
              border: '1px solid rgba(196, 85, 58, 0.2)',
              background: 'rgba(196, 85, 58, 0.04)',
              marginBottom: '24px',
            }}>
              <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', fontWeight: 700, color: 'var(--signal)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: '6px' }}>
                Weekly Digest
              </p>
              <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.88rem', color: 'var(--on)', lineHeight: 1.65 }}>
                {data.digest}
              </p>
            </div>
          )}

          {/* Insight cards */}
          {insights.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '64px 0', color: 'var(--on-low)' }}>
              <div style={{ width: '56px', height: '56px', borderRadius: '16px', background: 'var(--surface)', border: '1px solid var(--wire)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                <Newspaper style={{ width: '24px', height: '24px', opacity: 0.4 }} />
              </div>
              <p style={{ fontFamily: 'var(--font-display)', fontSize: '1.1rem', fontWeight: 600, color: 'var(--on)', marginBottom: '6px' }}>No new insights this period</p>
              <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-low)' }}>Everything looks normal, or all recent anomalies were already surfaced.</p>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {insights.map((card) => (
                <InsightCard
                  key={card.id}
                  card={card}
                  apiBaseUrl={API_BASE}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
