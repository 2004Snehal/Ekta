'use client';

interface InsightPanelProps {
  insights: {
    title: string;
    description: string;
    actionable?: boolean;
  }[];
  label?: string;
}

export function InsightPanel({ insights, label = 'Insights' }: InsightPanelProps) {
  if (!insights.length) return null;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
        <h3 style={{
          fontFamily: 'var(--font-display)',
          fontSize: '1rem',
          fontWeight: 700,
          color: 'var(--on)',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
        }}>
          <span style={{
            display: 'inline-block',
            width: '4px',
            height: '18px',
            background: 'linear-gradient(180deg, var(--signal) 0%, rgba(196, 85, 58, 0.3) 100%)',
            borderRadius: '2px',
            flexShrink: 0,
          }} />
          {label}
        </h3>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {insights.map((ins, i) => (
          <div
            key={i}
            style={{
              borderRadius: '12px',
              border: '1px solid var(--wire)',
              background: 'var(--surface)',
              padding: '14px 16px',
              boxShadow: '0 1px 4px rgba(43, 35, 32, 0.05)',
              animation: 'fade-up 0.4s ease-out both',
              animationDelay: `${i * 0.1}s`,
              transition: 'box-shadow 0.2s',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 16px rgba(43, 35, 32, 0.1)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = '0 1px 4px rgba(43, 35, 32, 0.05)'; }}
          >
            <p style={{
              fontFamily: 'var(--font-display)',
              fontSize: '0.88rem',
              fontWeight: 600,
              color: 'var(--on)',
              marginBottom: '6px',
              lineHeight: 1.35,
            }}>
              {ins.title}
            </p>
            <p style={{
              fontFamily: 'var(--font-sans)',
              fontSize: '0.77rem',
              color: 'var(--on-mid)',
              lineHeight: 1.6,
            }}>
              {ins.description}
            </p>
            {ins.actionable && (
              <span style={{
                display: 'inline-block',
                marginTop: '8px',
                fontFamily: 'var(--font-sans)',
                fontSize: '0.7rem',
                fontWeight: 700,
                color: 'var(--signal)',
                cursor: 'pointer',
                background: 'var(--signal-dim)',
                padding: '3px 10px',
                borderRadius: '20px',
                border: '1px solid rgba(196, 85, 58, 0.15)',
              }}>
                Take action →
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
