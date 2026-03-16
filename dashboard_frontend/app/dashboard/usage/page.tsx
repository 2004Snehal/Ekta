'use client';

import { useEffect, useState } from 'react';
import { useProfile } from '@/lib/profiles';
import { ChartRenderer } from '@/components/ChartRenderer';
import { PeriodComparison } from '@/components/PeriodComparison';
import type { UniversalChartSpec } from '@/types/chart';

const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';

export default function UsagePage() {
  const { profileDef } = useProfile();
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

  const countChart: UniversalChartSpec = {
    chart_type: 'line',
    title: 'Video Count Over Time',
    x: 'period',
    y: 'count',
    data: timeSeries,
  };

  const durationChart: UniversalChartSpec = {
    chart_type: 'line',
    title: 'Cumulative Duration (hrs)',
    x: 'period',
    y: 'duration_hrs',
    data: durationSeries,
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

      {loading ? (
        <div className="px-6 py-8"><div className="scan-loader" /></div>
      ) : (
        <div style={{ padding: '24px 28px' }}>
          {/* Primary chart */}
          <ChartRenderer chart={countChart} />

          <div className="wire-h" style={{ margin: '28px 0' }} />

          {/* Two-column: Period comparison + Duration chart */}
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '28px', marginBottom: '28px' }}>
            {periodData && (
              <PeriodComparison
                current={periodData.current}
                previous={periodData.previous}
                deltas={periodData.deltas}
              />
            )}
            <ChartRenderer chart={durationChart} />
          </div>
        </div>
      )}
    </div>
  );
}
