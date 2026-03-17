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

const SEVERITY_CONFIG: Record<string, { border: string; bg: string; text: string; label: string; dot: string }> = {
  high:   { border: 'rgba(196, 85, 58, 0.35)',  bg: 'rgba(196, 85, 58, 0.05)',  text: 'var(--signal)', label: 'Alert',   dot: '#C4553A' },
  medium: { border: 'rgba(198, 139, 44, 0.35)', bg: 'rgba(198, 139, 44, 0.05)', text: 'var(--warn)',   label: 'Warning', dot: '#C68B2C' },
  low:    { border: 'rgba(91, 126, 161, 0.35)', bg: 'rgba(91, 126, 161, 0.05)', text: 'var(--uplink)', label: 'Info',    dot: '#5B7EA1' },
};

export function InsightBanner({ insights }: InsightBannerProps) {
  if (insights.length === 0) return null;

  return (
    <div style={{
      borderRadius: '14px',
      border: '1px solid var(--wire)',
      background: 'var(--surface)',
      overflow: 'hidden',
      boxShadow: '0 1px 4px rgba(43, 35, 32, 0.05)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 14px',
        borderBottom: '1px solid var(--wire)',
        background: 'var(--surface-hi)',
      }}>
        <span style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '0.65rem',
          fontWeight: 700,
          letterSpacing: '0.09em',
          textTransform: 'uppercase',
          color: 'var(--on-low)',
        }}>
          Live Alerts · {insights.length}
        </span>
        <Link
          href="/narrator"
          style={{
            fontFamily: 'var(--font-sans)',
            fontSize: '0.65rem',
            fontWeight: 600,
            color: 'var(--signal)',
            textDecoration: 'none',
          }}
        >
          View all →
        </Link>
      </div>

      {/* Alerts */}
      {insights.map((insight, i) => {
        const cfg = SEVERITY_CONFIG[insight.severity] ?? SEVERITY_CONFIG.low;
        return (
          <div
            key={i}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
              padding: '10px 14px',
              borderBottom: i < insights.length - 1 ? '1px solid var(--wire)' : 'none',
              background: cfg.bg,
              borderLeft: `3px solid ${cfg.dot}`,
            }}
          >
            {/* Severity badge */}
            <span style={{
              flexShrink: 0,
              fontFamily: 'var(--font-sans)',
              fontSize: '0.58rem',
              fontWeight: 700,
              letterSpacing: '0.07em',
              textTransform: 'uppercase',
              color: cfg.text,
              background: 'rgba(255,255,255,0.8)',
              padding: '2px 7px',
              borderRadius: '20px',
              border: `1px solid ${cfg.border}`,
              marginTop: '1px',
            }}>
              {cfg.label}
            </span>

            {/* Title */}
            <span style={{
              fontFamily: 'var(--font-sans)',
              fontSize: '0.78rem',
              fontWeight: 600,
              color: 'var(--on)',
              lineHeight: 1.4,
              flex: 1,
            }}>
              {insight.title}
            </span>
          </div>
        );
      })}
    </div>
  );
}
