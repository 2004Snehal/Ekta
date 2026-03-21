'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Zap, BarChart3, RefreshCw, ChevronDown, ChevronRight, CheckCircle2,
  AlertCircle, Loader2, Database, FlaskConical, Lightbulb, Play, X,
  Server, TrendingUp, BookOpen, ArrowUp, ArrowDown, PenLine, Sparkles,
  Plus, Table2, Copy, CornerDownLeft, Star, RotateCcw,
} from 'lucide-react';
import { FALLBACK_KPIS } from '@/lib/fallback-kpis';
import type { FallbackExpandPage } from '@/lib/fallback-kpis';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts';

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
const BASE    = `${API_URL}/kpi-lab`;

// ── Types ──────────────────────────────────────────────────────────────────────

interface ColumnInfo  { name: string; type: string; }
interface TableSchema { columns: ColumnInfo[]; row_count: number; sample_rows: Record<string, unknown>[]; }
interface SchemaResponse { tables: Record<string, TableSchema>; cached?: boolean; }

interface GoodKPI {
  kpi_id: string; name: string; description?: string; formula?: string;
  value?: number | string; unit?: string; category?: string;
  usefulness_score?: number; sql?: string; registry_id?: string;
}
interface KPIInsight { kpi_name?: string; insight?: string; text?: string; summary?: string; }
interface DiscoverResult {
  run_id: string; table_groups: string[][]; good_kpis: GoodKPI[];
  insights: KPIInsight[]; errors: string[];
}

interface ExpandStat  { label: string; value: string; }
interface ExpandChart {
  chart_type: 'line' | 'bar' | 'pie'; title: string;
  data: Record<string, unknown>[];
  axes?: { x: { field: string; label: string }; y: { field: string; label: string } };
}
interface ExpandDetail {
  interpretation: string; value_range: string;
  high_value_means: string; low_value_means: string;
  stats: ExpandStat[]; charts: ExpandChart[];
}
interface RegistryKPIFull {
  id: string; name: string; description?: string; formula?: string;
  current_value?: unknown; unit?: string; usefulness_score?: number;
  expand_detail: ExpandDetail;
}

type PageTab    = 'discover' | 'manual' | 'agent';
type PageState  = 'idle' | 'loading_schema' | 'running' | 'done' | 'error';

interface RegistryEntry {
  id: string; name: string; description?: string; formula?: string;
  sql_expression?: string; category?: string; current_value?: unknown;
  unit?: string; usefulness_score?: number; source?: string;
  has_expand?: boolean; created_at?: string;
}
type FormState  = 'idle' | 'loading' | 'success' | 'error';

// ── Static data ────────────────────────────────────────────────────────────────

const FORMULA_FUNCTIONS = [
  { name: 'COUNT',          sig: 'COUNT(column)',                              cat: 'aggregation', insert: 'COUNT(column)',          desc: 'Count non-null values' },
  { name: 'COUNT_DISTINCT', sig: 'COUNT_DISTINCT(column)',                     cat: 'aggregation', insert: 'COUNT_DISTINCT(column)',  desc: 'Count unique values' },
  { name: 'SUM',            sig: 'SUM(column)',                                cat: 'aggregation', insert: 'SUM(column)',             desc: 'Sum of values' },
  { name: 'AVG',            sig: 'AVG(column)',                                cat: 'aggregation', insert: 'AVG(column)',             desc: 'Average value' },
  { name: 'MAX',            sig: 'MAX(column)',                                cat: 'aggregation', insert: 'MAX(column)',             desc: 'Maximum value' },
  { name: 'MIN',            sig: 'MIN(column)',                                cat: 'aggregation', insert: 'MIN(column)',             desc: 'Minimum value' },
  { name: 'FILTER',         sig: "FILTER(expr, condition AND condition2)",     cat: 'filter',      insert: "FILTER(COUNT_DISTINCT(column), condition = 'value')", desc: 'Aggregate with WHERE — supports AND/OR for multiple dimensions' },
  { name: 'RATIO',          sig: 'RATIO(numerator_expr, denominator_expr)',    cat: 'derived',     insert: 'RATIO(numerator_expr, denominator_expr)',   desc: '(A ÷ B) × 100, NULL-safe' },
  { name: 'GROWTH',         sig: 'GROWTH(current_expr, previous_expr)',        cat: 'derived',     insert: 'GROWTH(CURRENT_PERIOD(COUNT_DISTINCT(column), 30), PREVIOUS_PERIOD(COUNT_DISTINCT(column), 30))', desc: 'Period-over-period % change' },
  { name: 'RATE',           sig: 'RATE(metric_expr, total_expr)',              cat: 'derived',     insert: 'RATE(FILTER(COUNT_DISTINCT(column), condition), COUNT_DISTINCT(column))', desc: '(metric ÷ total) × 100' },
  { name: 'CURRENT_PERIOD', sig: 'CURRENT_PERIOD(expr, days)',                 cat: 'temporal',    insert: 'CURRENT_PERIOD(COUNT_DISTINCT(column), 30)', desc: 'Last N days' },
  { name: 'PREVIOUS_PERIOD',sig: 'PREVIOUS_PERIOD(expr, days)',                cat: 'temporal',    insert: 'PREVIOUS_PERIOD(COUNT_DISTINCT(column), 30)', desc: 'Previous N-day window' },
] as const;

const CAT_COLORS: Record<string, string> = {
  aggregation: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  filter:      'bg-orange-500/10 text-orange-400 border-orange-500/20',
  derived:     'bg-purple-500/10 text-purple-400 border-purple-500/20',
  temporal:    'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
};

const FORMULA_TEMPLATES = [
  {
    label: 'Simple distinct count',
    formula: 'COUNT_DISTINCT(video_id)',
  },
  {
    label: 'Filtered count (1 dimension)',
    formula: "FILTER(COUNT_DISTINCT(video_id), output_type = 'Chapters')",
  },
  {
    label: 'Multi-dimension ratio  ← your example',
    formula: "RATIO(\n  FILTER(COUNT_DISTINCT(video_id), published_flag = TRUE AND output_type = 'Chapters'),\n  FILTER(COUNT_DISTINCT(video_id), output_type = 'Chapters')\n)",
  },
  {
    label: 'Publication rate',
    formula: "RATE(\n  FILTER(COUNT_DISTINCT(video_id), published_flag = TRUE),\n  COUNT_DISTINCT(video_id)\n)",
  },
  {
    label: 'Period-over-period growth',
    formula: 'GROWTH(\n  CURRENT_PERIOD(COUNT_DISTINCT(video_id), 30),\n  PREVIOUS_PERIOD(COUNT_DISTINCT(video_id), 30)\n)',
  },
  {
    label: 'Average with filter',
    formula: "AVG(FILTER(duration_seconds, output_type = 'Chapters'))",
  },
];

const CATEGORIES = [
  'Founders and Executive Leadership',
  'Client Success Teams',
  'Operations Teams',
  'Editorial and Production Teams',
  'Technology and Product Teams',
];
const UNITS      = ['%', 'count', 'ratio', 'seconds', 'minutes', 'hours'];
const AGENT_LABELS = [
  'Reading schema','Discovering relationships','Grouping tables','Extracting statistics',
  'Generating KPI candidates','Building SQL','Executing queries','Evaluating KPIs','Generating insights',
];

const AI_GEN_STEPS = [
  'Reading database schema',
  'Analyzing business context',
  'Generating KPI candidates',
  'Building SQL expressions',
  'Computing current values',
  'Saving to registry',
];

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(val: number | string | undefined | null): string {
  if (val === undefined || val === null) return '—';
  const n = typeof val === 'string' ? parseFloat(val) : val;
  if (isNaN(n)) return String(val);
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(4) + 'M';
  if (Math.abs(n) >= 1_000)     return (n / 1_000).toFixed(4) + 'K';
  if (Number.isInteger(n))      return n.toLocaleString();
  return n.toFixed(4);
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function SchemaCard({ name, schema }: { name: string; schema: TableSchema }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-card hover:bg-secondary/30 transition-colors text-left">
        <div className="flex items-center gap-2.5">
          <Database className="w-4 h-4 text-primary" />
          <span className="font-mono text-sm font-semibold text-foreground">{name}</span>
          <span className="text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded-full">
            {schema.row_count.toLocaleString()} rows · {schema.columns.length} cols
          </span>
        </div>
        {open ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
      </button>
      {open && (
        <div className="px-4 pb-4 bg-card/50 border-t border-border">
          <div className="mt-3 flex flex-wrap gap-2">
            {schema.columns.map(col => (
              <span key={col.name} className="inline-flex items-center gap-1.5 text-xs bg-secondary rounded-lg px-2.5 py-1 font-mono">
                <span className="text-foreground">{col.name}</span>
                <span className="text-muted-foreground">·</span>
                <span className="text-primary/80">{col.type}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AgentProgress({ active, agentIndex }: { active: boolean; agentIndex: number }) {
  if (!active) return null;
  return (
    <div className="mt-4 space-y-2">
      <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Pipeline agents</p>
      <div className="space-y-1.5">
        {AGENT_LABELS.map((label, i) => (
          <div key={label} className="flex items-center gap-3">
            <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
              i < agentIndex ? 'bg-green-500/20 text-green-400' :
              i === agentIndex ? 'bg-primary/20 text-primary' :
              'bg-secondary text-muted-foreground/40'}`}>
              {i < agentIndex ? <CheckCircle2 className="w-3 h-3" /> :
               i === agentIndex ? <Loader2 className="w-3 h-3 animate-spin" /> :
               <span className="w-1.5 h-1.5 rounded-full bg-current" />}
            </div>
            <span className={`text-xs ${i < agentIndex ? 'text-green-400' : i === agentIndex ? 'text-foreground font-medium' : 'text-muted-foreground/50'}`}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function KPIExpandPanel({ registryId }: { registryId: string }) {
  const [detail, setDetail] = useState<RegistryKPIFull | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr]         = useState<string | null>(null);

  useEffect(() => {
    setLoading(true); setErr(null);
    fetch(`${BASE}/registry/${registryId}`)
      .then(r => r.ok ? r.json() : r.json().then((e: { detail?: string }) => { throw new Error(e.detail ?? 'Load failed'); }))
      .then((d: RegistryKPIFull) => setDetail(d))
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [registryId]);

  if (loading) return <div className="flex items-center gap-2 py-5 text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /><span className="text-xs">Loading detail page…</span></div>;
  if (err)     return <div className="py-3 text-xs text-destructive flex items-center gap-2"><AlertCircle className="w-4 h-4 flex-shrink-0" />{err}</div>;
  if (!detail) return null;

  const ex = detail.expand_detail;
  const hasContent = ex.interpretation || ex.stats?.length > 0 || ex.charts?.length > 0;

  if (!hasContent) return (
    <div className="py-4 text-xs text-muted-foreground flex items-center gap-2">
      <Loader2 className="w-3 h-3 animate-spin" />Detail page is being generated in the background — check back in a moment.
    </div>
  );

  return (
    <div className="space-y-5 pt-4 border-t border-border mt-2">
      {ex.interpretation && (
        <div className="flex gap-3">
          <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
            <BookOpen className="w-3.5 h-3.5 text-primary" />
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed pt-1">{ex.interpretation}</p>
        </div>
      )}
      {(ex.high_value_means || ex.low_value_means) && (
        <div className="grid grid-cols-2 gap-3">
          {ex.high_value_means && (
            <div className="bg-green-500/5 border border-green-500/20 rounded-xl p-3 space-y-1">
              <div className="flex items-center gap-1.5"><ArrowUp className="w-3 h-3 text-green-400" /><span className="text-xs font-semibold text-green-400">High value</span></div>
              <p className="text-xs text-muted-foreground leading-snug">{ex.high_value_means}</p>
            </div>
          )}
          {ex.low_value_means && (
            <div className="bg-destructive/5 border border-destructive/20 rounded-xl p-3 space-y-1">
              <div className="flex items-center gap-1.5"><ArrowDown className="w-3 h-3 text-destructive" /><span className="text-xs font-semibold text-destructive">Low value</span></div>
              <p className="text-xs text-muted-foreground leading-snug">{ex.low_value_means}</p>
            </div>
          )}
        </div>
      )}
      {ex.stats?.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {ex.stats.map((s, i) => (
            <div key={i} className="bg-secondary/40 rounded-xl p-3 space-y-1">
              <p className="text-xs text-muted-foreground leading-tight">{s.label}</p>
              <p className="text-lg font-bold text-foreground tabular-nums">{s.value}</p>
            </div>
          ))}
        </div>
      )}
      {ex.charts?.map((chart, i) => {
        const xField = chart.axes?.x?.field ?? 'x';
        const yField = chart.axes?.y?.field ?? 'value';
        return (
          <div key={i} className="space-y-2">
            <p className="text-xs font-semibold text-foreground">{chart.title}</p>
            <div className="bg-secondary/20 rounded-xl p-3">
              <ResponsiveContainer width="100%" height={180}>
                {chart.chart_type === 'line' ? (
                  <LineChart data={chart.data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey={xField} tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} width={45} />
                    <Tooltip contentStyle={{ background: '#1a1a1a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 11 }} labelStyle={{ color: 'rgba(255,255,255,0.6)' }} itemStyle={{ color: '#FF4D5A' }} />
                    <Line type="monotone" dataKey={yField} stroke="#FF4D5A" strokeWidth={2} dot={false} />
                  </LineChart>
                ) : (
                  <BarChart data={chart.data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                    <XAxis dataKey={xField} tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} width={45} />
                    <Tooltip contentStyle={{ background: '#1a1a1a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 11 }} labelStyle={{ color: 'rgba(255,255,255,0.6)' }} itemStyle={{ color: '#FF4D5A' }} />
                    <Bar dataKey={yField} fill="#FF4D5A" radius={[4, 4, 0, 0]} maxBarSize={40} />
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>
        );
      })}
      {ex.value_range && <p className="text-xs text-muted-foreground/60 italic">{ex.value_range}</p>}
    </div>
  );
}

function FallbackExpandPanel({ data }: { data: FallbackExpandPage }) {
  return (
    <div className="space-y-5 pt-4 border-t border-border mt-2">
      {data.interpretation && (
        <div className="flex gap-3">
          <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
            <BookOpen className="w-3.5 h-3.5 text-primary" />
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed pt-1">{data.interpretation}</p>
        </div>
      )}
      {(data.high_value_means || data.low_value_means) && (
        <div className="grid grid-cols-2 gap-3">
          {data.high_value_means && (
            <div className="bg-green-500/5 border border-green-500/20 rounded-xl p-3 space-y-1">
              <div className="flex items-center gap-1.5"><ArrowUp className="w-3 h-3 text-green-400" /><span className="text-xs font-semibold text-green-400">High value</span></div>
              <p className="text-xs text-muted-foreground leading-snug">{data.high_value_means}</p>
            </div>
          )}
          {data.low_value_means && (
            <div className="bg-destructive/5 border border-destructive/20 rounded-xl p-3 space-y-1">
              <div className="flex items-center gap-1.5"><ArrowDown className="w-3 h-3 text-destructive" /><span className="text-xs font-semibold text-destructive">Low value</span></div>
              <p className="text-xs text-muted-foreground leading-snug">{data.low_value_means}</p>
            </div>
          )}
        </div>
      )}
      {data.stat_queries?.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {data.stat_queries.map((s, i) => (
            <div key={i} className="bg-secondary/40 rounded-xl p-3 space-y-1">
              <p className="text-xs text-muted-foreground leading-tight">{s.label}</p>
              <p className="text-xs font-mono text-muted-foreground/60 truncate" title={s.sql}>SQL query</p>
            </div>
          ))}
        </div>
      )}
      {data.chart_configs?.map((chart, i) => (
        <div key={i} className="space-y-2">
          <p className="text-xs font-semibold text-foreground">{chart.title}</p>
          <div className="bg-secondary/20 rounded-xl p-3">
            <ResponsiveContainer width="100%" height={180}>
              {chart.chart_type === 'line' ? (
                <LineChart data={[]} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey={chart.axes.x.field} tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} label={{ value: chart.axes.x.label, position: 'insideBottom', fill: 'rgba(255,255,255,0.3)', fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} width={45} label={{ value: chart.axes.y.label, angle: -90, position: 'insideLeft', fill: 'rgba(255,255,255,0.3)', fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: '#1a1a1a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 11 }} />
                  <Line type="monotone" dataKey={chart.axes.y.field} stroke="#FF4D5A" strokeWidth={2} dot={false} />
                </LineChart>
              ) : (
                <BarChart data={[]} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                  <XAxis dataKey={chart.axes.x.field} tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} width={45} />
                  <Tooltip contentStyle={{ background: '#1a1a1a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 11 }} />
                  <Bar dataKey={chart.axes.y.field} fill="#FF4D5A" radius={[4, 4, 0, 0]} maxBarSize={40} />
                </BarChart>
              )}
            </ResponsiveContainer>
            <p className="text-[10px] text-muted-foreground/40 mt-1 text-center">Live data not available for fallback KPIs — chart shows structure only</p>
          </div>
        </div>
      ))}
      {data.value_range && <p className="text-xs text-muted-foreground/60 italic">{data.value_range}</p>}
    </div>
  );
}

function KPICard({ name, value, unit, description, formula, category, usefulness_score, sql, registryId, expandPage, index }:
  { name: string; value?: unknown; unit?: string; description?: string; formula?: string; category?: string;
    usefulness_score?: number; sql?: string; registryId?: string; expandPage?: FallbackExpandPage; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const [sqlOpen, setSqlOpen]   = useState(false);
  const [pinned, setPinned]     = useState(false);
  const score = usefulness_score ?? 0;
  const scoreColor = score >= 8 ? 'text-green-400' : score >= 6 ? 'text-yellow-400' : 'text-muted-foreground';

  useEffect(() => {
    if (!registryId) return;
    try {
      const stored = JSON.parse(localStorage.getItem('dashboard_pinned_kpis') ?? '[]') as string[];
      setPinned(stored.includes(registryId));
    } catch { /* ignore */ }
  }, [registryId]);

  function togglePin(e: React.MouseEvent) {
    e.stopPropagation();
    if (!registryId) return;
    try {
      const stored = JSON.parse(localStorage.getItem('dashboard_pinned_kpis') ?? '[]') as string[];
      const next = pinned ? stored.filter(id => id !== registryId) : [...stored, registryId];
      localStorage.setItem('dashboard_pinned_kpis', JSON.stringify(next));
      setPinned(!pinned);
    } catch { /* ignore */ }
  }

  return (
    <div className={`bg-card border rounded-xl p-4 flex flex-col gap-3 transition-all duration-200 ${expanded ? 'border-primary/40 shadow-sm shadow-primary/10' : 'border-border hover:border-primary/30'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs text-muted-foreground font-mono">#{index + 1}</span>
            {category && <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full">{category}</span>}
          </div>
          <h3 className="font-semibold text-foreground text-sm leading-tight">{name}</h3>
        </div>
        <div className="flex items-start gap-2 flex-shrink-0">
          <div className="text-right">
            <div className="text-2xl font-bold text-foreground tabular-nums">
              {fmt(value as number | string | null)}{unit && <span className="text-sm text-muted-foreground ml-1">{unit}</span>}
            </div>
            {usefulness_score !== undefined && <div className={`text-xs font-medium ${scoreColor}`}>score {score.toFixed(1)}</div>}
          </div>
          {registryId && (
            <button onClick={togglePin} title={pinned ? 'Remove from Dashboard' : 'Pin to Dashboard'}
              className="mt-0.5 p-1 rounded hover:bg-secondary/50 transition-colors">
              <Star className={`w-4 h-4 transition-colors ${pinned ? 'fill-yellow-400 text-yellow-400' : 'text-muted-foreground/40 hover:text-yellow-400'}`} />
            </button>
          )}
        </div>
      </div>
      {description && <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>}
      {formula && (
        <div className="bg-secondary/30 rounded-lg px-3 py-2">
          <p className="text-[10px] text-muted-foreground/60 uppercase tracking-wider font-mono mb-1">Formula</p>
          <pre className="text-xs text-foreground/80 font-mono leading-relaxed whitespace-pre-wrap">{formula}</pre>
        </div>
      )}
      {sql && (
        <div>
          <button onClick={() => setSqlOpen(o => !o)} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
            {sqlOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}View SQL
          </button>
          {sqlOpen && <pre className="mt-2 text-xs bg-secondary/50 rounded-lg p-3 overflow-x-auto text-muted-foreground font-mono leading-relaxed whitespace-pre-wrap">{sql}</pre>}
        </div>
      )}
      {(registryId || expandPage) && (
        <button onClick={() => setExpanded(o => !o)}
          className={`flex items-center gap-2 text-xs font-medium transition-colors mt-1 ${expanded ? 'text-primary' : 'text-muted-foreground hover:text-primary'}`}>
          {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          {expanded ? 'Hide detail page' : 'View detail page'}
          <TrendingUp className="w-3 h-3 opacity-60" />
        </button>
      )}
      {expanded && registryId && <KPIExpandPanel registryId={registryId} />}
      {expanded && !registryId && expandPage && <FallbackExpandPanel data={expandPage} />}
    </div>
  );
}

function InsightCard({ insight }: { insight: KPIInsight }) {
  const text = insight.insight ?? insight.text ?? insight.summary ?? '';
  if (!text) return null;
  return (
    <div className="flex gap-3 bg-card border border-border rounded-xl p-4">
      <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Lightbulb className="w-4 h-4 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        {insight.kpi_name && <p className="text-xs font-semibold text-primary mb-1">{insight.kpi_name}</p>}
        <p className="text-sm text-muted-foreground leading-relaxed">{text}</p>
      </div>
    </div>
  );
}

// ── Column browser (used in manual builder) ───────────────────────────────────

function ColumnBrowser({ schema, onInsert }: { schema: SchemaResponse | null; onInsert: (col: string) => void }) {
  const [openTable, setOpenTable] = useState<string | null>(null);

  if (!schema) return (
    <div className="flex items-center justify-center h-32 text-muted-foreground/50">
      <div className="text-center"><Database className="w-6 h-6 mx-auto mb-2" /><p className="text-xs">Schema loading…</p></div>
    </div>
  );

  return (
    <div className="space-y-1 max-h-[480px] overflow-y-auto pr-1">
      {Object.entries(schema.tables).map(([tbl, info]) => (
        <div key={tbl} className="border border-border rounded-xl overflow-hidden">
          <button onClick={() => setOpenTable(t => t === tbl ? null : tbl)}
            className="w-full flex items-center justify-between px-3 py-2.5 bg-card hover:bg-secondary/30 transition-colors text-left">
            <div className="flex items-center gap-2">
              <Table2 className="w-3.5 h-3.5 text-primary" />
              <span className="font-mono text-xs font-semibold text-foreground">{tbl}</span>
              <span className="text-xs text-muted-foreground/60">{info.columns.length} cols</span>
            </div>
            {openTable === tbl ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
          </button>
          {openTable === tbl && (
            <div className="px-3 pb-3 bg-card/50 border-t border-border">
              <p className="text-xs text-muted-foreground/50 mt-2 mb-1.5">Click to insert column name</p>
              <div className="flex flex-wrap gap-1.5">
                {info.columns.map(col => (
                  <button key={col.name} onClick={() => onInsert(col.name)}
                    className="inline-flex items-center gap-1 text-xs bg-secondary hover:bg-primary/10 hover:text-primary border border-border hover:border-primary/30 rounded-lg px-2 py-1 font-mono transition-colors">
                    <span>{col.name}</span>
                    <span className="text-muted-foreground/50 text-[10px]">{col.type.split('(')[0]}</span>
                    <Plus className="w-2.5 h-2.5 opacity-0 group-hover:opacity-100" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Formula Builder Tab ────────────────────────────────────────────────────────

interface ManualCreatedKPI {
  id: string; name: string; sql?: string; current_value?: unknown; unit?: string; message?: string;
}

function FormulaBuilderTab({ schema }: { schema: SchemaResponse | null }) {
  const [name, setName]             = useState('');
  const [description, setDesc]      = useState('');
  const [formula, setFormula]       = useState('');
  const [category, setCategory]     = useState('');
  const [unit, setUnit]             = useState('');
  const [columnsUsed, setColumns]   = useState<string[]>([]);
  const [formState, setFormState]   = useState<FormState>('idle');
  const [formError, setFormError]   = useState('');
  const [created, setCreated]       = useState<ManualCreatedKPI | null>(null);
  const [activeSection, setSection] = useState<'templates' | 'functions'>('templates');
  const formulaRef = useRef<HTMLTextAreaElement>(null);

  function insertToFormula(text: string) {
    const el = formulaRef.current;
    if (!el) { setFormula(f => f + text); return; }
    const start = el.selectionStart ?? formula.length;
    const end   = el.selectionEnd   ?? formula.length;
    const next  = formula.substring(0, start) + text + formula.substring(end);
    setFormula(next);
    setTimeout(() => { el.selectionStart = el.selectionEnd = start + text.length; el.focus(); }, 0);
  }

  function addColumn(col: string) {
    insertToFormula(col);
    setColumns(cs => cs.includes(col) ? cs : [...cs, col]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !formula.trim()) return;
    setFormState('loading'); setFormError(''); setCreated(null);
    try {
      const res = await fetch(`${BASE}/kpi/manual`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), description: description.trim() || undefined, formula: formula.trim(), columns_used: columnsUsed, category: category || undefined, unit: unit || undefined }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Creation failed');
      setCreated(data as ManualCreatedKPI);
      setFormState('success');
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : String(err));
      setFormState('error');
    }
  }

  const catColors: Record<string, string> = {
    templates: 'bg-primary/10 text-primary border-primary/30',
    functions: 'bg-secondary text-muted-foreground border-border',
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

      {/* ── Left: Column browser ──────────────────────────────────── */}
      <div className="lg:col-span-2 space-y-3">
        <div className="bg-card border border-border rounded-2xl p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">Column Browser</h3>
            <span className="text-xs text-muted-foreground">click to insert</span>
          </div>
          <ColumnBrowser schema={schema} onInsert={addColumn} />
        </div>
        {columnsUsed.length > 0 && (
          <div className="bg-card border border-border rounded-xl p-3 space-y-2">
            <p className="text-xs text-muted-foreground font-medium">Columns in formula</p>
            <div className="flex flex-wrap gap-1.5">
              {columnsUsed.map(c => (
                <span key={c} className="inline-flex items-center gap-1 text-xs bg-primary/10 text-primary border border-primary/20 rounded-lg px-2 py-0.5 font-mono">
                  {c}
                  <button onClick={() => setColumns(cs => cs.filter(x => x !== c))} className="hover:text-destructive transition-colors"><X className="w-2.5 h-2.5" /></button>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Right: Form ───────────────────────────────────────────── */}
      <div className="lg:col-span-3 space-y-4">

        {/* Metadata */}
        <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <PenLine className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">KPI Details</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2">
              <label className="text-xs text-muted-foreground mb-1.5 block">KPI Name *</label>
              <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Chapter Publication Rate"
                className="w-full bg-secondary border border-border rounded-xl px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/60 transition-colors" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1.5 block">Category</label>
              <select value={category} onChange={e => setCategory(e.target.value)}
                className="w-full bg-secondary border border-border rounded-xl px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-primary/60 transition-colors">
                <option value="">— select —</option>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1.5 block">Unit</label>
              <select value={unit} onChange={e => setUnit(e.target.value)}
                className="w-full bg-secondary border border-border rounded-xl px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-primary/60 transition-colors">
                <option value="">— select —</option>
                {UNITS.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs text-muted-foreground mb-1.5 block">Description</label>
              <input value={description} onChange={e => setDesc(e.target.value)} placeholder="What this KPI measures…"
                className="w-full bg-secondary border border-border rounded-xl px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/60 transition-colors" />
            </div>
          </div>
        </div>

        {/* Formula builder */}
        <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">Formula Builder</h3>
          </div>

          {/* Toggle: Templates / Functions */}
          <div className="flex items-center gap-1 bg-secondary rounded-xl p-1 w-fit">
            {(['templates', 'functions'] as const).map(s => (
              <button key={s} onClick={() => setSection(s)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-all capitalize ${activeSection === s ? catColors[s] : 'text-muted-foreground border-transparent hover:text-foreground'}`}>
                {s === 'templates' ? 'Templates' : 'Functions'}
              </button>
            ))}
          </div>

          {/* Templates */}
          {activeSection === 'templates' && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">Click a template to fill the formula editor</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {FORMULA_TEMPLATES.map(t => (
                  <button key={t.label} onClick={() => setFormula(t.formula)}
                    className="text-left p-3 bg-secondary/50 hover:bg-secondary border border-border hover:border-primary/30 rounded-xl transition-colors group">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs font-medium text-foreground leading-snug">{t.label}</p>
                      <Copy className="w-3 h-3 text-muted-foreground/40 group-hover:text-primary flex-shrink-0 mt-0.5 transition-colors" />
                    </div>
                    <p className="text-[10px] font-mono text-muted-foreground/60 mt-1 leading-relaxed truncate">{t.formula.split('\n')[0]}</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Functions reference */}
          {activeSection === 'functions' && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">Click to insert function template at cursor</p>
              <div className="space-y-1.5">
                {(['aggregation', 'filter', 'derived', 'temporal'] as const).map(cat => (
                  <div key={cat}>
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground/50 mb-1.5 mt-2 font-medium">{cat}</p>
                    <div className="space-y-1">
                      {FORMULA_FUNCTIONS.filter(f => f.cat === cat).map(fn => (
                        <button key={fn.name} onClick={() => insertToFormula(fn.insert)}
                          className="w-full text-left flex items-start gap-3 p-2.5 bg-secondary/40 hover:bg-secondary border border-transparent hover:border-border rounded-xl transition-colors group">
                          <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded-md border flex-shrink-0 mt-0.5 ${CAT_COLORS[cat]}`}>{fn.name}</span>
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-mono text-muted-foreground/70 leading-snug truncate">{fn.sig}</p>
                            <p className="text-xs text-muted-foreground/50 leading-snug mt-0.5">{fn.desc}</p>
                          </div>
                          <CornerDownLeft className="w-3.5 h-3.5 text-muted-foreground/30 group-hover:text-primary flex-shrink-0 mt-1 transition-colors" />
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Formula textarea */}
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 flex items-center gap-2 block">
              Formula *
              <span className="text-muted-foreground/40">— use FILTER for multi-dimensional conditions</span>
            </label>
            <textarea ref={formulaRef} value={formula} onChange={e => setFormula(e.target.value)}
              rows={5} spellCheck={false}
              placeholder={"e.g.\nRATIO(\n  FILTER(COUNT_DISTINCT(video_id), published_flag = TRUE AND output_type = 'Chapters'),\n  FILTER(COUNT_DISTINCT(video_id), output_type = 'Chapters')\n)"}
              className="w-full bg-secondary border border-border rounded-xl px-3 py-2.5 text-sm text-foreground font-mono placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/60 transition-colors resize-y leading-relaxed" />
            <p className="text-xs text-muted-foreground/50 mt-1.5">Use function names from the reference above — combine them freely to express any calculation.</p>
          </div>

          {/* Submit */}
          <form onSubmit={handleSubmit}>
            <button type="submit" disabled={!name.trim() || !formula.trim() || formState === 'loading'}
              className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-primary text-primary-foreground font-semibold text-sm transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-primary/20">
              {formState === 'loading'
                ? <><Loader2 className="w-4 h-4 animate-spin" />Generating SQL & computing…</>
                : <><Zap className="w-4 h-4" />Create KPI</>}
            </button>
          </form>

          {/* Error */}
          {formState === 'error' && (
            <div className="flex items-start gap-2.5 bg-destructive/5 border border-destructive/20 rounded-xl p-3">
              <AlertCircle className="w-4 h-4 text-destructive flex-shrink-0 mt-0.5" />
              <p className="text-xs text-muted-foreground">{formError}</p>
            </div>
          )}
        </div>

        {/* Created KPI result */}
        {created && formState === 'success' && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-green-400" />
              <p className="text-sm font-semibold text-green-400">KPI created and saved to registry</p>
            </div>
            <KPICard
              index={0} name={created.name} value={created.current_value} unit={created.unit}
              sql={created.sql} registryId={created.id}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── AI Generate Tab ────────────────────────────────────────────────────────────

interface AgentResult {
  context: string; kpis_created: number;
  kpis: { id: string; name: string; description?: string; category?: string; current_value?: unknown; unit?: string; formula?: string; }[];
}

function AIStepProgress({ stepIndex, statusMsg }: { stepIndex: number; statusMsg: string }) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground font-medium">{statusMsg}</p>
      <div className="space-y-2">
        {AI_GEN_STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-3">
            <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
              i < stepIndex ? 'bg-green-500/20 text-green-400' :
              i === stepIndex ? 'bg-primary/20 text-primary' :
              'bg-secondary text-muted-foreground/40'}`}>
              {i < stepIndex ? <CheckCircle2 className="w-3 h-3" /> :
               i === stepIndex ? <Loader2 className="w-3 h-3 animate-spin" /> :
               <span className="w-1.5 h-1.5 rounded-full bg-current" />}
            </div>
            <span className={`text-xs ${i < stepIndex ? 'text-green-400' : i === stepIndex ? 'text-foreground font-medium' : 'text-muted-foreground/50'}`}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AIGenerateTab({ schema }: { schema: SchemaResponse | null }) {
  const [context, setContext]       = useState('');
  const [selectedTables, setTables] = useState<string[]>([]);
  const [formState, setFormState]   = useState<FormState>('idle');
  const [formError, setFormError]   = useState('');
  const [result, setResult]         = useState<AgentResult | null>(null);
  const [stepIndex, setStepIndex]   = useState(0);
  const [statusMsg, setStatusMsg]   = useState('');
  const [isFallback, setIsFallback] = useState(false);
  const stepTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  function startSteps(msg: string) {
    setStepIndex(0); setStatusMsg(msg);
    let idx = 0;
    stepTimer.current = setInterval(() => {
      idx++;
      setStepIndex(idx);
      if (idx >= AI_GEN_STEPS.length) { clearInterval(stepTimer.current!); stepTimer.current = null; }
    }, 2000);
  }

  function stopSteps() {
    if (stepTimer.current) { clearInterval(stepTimer.current); stepTimer.current = null; }
    setStepIndex(AI_GEN_STEPS.length);
  }

  function toggleTable(tbl: string) {
    setTables(ts => ts.includes(tbl) ? ts.filter(t => t !== tbl) : [...ts, tbl]);
  }

  async function runGenerate(ctx: string, attempt: number): Promise<AgentResult | null> {
    const res = await fetch(`${BASE}/kpi/agent-create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context: ctx, tables: selectedTables.length > 0 ? selectedTables : undefined }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail ?? 'Generation failed');
    return data as AgentResult;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!context.trim()) return;
    setFormState('loading'); setFormError(''); setResult(null); setIsFallback(false);

    startSteps('Generating KPIs…');
    try {
      // Attempt 1
      let data = await runGenerate(context.trim(), 1);

      if (!data || data.kpis_created === 0) {
        // Retry attempt 2 with broader context
        stopSteps();
        startSteps('No KPIs found — retrying with broader context…');
        try {
          data = await runGenerate(context.trim() + ' Be creative and generate at least 3 KPIs.', 2);
        } catch { data = null; }
      }

      stopSteps();

      if (!data || data.kpis_created === 0) {
        // Use fallback KPIs from codebase
        setIsFallback(true);
        setResult({
          kpis_created: FALLBACK_KPIS.length,
          kpis: FALLBACK_KPIS.map(k => ({
            id: k.id, name: k.name, description: k.description,
            formula: k.formula, category: k.category, unit: k.unit,
            current_value: k.current_value,
          })),
        });
      } else {
        setResult(data);
      }
      setFormState('success');
    } catch (err: unknown) {
      stopSteps();
      setFormError(err instanceof Error ? err.message : String(err));
      setFormState('error');
    }
  }

  const tables = schema ? Object.keys(schema.tables) : [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

      {/* ── Left: Config ──────────────────────────────────────────── */}
      <div className="lg:col-span-1 space-y-4">
        <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">AI KPI Generator</h3>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Describe your team or business objective. The AI generates 3–6 complex, meaningful KPIs — each with SQL, computed values, and an expand detail page.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs text-muted-foreground mb-1.5 block">Business context *</label>
              <textarea value={context} onChange={e => setContext(e.target.value)} rows={5}
                placeholder={"Examples:\n• KPIs for the content operations team\n• Track chapter publishing efficiency\n• Monitor video production pipeline health"}
                className="w-full bg-secondary border border-border rounded-xl px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/60 transition-colors resize-none leading-relaxed" />
            </div>

            {tables.length > 0 && (
              <div>
                <label className="text-xs text-muted-foreground mb-1.5 block">
                  Focus tables <span className="text-muted-foreground/50">(optional — leave blank for all)</span>
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {tables.map(tbl => (
                    <button key={tbl} type="button" onClick={() => toggleTable(tbl)}
                      className={`text-xs font-mono px-2.5 py-1 rounded-lg border transition-colors ${
                        selectedTables.includes(tbl)
                          ? 'bg-primary/10 text-primary border-primary/30'
                          : 'bg-secondary text-muted-foreground border-border hover:border-primary/30 hover:text-foreground'
                      }`}>
                      {selectedTables.includes(tbl) && <CheckCircle2 className="w-2.5 h-2.5 inline mr-1" />}
                      {tbl}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <button type="submit" disabled={!context.trim() || formState === 'loading'}
              className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-primary text-primary-foreground font-semibold text-sm transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-primary/20">
              {formState === 'loading'
                ? <><Loader2 className="w-4 h-4 animate-spin" />Generating…</>
                : <><Sparkles className="w-4 h-4" />Generate KPIs</>}
            </button>

            {formState === 'error' && (
              <div className="flex items-start gap-2.5 bg-destructive/5 border border-destructive/20 rounded-xl p-3">
                <AlertCircle className="w-4 h-4 text-destructive flex-shrink-0 mt-0.5" />
                <p className="text-xs text-muted-foreground">{formError}</p>
              </div>
            )}
          </form>
        </div>
      </div>

      {/* ── Right: Results / Steps ────────────────────────────────── */}
      <div className="lg:col-span-2">
        {formState === 'loading' && (
          <div className="flex flex-col items-center justify-center py-20 gap-8">
            <div className="flex flex-col items-center gap-3">
              <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center">
                <Sparkles className="w-7 h-7 text-primary animate-pulse" />
              </div>
              <p className="text-base font-semibold text-foreground">{statusMsg}</p>
            </div>
            <div className="w-full max-w-xs space-y-3">
              {AI_GEN_STEPS.map((label, i) => (
                <div key={label} className="flex items-center gap-3">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
                    i < stepIndex ? 'bg-green-500/20 text-green-400' :
                    i === stepIndex ? 'bg-primary/20 text-primary' :
                    'bg-secondary text-muted-foreground/30'}`}>
                    {i < stepIndex ? <CheckCircle2 className="w-3.5 h-3.5" /> :
                     i === stepIndex ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> :
                     <span className="w-1.5 h-1.5 rounded-full bg-current" />}
                  </div>
                  <span className={`text-sm ${i < stepIndex ? 'text-green-400' : i === stepIndex ? 'text-foreground font-medium' : 'text-muted-foreground/40'}`}>{label}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {result && formState === 'success' && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              {isFallback
                ? <RotateCcw className="w-4 h-4 text-yellow-400" />
                : <CheckCircle2 className="w-4 h-4 text-green-400" />}
              <p className="text-sm font-semibold text-foreground">
                {isFallback
                  ? `Showing ${result.kpis_created} default KPIs — AI generation returned no results`
                  : `${result.kpis_created} KPI${result.kpis_created !== 1 ? 's' : ''} generated and saved to registry`}
              </p>
            </div>
            <div className="space-y-3">
              {result.kpis.map((kpi, i) => (
                <KPICard
                  key={kpi.id} index={i} name={kpi.name}
                  value={kpi.current_value} unit={kpi.unit}
                  description={kpi.description} category={kpi.category}
                  formula={(kpi as { formula?: string }).formula}
                  registryId={isFallback ? undefined : kpi.id}
                  expandPage={isFallback ? FALLBACK_KPIS[i]?.expand_page : undefined}
                />
              ))}
            </div>
          </div>
        )}

        {formState === 'idle' && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center mb-4">
              <Sparkles className="w-8 h-8 text-muted-foreground/40" />
            </div>
            <p className="text-sm font-semibold text-foreground mb-2">Describe your objective</p>
            <p className="text-xs text-muted-foreground max-w-xs">Enter a business context on the left — the AI will generate KPIs tailored to your team and data.</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function KPILabPage() {
  const [tab, setTab]               = useState<PageTab>('discover');
  const [pageState, setPageState]   = useState<PageState>('idle');
  const [schema, setSchema]         = useState<SchemaResponse | null>(null);
  const [result, setResult]         = useState<DiscoverResult | null>(null);
  const [errors, setErrors]         = useState<string[]>([]);
  const [agentIndex, setAgentIndex] = useState(0);
  const agentTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Registry state ────────────────────────────────────────
  const [registryKpis, setRegistryKpis]     = useState<RegistryEntry[]>([]);
  const [registryLoading, setRegistryLoading] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');

  const loadSchema = useCallback(async (forceRefresh = false) => {
    setPageState('loading_schema'); setErrors([]);
    try {
      const res = await fetch(`${BASE}/schema?source=postgres${forceRefresh ? '&refresh=true' : ''}`);
      if (!res.ok) throw new Error(await res.text());
      setSchema(await res.json());
      setPageState('idle');
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : String(e)]);
      setPageState('error');
    }
  }, []);

  useEffect(() => { loadSchema(); }, [loadSchema]);

  const loadRegistry = useCallback(async () => {
    setRegistryLoading(true);
    try {
      const res = await fetch(`${BASE}/registry`);
      if (res.ok) {
        const data = await res.json() as { kpis: RegistryEntry[] };
        setRegistryKpis(data.kpis ?? []);
      }
    } catch { /* ignore */ } finally {
      setRegistryLoading(false);
    }
  }, []);

  // Load registry whenever discover tab is active
  useEffect(() => { if (tab === 'discover') loadRegistry(); }, [tab, loadRegistry]);

  const startAgentSim = useCallback(() => {
    setAgentIndex(0); let idx = 0;
    agentTimer.current = setInterval(() => {
      idx++; setAgentIndex(idx);
      if (idx >= AGENT_LABELS.length) { clearInterval(agentTimer.current!); agentTimer.current = null; }
    }, 1800);
  }, []);

  const runPipeline = useCallback(async () => {
    if (!schema || Object.keys(schema.tables).length === 0) return;
    setPageState('running'); setResult(null); setErrors([]); startAgentSim();
    try {
      const res  = await fetch(`${BASE}/kpi/discover?source=postgres`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Pipeline failed');
      if (agentTimer.current) { clearInterval(agentTimer.current); agentTimer.current = null; }
      setAgentIndex(AGENT_LABELS.length);
      setResult(data as DiscoverResult); setErrors(data.errors ?? []);
      setPageState('done');
      void loadRegistry(); // refresh registry to show newly discovered KPIs
    } catch (e: unknown) {
      if (agentTimer.current) { clearInterval(agentTimer.current); agentTimer.current = null; }
      setErrors([e instanceof Error ? e.message : String(e)]); setPageState('error');
    }
  }, [schema, startAgentSim, loadRegistry]);

  const hasSchema = !!schema && Object.keys(schema.tables).length > 0;
  const isRunning = pageState === 'running';
  const isBusy    = pageState === 'loading_schema';
  const canRun    = hasSchema && !isRunning && !isBusy;

  const TABS = [
    { id: 'discover' as PageTab, label: 'Discover',        icon: Zap },
    { id: 'manual'   as PageTab, label: 'Formula Builder', icon: PenLine },
    { id: 'agent'    as PageTab, label: 'AI Generate',     icon: Sparkles },
  ];

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">

        {/* ── Header ────────────────────────────────────────────────── */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <Zap className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">KPI Lab</h1>
            <p className="text-sm text-muted-foreground">Discover, build, and manage KPIs — all saved to your registry</p>
          </div>
        </div>

        {/* ── Tabs ──────────────────────────────────────────────────── */}
        <div className="flex items-center gap-1 bg-card border border-border rounded-2xl p-1 w-fit">
          {TABS.map(t => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                  active ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
                }`}>
                <Icon className="w-4 h-4" />{t.label}
              </button>
            );
          })}
        </div>

        {/* ── Discover Tab ──────────────────────────────────────────── */}
        {tab === 'discover' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: controls */}
            <div className="lg:col-span-1 space-y-4">
              <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
                <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-green-500/5 border border-green-500/20">
                  <Server className="w-4 h-4 text-green-400 flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-green-400">Frammer Database</p>
                    <p className="text-xs text-muted-foreground truncate">Live Supabase PostgreSQL</p>
                  </div>
                  {hasSchema && (
                    <span className="ml-auto text-xs bg-green-500/10 text-green-400 border border-green-500/20 px-2 py-0.5 rounded-full flex-shrink-0">
                      {Object.keys(schema!.tables).length} tables
                    </span>
                  )}
                </div>
                <div className="flex items-start gap-3 px-1">
                  <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Play className="w-3.5 h-3.5 text-primary" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-foreground">Full Discovery</p>
                    <p className="text-xs text-muted-foreground leading-snug mt-0.5">
                      All 9 agents: schema → relationships → SQL → insights. KPIs are saved to registry with expandable detail pages.
                    </p>
                  </div>
                </div>
                <button onClick={runPipeline} disabled={!canRun}
                  className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-primary text-primary-foreground font-semibold text-sm transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-primary/20">
                  {isRunning ? <><Loader2 className="w-4 h-4 animate-spin" />Running…</> : <><Zap className="w-4 h-4" />Discover KPIs</>}
                </button>
                <AgentProgress active={isRunning} agentIndex={agentIndex} />
              </div>
            </div>

            {/* Right: KPI Registry ─────────────────────────────── */}
            <div className="lg:col-span-2 space-y-4">
              {/* Header row */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-primary" />
                  <h2 className="font-semibold text-sm text-foreground">
                    KPI Registry
                    {!registryLoading && (
                      <span className="ml-2 text-xs text-muted-foreground font-normal">{registryKpis.length} saved</span>
                    )}
                  </h2>
                </div>
                <button
                  onClick={() => void loadRegistry()}
                  disabled={registryLoading}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
                >
                  <RefreshCw className={`w-3 h-3 ${registryLoading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              </div>

              {/* Category filter — only shown when categories exist in registry */}
              {(() => {
                const cats = Array.from(new Set(registryKpis.map(k => k.category).filter((c): c is string => !!c)));
                if (cats.length === 0) return null;
                return (
                  <div className="flex items-center gap-2 flex-wrap">
                    {(['all', ...cats]).map(cat => (
                      <button
                        key={cat}
                        onClick={() => setCategoryFilter(cat)}
                        className={`text-xs px-3 py-1 rounded-full border transition-colors font-medium ${
                          categoryFilter === cat
                            ? 'bg-primary/15 text-primary border-primary/40'
                            : 'bg-secondary text-muted-foreground border-border hover:border-primary/30 hover:text-foreground'
                        }`}
                      >
                        {cat === 'all' ? `All (${registryKpis.length})` : `${cat} (${registryKpis.filter(k => k.category === cat).length})`}
                      </button>
                    ))}
                  </div>
                );
              })()}

              {/* KPI list */}
              {registryLoading && (
                <div className="flex items-center justify-center py-16">
                  <div className="flex flex-col items-center gap-3">
                    <Loader2 className="w-8 h-8 text-primary animate-spin" />
                    <p className="text-sm text-muted-foreground">Loading registry…</p>
                  </div>
                </div>
              )}

              {!registryLoading && registryKpis.length === 0 && (
                <div className="flex flex-col items-center justify-center py-20 text-center">
                  <div className="w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center mb-4">
                    <FlaskConical className="w-8 h-8 text-muted-foreground/50" />
                  </div>
                  <h3 className="font-semibold text-foreground mb-2">Registry is empty</h3>
                  <p className="text-xs text-muted-foreground max-w-xs">
                    Run the discovery pipeline, use the Formula Builder, or AI Generate to create KPIs — they&apos;ll appear here.
                  </p>
                </div>
              )}

              {!registryLoading && registryKpis.length > 0 && (
                <div className="space-y-3">
                  {registryKpis
                    .filter(k => categoryFilter === 'all' || k.category === categoryFilter)
                    .map((kpi, i) => (
                      <KPICard
                        key={kpi.id}
                        index={i}
                        name={kpi.name}
                        value={kpi.current_value}
                        unit={kpi.unit}
                        description={kpi.description}
                        formula={kpi.formula}
                        category={kpi.category}
                        usefulness_score={kpi.usefulness_score}
                        sql={kpi.sql_expression}
                        registryId={kpi.id}
                      />
                    ))}
                  {registryKpis.filter(k => categoryFilter === 'all' || k.category === categoryFilter).length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-8">No KPIs in category &quot;{categoryFilter}&quot;.</p>
                  )}
                </div>
              )}

              {/* Pipeline errors (if any from last run) */}
              {pageState === 'error' && errors.length > 0 && (
                <div className="space-y-2 mt-4">
                  <div className="flex items-center gap-2"><AlertCircle className="w-4 h-4 text-destructive" /><h2 className="font-semibold text-sm">Discovery errors</h2></div>
                  {errors.map((err, i) => (
                    <div key={i} className="flex items-start gap-2.5 bg-destructive/5 border border-destructive/20 rounded-xl p-3">
                      <X className="w-4 h-4 text-destructive flex-shrink-0 mt-0.5" />
                      <p className="text-xs text-muted-foreground">{err}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Formula Builder Tab ───────────────────────────────────── */}
        {tab === 'manual' && <FormulaBuilderTab schema={schema} />}

        {/* ── AI Generate Tab ───────────────────────────────────────── */}
        {tab === 'agent' && <AIGenerateTab schema={schema} />}

      </div>
    </div>
  );
}
