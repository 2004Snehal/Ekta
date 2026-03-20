'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useProfile } from '@/lib/profiles';
import { parseDrillParams, buildDrillUrl } from '@/lib/drill-down';
import { ChartRenderer } from '@/components/ChartRenderer';
import { PeriodComparison } from '@/components/PeriodComparison';
import { DrillBreadcrumb } from '@/components/DrillBreadcrumb';
import type { UniversalChartSpec } from '@/types/chart';

const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';

export default function UsagePage() {
  return (
    <Suspense fallback={<div className="px-6 py-8"><div className="scan-loader" /></div>}>
      <UsagePageInner />
    </Suspense>
  );
}

function UsagePageInner() {
  const { profileDef } = useProfile();
  const searchParams = useSearchParams();
  const drillParams = parseDrillParams(searchParams);

  const [granularity, setGranularity] = useState<'day' | 'week' | 'month'>('month');
  const [timeSeries, setTimeSeries] = useState<any[]>([]);
  const [durationSeries, setDurationSeries] = useState<any[]>([]);
  const [periodData, setPeriodData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/analytics/time-series?client_id=1&metric=count&granularity=${granularity}`).then(r => r.json()),
      fetch(`${API}/analytics/time-series?client_id=1&metric=duration&granularity=${granularity}`).then(r => r.json()),
      fetch(`${API}/analytics/period-compare?client_id=1&period=month`).then(r => r.json()),
    ]).then(([ts, dur, period]) => {
      setTimeSeries(ts.series ?? []);
      setDurationSeries(dur.series ?? []);
      setPeriodData(period);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [granularity]);

  function handlePeriodClick(_dimKey: string, periodValue: string) {
    window.location.href = buildDrillUrl('/dashboard/analysis', {
      dim1: 'period',
      filter: { period: periodValue },
      from: 'usage',
    });
  }

  const countChart: UniversalChartSpec = {
    chart_type: 'line',
    title: 'Video Count Over Time',
    x: 'period',
    y: 'count',
    data: timeSeries,
    drillDown: {
      dimensionKey: 'period',
      targetPage: '/dashboard/analysis',
      targetParam: 'filter',
    },
    refLinks: [
      { label: 'View in Analysis', href: buildDrillUrl('/dashboard/analysis', { dim1: 'channel', from: 'usage' }) },
    ],
  };

  const durationChart: UniversalChartSpec = {
    chart_type: 'line',
    title: 'Cumulative Duration (hrs)',
    x: 'period',
    y: 'duration_hrs',
    data: durationSeries,
    drillDown: {
      dimensionKey: 'period',
      targetPage: '/dashboard/analysis',
      targetParam: 'filter',
    },
    refLinks: [
      { label: 'View in Analysis', href: buildDrillUrl('/dashboard/analysis', { dim1: 'channel', from: 'usage' }) },
    ],
  };

  const GRANS = [
    { value: 'day' as const, label: 'DAY' },
    { value: 'week' as const, label: 'WEEK' },
    { value: 'month' as const, label: 'MONTH' },
  ];

  return (
    <div style={{ minHeight: '100vh', background: 'var(--void)' }}>
      {/* Granularity bar */}
      <div className="flex items-center gap-4 px-6 py-2.5" style={{ borderBottom: '1px solid var(--wire)' }}>
        <span className="section-id">Usage & Trends</span>
        <div className="wire-v" style={{ height: '14px' }} />
        <span style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.14em', color: 'var(--on-low)', textTransform: 'uppercase' }}>
          Granularity
        </span>
        {GRANS.map((g, i) => (
          <span key={g.value} className="flex items-center gap-0">
            <span
              className={`range-opt${granularity === g.value ? ' selected' : ''}`}
              onClick={() => setGranularity(g.value)}
            >
              {g.label}
            </span>
            {i < GRANS.length - 1 && <span style={{ color: 'var(--wire-mid)', margin: '0 3px', fontSize: '0.55rem' }}>·</span>}
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
            currentPage="Usage"
            filters={drillParams.filters}
          />
        </div>
      )}

      {loading ? (
        <div className="px-6 py-8"><div className="scan-loader" /></div>
      ) : (
        <div style={{ padding: '24px 28px' }}>
          {/* Primary chart */}
          <ChartRenderer chart={countChart} onElementClick={handlePeriodClick} />

          <div className="wire-h" style={{ margin: '28px 0' }} />

          {/* Two-column: Period comparison + Duration chart */}
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '28px', marginBottom: '28px', overflow: 'visible' }}>
            {periodData && (
              <PeriodComparison
                current={periodData.current}
                previous={periodData.previous}
                deltas={periodData.deltas}
              />
            )}
            <ChartRenderer chart={durationChart} onElementClick={handlePeriodClick} />
          </div>
        </div>
      )}
    </div>
  );
}
