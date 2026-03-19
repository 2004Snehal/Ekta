"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const COLORS = [
  "#E55A5A",
  "#2D9CDB",
  "#F2A11A",
  "#1DB954",
  "#9B59B6",
  "#E67E22",
  "#1ABC9C",
  "#E74C3C",
];

const TOOLTIP_STYLE = {
  backgroundColor: "#141414",
  border: "1px solid #2C2C2C",
  borderRadius: "0",
  color: "#F0EDE8",
  fontFamily: "var(--font-mono)",
  fontSize: "0.7rem",
};

const AXIS_STYLE = {
  tick: { fill: "#A3A3A3", fontSize: 10, fontFamily: "var(--font-mono)" },
  axisLine: { stroke: "#2C2C2C" },
  tickLine: { stroke: "#2C2C2C" },
};

function formatXAxisLabel(value: string): string {
  if (!value) return "";
  try {
    const date = new Date(value);
    if (!isNaN(date.getTime())) {
      return date.toLocaleDateString("en-US", {
        month: "short",
        day: "2-digit",
      });
    }
  } catch (e) {
    // fallback
  }
  return String(value).substring(0, 8);
}

interface CrossTabRow {
  dim1: string;
  dim2?: string;
  count: number;
  duration_hrs: number;
  published_count: number;
  publish_rate: number;
}

interface CrossTabChartProps {
  rows: CrossTabRow[];
  dim1Key: string;
  dim2Key: string | null;
  metric: string;
  onBarClick?: (dimensionValue: string) => void;
}

export function CrossTabChart({
  rows,
  dim1Key,
  dim2Key,
  metric,
  onBarClick,
}: CrossTabChartProps) {
  const barCursor = onBarClick ? "pointer" : "default";
  if (!dim2Key) {
    // Single dimension — simple bar chart
    return (
      <div>
        <div className="flex items-center gap-3 mb-4">
          <span className="section-id">
            {dim1Key} by {metric}
          </span>
        </div>
        <ResponsiveContainer
          width="100%"
          height={Math.max(220, rows.length * 28)}
        >
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ top: 4, right: 8, left: 80, bottom: 4 }}
          >
            <CartesianGrid
              stroke="#1E1E1E"
              strokeDasharray="1 4"
              horizontal={false}
            />
            <XAxis type="number" {...AXIS_STYLE} />
            <YAxis type="category" dataKey="dim1" {...AXIS_STYLE} width={75} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Bar
              dataKey={metric}
              fill={COLORS[0]}
              maxBarSize={20}
              radius={[0, 2, 2, 0]}
              cursor={barCursor}
              onClick={(entry: any) => onBarClick?.(String(entry?.dim1 ?? ""))}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // Two dimensions — pivot into stacked bar
  const pivotMap = new Map<string, Record<string, unknown>>();
  const dim2Values = new Set<string>();

  for (const row of rows) {
    const d1 = row.dim1;
    const d2 = row.dim2 ?? "unknown";
    dim2Values.add(d2);
    if (!pivotMap.has(d1)) pivotMap.set(d1, { dim1: d1 });
    pivotMap.get(d1)![d2] = row[metric as keyof CrossTabRow] ?? row.count;
  }

  const pivoted = Array.from(pivotMap.values());
  const series = Array.from(dim2Values);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <span className="section-id">
          {dim1Key} × {dim2Key}
        </span>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.55rem",
            color: "var(--on-low)",
          }}
        >
          — metric: {metric}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart
          data={pivoted}
          margin={{ top: 4, right: 8, left: -16, bottom: 4 }}
        >
          <CartesianGrid stroke="#1E1E1E" strokeDasharray="1 4" />
          <XAxis dataKey="dim1" {...AXIS_STYLE} />
          <YAxis {...AXIS_STYLE} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend
            wrapperStyle={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.55rem",
              color: "#9A9590",
            }}
          />
          {series.map((s, i) => (
            <Bar
              key={s}
              dataKey={s}
              stackId="a"
              fill={COLORS[i % COLORS.length]}
              maxBarSize={32}
              radius={[2, 2, 0, 0]}
              cursor={barCursor}
              onClick={(entry: any) => onBarClick?.(String(entry?.dim1 ?? ""))}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
