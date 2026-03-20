'use client';

import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, LineChart, Line, Tooltip } from 'recharts';
import type { DQScorecard, DQPeriodScore } from '@/types/narrator';

interface DQScorecardVizProps {
  scorecard: DQScorecard;
  trend?: DQPeriodScore[];
}

function scoreColor(pct: number): string {
  if (pct >= 95) return 'var(--ok)';
  if (pct >= 80) return 'var(--uplink)';
  if (pct >= 60) return 'var(--warn)';
  return 'var(--signal)';
}

function trendIcon(trend: string): string {
  if (trend === 'improving') return '↑';
  if (trend === 'declining') return '↓';
  return '→';
}

export function DQScorecardViz({ scorecard, trend = [] }: DQScorecardVizProps) {
  const barData = scorecard.fields.map(f => ({
    name: f.field_name.replace(/_id$/, '').replace(/_/g, ' '),
    pct: Math.round(f.pct_complete),
    fill: scoreColor(f.pct_complete),
  }));

  return (
    <div className="space-y-6">
      {/* Overall score header */}
      <div className="flex items-center justify-between">
        <h3 className="section-id">Data Quality</h3>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <span className="font-mono text-3xl font-bold" style={{ color: scoreColor(scorecard.overall_score) }}>
              {scorecard.overall_score}
            </span>
            <span className="text-xs block" style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)', textTransform: 'uppercase', letterSpacing: '0.15em' }}>
              DQ Score
            </span>
          </div>
          {scorecard.delta_vs_last != null && (
            <span
              className="text-sm font-mono font-medium"
              style={{ color: scorecard.delta_vs_last > 0 ? 'var(--ok)' : scorecard.delta_vs_last < 0 ? 'var(--signal)' : 'var(--on-low)' }}
            >
              {scorecard.delta_vs_last > 0 ? '+' : ''}{scorecard.delta_vs_last}
            </span>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="flex gap-4">
        <StatChip label="Total Rows" value={scorecard.total_rows.toLocaleString()} />
        {scorecard.duplicate_video_ids > 0 && (
          <StatChip label="Duplicates" value={String(scorecard.duplicate_video_ids)} warn />
        )}
        {scorecard.invalid_publish_urls > 0 && (
          <StatChip label="Invalid URLs" value={String(scorecard.invalid_publish_urls)} warn />
        )}
      </div>

      {/* Field completeness bars */}
      <div className="space-y-2">
        {scorecard.fields.map((f) => {
          const color = scoreColor(f.pct_complete);
          return (
            <div key={f.field_name} className="flex items-center gap-3">
              <span
                className="text-[0.6rem] w-24 text-right uppercase tracking-wider shrink-0 truncate"
                style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)' }}
              >
                {f.field_name.replace(/_id$/, '').replace(/_/g, ' ')}
              </span>
              <div className="flex-1 h-4 rounded" style={{ background: 'var(--wire)' }}>
                <div
                  className="h-4 rounded flex items-center px-2"
                  style={{ width: `${Math.max(f.pct_complete, 3)}%`, background: color, transition: 'width 0.8s ease-out' }}
                >
                  {f.pct_complete >= 20 && (
                    <span className="text-[0.55rem] font-mono font-bold text-white">{f.pct_complete.toFixed(0)}%</span>
                  )}
                </div>
              </div>
              <span className="text-xs font-mono w-8 text-right" style={{ color }}>
                {f.pct_complete < 20 ? `${f.pct_complete.toFixed(0)}%` : ''}
              </span>
              <span className="text-xs w-4" style={{ color: f.trend === 'improving' ? 'var(--ok)' : f.trend === 'declining' ? 'var(--signal)' : 'var(--on-low)' }}>
                {trendIcon(f.trend)}
              </span>
            </div>
          );
        })}
      </div>

      {/* DQ Trend chart */}
      {trend.length > 1 && (
        <div className="space-y-2">
          <h3 className="section-id">Score Trend</h3>
          <div style={{ width: '100%', height: 120 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend}>
                <XAxis
                  dataKey="period"
                  tick={{ fill: 'var(--on-low)', fontSize: 10, fontFamily: 'var(--font-condensed)' }}
                  axisLine={{ stroke: 'var(--wire)' }}
                  tickLine={false}
                />
                <YAxis domain={[0, 100]} hide />
                <Tooltip
                  contentStyle={{ background: 'var(--surface)', border: '1px solid var(--wire)', borderRadius: 2, fontSize: 12 }}
                  labelStyle={{ color: 'var(--on-mid)' }}
                />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="var(--uplink)"
                  strokeWidth={2}
                  dot={{ fill: 'var(--uplink)', r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

function StatChip({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={`dq-chip ${warn ? 'warn' : 'ok'}`}>
      <span style={{ fontFamily: 'var(--font-condensed)', textTransform: 'uppercase', letterSpacing: '0.08em', marginRight: 4 }}>
        {label}
      </span>
      {value}
    </div>
  );
}
