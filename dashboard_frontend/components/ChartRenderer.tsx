"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
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
  Brush,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from "recharts";
import type { UniversalChartSpec } from "@/types/chart";
import { ChartInsightPanel } from "@/components/ChartInsightPanel";
import { useProfile } from "@/lib/profiles";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

const COLORS = [
  "#E55A5A",
  "#2D9CDB",
  "#F2A11A",
  "#1DB954",
  "#9B59B6",
  "#E67E22",
];

const TOOLTIP_STYLE = {
  backgroundColor: "#141414",
  border: "1px solid #2C2C2C",
  borderRadius: "0",
  color: "#F5F5F5",
  fontFamily: "var(--font-mono)",
  fontSize: "0.7rem",
  letterSpacing: "0.04em",
};

const AXIS_STYLE = {
  tick: { fill: "#A3A3A3", fontSize: 10, fontFamily: "var(--font-mono)" },
  axisLine: { stroke: "#2C2C2C" },
  tickLine: { stroke: "#2C2C2C" },
};

const GRID_STYLE = { stroke: "#1E1E1E", strokeDasharray: "1 4" };

const BAR_SHOW_ALL_THRESHOLD = 10;
const BRUSH_THRESHOLD = 15;

function resolveFields(chart: UniversalChartSpec): {
  xField: string;
  yField: string;
} {
  return {
    xField: chart.axes?.x?.field ?? chart.x ?? "",
    yField: chart.axes?.y?.field ?? chart.y ?? chart.yAxis ?? "",
  };
}

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

function resolvePieFields(chart: UniversalChartSpec): {
  categoryField: string;
  valueField: string;
} {
  const { xField, yField } = resolveFields(chart);
  return {
    categoryField: chart.category ?? chart.axes?.x?.field ?? xField,
    valueField: chart.value ?? chart.axes?.y?.field ?? yField,
  };
}

function pivotStackedData(
  data: Record<string, unknown>[],
  xField: string,
  yField: string,
  groupBy: string,
): { pivoted: Record<string, unknown>[]; seriesKeys: string[] } {
  const map = new Map<string, Record<string, unknown>>();
  const seriesSet = new Set<string>();
  for (const row of data) {
    const xVal = String(row[xField]),
      groupVal = String(row[groupBy]);
    seriesSet.add(groupVal);
    if (!map.has(xVal)) map.set(xVal, { [xField]: row[xField] });
    map.get(xVal)![groupVal] = row[yField];
  }
  return {
    pivoted: Array.from(map.values()),
    seriesKeys: Array.from(seriesSet),
  };
}

function pivotRadarData(
  data: Record<string, unknown>[],
  entityField: string,
): { pivoted: Record<string, unknown>[]; entityKeys: string[] } {
  if (!data.length) return { pivoted: [], entityKeys: [] };
  const first = data[0];
  const metricCols = Object.keys(first).filter(
    (k) => k !== entityField && typeof first[k] === "number",
  );
  const entityKeys = data.map((r) => String(r[entityField]));
  const pivoted = metricCols.map((col) => {
    const entry: Record<string, unknown> = { subject: col };
    data.forEach((row) => {
      entry[String(row[entityField])] = row[col];
    });
    return entry;
  });
  return { pivoted, entityKeys };
}

function RefLinks({
  links,
}: {
  links: Array<{ label: string; href: string }>;
}) {
  return (
    <div className="flex gap-4 mt-2">
      {links.map((link) => (
        <a
          key={link.href}
          href={link.href}
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.6rem",
            color: "var(--uplink)",
            textDecoration: "none",
            letterSpacing: "0.04em",
          }}
          onMouseEnter={(e) => {
            (e.target as HTMLElement).style.textDecoration = "underline";
          }}
          onMouseLeave={(e) => {
            (e.target as HTMLElement).style.textDecoration = "none";
          }}
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
  const cursorStyle = hasDrill ? "pointer" : "default";
  const [showAll, setShowAll] = useState(false);
  const { profile } = useProfile();

  // ── Hover insight state ────────────────────────────────────────────────────
  const [insightVisible, setInsightVisible] = useState(false);
  const dismissed = useRef(false);
  const [descLoading, setDescLoading] = useState(false);
  const [description, setDescription] = useState("");
  const [dataLoading, setDataLoading] = useState(false);
  const [insightSummary, setInsightSummary] = useState("");
  const [insightBullets, setInsightBullets] = useState<string[]>([]);
  const [descError, setDescError] = useState(false);
  const [dataError, setDataError] = useState(false);

  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const descFetched = useRef(false);

  // ── sessionStorage-backed cache helpers ──────────────────────────────────
  function dataFingerprint(data: Record<string, unknown>[]): string {
    if (!data.length) return "empty";
    return `${data.length}|${JSON.stringify(data[0])}|${JSON.stringify(data[data.length - 1])}`;
  }

  function cacheKey(prefix: string, extra: string): string {
    return `ci_${prefix}_${extra}`;
  }

  function getSessionCache(key: string): { summary: string; insights: string[] } | null {
    try {
      const raw = sessionStorage.getItem(key);
      if (raw) return JSON.parse(raw);
    } catch {}
    return null;
  }

  function setSessionCache(key: string, val: { summary: string; insights: string[] }) {
    try {
      sessionStorage.setItem(key, JSON.stringify(val));
    } catch {}
  }

  function getDescCache(key: string): string | null {
    try { return sessionStorage.getItem(key); } catch { return null; }
  }

  function setDescCache(key: string, val: string) {
    try { sessionStorage.setItem(key, val); } catch {}
  }

  const chartTitle = chart.title ?? chart.chart_type;

  const fetchDescription = useCallback(async () => {
    if (descFetched.current) return;
    descFetched.current = true;

    // Check sessionStorage first
    const descCacheKey = cacheKey("desc", chartTitle);
    const cachedDesc = getDescCache(descCacheKey);
    if (cachedDesc) {
      setDescription(cachedDesc);
      return;
    }

    setDescLoading(true);
    setDescError(false);
    try {
      const params = new URLSearchParams({
        chart_title: chartTitle,
        chart_type: chart.chart_type,
      });
      if (xField) params.set("x_label", xField);
      if (yField) params.set("y_label", yField);
      const res = await fetch(`${API_BASE}/chart/description?${params}`);
      if (res.ok) {
        const json = await res.json();
        const desc = json.description ?? "";
        setDescription(desc);
        setDescCache(descCacheKey, desc);
      } else {
        setDescError(true);
      }
    } catch {
      setDescError(true);
    } finally {
      setDescLoading(false);
    }
  }, [chartTitle, chart.chart_type, xField, yField]);

  const fetchDataInsights = useCallback(async () => {
    if (!chart.data?.length) return;
    const fp = dataFingerprint(chart.data as Record<string, unknown>[]);
    const insightCacheKey = cacheKey("data", `${chartTitle}|${fp}`);

    // Check sessionStorage first (skip empty/error entries)
    const cached = getSessionCache(insightCacheKey);
    if (cached && (cached.summary || cached.insights.length > 0) && !cached.summary?.startsWith("AI Insights temporarily")) {
      setInsightSummary(cached.summary);
      setInsightBullets(cached.insights);
      setDataError(false);
      return;
    }

    setDataLoading(true);
    setDataError(false);
    setInsightSummary("");
    setInsightBullets([]);
    try {
      const res = await fetch(`${API_BASE}/chart/data-insights`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chart_title: chartTitle,
          chart_type: chart.chart_type,
          x_label: xField || undefined,
          y_label: yField || undefined,
          data: chart.data,
          user_role: profile,
        }),
      });
      if (res.ok) {
        const json = await res.json();
        const entry = {
          summary: json.summary ?? "",
          insights: json.insights ?? [],
        };
        // Only cache successful non-error responses
        if (!entry.summary.startsWith("AI Insights temporarily")) {
          setSessionCache(insightCacheKey, entry);
        }
        setInsightSummary(entry.summary);
        setInsightBullets(entry.insights);
      } else {
        setDataError(true);
      }
    } catch {
      setDataError(true);
    } finally {
      setDataLoading(false);
    }
  }, [chart.data, chart.chart_type, chartTitle, xField, yField]);

  // Re-fetch data insights when data changes (e.g. timeline/filter change)
  useEffect(() => {
    if (insightVisible) {
      fetchDataInsights();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chart.data]);

  function handleMouseEnter() {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    if (dismissed.current) return;
    hoverTimer.current = setTimeout(() => {
      setInsightVisible(true);
      fetchDescription();
      fetchDataInsights();
    }, 400);
  }

  function handleMouseLeave() {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    dismissed.current = false;
    hideTimer.current = setTimeout(() => setInsightVisible(false), 300);
  }

  function handleInsightClose() {
    dismissed.current = true;
    setInsightVisible(false);
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
          <p key={i} style={{ margin: "2px 0 0", color: entry.color }}>
            {entry.name}:{" "}
            {typeof entry.value === "number"
              ? entry.value.toLocaleString()
              : entry.value}
          </p>
        ))}
        {hasDrill && (
          <p
            style={{
              margin: "4px 0 0",
              fontSize: "0.55rem",
              color: "#A3A3A3",
              fontStyle: "italic",
            }}
          >
            Click to drill down
          </p>
        )}
      </div>
    );
  }

  const renderChart = () => {
    switch (chart.chart_type) {
      case "line":
        return (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart
              data={chart.data}
              margin={{ top: 4, right: 8, left: -16, bottom: 40 }}
            >
              <defs>
                <linearGradient id="colorGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="rgba(229, 90, 90, 0.2)" />
                  <stop offset="95%" stopColor="rgba(229, 90, 90, 0)" />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis
                dataKey={xField}
                {...AXIS_STYLE}
                tick={({ x, y, payload }: any) => {
                  const formatted = formatXAxisLabel(payload.value);
                  return (
                    <g transform={`translate(${x},${y})`}>
                      <text
                        x={0}
                        y={0}
                        dy={4}
                        textAnchor="end"
                        fill="#A3A3A3"
                        fontSize="10"
                        fontFamily="var(--font-mono)"
                        style={{
                          transform: "rotate(-45deg)",
                          transformOrigin: "0 0",
                        }}
                      >
                        {formatted}
                      </text>
                    </g>
                  );
                }}
                height={60}
              />
              <YAxis {...AXIS_STYLE} />
              <Tooltip
                content={hasDrill ? <DrillTooltip /> : undefined}
                contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined}
                cursor={{ stroke: "#2C2C2C" }}
              />
              <Area
                type="monotone"
                dataKey={yField}
                stroke={colors[0]}
                strokeWidth={2}
                fill="url(#colorGradient)"
                dot={false}
                activeDot={{
                  r: 3,
                  fill: colors[0],
                  cursor: cursorStyle,
                  onClick: (_: any, payload: any) => {
                    if (payload?.payload)
                      handleClick(xField, payload.payload[xField]);
                  },
                }}
              />
              {chart.data.length > BRUSH_THRESHOLD && (
                <Brush
                  dataKey={xField}
                  height={18}
                  stroke={colors[0]}
                  travellerWidth={8}
                  fill="#141414"
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        );

      case "bar": {
        const allData = chart.data;
        const displayData =
          !showAll && allData.length > BAR_SHOW_ALL_THRESHOLD
            ? allData.slice(0, BAR_SHOW_ALL_THRESHOLD)
            : allData;
        return (
          <>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={displayData}
                margin={{ top: 4, right: 8, left: -16, bottom: 40 }}
              >
                <CartesianGrid {...GRID_STYLE} />
                <XAxis
                  dataKey={xField}
                  {...AXIS_STYLE}
                  tick={({ x, y, payload }: any) => {
                    const formatted = formatXAxisLabel(payload.value);
                    return (
                      <g transform={`translate(${x},${y})`}>
                        <text
                          x={0}
                          y={0}
                          dy={4}
                          textAnchor="end"
                          fill="#A3A3A3"
                          fontSize="10"
                          fontFamily="var(--font-mono)"
                          style={{
                            transform: "rotate(-45deg)",
                            transformOrigin: "0 0",
                          }}
                        >
                          {formatted}
                        </text>
                      </g>
                    );
                  }}
                  height={60}
                />
                <YAxis {...AXIS_STYLE} />
                <Tooltip
                  content={hasDrill ? <DrillTooltip /> : undefined}
                  contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined}
                  cursor={{ fill: "rgba(255,255,255,0.03)" }}
                />
                <Bar
                  dataKey={yField}
                  fill={colors[0]}
                  radius={[2, 2, 0, 0]}
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
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.55rem",
                  color: "var(--uplink)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  marginTop: "4px",
                  padding: 0,
                  letterSpacing: "0.04em",
                }}
              >
                {showAll
                  ? `SHOW TOP ${BAR_SHOW_ALL_THRESHOLD}`
                  : `SHOW ALL ${allData.length}`}
              </button>
            )}
          </>
        );
      }

      case "pie": {
        const { categoryField, valueField } = resolvePieFields(chart);
        return (
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={chart.data}
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={85}
                dataKey={valueField}
                nameKey={categoryField}
                strokeWidth={0}
                cursor={cursorStyle}
                onClick={(entry: any) =>
                  handleClick(
                    categoryField,
                    entry?.[categoryField] ?? entry?.name,
                  )
                }
              >
                {chart.data.map((_, i) => (
                  <Cell key={i} fill={colors[i % colors.length]} />
                ))}
              </Pie>
              <Tooltip
                content={hasDrill ? <DrillTooltip /> : undefined}
                contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined}
              />
              <Legend
                iconSize={6}
                iconType="square"
                wrapperStyle={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  color: "#9A9590",
                  letterSpacing: "0.06em",
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        );
      }

      case "scatter":
        return (
          <ResponsiveContainer width="100%" height={220}>
            <ScatterChart margin={{ top: 4, right: 8, left: -16, bottom: 40 }}>
              <CartesianGrid {...GRID_STYLE} />
              <XAxis
                type="number"
                dataKey={xField}
                {...AXIS_STYLE}
                tick={({ x, y, payload }: any) => {
                  const formatted = formatXAxisLabel(String(payload.value));
                  return (
                    <g transform={`translate(${x},${y})`}>
                      <text
                        x={0}
                        y={0}
                        dy={4}
                        textAnchor="end"
                        fill="#A3A3A3"
                        fontSize="10"
                        fontFamily="var(--font-mono)"
                        style={{
                          transform: "rotate(-45deg)",
                          transformOrigin: "0 0",
                        }}
                      >
                        {formatted}
                      </text>
                    </g>
                  );
                }}
                height={60}
              />
              <YAxis type="number" dataKey={yField} {...AXIS_STYLE} />
              <Tooltip
                content={hasDrill ? <DrillTooltip /> : undefined}
                contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined}
                cursor={{ stroke: "#2C2C2C" }}
              />
              <Scatter
                data={chart.data}
                fill={colors[0]}
                cursor={cursorStyle}
                onClick={(entry: any) => handleClick(xField, entry?.[xField])}
              />
            </ScatterChart>
          </ResponsiveContainer>
        );

      case "stacked_bar": {
        const groupBy = chart.group_by;
        let renderData = chart.data;
        let seriesKeys: string[] = [];
        if (groupBy && chart.data.length > 0) {
          const { pivoted, seriesKeys: keys } = pivotStackedData(
            chart.data,
            xField,
            yField,
            groupBy,
          );
          renderData = pivoted;
          seriesKeys = keys;
        } else {
          seriesKeys = Object.keys(chart.data[0] ?? {}).filter(
            (k) => k !== xField,
          );
        }
        return (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={renderData}
              margin={{ top: 4, right: 8, left: -16, bottom: 40 }}
            >
              <CartesianGrid {...GRID_STYLE} />
              <XAxis
                dataKey={xField}
                {...AXIS_STYLE}
                tick={({ x, y, payload }: any) => {
                  const formatted = formatXAxisLabel(payload.value);
                  return (
                    <g transform={`translate(${x},${y})`}>
                      <text
                        x={0}
                        y={0}
                        dy={4}
                        textAnchor="end"
                        fill="#A3A3A3"
                        fontSize="10"
                        fontFamily="var(--font-mono)"
                        style={{
                          transform: "rotate(-45deg)",
                          transformOrigin: "0 0",
                        }}
                      >
                        {formatted}
                      </text>
                    </g>
                  );
                }}
                height={60}
              />
              <YAxis {...AXIS_STYLE} />
              <Tooltip
                content={hasDrill ? <DrillTooltip /> : undefined}
                contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined}
                cursor={{ fill: "rgba(255,255,255,0.03)" }}
              />
              <Legend
                wrapperStyle={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  color: "#9A9590",
                }}
              />
              {seriesKeys.map((key, idx) => (
                <Bar
                  key={key}
                  dataKey={key}
                  stackId="a"
                  fill={colors[idx % colors.length]}
                  radius={[2, 2, 0, 0]}
                  maxBarSize={32}
                  cursor={cursorStyle}
                  onClick={(entry: any) => handleClick(xField, entry?.[xField])}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
      }

      case "horizontal_bar": {
        const allData = chart.data;
        const displayData =
          !showAll && allData.length > BAR_SHOW_ALL_THRESHOLD
            ? allData.slice(0, BAR_SHOW_ALL_THRESHOLD)
            : allData;
        return (
          <>
            <ResponsiveContainer width="100%" height={Math.max(180, displayData.length * 28)}>
              <BarChart
                layout="vertical"
                data={displayData}
                margin={{ top: 4, right: 16, left: 8, bottom: 4 }}
              >
                <CartesianGrid {...GRID_STYLE} horizontal={false} />
                <XAxis type="number" {...AXIS_STYLE} />
                <YAxis
                  type="category"
                  dataKey={xField}
                  width={110}
                  tick={{ fill: "#A3A3A3", fontSize: 10, fontFamily: "var(--font-mono)" }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  content={hasDrill ? <DrillTooltip /> : undefined}
                  contentStyle={!hasDrill ? TOOLTIP_STYLE : undefined}
                  cursor={{ fill: "rgba(255,255,255,0.03)" }}
                />
                <Bar
                  dataKey={yField}
                  fill={colors[0]}
                  radius={[0, 2, 2, 0]}
                  maxBarSize={20}
                  cursor={cursorStyle}
                  onClick={(entry: any) => handleClick(xField, entry?.[xField])}
                />
              </BarChart>
            </ResponsiveContainer>
            {allData.length > BAR_SHOW_ALL_THRESHOLD && (
              <button
                onClick={() => setShowAll((p) => !p)}
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.55rem",
                  color: "var(--uplink)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  marginTop: "4px",
                  padding: 0,
                  letterSpacing: "0.04em",
                }}
              >
                {showAll
                  ? `SHOW TOP ${BAR_SHOW_ALL_THRESHOLD}`
                  : `SHOW ALL ${allData.length}`}
              </button>
            )}
          </>
        );
      }

      case "radar": {
        const { pivoted, entityKeys } = pivotRadarData(chart.data, xField);
        if (!pivoted.length) return <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", color: "var(--on-low)" }}>No data</p>;
        return (
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={pivoted} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
              <PolarGrid stroke="#1E1E1E" />
              <PolarAngleAxis
                dataKey="subject"
                tick={{ fill: "#A3A3A3", fontSize: 10, fontFamily: "var(--font-mono)" }}
              />
              <PolarRadiusAxis
                tick={{ fill: "#A3A3A3", fontSize: 9 }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              {entityKeys.map((key, idx) => (
                <Radar
                  key={key}
                  name={key}
                  dataKey={key}
                  stroke={colors[idx % colors.length]}
                  fill={colors[idx % colors.length]}
                  fillOpacity={0.15}
                  strokeWidth={2}
                />
              ))}
              {entityKeys.length > 1 && (
                <Legend
                  iconSize={6}
                  iconType="square"
                  wrapperStyle={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.6rem",
                    color: "#9A9590",
                    letterSpacing: "0.06em",
                  }}
                />
              )}
            </RadarChart>
          </ResponsiveContainer>
        );
      }

      case "table":
      default: {
        if (!chart.data?.length)
          return (
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.65rem",
                color: "var(--on-low)",
              }}
            >
              No data
            </p>
          );
        const cols = Object.keys(chart.data[0]);
        return (
          <div className="overflow-x-auto">
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--wire-mid)" }}>
                  {cols.map((col) => (
                    <th
                      key={col}
                      style={{
                        padding: "6px 8px",
                        fontFamily: "var(--font-condensed)",
                        fontSize: "0.6rem",
                        fontWeight: 700,
                        letterSpacing: "0.14em",
                        textTransform: "uppercase",
                        color: "var(--on-low)",
                        textAlign: "left",
                      }}
                    >
                      {col.replace(/_/g, " ")}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {chart.data.map((row, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--wire)" }}>
                    {cols.map((col) => (
                      <td
                        key={col}
                        style={{
                          padding: "5px 8px",
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.65rem",
                          color: "var(--on-mid)",
                        }}
                      >
                        {String(row[col] ?? "—")}
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
      style={{ position: "relative" }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {chart.title && (
        <div className="mb-4 flex flex-col items-start gap-1">
          <span className="section-id">{chart.title}</span>
          {chart.description && (
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                color: "var(--on-low)",
                lineHeight: 1.5,
              }}
            >
              — {chart.description}
            </span>
          )}
        </div>
      )}
      {renderChart()}
      {chart.refLinks && chart.refLinks.length > 0 && (
        <RefLinks links={chart.refLinks} />
      )}
      <ChartInsightPanel
        visible={insightVisible}
        onClose={handleInsightClose}
        description={description}
        descriptionLoading={descLoading}
        descriptionError={descError}
        summary={insightSummary}
        insights={insightBullets}
        dataLoading={dataLoading}
        dataError={dataError}
      />
    </div>
  );
}
