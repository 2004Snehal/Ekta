'use client';

import { useState } from 'react';
import { Activity, BarChart3, Zap, TrendingUp, TrendingDown, Minus, HelpCircle } from 'lucide-react';
import type { NarratorResponseV2, InsightCardData } from '@/types/narrator';

interface FleetActivitySummaryProps {
  data: NarratorResponseV2;
}

/** Tooltip on hover — explains what a metric means in plain language. */
function Tooltip({ text }: { text: string }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative inline-flex">
      <button
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onClick={() => setVisible(v => !v)}
        className="text-muted-foreground/40 hover:text-muted-foreground transition-colors"
        aria-label="What does this mean?"
      >
        <HelpCircle className="w-3.5 h-3.5" />
      </button>
      {visible && (
        <div
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 p-2.5 rounded-lg border text-xs leading-relaxed shadow-lg"
          style={{ background: 'var(--surface-raise)', borderColor: 'var(--wire)', color: 'var(--on-mid)' }}
        >
          {text}
          <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0" style={{ borderLeft: '5px solid transparent', borderRight: '5px solid transparent', borderTop: '5px solid var(--wire)' }} />
        </div>
      )}
    </div>
  );
}

/** Mini inline SVG sparkline. */
function MiniSparkline({ values, color }: { values: number[]; color: string }) {
  if (values.length < 2) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const w = 100;
  const h = 28;
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  }).join(' ');

  const lastY = h - ((values[values.length - 1] - min) / range) * (h - 4) - 2;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-7" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={w} cy={lastY} r="3" fill={color} opacity="0.8" />
    </svg>
  );
}

/** Severity stacked bar. */
function SeverityBar({ insights }: { insights: InsightCardData[] }) {
  const high = insights.filter(c => c.severity === 'high').length;
  const medium = insights.filter(c => c.severity === 'medium').length;
  const low = insights.filter(c => c.severity === 'low').length;
  const total = insights.length || 1;

  return (
    <div className="space-y-1.5">
      <div className="flex h-2 rounded-full overflow-hidden" style={{ background: 'var(--wire)' }}>
        {high > 0 && <div style={{ width: `${(high / total) * 100}%`, background: 'var(--signal)' }} />}
        {medium > 0 && <div style={{ width: `${(medium / total) * 100}%`, background: 'var(--warn)' }} />}
        {low > 0 && <div style={{ width: `${(low / total) * 100}%`, background: 'var(--uplink)' }} />}
      </div>
      <div className="flex gap-3 text-[0.6rem] uppercase tracking-wider" style={{ fontFamily: 'var(--font-condensed)', color: 'var(--on-low)' }}>
        {high > 0 && <span><span style={{ color: 'var(--signal)' }}>{high}</span> critical</span>}
        {medium > 0 && <span><span style={{ color: 'var(--warn)' }}>{medium}</span> watch</span>}
        {low > 0 && <span><span style={{ color: 'var(--uplink)' }}>{low}</span> info</span>}
        {insights.length === 0 && <span>No signals detected</span>}
      </div>
    </div>
  );
}

export function FleetActivitySummary({ data }: FleetActivitySummaryProps) {
  const insights = data.insights ?? [];
  const periodSummary = data.period_summary;
  const entityHealth = data.entity_health ?? [];

  const avgHealth = entityHealth.length > 0
    ? Math.round(entityHealth.reduce((s, e) => s + e.score, 0) / entityHealth.length)
    : null;

  // Sparkline from signal deltas
  const insightValues = insights.slice(0, 8).map(c => Math.abs(c.delta_pct ?? 0));

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {/* Card 1: Active Signals */}
      <div className="rounded-lg p-4 border border-border/40 space-y-3" style={{ background: 'var(--surface)' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4" style={{ color: 'var(--signal)' }} />
            <span className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)' }}>
              Active Signals
            </span>
            <Tooltip text="The number of unusual patterns the system detected in your data this period. Critical = needs immediate attention, Watch = monitor closely, Info = good to know." />
          </div>
          <span className="font-mono text-xl font-bold text-foreground">{insights.length}</span>
        </div>
        <SeverityBar insights={insights as InsightCardData[]} />
        {insightValues.length >= 2 && (
          <MiniSparkline values={insightValues} color="var(--signal)" />
        )}
      </div>

      {/* Card 2: Fleet Health */}
      <div className="rounded-lg p-4 border border-border/40 space-y-3" style={{ background: 'var(--surface)' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4" style={{ color: 'var(--uplink)' }} />
            <span className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)' }}>
              Fleet Health
            </span>
            <Tooltip text="Each bar represents one of your channels, scored 0–100 based on publish rate, activity level, data quality, and trends. A (green) = excellent, B (blue) = good, C (amber) = needs attention, D (red) = critical." />
          </div>
          {avgHealth != null ? (
            <span className="font-mono text-xl font-bold" style={{ color: avgHealth >= 60 ? 'var(--ok)' : avgHealth >= 40 ? 'var(--warn)' : 'var(--signal)' }}>
              {avgHealth}
            </span>
          ) : (
            <span className="font-mono text-xl font-bold" style={{ color: 'var(--on-low)' }}>—</span>
          )}
        </div>
        {entityHealth.length > 0 ? (
          <div className="space-y-1.5">
            <div className="flex gap-1">
              {entityHealth.slice(0, 10).map((e, i) => (
                <div
                  key={i}
                  className="h-6 rounded-sm flex-1 min-w-[6px]"
                  title={`${e.entity_label}: ${e.score}/100 (Grade ${e.grade})`}
                  style={{
                    background: e.grade === 'A' ? 'var(--ok)' : e.grade === 'B' ? 'var(--uplink)' : e.grade === 'C' ? 'var(--warn)' : 'var(--signal)',
                    opacity: 0.3 + (e.score / 100) * 0.7,
                  }}
                />
              ))}
            </div>
            <p className="text-[0.6rem] uppercase tracking-wider" style={{ fontFamily: 'var(--font-condensed)', color: 'var(--on-low)' }}>
              {entityHealth.filter(e => e.grade === 'A' || e.grade === 'B').length}/{entityHealth.length} channels healthy
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            <div className="flex gap-1">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-6 w-full rounded-sm animate-pulse" style={{ background: 'var(--wire)', animationDelay: `${i * 120}ms` }} />
              ))}
            </div>
            <p className="text-[0.6rem] uppercase tracking-wider" style={{ fontFamily: 'var(--font-condensed)', color: 'var(--on-low)' }}>
              Run v2 pipeline for health scores
            </p>
          </div>
        )}
      </div>

      {/* Card 3: Period Snapshot */}
      <div className="rounded-lg p-4 border border-border/40 space-y-3" style={{ background: 'var(--surface)' }}>
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4" style={{ color: 'var(--ok)' }} />
          <span className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)' }}>
            Period Snapshot
          </span>
          <Tooltip text="Key metrics compared month-over-month. Green arrow = improved vs last month, red arrow = declined. The percentage shows how much it changed." />
        </div>
        {periodSummary ? (
          <div className="space-y-2">
            {periodSummary.metrics.slice(0, 3).map(m => {
              const DirIcon = m.direction === 'improved' ? TrendingUp : m.direction === 'declined' ? TrendingDown : Minus;
              const dirColor = m.direction === 'improved' ? 'var(--ok)' : m.direction === 'declined' ? 'var(--signal)' : 'var(--on-low)';
              return (
                <div key={m.metric_name} className="flex items-center justify-between gap-2">
                  <span className="text-xs text-foreground truncate">{m.metric_label}</span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="font-mono text-sm font-medium text-foreground">
                      {m.current_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                    <DirIcon className="w-3 h-3" style={{ color: dirColor }} />
                    <span className="font-mono text-xs" style={{ color: dirColor }}>
                      {m.delta_pct > 0 ? '+' : ''}{m.delta_pct.toFixed(0)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="space-y-2 py-1">
            <div className="flex items-center justify-between">
              <span className="text-xs" style={{ color: 'var(--on-low)' }}>Data period</span>
              <span className="text-xs font-mono text-foreground">{data.period ?? '—'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs" style={{ color: 'var(--on-low)' }}>Last generated</span>
              <span className="text-xs font-mono text-foreground">
                {data.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs" style={{ color: 'var(--on-low)' }}>Total insights</span>
              <span className="text-xs font-mono text-foreground">{insights.length} cards</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
