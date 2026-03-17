'use client';

import React, { useState, useRef, useCallback } from 'react';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ScatterChart, Scatter, Brush,
} from 'recharts';
import type { UniversalChartSpec } from '@/types/chart';
import { ChartInsightPanel } from '@/components/ChartInsightPanel';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '';

const COLORS = ['#E5001A', '#2D9CDB', '#F2A11A', '#1DB954', '#9B59B6', '#E67E22'];

const TOOLTIP_STYLE = {
  backgroundColor: '#141414',
  border: '1px solid #2C2C2C',
  borderRadius: '0',
  color: '#F0EDE8',
  fontFamily: 'var(--font-mono)',
  fontSize: '0.7rem',
  letterSpacing: '0.04em',
};

const AXIS_STYLE = {
  tick: { fill: '#52504C', fontSize: 10, fontFamily: 'var(--font-mono)' },
  axisLine: { stroke: '#2C2C2C' },
  tickLine: { stroke: '#2C2C2C' },
};

const GRID_STYLE = { stroke: '#1E1E1E', strokeDasharray: '1 4' };

const BAR_SHOW_ALL_THRESHOLD = 10;
const BRUSH_THRESHOLD = 15;

function resolveFields(chart: UniversalChartSpec): { xField: string; yField: string } {
  return {
    xField: chart.axes?.x?.field ?? chart.x ?? '',
    yField: chart.axes?.y?.field ?? chart.y ?? chart.yAxis ?? '',
  };
}

function resolvePieFields(chart: UniversalChartSpec): { categoryField: string; valueField: string } {
  const { xField, yField } = resolveFields(chart);
  return {
    categoryField: chart.category ?? chart.axes?.x?.field ?? xField,
    valueField:    chart.value    ?? chart.axes?.y?.field ?? yField,
  };
}

function pivotStackedData(
  data: Record<string, unknown>[], xField: string, yField: string, groupBy: string
): { pivoted: Record<string, unknown>[]; seriesKeys: string[] } {
  const map = new Map<string, Record<string, unknown>>();
  const seriesSet = new Set<string>();
  for (const row of data) {
    const xVal = String(row[xField]), groupVal = String(row[groupBy]);
    seriesSet.add(groupVal);
    if (!map.has(xVal)) map.set(xVal, { [xField]: row[xField] });
    map.get(xVal)![groupVal] = row[yField];
  }
  return { pivoted: Array.from(map.values()), seriesKeys: Array.from(seriesSet) };
}

function RefLinks({ links }: { links: Array<{ label: string; href: string }> }) {
  return (
    <div className="flex gap-4 mt-2">
      {links.map((link) => (
        <a
          key={link.href}
          href={link.href}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.6rem',
            color: 'var(--uplink)',
            textDecoration: 'none',
            letterSpacing: '0.04em',
          }}
          onMouseEnter={(e) => { (e.target as HTMLElement).style.textDecoration = 'underline'; }}
          onMouseLeave={(e) => { (e.target as HTMLElement).style.textDecoration = 'none'; }}
        >
          {link.label} →
        </a>
      ))}
    </div>
  );
}

interface ChartRendererProps {
  chart: UniversalChartSpec;
  onElementClick?: (dimensionKey: string, value: string) => void;
}

export function ChartRenderer({ chart, onElementClick }: ChartRendererProps) {
  const colors = chart.colors ?? COLORS;
  const { xField, yField } = resolveFields(chart);
  const hasDrill = Boolean(chart.drillDown);
  const cursorStyle = hasDrill ? 'pointer' : 'default';
  const [showAll, setShowAll] = useState(false);

  // ── Hover insight state ────────────────────────────────────────────────────
  const [insightVisible, setInsightVisible] = useState(false);
  const [insightLoading, setInsightLoading] = useState(false);
  const [insightSummary, setInsightSummary] = useState('');
  const [insightBullets, setInsightBullets] = useState<string[]>([]);
  const [insightError, setInsightError] = useState(false);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideTimer  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetched    = useRef(false);

  const fetchInsights = useCallback(async () => {
    if (fetched.current || !chart.data?.length) return;
    fetched.current = true;
    setInsightLoading(true);
    setInsightError(false);
    try {
      const url = `${API_BASE}/chart/insights`;
      console.log(`[ChartInsights] calling ${url} for chart: "${chart.title ?? chart.chart_type}" (${chart.data.length} rows)`);
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chart_title: chart.title ?? chart.chart_type,
          chart_type:  chart.chart_type,
          x_label:     xField || undefined,
          y_label:     yField || undefined,
          data:        chart.data,
        }),
      });
      if (res.ok) {
        const json = await res.json();
        setInsightSummary(json.summary ?? '');
        setInsightBullets(json.insights ?? []);
      } else {
        console.error(`[ChartInsights] ${res.status} from ${url}`);
        setInsightError(true);
      }
    } catch (err) {
      console.error('[ChartInsights] fetch failed:', err);
      setInsightError(true);
    } finally {
      setInsightLoading(false);
    }
  }, [chart, xField, yField]);

  function handleMouseEnter() {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hoverTimer.current = setTimeout(() => {
      setInsightVisible(true);
      fetchInsights();
    }, 400);
  }

  function handleMouseLeave() {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    hideTimer.current = setTimeout(() => setInsightVisible(false), 300);
  }

  function handleClick(dimensionKey: string, value: unknown) {
    if (onElementClick && value != null) {
      onElementClick(dimensionKey, String(value));
    }
  }

  function DrillTooltip({ active, payload, label }: any) {
    if (!active || !payload?.length) return null;
    return (
      <div style={TOOLTIP_STYLE}>
        <p style={{ margin: 0, fontWeight: 600 }}>{label}</p>
        {payload.map((entry: any, i: number) => (
          <p key={i} style={{ margin: '2px 0 0', color: entry.color }}>
            {entry.name}: {typeof entry.value === 'number' ? entry.value.toLocaleString() : entry.value}
          </p>
        ))}
        {hasDrill && (
          <p style={{ margin: '4px 0 0', fontSize: '0.55rem', color: '#52504C', fontStyle: 'italic' }}>
            Click to drill down
          </p>
        )}
      </div>
    );
  }

  const renderChart = () => {
    switch (chart.chart_type) {

      case 'line':
        return (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chart.data} margin={{ top: 4, right: 8, left: -16, bottom: 4 }}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis dataKey={xField} {...AXIS_STYLE} />
              <YAxis {...AXIS_STYLE} />
              <Tooltip content={hasDrill ? <DrillTooltip /> : undefined} contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined} cursor={{ stroke: '#2C2C2C' }} />
              <Line
                type="monotone"
                dataKey={yField}
                stroke={colors[0]}
                strokeWidth={1.5}
                dot={false}
                activeDot={{
                  r: 3,
                  fill: colors[0],
                  cursor: cursorStyle,
                  onClick: (_: any, payload: any) => {
                    if (payload?.payload) handleClick(xField, payload.payload[xField]);
                  },
                }}
              />
              {chart.data.length > BRUSH_THRESHOLD && (
                <Brush dataKey={xField} height={18} stroke={colors[0]} travellerWidth={8}
                  fill="#141414" />
              )}
            </LineChart>
          </ResponsiveContainer>
        );

      case 'bar': {
        const allData = chart.data;
        const displayData = (!showAll && allData.length > BAR_SHOW_ALL_THRESHOLD)
          ? allData.slice(0, BAR_SHOW_ALL_THRESHOLD)
          : allData;
        return (
          <>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={displayData} margin={{ top: 4, right: 8, left: -16, bottom: 4 }}>
                <CartesianGrid {...GRID_STYLE} />
                <XAxis dataKey={xField} {...AXIS_STYLE} />
                <YAxis {...AXIS_STYLE} />
                <Tooltip content={hasDrill ? <DrillTooltip /> : undefined} contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
                <Bar
                  dataKey={yField}
                  fill={colors[0]}
                  radius={[0, 0, 0, 0]}
                  maxBarSize={32}
                  cursor={cursorStyle}
                  onClick={(entry: any) => handleClick(xField, entry?.[xField])}
                />
              </BarChart>
            </ResponsiveContainer>
            {allData.length > BAR_SHOW_ALL_THRESHOLD && (
              <button
                onClick={() => setShowAll((p) => !p)}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.55rem',
                  color: 'var(--uplink)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  marginTop: '4px',
                  padding: 0,
                  letterSpacing: '0.04em',
                }}
              >
                {showAll ? `SHOW TOP ${BAR_SHOW_ALL_THRESHOLD}` : `SHOW ALL ${allData.length}`}
              </button>
            )}
          </>
        );
      }

      case 'pie': {
        const { categoryField, valueField } = resolvePieFields(chart);
        return (
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={chart.data}
                cx="50%" cy="50%"
                innerRadius={55}
                outerRadius={85}
                dataKey={valueField}
                nameKey={categoryField}
                strokeWidth={0}
                cursor={cursorStyle}
                onClick={(entry: any) => handleClick(categoryField, entry?.[categoryField] ?? entry?.name)}
              >
                {chart.data.map((_, i) => (
                  <Cell key={i} fill={colors[i % colors.length]} />
                ))}
              </Pie>
              <Tooltip content={hasDrill ? <DrillTooltip /> : undefined} contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined} />
              <Legend
                iconSize={6}
                iconType="square"
                wrapperStyle={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: '#9A9590', letterSpacing: '0.06em' }}
              />
            </PieChart>
          </ResponsiveContainer>
        );
      }

      case 'scatter':
        return (
          <ResponsiveContainer width="100%" height={220}>
            <ScatterChart margin={{ top: 4, right: 8, left: -16, bottom: 4 }}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis type="number" dataKey={xField} {...AXIS_STYLE} />
              <YAxis type="number" dataKey={yField} {...AXIS_STYLE} />
              <Tooltip content={hasDrill ? <DrillTooltip /> : undefined} contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined} cursor={{ stroke: '#2C2C2C' }} />
              <Scatter
                data={chart.data}
                fill={colors[0]}
                cursor={cursorStyle}
                onClick={(entry: any) => handleClick(xField, entry?.[xField])}
              />
            </ScatterChart>
          </ResponsiveContainer>
        );

      case 'stacked_bar': {
        const groupBy = chart.group_by;
        let renderData = chart.data;
        let seriesKeys: string[] = [];
        if (groupBy && chart.data.length > 0) {
          const { pivoted, seriesKeys: keys } = pivotStackedData(chart.data, xField, yField, groupBy);
          renderData = pivoted; seriesKeys = keys;
        } else {
          seriesKeys = Object.keys(chart.data[0] ?? {}).filter((k) => k !== xField);
        }
        return (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={renderData} margin={{ top: 4, right: 8, left: -16, bottom: 4 }}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis dataKey={xField} {...AXIS_STYLE} />
              <YAxis {...AXIS_STYLE} />
              <Tooltip content={hasDrill ? <DrillTooltip /> : undefined} contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
              <Legend wrapperStyle={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: '#9A9590' }} />
              {seriesKeys.map((key, idx) => (
                <Bar key={key} dataKey={key} stackId="a" fill={colors[idx % colors.length]}
                  radius={[0,0,0,0]} maxBarSize={32} cursor={cursorStyle}
                  onClick={(entry: any) => handleClick(xField, entry?.[xField])} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
      }

      case 'table':
      default: {
        if (!chart.data?.length) return <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--on-low)' }}>No data</p>;
        const cols = Object.keys(chart.data[0]);
        return (
          <div className="overflow-x-auto">
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--wire-mid)' }}>
                  {cols.map((col) => (
                    <th key={col} style={{ padding: '6px 8px', fontFamily: 'var(--font-condensed)', fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--on-low)', textAlign: 'left' }}>
                      {col.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {chart.data.map((row, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--wire)' }}>
                    {cols.map((col) => (
                      <td key={col} style={{ padding: '5px 8px', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--on-mid)' }}>
                        {String(row[col] ?? '—')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
    }
  };

  return (
    <div
      className="chart-panel"
      style={{ position: 'relative' }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {chart.title && (
        <div className="flex items-center gap-3 mb-4">
          <span className="section-id">{chart.title}</span>
          {chart.description && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--on-low)' }}>
              — {chart.description}
            </span>
          )}
        </div>
      )}
      {renderChart()}
      {chart.refLinks && chart.refLinks.length > 0 && <RefLinks links={chart.refLinks} />}
      <ChartInsightPanel
        visible={insightVisible}
        loading={insightLoading}
        summary={insightSummary}
        insights={insightBullets}
        error={insightError}
      />
    </div>
  );
}
