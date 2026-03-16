'use client';

interface FunnelStep {
  group: string;
  uploaded: number;
  processed: number;
  published: number;
  process_rate: number;
  publish_rate: number;
}

interface FunnelChartProps {
  data: FunnelStep[];
  totals: {
    uploaded: number;
    processed: number;
    published: number;
    process_rate: number;
    publish_rate: number;
  };
}

function FunnelBar({ label, value, maxValue, color }: { label: string; value: number; maxValue: number; color: string }) {
  const pct = maxValue > 0 ? (value / maxValue) * 100 : 0;
  return (
    <div className="flex items-center gap-3" style={{ marginBottom: '4px' }}>
      <span style={{
        fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700,
        letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--on-low)',
        width: '80px', textAlign: 'right', flexShrink: 0,
      }}>
        {label}
      </span>
      <div style={{ flex: 1, height: '16px', background: 'var(--surface-hi)', position: 'relative' }}>
        <div style={{
          width: `${pct}%`, height: '100%', background: color,
          transition: 'width 0.6s ease-out',
        }} />
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on)', width: '50px', flexShrink: 0 }}>
        {value.toLocaleString()}
      </span>
    </div>
  );
}

export function FunnelChart({ data, totals }: FunnelChartProps) {
  const maxVal = Math.max(totals.uploaded, totals.processed, totals.published, 1);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <span className="section-id">Publishing Funnel</span>
      </div>

      {/* Overall funnel */}
      <div style={{ marginBottom: '20px' }}>
        <FunnelBar label="Uploaded" value={totals.uploaded} maxValue={maxVal} color="var(--uplink)" />
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', margin: '2px 0 2px 83px' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.5rem', color: 'var(--on-low)' }}>
            ↓ {totals.process_rate}%
          </span>
        </div>
        <FunnelBar label="Processed" value={totals.processed} maxValue={maxVal} color="var(--warn)" />
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', margin: '2px 0 2px 83px' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.5rem', color: 'var(--on-low)' }}>
            ↓ {totals.publish_rate}%
          </span>
        </div>
        <FunnelBar label="Published" value={totals.published} maxValue={maxVal} color="var(--ok)" />
      </div>

      {/* Per-group breakdown */}
      {data.length > 0 && (
        <>
          <div className="wire-h" style={{ marginBottom: '12px' }} />
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--wire-mid)' }}>
                  {['Group', 'Uploaded', 'Processed', 'Published', 'Pub %'].map((h) => (
                    <th key={h} style={{
                      padding: '6px 8px', fontFamily: 'var(--font-condensed)', fontSize: '0.55rem',
                      fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
                      color: 'var(--on-low)', textAlign: 'left',
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((row) => (
                  <tr key={row.group} style={{ borderBottom: '1px solid var(--wire)' }}>
                    <td style={{ padding: '5px 8px', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--on)' }}>{row.group}</td>
                    <td style={{ padding: '5px 8px', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--on-mid)' }}>{row.uploaded.toLocaleString()}</td>
                    <td style={{ padding: '5px 8px', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--on-mid)' }}>{row.processed.toLocaleString()}</td>
                    <td style={{ padding: '5px 8px', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--on-mid)' }}>{row.published.toLocaleString()}</td>
                    <td style={{
                      padding: '5px 8px', fontFamily: 'var(--font-mono)', fontSize: '0.65rem',
                      color: row.publish_rate >= 80 ? 'var(--ok)' : row.publish_rate >= 50 ? 'var(--warn)' : 'var(--signal)',
                    }}>
                      {row.publish_rate}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
