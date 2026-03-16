'use client';

import { useMemo } from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';

interface SparkKPIProps {
  title: string;
  value: string | number;
  delta?: number | null;      // percentage change vs previous period
  sparkData?: number[];        // last 30 data points for sparkline
  active?: boolean;
  onClick?: () => void;
}

export function SparkKPI({ title, value, delta, sparkData, active, onClick }: SparkKPIProps) {
  const sparkPoints = useMemo(() =>
    (sparkData ?? []).map((v, i) => ({ i, v })),
    [sparkData]
  );

  const deltaColor = delta == null ? 'var(--on-low)'
    : delta > 0 ? 'var(--ok)'
    : delta < 0 ? 'var(--signal)'
    : 'var(--on-low)';

  const deltaText = delta == null ? '—'
    : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%`;

  return (
    <div
      className={`kpi-cell ${active ? 'kpi-active' : ''}`}
      onClick={onClick}
      style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}
    >
      {/* Title */}
      <span
        style={{
          fontFamily: 'var(--font-condensed)',
          fontSize: '0.55rem',
          fontWeight: 700,
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: 'var(--on-low)',
        }}
      >
        {title}
      </span>

      {/* Value + Delta row */}
      <div className="flex items-end gap-3">
        <span className="data-number" style={{ fontSize: '1.4rem', color: 'var(--on)' }}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.6rem',
            fontWeight: 500,
            color: deltaColor,
            paddingBottom: '2px',
          }}
        >
          {deltaText}
        </span>
      </div>

      {/* Sparkline */}
      {sparkPoints.length > 2 && (
        <div style={{ width: '100%', height: '24px', marginTop: '2px' }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkPoints}>
              <Line
                type="monotone"
                dataKey="v"
                stroke="var(--on-low)"
                strokeWidth={1}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
