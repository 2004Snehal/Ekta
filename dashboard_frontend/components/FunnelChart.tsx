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
    <div className="flex items-center gap-4" style={{ marginBottom: '6px' }}>
      <span style={{
        fontFamily: 'var(--font-sans)',
        fontSize: '0.75rem',
        fontWeight: 600,
        color: 'var(--on-mid)',
        width: '80px',
        textAlign: 'right',
        flexShrink: 0,
      }}>
        {label}
      </span>
      <div style={{ flex: 1, height: '20px', background: 'var(--surface-raise)', position: 'relative', borderRadius: '6px', overflow: 'hidden' }}>
        <div style={{
          width: `${pct}%`, height: '100%', background: color,
          transition: 'width 0.7s cubic-bezier(0.4, 0, 0.2, 1)',
          borderRadius: '6px',
        }} />
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--on)', width: '60px', flexShrink: 0, textAlign: 'right' }}>
        {value.toLocaleString()}
      </span>
    </div>
  );
}

export function FunnelChart({ data, totals }: FunnelChartProps) {
  const maxVal = Math.max(totals.uploaded, totals.processed, totals.published, 1);

  return (
    <div>
      <div className="flex items-center gap-3 mb-5">
        <span className="section-id">Publishing Funnel</span>
      </div>

      {/* Overall funnel */}
      <div style={{ marginBottom: '24px' }}>
        <FunnelBar label="Uploaded" value={totals.uploaded} maxValue={maxVal} color="var(--uplink)" />
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', margin: '3px 0 3px 84px' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--on-low)' }}>
            ↓ {totals.process_rate}% processed
          </span>
        </div>
        <FunnelBar label="Processed" value={totals.processed} maxValue={maxVal} color="var(--warn)" />
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', margin: '3px 0 3px 84px' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--on-low)' }}>
            ↓ {totals.publish_rate}% published
          </span>
        </div>
        <FunnelBar label="Published" value={totals.published} maxValue={maxVal} color="var(--ok)" />
      </div>

      {/* Per-group breakdown */}
      {data.length > 0 && (
        <>
          <div className="wire-h" style={{ marginBottom: '16px' }} />
          <div style={{ overflowX: 'auto', borderRadius: '12px', border: '1px solid var(--wire)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--surface-hi)', borderBottom: '1.5px solid var(--wire)' }}>
                  {['Group', 'Uploaded', 'Processed', 'Published', 'Pub %'].map((h) => (
                    <th key={h} style={{
                      padding: '9px 12px',
                      fontFamily: 'var(--font-sans)',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      color: 'var(--on-low)',
                      textAlign: 'left',
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((row, i) => (
                  <tr key={row.group} style={{ borderBottom: '1px solid var(--wire)', background: i % 2 === 0 ? 'var(--surface)' : 'var(--surface-hi)' }}>
                    <td style={{ padding: '7px 12px', fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on)', fontWeight: 500 }}>{row.group}</td>
                    <td style={{ padding: '7px 12px', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--on-mid)' }}>{row.uploaded.toLocaleString()}</td>
                    <td style={{ padding: '7px 12px', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--on-mid)' }}>{row.processed.toLocaleString()}</td>
                    <td style={{ padding: '7px 12px', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--on-mid)' }}>{row.published.toLocaleString()}</td>
                    <td style={{
                      padding: '7px 12px',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.72rem',
                      fontWeight: 700,
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
