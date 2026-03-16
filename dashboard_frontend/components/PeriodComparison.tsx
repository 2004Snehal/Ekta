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
  const text = `${value > 0 ? '+' : ''}${value.toFixed(1)}${suffix}`;
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: '0.6rem', fontWeight: 500,
      color, padding: '1px 4px', background: value > 0 ? 'rgba(29,185,84,0.1)' : value < 0 ? 'var(--signal-dim)' : 'transparent',
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
      <div className="flex items-center gap-3 mb-3">
        <span className="section-id">Period Comparison</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr 1fr auto', gap: '0', fontSize: '0.65rem' }}>
        {/* Header */}
        <div style={{ padding: '6px 10px', borderBottom: '1px solid var(--wire-mid)' }} />
        <div style={{
          padding: '6px 10px', borderBottom: '1px solid var(--wire-mid)',
          fontFamily: 'var(--font-condensed)', fontWeight: 700, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: 'var(--on-low)', fontSize: '0.55rem',
        }}>
          {current.period}
        </div>
        <div style={{
          padding: '6px 10px', borderBottom: '1px solid var(--wire-mid)',
          fontFamily: 'var(--font-condensed)', fontWeight: 700, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: 'var(--on-low)', fontSize: '0.55rem',
        }}>
          {previous.period}
        </div>
        <div style={{
          padding: '6px 10px', borderBottom: '1px solid var(--wire-mid)',
          fontFamily: 'var(--font-condensed)', fontWeight: 700, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: 'var(--on-low)', fontSize: '0.55rem',
        }}>
          Delta
        </div>

        {/* Rows */}
        {METRICS.map((m) => (
          <Fragment key={m.key}>
            <div style={{
              padding: '6px 10px', borderBottom: '1px solid var(--wire)',
              fontFamily: 'var(--font-condensed)', fontWeight: 600, fontSize: '0.6rem',
              letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--on-mid)',
            }}>
              {m.label}
            </div>
            <div style={{
              padding: '6px 10px', borderBottom: '1px solid var(--wire)',
              fontFamily: 'var(--font-mono)', color: 'var(--on)',
            }}>
              {typeof current[m.key] === 'number' ? (current[m.key] as number).toLocaleString(undefined, { maximumFractionDigits: 1 }) : '—'}
            </div>
            <div style={{
              padding: '6px 10px', borderBottom: '1px solid var(--wire)',
              fontFamily: 'var(--font-mono)', color: 'var(--on-mid)',
            }}>
              {typeof previous[m.key] === 'number' ? (previous[m.key] as number).toLocaleString(undefined, { maximumFractionDigits: 1 }) : '—'}
            </div>
            <div style={{ padding: '6px 10px', borderBottom: '1px solid var(--wire)' }}>
              <DeltaChip value={deltas[m.deltaKey]} suffix={m.key === 'publish_rate' ? 'pp' : '%'} />
            </div>
          </Fragment>
        ))}
      </div>
    </div>
  );
}
