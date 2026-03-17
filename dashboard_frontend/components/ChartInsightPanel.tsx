'use client';

import React from 'react';

interface ChartInsightPanelProps {
  summary: string;
  insights: string[];
  loading: boolean;
  visible: boolean;
  error?: boolean;
}

export function ChartInsightPanel({ summary, insights, loading, visible, error }: ChartInsightPanelProps) {
  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        width: '220px',
        background: '#0E0E0E',
        border: '1px solid #2C2C2C',
        padding: '12px',
        zIndex: 10,
        pointerEvents: 'none',
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateX(0)' : 'translateX(8px)',
        transition: 'opacity 0.2s ease, transform 0.2s ease',
      }}
    >
      {/* Header */}
      <p
        style={{
          margin: '0 0 8px 0',
          fontFamily: 'var(--font-condensed)',
          fontSize: '0.55rem',
          fontWeight: 700,
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
          color: '#52504C',
        }}
      >
        Chart Insights
      </p>

      {loading ? (
        <Skeleton />
      ) : error ? (
        <p style={{
          margin: 0,
          fontFamily: 'var(--font-mono)',
          fontSize: '0.6rem',
          color: '#52504C',
          lineHeight: 1.5,
        }}>
          Could not load insights. Check that the backend is running.
        </p>
      ) : (
        <>
          {/* Summary */}
          {summary && (
            <p
              style={{
                margin: '0 0 10px 0',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.65rem',
                color: '#F0EDE8',
                lineHeight: 1.5,
              }}
            >
              {summary}
            </p>
          )}

          {/* Insight bullets */}
          <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {insights.map((insight, i) => (
              <li
                key={i}
                style={{
                  display: 'flex',
                  gap: '6px',
                  marginBottom: '6px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.6rem',
                  color: '#9A9590',
                  lineHeight: 1.5,
                }}
              >
                <span style={{ color: '#E5001A', flexShrink: 0, marginTop: '1px' }}>—</span>
                <span>{insight}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function Skeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {[90, 70, 80, 65, 75].map((w, i) => (
        <div
          key={i}
          style={{
            height: '8px',
            width: `${w}%`,
            background: '#1E1E1E',
            borderRadius: '2px',
            animation: 'pulse 1.4s ease-in-out infinite',
            animationDelay: `${i * 0.1}s`,
          }}
        />
      ))}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 0.9; }
        }
      `}</style>
    </div>
  );
}
