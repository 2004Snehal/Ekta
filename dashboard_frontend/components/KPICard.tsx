'use client';

interface KPICardProps {
  title: string;
  value: string | number;
  change: number;
  timeframe: string;
  icon?: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
}

export function KPICard({ title, value, change, onClick, active }: KPICardProps) {
  const isPositive = change >= 0;
  const changeAbs  = Math.abs(change);
  const arrow      = isPositive ? '▲' : '▼';

  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => { if (onClick && (e.key === 'Enter' || e.key === ' ')) onClick(); }}
      className={`kpi-cell${active ? ' kpi-active' : ''}`}
    >
      {/* Label */}
      <p
        style={{
          fontFamily: 'var(--font-condensed)',
          fontSize: '0.6rem',
          fontWeight: 700,
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: 'var(--on-low)',
          marginBottom: '8px',
        }}
      >
        {title}
      </p>

      {/* Value */}
      <p
        className="data-number"
        style={{
          fontSize: '2rem',
          fontWeight: 500,
          color: 'var(--on)',
          marginBottom: '6px',
        }}
      >
        {value}
      </p>

      {/* Change */}
      <p
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.65rem',
          color: isPositive ? 'var(--ok)' : 'var(--signal)',
          letterSpacing: '0.04em',
        }}
      >
        {arrow} {changeAbs}%
      </p>
    </div>
  );
}
