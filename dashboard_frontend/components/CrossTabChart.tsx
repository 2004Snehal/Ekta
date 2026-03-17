'use client';

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const COLORS = ['#C4553A', '#5B7EA1', '#C68B2C', '#5B8A72', '#8B6FA3', '#D4864B', '#6B9E8A', '#A0726A'];

const TOOLTIP_STYLE = {
  backgroundColor: '#FFFFFF',
  border: '1px solid #E5DFD7',
  borderRadius: '10px',
  color: '#2B2320',
  fontFamily: 'var(--font-mono)',
  fontSize: '0.72rem',
  boxShadow: '0 4px 16px rgba(43, 35, 32, 0.1)',
};

const AXIS_STYLE = {
  tick: { fill: '#B0A99F', fontSize: 11, fontFamily: 'var(--font-mono)' },
  axisLine: { stroke: '#E5DFD7' },
  tickLine: { stroke: '#E5DFD7' },
};

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

export function CrossTabChart({ rows, dim1Key, dim2Key, metric, onBarClick }: CrossTabChartProps) {
  const barCursor = onBarClick ? 'pointer' : 'default';
  if (!dim2Key) {
    return (
      <div>
        <div className="flex items-center gap-3 mb-4">
          <span className="section-id">{dim1Key} by {metric}</span>
        </div>
        <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 30)}>
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 12, left: 80, bottom: 4 }}>
            <CartesianGrid stroke="#E5DFD7" strokeDasharray="2 4" horizontal={false} />
            <XAxis type="number" {...AXIS_STYLE} />
            <YAxis type="category" dataKey="dim1" {...AXIS_STYLE} width={75} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Bar dataKey={metric} fill={COLORS[0]} maxBarSize={22} radius={[0, 4, 4, 0]}
              cursor={barCursor} onClick={(entry: any) => onBarClick?.(String(entry?.dim1 ?? ''))} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  const pivotMap = new Map<string, Record<string, unknown>>();
  const dim2Values = new Set<string>();

  for (const row of rows) {
    const d1 = row.dim1;
    const d2 = row.dim2 ?? 'unknown';
    dim2Values.add(d2);
    if (!pivotMap.has(d1)) pivotMap.set(d1, { dim1: d1 });
    pivotMap.get(d1)![d2] = row[metric as keyof CrossTabRow] ?? row.count;
  }

  const pivoted = Array.from(pivotMap.values());
  const series = Array.from(dim2Values);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <span className="section-id">{dim1Key} × {dim2Key}</span>
        <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', color: 'var(--on-low)' }}>
          {metric}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={pivoted} margin={{ top: 4, right: 12, left: -16, bottom: 4 }}>
          <CartesianGrid stroke="#E5DFD7" strokeDasharray="2 4" />
          <XAxis dataKey="dim1" {...AXIS_STYLE} />
          <YAxis {...AXIS_STYLE} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', color: '#7A7067' }} />
          {series.map((s, i) => (
            <Bar key={s} dataKey={s} stackId="a" fill={COLORS[i % COLORS.length]} maxBarSize={36}
              radius={i === series.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
              cursor={barCursor} onClick={(entry: any) => onBarClick?.(String(entry?.dim1 ?? ''))} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
