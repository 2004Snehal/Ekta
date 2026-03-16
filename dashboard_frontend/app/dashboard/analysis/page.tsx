'use client';

import { useEffect, useState } from 'react';
import { useProfile } from '@/lib/profiles';
import { DimensionPicker } from '@/components/DimensionPicker';
import { CrossTabChart } from '@/components/CrossTabChart';
import { DataTable } from '@/components/DataTable';

const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';

export default function AnalysisPage() {
  const { profileDef } = useProfile();
  const [dim1, setDim1] = useState('channel');
  const [dim2, setDim2] = useState<string | null>('input_type');
  const [metric, setMetric] = useState('count');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/analytics/multi-dim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: 1, dim1, dim2, metric }),
    })
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [dim1, dim2, metric]);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--void)' }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-2.5" style={{ borderBottom: '1px solid var(--wire)' }}>
        <span className="section-id">Drill-Down Analysis</span>
        <div className="flex-1" />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.55rem', color: 'var(--on-low)' }}>
          {profileDef.displayName}
        </span>
      </div>

      {/* Dimension picker */}
      <DimensionPicker
        dim1={dim1}
        dim2={dim2}
        metric={metric}
        onDim1Change={setDim1}
        onDim2Change={setDim2}
        onMetricChange={setMetric}
      />

      {loading ? (
        <div className="px-6 py-8"><div className="scan-loader" /></div>
      ) : data ? (
        <div style={{ padding: '24px 28px' }}>
          {/* Chart */}
          <CrossTabChart
            rows={data.rows}
            dim1Key={data.dim1_key}
            dim2Key={data.dim2_key}
            metric={metric}
          />

          <div className="wire-h" style={{ margin: '28px 0' }} />

          {/* Breakdown table */}
          <DataTable
            data={data.rows}
            title="Breakdown"
            pageSize={25}
          />

          {/* Grand total */}
          {data.grand_total && (
            <div style={{ marginTop: '20px', padding: '12px 14px', borderLeft: '2px solid var(--signal)', background: 'var(--signal-dim)' }}>
              <span style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--on-low)' }}>
                GRAND TOTAL
              </span>
              <div className="flex gap-6 mt-1">
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--on)' }}>
                  Count: {data.grand_total.count?.toLocaleString()}
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--on-mid)' }}>
                  Duration: {data.grand_total.duration_hrs?.toFixed(1)}h
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--on-mid)' }}>
                  Published: {data.grand_total.published_count?.toLocaleString()}
                </span>
                {data.grand_total.publish_rate != null && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--ok)' }}>
                    Rate: {data.grand_total.publish_rate}%
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="px-6 py-12">
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--on-low)' }}>
            — select dimensions to analyze
          </p>
        </div>
      )}
    </div>
  );
}
