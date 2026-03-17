'use client';

import { Fragment } from 'react';

interface PeriodData {
  period: string;
  count: number;
  duration_hrs: number;
  published: number;
  publish_rate: number;
}

interface PeriodComparisonProps {
  current: PeriodData;
  previous: PeriodData;
  deltas: {
    count_pct: number;
    duration_pct: number;
    published_pct: number;
    publish_rate_delta: number;
  };
}

function DeltaChip({ value, suffix = '%' }: { value: number; suffix?: string }) {
  const color = value > 0 ? 'var(--ok)' : value < 0 ? 'var(--signal)' : 'var(--on-low)';
  const bg = value > 0 ? 'rgba(91, 138, 114, 0.1)' : value < 0 ? 'rgba(196, 85, 58, 0.08)' : 'transparent';
  const text = `${value > 0 ? '+' : ''}${value.toFixed(1)}${suffix}`;
  return (
    <span style={{
      fontFamily: 'var(--font-mono)',
      fontSize: '0.72rem',
      fontWeight: 600,
      color,
      padding: '2px 8px',
      background: bg,
      borderRadius: '5px',
    }}>
      {text}
    </span>
  );
}

const METRICS = [
  { key: 'count', label: 'Count', deltaKey: 'count_pct' },
  { key: 'duration_hrs', label: 'Duration (hrs)', deltaKey: 'duration_pct' },
  { key: 'published', label: 'Published', deltaKey: 'published_pct' },
  { key: 'publish_rate', label: 'Publish Rate', deltaKey: 'publish_rate_delta' },
] as const;

export function PeriodComparison({ current, previous, deltas }: PeriodComparisonProps) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <span className="section-id">Period Comparison</span>
      </div>
      <div style={{
        borderRadius: '12px',
        border: '1px solid var(--wire)',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr 1fr auto', background: 'var(--surface-hi)', borderBottom: '1.5px solid var(--wire)' }}>
          <div style={{ padding: '8px 14px' }} />
          {[current.period, previous.period, 'Delta'].map((h) => (
            <div key={h} style={{
              padding: '8px 14px',
              fontFamily: 'var(--font-sans)',
              fontWeight: 700,
              fontSize: '0.72rem',
              color: 'var(--on-low)',
            }}>
              {h}
            </div>
          ))}
        </div>

        {/* Rows */}
        {METRICS.map((m, idx) => (
          <div key={m.key} style={{
            display: 'grid',
            gridTemplateColumns: 'auto 1fr 1fr auto',
            borderBottom: idx < METRICS.length - 1 ? '1px solid var(--wire)' : 'none',
            background: idx % 2 === 0 ? 'var(--surface)' : 'var(--surface-hi)',
          }}>
            <div style={{
              padding: '8px 14px',
              fontFamily: 'var(--font-sans)',
              fontWeight: 600,
              fontSize: '0.75rem',
              color: 'var(--on-mid)',
              minWidth: '110px',
            }}>
              {m.label}
            </div>
            <div style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--on)', fontWeight: 500 }}>
              {typeof current[m.key] === 'number' ? (current[m.key] as number).toLocaleString(undefined, { maximumFractionDigits: 1 }) : '\u2014'}
            </div>
            <div style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--on-mid)' }}>
              {typeof previous[m.key] === 'number' ? (previous[m.key] as number).toLocaleString(undefined, { maximumFractionDigits: 1 }) : '\u2014'}
            </div>
            <div style={{ padding: '8px 14px' }}>
              <DeltaChip value={deltas[m.deltaKey]} suffix={m.key === 'publish_rate' ? 'pp' : '%'} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
