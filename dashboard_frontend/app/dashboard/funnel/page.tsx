'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useProfile } from '@/lib/profiles';
import { parseDrillParams, buildDrillUrl } from '@/lib/drill-down';
import { FunnelChart } from '@/components/FunnelChart';
import { ChartRenderer } from '@/components/ChartRenderer';
import { DrillBreadcrumb } from '@/components/DrillBreadcrumb';
import type { UniversalChartSpec } from '@/types/chart';

const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';

export default function FunnelPage() {
  return (
    <Suspense fallback={<div className="px-6 py-8"><div className="scan-loader" /></div>}>
      <FunnelPageInner />
    </Suspense>
  );
}

function FunnelPageInner() {
  const { profileDef } = useProfile();
  const searchParams = useSearchParams();
  const drillParams = parseDrillParams(searchParams);

  const [groupBy, setGroupBy] = useState(drillParams.group_by ?? 'channel');
  const [funnelData, setFunnelData] = useState<any>(null);
  const [typeMix, setTypeMix] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/analytics/funnel?client_id=1&group_by=${groupBy}`).then(r => r.json()),
      fetch(`${API}/analytics/multi-dim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: 1, dim1: 'input_type', metric: 'count' }),
      }).then(r => r.json()),
    ]).then(([funnel, mix]) => {
      setFunnelData(funnel);
      setTypeMix(mix);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [groupBy]);

  const GROUP_OPTS = [
    { value: 'channel', label: 'Channel' },
    { value: 'user', label: 'User' },
    { value: 'input_type', label: 'Input Type' },
    { value: 'language', label: 'Language' },
  ];

  const inputTypeChart: UniversalChartSpec | null = typeMix ? {
    chart_type: 'pie',
    title: 'Input Type Mix',
    category: 'dim1',
    value: 'count',
    data: typeMix.rows ?? [],
    refLinks: [
      { label: 'Analyze in Detail', href: buildDrillUrl('/dashboard/analysis', { dim1: 'input_type', from: 'funnel' }) },
    ],
  } : null;

  const conversionChart: UniversalChartSpec | null = funnelData ? {
    chart_type: 'bar',
    title: 'Publish Rate by ' + groupBy.replace('_', ' '),
    x: 'group',
    y: 'publish_rate',
    data: (funnelData.funnel ?? []).sort((a: any, b: any) => (b.publish_rate ?? 0) - (a.publish_rate ?? 0)),
    drillDown: {
      dimensionKey: 'group',
      targetPage: '/dashboard/analysis',
      targetParam: 'dim1',
    },
    refLinks: [
      { label: 'View in Analysis', href: buildDrillUrl('/dashboard/analysis', { dim1: groupBy, from: 'funnel' }) },
    ],
  } : null;

  function handleGroupClick(groupName: string) {
    window.location.href = buildDrillUrl('/dashboard/analysis', {
      dim1: groupBy,
      filter: { [groupBy]: groupName },
      from: 'funnel',
    });
  }

  function handleConversionBarClick(_dimKey: string, value: string) {
    window.location.href = buildDrillUrl('/dashboard/analysis', {
      dim1: groupBy,
      filter: { [groupBy]: value },
      from: 'funnel',
    });
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--void)' }}>
      {/* Header */}
      <div className="flex items-center gap-4 px-6 py-2.5" style={{ borderBottom: '1px solid var(--wire)' }}>
        <span className="section-id">Funnel & Type Mix</span>
        <div className="wire-v" style={{ height: '14px' }} />
        <span style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.14em', color: 'var(--on-low)', textTransform: 'uppercase' }}>
          Group By
        </span>
        {GROUP_OPTS.map((g, i) => (
          <span key={g.value} className="flex items-center gap-0">
            <span
              className={`range-opt${groupBy === g.value ? ' selected' : ''}`}
              onClick={() => setGroupBy(g.value)}
            >
              {g.label}
            </span>
            {i < GROUP_OPTS.length - 1 && <span style={{ color: 'var(--wire-mid)', margin: '0 3px', fontSize: '0.55rem' }}>·</span>}
          </span>
        ))}
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
            currentPage="Funnel"
            filters={drillParams.filters}
          />
        </div>
      )}

      {loading ? (
        <div className="px-6 py-8"><div className="scan-loader" /></div>
      ) : (
        <div style={{ padding: '24px 28px' }}>
          {/* Funnel */}
          {funnelData && (
            <FunnelChart
              data={funnelData.funnel ?? []}
              totals={funnelData.totals ?? {}}
              onGroupClick={handleGroupClick}
            />
          )}

          <div className="wire-h" style={{ margin: '28px 0' }} />

          {/* Type mix + Conversion side by side */}
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '28px' }}>
            {inputTypeChart && <ChartRenderer chart={inputTypeChart} />}
            {conversionChart && <ChartRenderer chart={conversionChart} onElementClick={handleConversionBarClick} />}
          </div>
        </div>
      )}
    </div>
  );
}
