'use client';

import type { NarratorResponseV2 } from '@/types/narrator';
import { PulseScoreRing } from './PulseScoreRing';
import { HealthLeaderboard } from './HealthLeaderboard';
import { PeriodComparisonGrid } from './PeriodComparisonGrid';
import { InsightCardV2 } from './InsightCardV2';
import { FleetActivitySummary } from './FleetActivitySummary';
import { PlayCircle, Zap } from 'lucide-react';

interface PulseTabProps {
  data: NarratorResponseV2;
  apiBaseUrl: string;
}

export function PulseTab({ data, apiBaseUrl }: PulseTabProps) {
  const entityHealth = data.entity_health ?? [];
  const channels = entityHealth.filter(e => e.entity_type === 'channel');
  const users = entityHealth.filter(e => e.entity_type === 'user');

  const topSignals = data.top_signals ?? [];
  const followUps = data.follow_ups ?? [];
  const resolved = data.resolved ?? [];
  const hasV2Content = topSignals.length > 0 || followUps.length > 0 || entityHealth.length > 0;

  return (
    <div className="space-y-8">
      {/* Top strip: Pulse ring + digest */}
      <div className="flex flex-col md:flex-row gap-8 items-start">
        <PulseScoreRing score={data.pulse_score ?? 0} delta={data.pulse_delta} />

        <div className="flex-1 space-y-4">
          {/* Executive Digest */}
          {data.digest && (
            <div className="p-4 rounded border-l-2" style={{ borderLeftColor: 'var(--signal)', background: 'var(--signal-dim)' }}>
              <p className="text-xs font-bold uppercase tracking-widest mb-1" style={{ color: 'var(--signal)', fontFamily: 'var(--font-condensed)' }}>
                Executive Digest
              </p>
              <p className="text-sm text-foreground leading-relaxed">{data.digest}</p>
            </div>
          )}

          {/* Summary counts — only show if v2 ran */}
          {Object.keys(data.summary_counts ?? {}).length > 0 && (
            <div className="flex gap-3 flex-wrap">
              {Object.entries(data.summary_counts ?? {}).map(([tab, count]) => (
                <div key={tab} className="px-3 py-2 rounded border border-border/40" style={{ background: 'var(--surface)' }}>
                  <span className="font-mono text-lg font-bold text-foreground">{count}</span>
                  <span className="text-xs ml-2 capitalize" style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                    {tab === 'dq' ? 'DQ issues' : tab.replace(/_/g, ' ')}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Onboarding hint — when no v2 data yet */}
          {!hasV2Content && !data.digest && (
            <div className="p-4 rounded border border-border/40 flex items-start gap-3" style={{ background: 'var(--surface)' }}>
              <PlayCircle className="w-5 h-5 mt-0.5 shrink-0" style={{ color: 'var(--uplink)' }} />
              <div>
                <p className="text-sm font-semibold text-foreground">Intelligence hub ready</p>
                <p className="text-xs mt-1 leading-relaxed" style={{ color: 'var(--on-mid)' }}>
                  Click <strong>Run Now</strong> above to generate your first analysis. The system will scan 7 detectors across your data — it takes about 30–60 seconds.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Fleet activity summary — always visible, shows live stats */}
      <FleetActivitySummary data={data} />

      {/* Period comparison — only when v2 ran */}
      {data.period_summary && (
        <PeriodComparisonGrid summary={data.period_summary} />
      )}

      {/* Top Signals — v2 only, highest severity across all tabs */}
      {topSignals.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4" style={{ color: 'var(--signal)' }} />
            <h3 className="section-id">Top Signals This Period</h3>
            <span className="text-xs" style={{ color: 'var(--on-low)' }}>— highest impact across all tabs</span>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {topSignals.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </div>
      )}

      {/* Follow-ups — v2 only */}
      {followUps.length > 0 && (
        <div className="space-y-3">
          <h3 className="section-id">Active Follow-ups</h3>
          <p className="text-xs" style={{ color: 'var(--on-low)' }}>Issues that were flagged in a previous period and are still active or getting worse.</p>
          <div className="grid gap-3 md:grid-cols-2">
            {followUps.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </div>
      )}

      {/* Resolved — v2 only */}
      {resolved.length > 0 && (
        <div className="space-y-3">
          <h3 className="section-id">Recently Resolved</h3>
          <p className="text-xs" style={{ color: 'var(--on-low)' }}>Issues that were flagged before but have returned to normal this period.</p>
          <div className="space-y-2">
            {resolved.map(card => (
              <InsightCardV2 key={card.id} card={card} compact />
            ))}
          </div>
        </div>
      )}

      {/* Health leaderboards — v2 only */}
      {channels.length > 0 && <HealthLeaderboard entities={channels} title="Channel Health" />}
      {users.length > 0 && <HealthLeaderboard entities={users} title="User Health" />}
    </div>
  );
}
