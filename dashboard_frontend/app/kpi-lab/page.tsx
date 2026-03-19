'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Upload, Zap, BarChart3, RefreshCw, Trash2, ChevronDown, ChevronRight,
  CheckCircle2, AlertCircle, Loader2, Database, FlaskConical, Lightbulb,
  FileText, Play, X, Server,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
const BASE = `${API_URL}/kpi-lab`;

// ── Types ─────────────────────────────────────────────────────────────────────

type DataSource = 'csv' | 'postgres';

interface ColumnInfo { name: string; type: string; }
interface TableSchema { columns: ColumnInfo[]; row_count: number; sample_rows: Record<string, unknown>[]; }
interface SchemaResponse { source: DataSource; tables: Record<string, TableSchema>; }

interface SourceInfo {
  id: DataSource;
  label: string;
  description: string;
  table_count: number;
  tables: string[];
}

interface GoodKPI {
  name: string;
  description?: string;
  value?: number | string;
  unit?: string;
  category?: string;
  usefulness_score?: number;
  sql?: string;
}

interface CandidateKPI {
  name: string;
  description?: string;
  formula?: string;
  category?: string;
}

interface KPIInsight {
  kpi_name?: string;
  insight?: string;
  text?: string;
  summary?: string;
}

interface DiscoverResult {
  run_id: string;
  source: DataSource;
  table_groups: string[][];
  candidate_kpis: CandidateKPI[];
  computed_values: Record<string, unknown>;
  good_kpis: GoodKPI[];
  insights: KPIInsight[];
  errors: string[];
}

type PipelineMode = 'discover' | 'generate' | 'compute' | 'evaluate';
type PageState = 'idle' | 'loading_sources' | 'uploading' | 'loading_schema' | 'running' | 'done' | 'error';

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(val: number | string | undefined | null): string {
  if (val === undefined || val === null) return '—';
  const n = typeof val === 'string' ? parseFloat(val) : val;
  if (isNaN(n)) return String(val);
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M';
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  if (Number.isInteger(n)) return n.toLocaleString();
  return n.toFixed(2);
}

function insightText(ins: KPIInsight): string {
  return ins.insight ?? ins.text ?? ins.summary ?? '';
}

const PIPELINE_STEPS: { id: PipelineMode; label: string; icon: React.ElementType; description: string }[] = [
  { id: 'discover',  label: 'Full Discovery', icon: Zap,          description: 'All 9 agents: schema → relationships → SQL → insights' },
  { id: 'generate',  label: 'Generate KPIs',  icon: FlaskConical, description: 'Candidate KPI generation only (no SQL execution)' },
  { id: 'compute',   label: 'Compute Values', icon: BarChart3,    description: 'Generate + build SQL + execute queries' },
  { id: 'evaluate',  label: 'Evaluate KPIs',  icon: CheckCircle2, description: 'Compute + filter by variance, correlation & usefulness' },
];

const AGENT_LABELS = [
  'Reading schema',
  'Discovering relationships',
  'Grouping tables',
  'Extracting statistics',
  'Generating KPI candidates',
  'Building SQL',
  'Executing queries',
  'Evaluating KPIs',
  'Generating insights',
];

// ── Sub-components ────────────────────────────────────────────────────────────

function SchemaCard({ name, schema }: { name: string; schema: TableSchema }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-card hover:bg-secondary/30 transition-colors text-left"
      >
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
          {schema.sample_rows.length > 0 && (
            <div className="mt-3 overflow-x-auto rounded-lg border border-border">
              <table className="text-xs w-full">
                <thead className="bg-secondary/50">
                  <tr>{schema.columns.slice(0, 6).map(c => (
                    <th key={c.name} className="px-3 py-2 text-left text-muted-foreground font-medium truncate max-w-[120px]">{c.name}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {schema.sample_rows.slice(0, 3).map((row, i) => (
                    <tr key={i} className="border-t border-border/50">
                      {schema.columns.slice(0, 6).map(c => (
                        <td key={c.name} className="px-3 py-2 text-muted-foreground truncate max-w-[120px]">{String(row[c.name] ?? '—')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function KPIResultCard({ kpi, index }: { kpi: GoodKPI; index: number }) {
  const score = kpi.usefulness_score ?? 0;
  const scoreColor = score >= 8 ? 'text-green-400' : score >= 6 ? 'text-yellow-400' : 'text-muted-foreground';
  const [sqlOpen, setSqlOpen] = useState(false);
  return (
    <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-3 hover:border-primary/30 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs text-muted-foreground font-mono">#{index + 1}</span>
            {kpi.category && <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full">{kpi.category}</span>}
          </div>
          <h3 className="font-semibold text-foreground text-sm leading-tight">{kpi.name}</h3>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="text-2xl font-bold text-foreground tabular-nums">
            {fmt(kpi.value)}{kpi.unit && <span className="text-sm text-muted-foreground ml-1">{kpi.unit}</span>}
          </div>
          {kpi.usefulness_score !== undefined && <div className={`text-xs font-medium ${scoreColor}`}>score {score.toFixed(1)}</div>}
        </div>
      </div>
      {kpi.description && <p className="text-xs text-muted-foreground leading-relaxed">{kpi.description}</p>}
      {kpi.sql && (
        <div>
          <button onClick={() => setSqlOpen(o => !o)} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
            {sqlOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}View SQL
          </button>
          {sqlOpen && (
            <pre className="mt-2 text-xs bg-secondary/50 rounded-lg p-3 overflow-x-auto text-muted-foreground font-mono leading-relaxed whitespace-pre-wrap">{kpi.sql}</pre>
          )}
        </div>
      )}
    </div>
  );
}

function InsightCard({ insight }: { insight: KPIInsight }) {
  const text = insightText(insight);
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
              'bg-secondary text-muted-foreground/40'
            }`}>
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

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function KPILabPage() {
  const [pageState, setPageState]     = useState<PageState>('idle');
  const [dataSource, setDataSource]   = useState<DataSource>('postgres');
  const [sources, setSources]         = useState<SourceInfo[] | null>(null);
  const [schema, setSchema]           = useState<(SchemaResponse & { cached?: boolean }) | null>(null);
  const [result, setResult]           = useState<DiscoverResult | null>(null);
  const [errors, setErrors]           = useState<string[]>([]);
  const [mode, setMode]               = useState<PipelineMode>('discover');
  const [agentIndex, setAgentIndex]   = useState(0);
  const [dragOver, setDragOver]       = useState(false);
  const [uploadedTables, setUploadedTables] = useState<string[]>([]);
  const fileInputRef  = useRef<HTMLInputElement>(null);
  const agentTimer    = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── API helpers ──────────────────────────────────────────────────

  const loadSources = useCallback(async () => {
    setPageState('loading_sources');
    try {
      const res = await fetch(`${BASE}/sources`);
      const data = await res.json();
      setSources(data.sources ?? []);
      setPageState('idle');
    } catch {
      setPageState('idle');
    }
  }, []);

  const loadSchema = useCallback(async (src: DataSource, forceRefresh = false) => {
    setPageState('loading_schema');
    setErrors([]);
    try {
      const url = `${BASE}/schema?source=${src}${forceRefresh ? '&refresh=true' : ''}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(await res.text());
      const data: SchemaResponse & { cached?: boolean } = await res.json();
      setSchema(data);
      setPageState('idle');
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : String(e)]);
      setPageState('error');
    }
  }, []);

  const handleSourceChange = useCallback((src: DataSource) => {
    setDataSource(src);
    setSchema(null);
    setResult(null);
    setErrors([]);
    loadSchema(src);
  }, [loadSchema]);

  const uploadFiles = useCallback(async (files: FileList | File[]) => {
    setPageState('uploading');
    setErrors([]);
    const form = new FormData();
    Array.from(files).forEach(f => form.append('files', f));
    try {
      const res = await fetch(`${BASE}/data/upload`, { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Upload failed');
      setUploadedTables(data.tables_loaded ?? []);
      await loadSchema('csv');
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : String(e)]);
      setPageState('error');
    }
  }, [loadSchema]);

  const startAgentSim = useCallback(() => {
    setAgentIndex(0);
    let idx = 0;
    agentTimer.current = setInterval(() => {
      idx++;
      setAgentIndex(idx);
      if (idx >= AGENT_LABELS.length) { clearInterval(agentTimer.current!); agentTimer.current = null; }
    }, 1800);
  }, []);

  const runPipeline = useCallback(async () => {
    if (!schema || Object.keys(schema.tables).length === 0) return;
    setPageState('running');
    setResult(null);
    setErrors([]);
    startAgentSim();
    try {
      const res = await fetch(`${BASE}/kpi/${mode}?source=${dataSource}`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? 'Pipeline failed');
      if (agentTimer.current) { clearInterval(agentTimer.current); agentTimer.current = null; }
      setAgentIndex(AGENT_LABELS.length);
      setResult(data as DiscoverResult);
      setErrors(data.errors ?? []);
      setPageState('done');
    } catch (e: unknown) {
      if (agentTimer.current) { clearInterval(agentTimer.current); agentTimer.current = null; }
      setErrors([e instanceof Error ? e.message : String(e)]);
      setPageState('error');
    }
  }, [schema, mode, dataSource, startAgentSim]);

  const resetAll = useCallback(async () => {
    if (dataSource === 'csv') {
      try { await fetch(`${BASE}/data/reset`, { method: 'DELETE' }); } catch { /* ignore */ }
      setUploadedTables([]);
    }
    setSchema(null);
    setResult(null);
    setErrors([]);
    setAgentIndex(0);
    setPageState('idle');
  }, [dataSource]);

  // ── Init: load sources + default postgres schema ──────────────────────────
  useEffect(() => {
    loadSources();
    loadSchema('postgres');
  }, []);

  // ── Drag & drop ──────────────────────────────────────────────────
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length) {
      setDataSource('csv');
      uploadFiles(e.dataTransfer.files);
    }
  }, [uploadFiles]);

  // ── Computed ─────────────────────────────────────────────────────
  const hasSchema  = !!schema && Object.keys(schema.tables).length > 0;
  const isRunning  = pageState === 'running';
  const isBusy     = pageState === 'uploading' || pageState === 'loading_schema' || pageState === 'loading_sources';
  const canRun     = hasSchema && !isRunning && !isBusy;

  const pgSource   = sources?.find(s => s.id === 'postgres');
  const csvSource  = sources?.find(s => s.id === 'csv');

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">

        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <Zap className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">KPI Lab</h1>
              <p className="text-sm text-muted-foreground">Agentic KPI discovery — choose a data source and run the pipeline</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {(hasSchema || result) && (
              <button onClick={resetAll} className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border border-border text-muted-foreground hover:text-destructive hover:border-destructive/50 transition-colors">
                <Trash2 className="w-3.5 h-3.5" />Reset
              </button>
            )}
          </div>
        </div>

        {/* ── Data Source Selector ────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">

          {/* Postgres */}
          <button
            onClick={() => handleSourceChange('postgres')}
            className={`flex items-start gap-4 p-4 rounded-2xl border-2 text-left transition-all duration-150 ${
              dataSource === 'postgres'
                ? 'border-primary bg-primary/5 shadow-sm shadow-primary/10'
                : 'border-border hover:border-primary/30 bg-card'
            }`}
          >
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${dataSource === 'postgres' ? 'bg-primary/20' : 'bg-secondary'}`}>
              <Server className={`w-5 h-5 ${dataSource === 'postgres' ? 'text-primary' : 'text-muted-foreground'}`} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-0.5">
                <span className={`text-sm font-semibold ${dataSource === 'postgres' ? 'text-primary' : 'text-foreground'}`}>Frammer Database</span>
                {pgSource && (
                  <span className="text-xs bg-green-500/10 text-green-400 border border-green-500/20 px-2 py-0.5 rounded-full">
                    {pgSource.table_count} tables
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground leading-snug">Discover KPIs directly from your live Supabase PostgreSQL tables — no upload needed</p>
            </div>
            {dataSource === 'postgres' && <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0 mt-1" />}
          </button>

          {/* CSV Upload */}
          <button
            onClick={() => handleSourceChange('csv')}
            className={`flex items-start gap-4 p-4 rounded-2xl border-2 text-left transition-all duration-150 ${
              dataSource === 'csv'
                ? 'border-primary bg-primary/5 shadow-sm shadow-primary/10'
                : 'border-border hover:border-primary/30 bg-card'
            }`}
          >
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${dataSource === 'csv' ? 'bg-primary/20' : 'bg-secondary'}`}>
              <Upload className={`w-5 h-5 ${dataSource === 'csv' ? 'text-primary' : 'text-muted-foreground'}`} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-0.5">
                <span className={`text-sm font-semibold ${dataSource === 'csv' ? 'text-primary' : 'text-foreground'}`}>Upload CSV</span>
                {csvSource && csvSource.table_count > 0 && (
                  <span className="text-xs bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded-full">
                    {csvSource.table_count} loaded
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground leading-snug">Upload your own CSV files and discover KPIs from any dataset in memory</p>
            </div>
            {dataSource === 'csv' && <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0 mt-1" />}
          </button>
        </div>

        {/* ── CSV upload zone (only shown when csv selected) ─────────── */}
        {dataSource === 'csv' && (
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all duration-200 ${
              dragOver ? 'border-primary bg-primary/5 scale-[1.01]' : 'border-border hover:border-primary/40 hover:bg-secondary/10 bg-card'
            }`}
          >
            <input ref={fileInputRef} type="file" accept=".csv,.tsv,.txt" multiple className="hidden"
              onChange={e => { if (e.target.files?.length) uploadFiles(e.target.files); }} />
            {pageState === 'uploading' ? (
              <div className="flex flex-col items-center gap-2">
                <Loader2 className="w-8 h-8 text-primary animate-spin" />
                <p className="text-sm text-muted-foreground">Uploading and loading into DuckDB…</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <div className="w-12 h-12 rounded-2xl bg-secondary flex items-center justify-center">
                  <FileText className="w-6 h-6 text-muted-foreground" />
                </div>
                <p className="text-sm font-medium text-foreground">Drop CSV files here or click to browse</p>
                <p className="text-xs text-muted-foreground">.csv · .tsv · .txt · multiple files supported</p>
              </div>
            )}
          </div>
        )}

        {/* ── Uploaded tables chips ───────────────────────────────────── */}
        {dataSource === 'csv' && uploadedTables.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {uploadedTables.map(t => (
              <span key={t} className="inline-flex items-center gap-1.5 text-xs text-green-400 bg-green-400/5 border border-green-400/20 rounded-lg px-3 py-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /><span className="font-mono">{t}</span>
              </span>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* ── Left: Pipeline config ─────────────────────────────────── */}
          <div className="lg:col-span-1 space-y-4">
            <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
              <div className="flex items-center gap-2">
                <Play className="w-4 h-4 text-primary" />
                <h2 className="font-semibold text-sm text-foreground">Pipeline Mode</h2>
              </div>
              <div className="space-y-2">
                {PIPELINE_STEPS.map(step => {
                  const Icon = step.icon;
                  const active = mode === step.id;
                  return (
                    <button key={step.id} onClick={() => setMode(step.id)}
                      className={`w-full flex items-start gap-3 p-3 rounded-xl border text-left transition-all duration-150 ${
                        active ? 'border-primary bg-primary/5' : 'border-border hover:bg-secondary/20'
                      }`}>
                      <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${active ? 'bg-primary/20' : 'bg-secondary'}`}>
                        <Icon className={`w-4 h-4 ${active ? 'text-primary' : 'text-muted-foreground'}`} />
                      </div>
                      <div>
                        <p className={`text-xs font-semibold ${active ? 'text-primary' : 'text-foreground'}`}>{step.label}</p>
                        <p className="text-xs text-muted-foreground leading-snug mt-0.5">{step.description}</p>
                      </div>
                    </button>
                  );
                })}
              </div>

              <button onClick={runPipeline} disabled={!canRun}
                className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-primary text-primary-foreground font-semibold text-sm transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-primary/20">
                {isRunning
                  ? <><Loader2 className="w-4 h-4 animate-spin" />Running…</>
                  : <><Zap className="w-4 h-4" />Run on {dataSource === 'postgres' ? 'Frammer DB' : 'Uploaded CSV'}</>}
              </button>

              {/* Source badge */}
              <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${dataSource === 'postgres' ? 'bg-green-500/5 border border-green-500/20 text-green-400' : 'bg-blue-500/5 border border-blue-500/20 text-blue-400'}`}>
                {dataSource === 'postgres' ? <Server className="w-3.5 h-3.5" /> : <Upload className="w-3.5 h-3.5" />}
                <span>{dataSource === 'postgres' ? 'Using Frammer PostgreSQL' : 'Using uploaded CSV tables'}</span>
              </div>

              <AgentProgress active={isRunning} agentIndex={agentIndex} />
            </div>
          </div>

          {/* ── Right: Schema + Results ───────────────────────────────── */}
          <div className="lg:col-span-2 space-y-6">

            {/* Loading state */}
            {isBusy && !isRunning && (
              <div className="flex items-center justify-center py-12">
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="w-8 h-8 text-primary animate-spin" />
                  <p className="text-sm text-muted-foreground">
                    {pageState === 'loading_schema' ? `Loading ${dataSource === 'postgres' ? 'Frammer database' : 'CSV'} schema…` : 'Loading sources…'}
                  </p>
                </div>
              </div>
            )}

            {/* Schema */}
            {hasSchema && !isBusy && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {dataSource === 'postgres' ? <Server className="w-4 h-4 text-primary" /> : <Database className="w-4 h-4 text-primary" />}
                    <h2 className="font-semibold text-sm text-foreground">
                      {dataSource === 'postgres' ? 'Frammer Database Schema' : 'Uploaded CSV Schema'}
                      <span className="ml-2 text-xs text-muted-foreground font-normal">{Object.keys(schema!.tables).length} tables</span>
                    </h2>
                  </div>
                  <div className="flex items-center gap-2">
                    {schema?.cached && dataSource === 'postgres' && (
                      <span className="text-xs text-muted-foreground/60 bg-secondary px-2 py-0.5 rounded-full">cached</span>
                    )}
                    <button onClick={() => loadSchema(dataSource, true)}
                      className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                      title={dataSource === 'postgres' ? 'Force re-fetch from database' : 'Reload schema'}>
                      <RefreshCw className="w-3 h-3" />Refresh
                    </button>
                  </div>
                </div>
                <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  {Object.entries(schema!.tables).map(([name, tbl]) => (
                    <SchemaCard key={name} name={name} schema={tbl} />
                  ))}
                </div>
              </div>
            )}

            {/* Empty idle state */}
            {!hasSchema && !isBusy && pageState !== 'error' && (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center mb-4">
                  <FlaskConical className="w-8 h-8 text-muted-foreground/50" />
                </div>
                <h3 className="font-semibold text-foreground mb-2">
                  {dataSource === 'csv' ? 'No CSV files uploaded yet' : 'Could not load database schema'}
                </h3>
                <p className="text-sm text-muted-foreground max-w-xs">
                  {dataSource === 'csv'
                    ? 'Upload one or more CSV files above to get started.'
                    : 'Make sure the backend is running and DATABASE_URL is configured correctly.'}
                </p>
              </div>
            )}

            {/* Results */}
            {result && (
              <div className="space-y-6">
                {/* Summary row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { label: 'Table Groups', value: (result.table_groups   ?? []).length, icon: Database },
                    { label: 'Candidates',   value: (result.candidate_kpis ?? []).length, icon: FlaskConical },
                    { label: 'Good KPIs',    value: (result.good_kpis      ?? []).length, icon: CheckCircle2 },
                    { label: 'Insights',     value: (result.insights        ?? []).length, icon: Lightbulb },
                  ].map(s => {
                    const Icon = s.icon;
                    return (
                      <div key={s.label} className="bg-card border border-border rounded-xl p-4">
                        <div className="flex items-center gap-2 mb-1">
                          <Icon className="w-4 h-4 text-primary" />
                          <span className="text-xs text-muted-foreground">{s.label}</span>
                        </div>
                        <span className="text-2xl font-bold text-foreground tabular-nums">{s.value}</span>
                      </div>
                    );
                  })}
                </div>

                {/* Good KPIs */}
                {(result.good_kpis ?? []).length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-primary" />
                      <h2 className="font-semibold text-sm text-foreground">
                        Discovered KPIs
                        <span className="ml-2 text-xs text-muted-foreground font-normal">{(result.good_kpis ?? []).length} passed all filters</span>
                      </h2>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {(result.good_kpis ?? []).map((kpi, i) => <KPIResultCard key={kpi.name ?? i} kpi={kpi} index={i} />)}
                    </div>
                  </div>
                )}

                {/* Candidate KPIs (generate mode only) */}
                {(result.candidate_kpis ?? []).length > 0 && (result.good_kpis ?? []).length === 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <FlaskConical className="w-4 h-4 text-primary" />
                      <h2 className="font-semibold text-sm text-foreground">Candidate KPIs</h2>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {(result.candidate_kpis ?? []).map((kpi, i) => (
                        <div key={kpi.name ?? i} className="bg-card border border-border rounded-xl p-4 space-y-1.5">
                          {kpi.category && <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full">{kpi.category}</span>}
                          <h3 className="font-semibold text-sm text-foreground">{kpi.name}</h3>
                          {kpi.description && <p className="text-xs text-muted-foreground">{kpi.description}</p>}
                          {kpi.formula && <p className="text-xs font-mono text-muted-foreground/70 bg-secondary/50 rounded px-2 py-1">{kpi.formula}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Table groups */}
                {(result.table_groups ?? []).length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Database className="w-4 h-4 text-primary" />
                      <h2 className="font-semibold text-sm text-foreground">Table Groups</h2>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {(result.table_groups ?? []).map((group, i) => (
                        <div key={i} className="flex items-center gap-1.5 bg-secondary border border-border rounded-lg px-3 py-1.5">
                          <span className="text-xs text-muted-foreground">Group {i + 1}:</span>
                          <span className="text-xs font-mono text-foreground">{group.join(' · ')}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Insights */}
                {(result.insights ?? []).length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Lightbulb className="w-4 h-4 text-primary" />
                      <h2 className="font-semibold text-sm text-foreground">
                        AI Insights <span className="ml-1 text-xs text-muted-foreground font-normal">{(result.insights ?? []).length} generated</span>
                      </h2>
                    </div>
                    <div className="space-y-2">
                      {(result.insights ?? []).map((ins, i) => <InsightCard key={i} insight={ins} />)}
                    </div>
                  </div>
                )}

                {/* Errors */}
                {errors.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-destructive" />
                      <h2 className="font-semibold text-sm text-foreground">Errors / Warnings</h2>
                    </div>
                    {errors.map((err, i) => (
                      <div key={i} className="flex items-start gap-2.5 bg-destructive/5 border border-destructive/20 rounded-xl p-3">
                        <X className="w-4 h-4 text-destructive flex-shrink-0 mt-0.5" />
                        <p className="text-xs text-muted-foreground">{err}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Top-level error (no results) */}
            {pageState === 'error' && !result && errors.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-destructive" />
                  <h2 className="font-semibold text-sm">Something went wrong</h2>
                </div>
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
      </div>
    </div>
  );
}
