'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useProfile } from '@/lib/profiles';
import { parseDrillParams, buildDrillUrl } from '@/lib/drill-down';
import { DimensionPicker } from '@/components/DimensionPicker';
import { CrossTabChart } from '@/components/CrossTabChart';
import { DataTable } from '@/components/DataTable';
import { DrillBreadcrumb } from '@/components/DrillBreadcrumb';

const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';

export default function AnalysisPage() {
  return (
    <Suspense fallback={<div className="px-6 py-8"><div className="scan-loader" /></div>}>
      <AnalysisPageInner />
    </Suspense>
  );
}

function AnalysisPageInner() {
  const { profileDef } = useProfile();
  const searchParams = useSearchParams();
  const drillParams = parseDrillParams(searchParams);

  const [dim1, setDim1] = useState(drillParams.dim1 ?? 'channel');
  const [dim2, setDim2] = useState<string | null>(drillParams.dim2 ?? 'input_type');
  const [metric, setMetric] = useState(drillParams.metric ?? 'count');
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

  // Client-side filter from URL params
  const filteredRows = data?.rows
    ? data.rows.filter((row: any) => {
        for (const [key, val] of Object.entries(drillParams.filters)) {
          if (row[key] != null && String(row[key]) !== val && row.dim1 !== val && row.dim2 !== val) {
            return false;
          }
        }
        return true;
      })
    : [];

  const displayData = data ? { ...data, rows: Object.keys(drillParams.filters).length > 0 ? filteredRows : data.rows } : null;

  function handleBarClick(dimensionValue: string) {
    window.location.href = buildDrillUrl('/dashboard/funnel', {
      group_by: dim1,
      filter: { [dim1]: dimensionValue },
      from: 'analysis',
    });
  }

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

      {/* Breadcrumb */}
      {drillParams.source && (
        <div className="px-6 pt-2">
          <DrillBreadcrumb
            source={drillParams.source}
            currentPage="Analysis"
            filters={drillParams.filters}
          />
        </div>
      )}

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
      ) : displayData ? (
        <div style={{ padding: '24px 28px' }}>
          {/* Chart */}
          <CrossTabChart
            rows={displayData.rows}
            dim1Key={displayData.dim1_key}
            dim2Key={displayData.dim2_key}
            metric={metric}
            onBarClick={handleBarClick}
          />

          {/* Ref links */}
          <div className="flex gap-4 mt-3">
            <a href={buildDrillUrl('/dashboard/funnel', { group_by: dim1, from: 'analysis' })}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--uplink)', textDecoration: 'none' }}>
              See Funnel →
            </a>
            <a href={buildDrillUrl('/dashboard/usage', { from: 'analysis' })}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--uplink)', textDecoration: 'none' }}>
              See Usage →
            </a>
          </div>

          <div className="wire-h" style={{ margin: '28px 0' }} />

          {/* Breakdown table */}
          <DataTable
            data={displayData.rows}
            title="Breakdown"
            pageSize={25}
          />

          {/* Grand total */}
          {displayData.grand_total && (
            <div style={{ marginTop: '20px', padding: '12px 14px', borderLeft: '2px solid var(--signal)', background: 'var(--signal-dim)' }}>
              <span style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--on-low)' }}>
                GRAND TOTAL
              </span>
              <div className="flex gap-6 mt-1">
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--on)' }}>
                  Count: {displayData.grand_total.count?.toLocaleString()}
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--on-mid)' }}>
                  Duration: {displayData.grand_total.duration_hrs?.toFixed(1)}h
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--on-mid)' }}>
                  Published: {displayData.grand_total.published_count?.toLocaleString()}
                </span>
                {displayData.grand_total.publish_rate != null && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--ok)' }}>
                    Rate: {displayData.grand_total.publish_rate}%
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
