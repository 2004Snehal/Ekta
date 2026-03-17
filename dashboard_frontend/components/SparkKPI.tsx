'use client';

import { useMemo } from 'react';
import { AreaChart, Area, ResponsiveContainer } from 'recharts';

interface SparkKPIProps {
  title: string;
  value: string | number;
  delta?: number | null;
  sparkData?: number[];
  active?: boolean;
  onClick?: () => void;
}

export function SparkKPI({ title, value, delta, sparkData, active, onClick }: SparkKPIProps) {
  const sparkPoints = useMemo(() =>
    (sparkData ?? []).map((v, i) => ({ i, v })),
    [sparkData]
  );

  const isPositive = delta != null && delta > 0;
  const isNegative = delta != null && delta < 0;

  const deltaColor = delta == null ? 'var(--on-low)'
    : isPositive ? 'var(--ok)'
    : isNegative ? 'var(--signal)'
    : 'var(--on-low)';

  const deltaBg = isPositive ? 'rgba(91, 138, 114, 0.1)'
    : isNegative ? 'rgba(196, 85, 58, 0.08)'
    : 'transparent';

  const deltaText = delta == null ? null
    : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%`;

  const areaColor = isNegative ? '#C4553A' : '#5B8A72';
  const areaFill = isNegative
    ? 'url(#sparkFillRed)'
    : 'url(#sparkFillGreen)';

  const gradientId = isNegative ? 'sparkFillRed' : 'sparkFillGreen';

  return (
    <div
      onClick={onClick}
      style={{
        position: 'relative',
        flex: 1,
        padding: '22px 24px 16px',
        cursor: 'pointer',
        transition: 'background 0.2s ease, box-shadow 0.2s ease',
        background: active ? 'var(--surface)' : 'transparent',
        boxShadow: active ? 'inset 0 -3px 0 var(--signal)' : 'none',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        minHeight: '110px',
      }}
      onMouseEnter={(e) => {
        if (!active) (e.currentTarget as HTMLElement).style.background = 'var(--surface-hi)';
      }}
      onMouseLeave={(e) => {
        if (!active) (e.currentTarget as HTMLElement).style.background = 'transparent';
      }}
    >
      {/* Active indicator bar at top */}
      {active && (
        <div style={{
          position: 'absolute',
          top: 0, left: 0, right: 0,
          height: '3px',
          background: 'var(--signal)',
          borderRadius: '0 0 2px 2px',
        }} />
      )}

      {/* Title */}
      <span style={{
        fontFamily: 'var(--font-sans)',
        fontSize: '0.68rem',
        fontWeight: 600,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        color: active ? 'var(--signal)' : 'var(--on-low)',
        transition: 'color 0.2s',
      }}>
        {title}
      </span>

      {/* Value — big Playfair number */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '10px', marginTop: '2px' }}>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: '2rem',
          fontWeight: 700,
          color: 'var(--on)',
          lineHeight: 1,
          letterSpacing: '-0.02em',
          animation: 'count-up 0.5s ease-out both',
        }}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </span>

        {/* Delta */}
        {deltaText && (
          <span style={{
            fontFamily: 'var(--font-sans)',
            fontSize: '0.7rem',
            fontWeight: 700,
            color: deltaColor,
            background: deltaBg,
            padding: '3px 7px',
            borderRadius: '20px',
            marginBottom: '4px',
            flexShrink: 0,
          }}>
            {isPositive ? '↑' : isNegative ? '↓' : ''} {deltaText}
          </span>
        )}
      </div>

      {/* vs prev label */}
      {deltaText && (
        <span style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '0.6rem',
          color: 'var(--on-low)',
          marginTop: '-2px',
        }}>
          vs prev period
        </span>
      )}

      {/* Area sparkline */}
      {sparkPoints.length > 2 && (
        <div style={{ width: '100%', height: '32px', marginTop: 'auto' }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkPoints} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={areaColor} stopOpacity={0.18} />
                  <stop offset="95%" stopColor={areaColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="v"
                stroke={areaColor}
                strokeWidth={1.5}
                fill={areaFill}
                dot={false}
                isAnimationActive={true}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
