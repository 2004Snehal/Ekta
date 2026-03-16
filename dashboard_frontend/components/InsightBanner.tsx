'use client';

import Link from 'next/link';

interface InsightAlert {
  title: string;
  severity: 'high' | 'medium' | 'low';
  body?: string;
}

interface InsightBannerProps {
  insights: InsightAlert[];
}

const SEVERITY_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  high:   { border: 'var(--signal)', bg: 'var(--signal-dim)', text: 'var(--signal)' },
  medium: { border: 'var(--warn)',   bg: 'rgba(242,161,26,0.08)', text: 'var(--warn)' },
  low:    { border: 'var(--uplink)', bg: 'rgba(45,156,219,0.08)', text: 'var(--uplink)' },
};

export function InsightBanner({ insights }: InsightBannerProps) {
  if (insights.length === 0) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {insights.map((insight, i) => {
        const colors = SEVERITY_COLORS[insight.severity] ?? SEVERITY_COLORS.low;
        return (
          <div
            key={i}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '8px 14px',
              borderLeft: `2px solid ${colors.border}`,
              background: colors.bg,
            }}
          >
            <span style={{
              fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700,
              letterSpacing: '0.14em', textTransform: 'uppercase', color: colors.text,
              flexShrink: 0,
            }}>
              {insight.severity}
            </span>
            <span style={{
              fontFamily: 'var(--font-sans)', fontSize: '0.75rem', color: 'var(--on)',
              flex: 1, lineHeight: 1.3,
            }}>
              {insight.title}
            </span>
            <Link
              href="/narrator"
              style={{
                fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700,
                letterSpacing: '0.14em', color: 'var(--on-low)', textDecoration: 'none',
                flexShrink: 0,
              }}
            >
              VIEW →
            </Link>
          </div>
        );
      })}
    </div>
  );
}
