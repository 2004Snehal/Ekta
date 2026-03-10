'use client';

import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
} from 'recharts';
import type { UniversalChartSpec } from '@/types/chart';

// ─── Constants ────────────────────────────────────────────────────────────────

const COLORS = ['#FF4D5A', '#3B82F6', '#06B6D4', '#FB923C', '#8B5CF6', '#10B981'];

const TOOLTIP_STYLE = {
  backgroundColor: '#141414',
  border: '1px solid #2B2B2B',
  borderRadius: '8px',
  color: '#FFFFFF',
};

// ─── Field resolver ───────────────────────────────────────────────────────────
/**
 * Extracts the x / y field key from either the new universal spec
 * (axes.x.field / axes.y.field) or the legacy flat fields (x / y / yAxis).
 * This keeps the component backward-compatible while supporting the new format.
 */
function resolveFields(chart: UniversalChartSpec): { xField: string; yField: string } {
  const xField = chart.axes?.x?.field ?? chart.x ?? '';
  const yField = chart.axes?.y?.field ?? chart.y ?? chart.yAxis ?? '';
  return { xField, yField };
}

/** Resolves pie-specific fields: category (name column) and value (size column). */
function resolvePieFields(chart: UniversalChartSpec): { categoryField: string; valueField: string } {
  const { xField, yField } = resolveFields(chart);
  const categoryField = chart.category ?? chart.axes?.x?.field ?? xField;
  const valueField = chart.value ?? chart.axes?.y?.field ?? yField;
  return { categoryField, valueField };
}

/**
 * For stacked_bar the data is optionally in long format (each row has a
 * group_by column).  If group_by is provided we pivot to wide format so
 * Recharts can consume it directly.
 */
function pivotStackedData(
  data: Record<string, unknown>[],
  xField: string,
  yField: string,
  groupBy: string
): { pivoted: Record<string, unknown>[]; seriesKeys: string[] } {
  const map = new Map<string, Record<string, unknown>>();
  const seriesSet = new Set<string>();

  for (const row of data) {
    const xVal = String(row[xField]);
    const groupVal = String(row[groupBy]);
    seriesSet.add(groupVal);
    if (!map.has(xVal)) {
      map.set(xVal, { [xField]: row[xField] });
    }
    map.get(xVal)![groupVal] = row[yField];
  }

  return { pivoted: Array.from(map.values()), seriesKeys: Array.from(seriesSet) };
}

// ─── ChartRenderer ────────────────────────────────────────────────────────────
/**
 * Universal chart renderer.
 *
 * Accepts any chart spec that conforms to UniversalChartSpec.
 * The backend drives chart type, axes, and data — the frontend just renders.
 *
 * Supported chart_type values:
 *   "bar" | "line" | "pie" | "scatter" | "stacked_bar" | "table"
 *
 * @example
 * // New universal spec
 * <ChartRenderer chart={{
 *   chart_type: "bar",
 *   title: "Videos by Channel",
 *   axes: { x: { field: "channel" }, y: { field: "video_count" } },
 *   data: [{ channel: "News", video_count: 120 }]
 * }} />
 *
 * @example
 * // Legacy flat spec (still supported)
 * <ChartRenderer chart={{ chart_type: "bar", title: "...", x: "channel", y: "video_count", data: [...] }} />
 */
export function ChartRenderer({ chart }: { chart: UniversalChartSpec }) {
  const colors = chart.colors ?? COLORS;
  const { xField, yField } = resolveFields(chart);

  const renderChart = () => {
    switch (chart.chart_type) {

      // ── Line ───────────────────────────────────────────────────────────────
      case 'line':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chart.data} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2B2B2B" />
              <XAxis dataKey={xField} stroke="#9CA3AF" label={chart.axes?.x?.label ? { value: chart.axes.x.label, position: 'insideBottom', offset: -4, fill: '#9CA3AF', fontSize: 12 } : undefined} />
              <YAxis stroke="#9CA3AF" label={chart.axes?.y?.label ? { value: chart.axes.y.label, angle: -90, position: 'insideLeft', fill: '#9CA3AF', fontSize: 12 } : undefined} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend />
              <Line type="monotone" dataKey={yField} stroke={colors[0]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        );

      // ── Bar ────────────────────────────────────────────────────────────────
      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chart.data} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2B2B2B" />
              <XAxis dataKey={xField} stroke="#9CA3AF" label={chart.axes?.x?.label ? { value: chart.axes.x.label, position: 'insideBottom', offset: -4, fill: '#9CA3AF', fontSize: 12 } : undefined} />
              <YAxis stroke="#9CA3AF" label={chart.axes?.y?.label ? { value: chart.axes.y.label, angle: -90, position: 'insideLeft', fill: '#9CA3AF', fontSize: 12 } : undefined} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend />
              <Bar dataKey={yField} fill={colors[0]} radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        );

      // ── Pie ────────────────────────────────────────────────────────────────
      case 'pie': {
        const { categoryField, valueField } = resolvePieFields(chart);
        return (
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={chart.data}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, value: v }) => `${name}: ${v}`}
                outerRadius={100}
                dataKey={valueField}
                nameKey={categoryField}
              >
                {chart.data.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        );
      }

      // ── Scatter ────────────────────────────────────────────────────────────
      case 'scatter':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2B2B2B" />
              <XAxis type="number" dataKey={xField} stroke="#9CA3AF" name={chart.axes?.x?.label ?? xField} />
              <YAxis type="number" dataKey={yField} stroke="#9CA3AF" name={chart.axes?.y?.label ?? yField} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ strokeDasharray: '3 3' }} />
              <Legend />
              <Scatter name={chart.axes?.y?.label ?? yField} data={chart.data} fill={colors[0]} />
            </ScatterChart>
          </ResponsiveContainer>
        );

      // ── Stacked Bar ────────────────────────────────────────────────────────
      case 'stacked_bar': {
        // If group_by is present, pivot long → wide so Recharts can stack
        const groupBy = chart.group_by;
        let renderData = chart.data;
        let seriesKeys: string[] = [];

        if (groupBy && chart.data.length > 0) {
          const { pivoted, seriesKeys: keys } = pivotStackedData(chart.data, xField, yField, groupBy);
          renderData = pivoted;
          seriesKeys = keys;
        } else {
          // Wide format: every key except xField is a series
          seriesKeys = Object.keys(chart.data[0] ?? {}).filter((k) => k !== xField);
        }

        return (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={renderData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2B2B2B" />
              <XAxis dataKey={xField} stroke="#9CA3AF" />
              <YAxis stroke="#9CA3AF" />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend />
              {seriesKeys.map((key, idx) => (
                <Bar
                  key={key}
                  dataKey={key}
                  stackId="a"
                  fill={colors[idx % colors.length]}
                  radius={idx === seriesKeys.length - 1 ? [8, 8, 0, 0] : [0, 0, 0, 0]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
      }

      // ── Table fallback ─────────────────────────────────────────────────────
      case 'table':
      default: {
        if (!chart.data?.length) {
          return <div className="text-muted-foreground text-sm">No data available.</div>;
        }
        const cols = Object.keys(chart.data[0]);
        return (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left text-foreground">
              <thead>
                <tr className="border-b border-border">
                  {cols.map((col) => (
                    <th key={col} className="px-3 py-2 font-semibold text-muted-foreground capitalize">
                      {col.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {chart.data.map((row, i) => (
                  <tr key={i} className="border-b border-border/50 hover:bg-secondary/30 transition-colors">
                    {cols.map((col) => (
                      <td key={col} className="px-3 py-2">
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
    <div className="bg-card border border-border rounded-lg p-6">
      {chart.title && (
        <h3 className="text-lg font-semibold text-foreground mb-1">{chart.title}</h3>
      )}
      {chart.description && (
        <p className="text-muted-foreground text-sm mb-4">{chart.description}</p>
      )}
      {!chart.title && !chart.description && <div className="mb-4" />}
      {renderChart()}
    </div>
  );
}
