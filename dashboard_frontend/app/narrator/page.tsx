'use client';

import { useCallback, useEffect, useState } from 'react';
import { Newspaper, RefreshCw, AlertCircle, Clock } from 'lucide-react';
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
    <div className="flex gap-3">
      {high > 0 && (
        <span className="text-xs font-semibold px-2 py-1 rounded-full bg-red-500/20 text-red-400 border border-red-500/30">
          {high} high
        </span>
      )}
      {medium > 0 && (
        <span className="text-xs font-semibold px-2 py-1 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30">
          {medium} medium
        </span>
      )}
      {low > 0 && (
        <span className="text-xs font-semibold px-2 py-1 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30">
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
      // The endpoint returns either the full payload or the cached insights dict
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
    <div className="min-h-screen bg-background p-6 space-y-6">

      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
            <Newspaper className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Insight Narrator</h1>
            <p className="text-muted-foreground text-sm">
              Automatically surfaced anomalies, trends, and milestones — no dashboard reading required.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchInsights(true)}
            disabled={loadState !== 'idle'}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loadState === 'refreshing' ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={triggerRun}
            disabled={loadState !== 'idle'}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            Run Now
          </button>
        </div>
      </div>

      {triggerMsg && (
        <p className="text-sm text-muted-foreground bg-secondary/50 border border-border rounded-lg px-4 py-2">
          {triggerMsg}
        </p>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 rounded-lg bg-secondary/30 animate-pulse" />
          ))}
        </div>
      )}

      {/* Error */}
      {!isLoading && errorMsg && (
        <div className="flex items-center gap-3 p-4 rounded-lg border border-red-500/30 bg-red-950/20 text-red-400">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <p className="text-sm">{errorMsg}</p>
        </div>
      )}

      {/* Content */}
      {!isLoading && !errorMsg && data && (
        <>
          {/* Meta bar */}
          <div className="flex items-center justify-between flex-wrap gap-3 p-4 rounded-lg bg-secondary/30 border border-border/40">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="w-4 h-4" />
              Generated {formatRelativeTime(data.generated_at)} · Period: {data.period}
            </div>
            <SeveritySummary insights={insights} />
          </div>

          {/* Weekly digest card */}
          {data.digest && (
            <div className="p-4 rounded-lg border border-primary/20 bg-primary/5 space-y-1">
              <p className="text-xs font-semibold text-primary uppercase tracking-wide">Weekly Digest</p>
              <p className="text-sm text-foreground leading-relaxed">{data.digest}</p>
            </div>
          )}

          {/* Insight cards */}
          {insights.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <Newspaper className="w-12 h-12 mx-auto mb-4 opacity-30" />
              <p className="font-medium">No new insights this period</p>
              <p className="text-sm mt-1">Everything looks normal, or all recent anomalies were already surfaced.</p>
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
