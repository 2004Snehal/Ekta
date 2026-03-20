'use client';

import { useCallback, useEffect, useState } from 'react';
import { Newspaper, RefreshCw, AlertCircle, Clock, Activity, Eye, GitBranch, Shield } from 'lucide-react';
import { useProfile } from '@/lib/profiles';
import type { NarratorResponseV2 } from '@/types/narrator';
import { PulseTab } from '@/components/narrator/PulseTab';
import { WatchlistTab } from '@/components/narrator/WatchlistTab';
import { PipelineTab } from '@/components/narrator/PipelineTab';
import { DataGovernanceTab } from '@/components/narrator/DataGovernanceTab';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '');
const CLIENT_ID = 1;

type TabId = 'pulse' | 'watchlist' | 'pipeline' | 'data_governance';

interface TabDef {
  id: TabId;
  label: string;
  icon: typeof Activity;
  countKey?: string;
}

const TABS: TabDef[] = [
  { id: 'pulse',           label: 'Pulse',                  icon: Activity },
  { id: 'watchlist',       label: 'Watchlist & Patterns',   icon: Eye,         countKey: 'watchlist' },
  { id: 'pipeline',        label: 'Pipeline & Operations',  icon: GitBranch,   countKey: 'pipeline' },
  { id: 'data_governance', label: 'Data Governance',        icon: Shield,      countKey: 'dq' },
];

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

export default function NarratorPage() {
  const { profileDef } = useProfile();
  const [data,       setData]       = useState<NarratorResponseV2 | null>(null);
  const [loadState,  setLoadState]  = useState<LoadState>('idle');
  const [errorMsg,   setErrorMsg]   = useState('');
  const [triggerMsg, setTriggerMsg] = useState('');
  const [activeTab,  setActiveTab]  = useState<TabId>('pulse');

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
      setData(json);
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

  const isLoading = loadState === 'loading';

  return (
    <div className="min-h-screen p-8 space-y-6" style={{ background: 'var(--void)' }}>

      {/* ── Page header ── */}
      <div className="flex items-start justify-between gap-4">
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
        <p className="text-sm px-4 py-2 rounded-lg border" style={{ color: 'var(--on-mid)', background: 'var(--surface)', borderColor: 'var(--wire)' }}>
          {triggerMsg}
        </p>
      )}

      {/* ── Loading skeleton ── */}
      {isLoading && (
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 rounded-lg animate-pulse" style={{ background: 'var(--surface)' }} />
          ))}
        </div>
      )}

      {/* ── Error ── */}
      {!isLoading && errorMsg && (
        <div className="flex items-center gap-3 p-4 rounded-lg border" style={{ borderColor: 'rgba(229,0,26,0.3)', background: 'rgba(229,0,26,0.05)', color: 'var(--signal)' }}>
          <AlertCircle className="w-5 h-5 shrink-0" />
          <p className="text-sm">{errorMsg}</p>
        </div>
      )}

      {/* ── Content with tabs ── */}
      {!isLoading && !errorMsg && data && (
        <>
          {/* Tab navigation */}
          <div className="flex items-center gap-1 border-b" style={{ borderColor: 'var(--wire)' }}>
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id;
              const Icon = tab.icon;
              const count = tab.countKey ? ((data.summary_counts ?? {})[tab.countKey] ?? 0) : null;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className="relative flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors"
                  style={{
                    color: isActive ? 'var(--on)' : 'var(--on-low)',
                    fontFamily: 'var(--font-condensed)',
                    fontWeight: 600,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    fontSize: '0.7rem',
                  }}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                  {count != null && count > 0 && (
                    <span
                      className="text-[0.55rem] font-mono font-bold px-1.5 py-0.5 rounded-full"
                      style={{
                        background: isActive ? 'var(--signal-dim)' : 'var(--surface-raise)',
                        color: isActive ? 'var(--signal)' : 'var(--on-low)',
                      }}
                    >
                      {count}
                    </span>
                  )}
                  {/* Active underline */}
                  {isActive && (
                    <span
                      className="absolute bottom-0 left-4 right-4 h-[2px]"
                      style={{ background: 'var(--signal)' }}
                    />
                  )}
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          <div className="pt-2">
            {activeTab === 'pulse' && <PulseTab data={data} apiBaseUrl={API_BASE} />}
            {activeTab === 'watchlist' && <WatchlistTab data={data} apiBaseUrl={API_BASE} />}
            {activeTab === 'pipeline' && <PipelineTab data={data} apiBaseUrl={API_BASE} />}
            {activeTab === 'data_governance' && <DataGovernanceTab data={data} apiBaseUrl={API_BASE} />}
          </div>
        </>
      )}
    </div>
  );
}
