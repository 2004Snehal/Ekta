'use client';

import { cn } from '@/lib/utils';
import type { FunnelSummary, FunnelByEntity } from '@/types/narrator';

interface FunnelVizProps {
  funnel: FunnelSummary;
}

const STAGE_COLORS: Record<string, string> = {
  uploaded:  'var(--uplink)',
  processed: 'var(--warn)',
  published: 'var(--ok)',
};

const STATUS_STYLE: Record<string, string> = {
  critical: 'text-red-400 bg-red-500/10 border-red-500/30',
  watch:    'text-amber-400 bg-amber-500/10 border-amber-500/30',
  healthy:  'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
};

export function FunnelViz({ funnel }: FunnelVizProps) {
  const maxCount = Math.max(...funnel.stages.map(s => s.count), 1);

  return (
    <div className="space-y-6">
      {/* Fleet-level funnel */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="section-id">Publishing Funnel</h3>
          <div className="flex items-center gap-4 text-xs">
            <span style={{ color: 'var(--on-low)' }}>
              Fleet publish rate:{' '}
              <span className="font-mono font-bold" style={{ color: funnel.fleet_publish_rate >= 70 ? 'var(--ok)' : funnel.fleet_publish_rate >= 50 ? 'var(--warn)' : 'var(--signal)' }}>
                {funnel.fleet_publish_rate.toFixed(1)}%
              </span>
            </span>
            {funnel.total_gap > 0 && (
              <span style={{ color: 'var(--signal)' }} className="font-mono">
                {funnel.total_gap} unpublished
              </span>
            )}
          </div>
        </div>

        {/* Horizontal funnel bars */}
        <div className="space-y-2">
          {funnel.stages.map((stage) => {
            const pct = (stage.count / maxCount) * 100;
            const color = STAGE_COLORS[stage.stage] ?? 'var(--on-low)';
            return (
              <div key={stage.stage} className="flex items-center gap-3">
                <span
                  className="text-[0.6rem] w-20 text-right uppercase tracking-wider shrink-0"
                  style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)' }}
                >
                  {stage.stage}
                </span>
                <div className="flex-1 h-6 rounded" style={{ background: 'var(--wire)' }}>
                  <div
                    className="h-6 rounded flex items-center px-2"
                    style={{ width: `${Math.max(pct, 3)}%`, background: color, transition: 'width 0.8s ease-out' }}
                  >
                    <span className="text-xs font-mono font-bold text-white whitespace-nowrap">
                      {stage.count.toLocaleString()}
                    </span>
                  </div>
                </div>
                <span className="text-xs font-mono w-12 text-right" style={{ color: 'var(--on-mid)' }}>
                  {stage.pct_of_uploaded.toFixed(0)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Per-channel breakdown */}
      {funnel.by_channel.length > 0 && (
        <div className="space-y-3">
          <h3 className="section-id">Channel Breakdown</h3>
          <div className="space-y-2">
            {funnel.by_channel
              .sort((a, b) => a.publish_rate - b.publish_rate)
              .map((ch) => (
                <ChannelFunnelRow key={ch.entity_id} channel={ch} />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ChannelFunnelRow({ channel }: { channel: FunnelByEntity }) {
  return (
    <div className="flex items-center gap-3 p-2 rounded border border-border/30 hover:border-border/60 transition-colors">
      <span className="text-sm font-medium text-foreground w-32 truncate shrink-0">{channel.entity_label}</span>
      {/* Mini stacked bar */}
      <div className="flex-1 flex items-center gap-1">
        <div className="flex-1 h-3 rounded overflow-hidden flex" style={{ background: 'var(--wire)' }}>
          {channel.uploaded > 0 && (
            <>
              <div
                className="h-3"
                style={{
                  width: `${(channel.published / channel.uploaded) * 100}%`,
                  background: 'var(--ok)',
                  transition: 'width 0.6s ease-out',
                }}
              />
              <div
                className="h-3"
                style={{
                  width: `${((channel.processed - channel.published) / channel.uploaded) * 100}%`,
                  background: 'var(--warn)',
                  transition: 'width 0.6s ease-out',
                }}
              />
            </>
          )}
        </div>
      </div>
      <span className="text-xs font-mono w-12 text-right font-bold"
        style={{ color: channel.publish_rate >= 70 ? 'var(--ok)' : channel.publish_rate >= 50 ? 'var(--warn)' : 'var(--signal)' }}
      >
        {channel.publish_rate.toFixed(0)}%
      </span>
      <span className={cn('text-[0.55rem] font-bold px-1.5 py-0.5 rounded border uppercase tracking-wider', STATUS_STYLE[channel.status])}>
        {channel.status}
      </span>
      {channel.gap > 0 && (
        <span className="text-xs font-mono" style={{ color: 'var(--on-low)' }}>
          -{channel.gap}
        </span>
      )}
    </div>
  );
}
