'use client';

import type { PeriodSummary } from '@/types/narrator';

interface PeriodComparisonGridProps {
  summary: PeriodSummary;
}

export function PeriodComparisonGrid({ summary }: PeriodComparisonGridProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="section-id">Period Comparison</h3>
        <div className="flex gap-3 text-xs" style={{ color: 'var(--on-low)' }}>
          <span>{summary.current_period} vs {summary.previous_period}</span>
          <span className="font-mono" style={{ color: 'var(--ok)' }}>{summary.improved_count} improved</span>
          <span className="font-mono" style={{ color: 'var(--signal)' }}>{summary.declined_count} declined</span>
        </div>
      </div>

      <div className="period-grid">
        {/* Header */}
        <div className="text-on-low uppercase tracking-wider" style={{ fontFamily: 'var(--font-condensed)', fontWeight: 700 }}>Metric</div>
        <div className="text-on-low uppercase tracking-wider text-right" style={{ fontFamily: 'var(--font-condensed)', fontWeight: 700 }}>Previous</div>
        <div className="text-on-low uppercase tracking-wider text-right" style={{ fontFamily: 'var(--font-condensed)', fontWeight: 700 }}>Current</div>
        <div className="text-on-low uppercase tracking-wider text-right" style={{ fontFamily: 'var(--font-condensed)', fontWeight: 700 }}>Change</div>

        {/* Rows */}
        {summary.metrics.map((m) => (
          <>
            <div key={`${m.metric_name}-label`} className="text-foreground text-sm">{m.metric_label}</div>
            <div key={`${m.metric_name}-prev`} className="text-right font-mono" style={{ color: 'var(--on-mid)' }}>
              {m.previous_value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
            </div>
            <div key={`${m.metric_name}-curr`} className="text-right font-mono text-foreground font-medium">
              {m.current_value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
            </div>
            <div key={`${m.metric_name}-delta`} className="text-right">
              <span className={`delta-chip ${m.direction === 'improved' ? 'positive' : m.direction === 'declined' ? 'negative' : 'neutral'}`}>
                {m.delta_pct > 0 ? '+' : ''}{m.delta_pct.toFixed(1)}%
              </span>
            </div>
          </>
        ))}
      </div>
    </div>
  );
}
