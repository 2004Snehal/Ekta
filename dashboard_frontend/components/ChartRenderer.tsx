'use client';

import React from 'react';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ScatterChart, Scatter,
} from 'recharts';
import type { UniversalChartSpec } from '@/types/chart';

const COLORS = ['#C4553A', '#5B7EA1', '#C68B2C', '#5B8A72', '#8B6FA3', '#D4864B'];

const TOOLTIP_STYLE = {
  backgroundColor: '#FFFFFF',
  border: '1px solid #E5DFD7',
  borderRadius: '10px',
  color: '#2B2320',
  fontFamily: 'var(--font-mono)',
  fontSize: '0.72rem',
  letterSpacing: '0.02em',
  boxShadow: '0 4px 16px rgba(43, 35, 32, 0.1)',
};

const AXIS_STYLE = {
  tick: { fill: '#B0A99F', fontSize: 11, fontFamily: 'var(--font-mono)' },
  axisLine: { stroke: '#E5DFD7' },
  tickLine: { stroke: '#E5DFD7' },
};

const GRID_STYLE = { stroke: '#E5DFD7', strokeDasharray: '2 4' };

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

export function ChartRenderer({ chart }: { chart: UniversalChartSpec }) {
  const colors = chart.colors ?? COLORS;
  const { xField, yField } = resolveFields(chart);

  const renderChart = () => {
    switch (chart.chart_type) {

      case 'line':
        return (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chart.data} margin={{ top: 4, right: 12, left: -16, bottom: 4 }}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis dataKey={xField} {...AXIS_STYLE} />
              <YAxis {...AXIS_STYLE} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: '#E5DFD7' }} />
              <Line type="monotone" dataKey={yField} stroke={colors[0]} strokeWidth={2} dot={false} activeDot={{ r: 4, fill: colors[0], stroke: '#fff', strokeWidth: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        );

      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chart.data} margin={{ top: 4, right: 12, left: -16, bottom: 4 }}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis dataKey={xField} {...AXIS_STYLE} />
              <YAxis {...AXIS_STYLE} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(196, 85, 58, 0.04)' }} />
              <Bar dataKey={yField} fill={colors[0]} radius={[4, 4, 0, 0]} maxBarSize={36} />
            </BarChart>
          </ResponsiveContainer>
        );

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
                strokeWidth={2}
                stroke="#F5F1EB"
              >
                {chart.data.map((_, i) => (
                  <Cell key={i} fill={colors[i % colors.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend
                iconSize={8}
                iconType="circle"
                wrapperStyle={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', color: '#7A7067' }}
              />
            </PieChart>
          </ResponsiveContainer>
        );
      }

      case 'scatter':
        return (
          <ResponsiveContainer width="100%" height={220}>
            <ScatterChart margin={{ top: 4, right: 12, left: -16, bottom: 4 }}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis type="number" dataKey={xField} {...AXIS_STYLE} />
              <YAxis type="number" dataKey={yField} {...AXIS_STYLE} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: '#E5DFD7' }} />
              <Scatter data={chart.data} fill={colors[0]} />
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
            <BarChart data={renderData} margin={{ top: 4, right: 12, left: -16, bottom: 4 }}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis dataKey={xField} {...AXIS_STYLE} />
              <YAxis {...AXIS_STYLE} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(196, 85, 58, 0.04)' }} />
              <Legend wrapperStyle={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', color: '#7A7067' }} />
              {seriesKeys.map((key, idx) => (
                <Bar key={key} dataKey={key} stackId="a" fill={colors[idx % colors.length]} radius={idx === seriesKeys.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} maxBarSize={36} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
      }

      case 'table':
      default: {
        if (!chart.data?.length) return <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--on-low)' }}>No data</p>;
        const cols = Object.keys(chart.data[0]);
        return (
          <div className="overflow-x-auto">
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--wire)' }}>
                  {cols.map((col) => (
                    <th key={col} style={{ padding: '8px 10px', fontFamily: 'var(--font-sans)', fontSize: '0.7rem', fontWeight: 700, color: 'var(--on-low)', textAlign: 'left' }}>
                      {col.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {chart.data.map((row, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--wire)' }}>
                    {cols.map((col) => (
                      <td key={col} style={{ padding: '7px 10px', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--on-mid)' }}>
                        {String(row[col] ?? '\u2014')}
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

  if (chart.chart_type === 'table') {
    return renderChart() as React.ReactElement;
  }

  return (
    <div style={{
      borderRadius: '16px',
      border: '1px solid var(--wire)',
      background: 'var(--surface)',
      padding: '20px 20px 16px',
      boxShadow: '0 1px 4px rgba(43, 35, 32, 0.04)',
      animation: 'fade-up 0.4s ease-out both',
    }}>
      {chart.title && (
        <div style={{ marginBottom: '16px' }}>
          <h3 style={{
            fontFamily: 'var(--font-display)',
            fontSize: '0.95rem',
            fontWeight: 700,
            color: 'var(--on)',
            lineHeight: 1.3,
            marginBottom: chart.description ? '3px' : 0,
          }}>
            {chart.title}
          </h3>
          {chart.description && (
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', color: 'var(--on-low)' }}>
              {chart.description}
            </span>
          )}
        </div>
      )}
      {renderChart()}
    </div>
  );
}
