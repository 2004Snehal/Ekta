'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Upload, Zap, BarChart3, RefreshCw, Trash2, ChevronDown, ChevronRight,
  CheckCircle2, AlertCircle, Loader2, Database, FlaskConical, Lightbulb,
  FileText, Play, X, Server,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
const BASE = `${API_URL}/kpi-lab`;

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

function fmt(val: number | string | undefined | null): string {
  if (val === undefined || val === null) return '\u2014';
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
  'Reading schema', 'Discovering relationships', 'Grouping tables',
  'Extracting statistics', 'Generating KPI candidates', 'Building SQL',
  'Executing queries', 'Evaluating KPIs', 'Generating insights',
];

function SchemaCard({ name, schema }: { name: string; schema: TableSchema }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ border: '1px solid var(--wire)', borderRadius: '14px', overflow: 'hidden' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', background: 'var(--surface)', cursor: 'pointer',
          border: 'none', transition: 'background 0.15s', textAlign: 'left',
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-hi)'; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--surface)'; }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Database style={{ width: '15px', height: '15px', color: 'var(--signal)' }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', fontWeight: 700, color: 'var(--on)' }}>{name}</span>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', color: 'var(--on-low)', background: 'var(--surface-raise)', padding: '2px 8px', borderRadius: '20px' }}>
            {schema.row_count.toLocaleString()} rows · {schema.columns.length} cols
          </span>
        </div>
        {open
          ? <ChevronDown style={{ width: '14px', height: '14px', color: 'var(--on-low)' }} />
          : <ChevronRight style={{ width: '14px', height: '14px', color: 'var(--on-low)' }} />}
      </button>
      {open && (
        <div style={{ padding: '14px 16px', background: 'var(--surface-hi)', borderTop: '1px solid var(--wire)' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: schema.sample_rows.length ? '12px' : 0 }}>
            {schema.columns.map(col => (
              <span key={col.name} style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px',
                fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                background: 'var(--surface)', border: '1px solid var(--wire)',
                borderRadius: '8px', padding: '3px 10px',
              }}>
                <span style={{ color: 'var(--on)' }}>{col.name}</span>
                <span style={{ color: 'var(--on-low)' }}>·</span>
                <span style={{ color: 'var(--signal)' }}>{col.type}</span>
              </span>
            ))}
          </div>
          {schema.sample_rows.length > 0 && (
            <div style={{ overflowX: 'auto', borderRadius: '10px', border: '1px solid var(--wire)' }}>
              <table style={{ fontSize: '0.72rem', width: '100%', borderCollapse: 'collapse' }}>
                <thead style={{ background: 'var(--surface-raise)' }}>
                  <tr>
                    {schema.columns.slice(0, 6).map(c => (
                      <th key={c.name} style={{ padding: '8px 12px', textAlign: 'left', fontFamily: 'var(--font-sans)', fontWeight: 700, color: 'var(--on-low)', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {c.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {schema.sample_rows.slice(0, 3).map((row, i) => (
                    <tr key={i} style={{ borderTop: '1px solid var(--wire)', background: i % 2 === 0 ? 'var(--surface)' : 'var(--surface-hi)' }}>
                      {schema.columns.slice(0, 6).map(c => (
                        <td key={c.name} style={{ padding: '7px 12px', fontFamily: 'var(--font-mono)', color: 'var(--on-mid)', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {String(row[c.name] ?? '\u2014')}
                        </td>
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
  const scoreColor = score >= 8 ? 'var(--ok)' : score >= 6 ? 'var(--warn)' : 'var(--on-low)';
  const [sqlOpen, setSqlOpen] = useState(false);
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--wire)',
      borderRadius: '16px', padding: '16px 18px',
      display: 'flex', flexDirection: 'column', gap: '10px',
      transition: 'border-color 0.2s, box-shadow 0.2s',
      boxShadow: '0 2px 8px rgba(43, 35, 32, 0.05)',
    }}
    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(196, 85, 58, 0.3)'; (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 16px rgba(43, 35, 32, 0.1)'; }}
    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--wire)'; (e.currentTarget as HTMLElement).style.boxShadow = '0 2px 8px rgba(43, 35, 32, 0.05)'; }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '5px' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--on-low)' }}>#{index + 1}</span>
            {kpi.category && (
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', fontWeight: 600, color: 'var(--signal)', background: 'var(--signal-dim)', padding: '2px 8px', borderRadius: '20px' }}>
                {kpi.category}
              </span>
            )}
          </div>
          <h3 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--on)', lineHeight: 1.35 }}>{kpi.name}</h3>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.5rem', fontWeight: 700, color: 'var(--on)' }}>
            {fmt(kpi.value)}{kpi.unit && <span style={{ fontSize: '0.85rem', color: 'var(--on-low)', marginLeft: '4px' }}>{kpi.unit}</span>}
          </div>
          {kpi.usefulness_score !== undefined && (
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', fontWeight: 600, color: scoreColor }}>
              score {score.toFixed(1)}
            </div>
          )}
        </div>
      </div>
      {kpi.description && (
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-mid)', lineHeight: 1.55 }}>{kpi.description}</p>
      )}
      {kpi.sql && (
        <div>
          <button
            onClick={() => setSqlOpen(o => !o)}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: '0.75rem', color: 'var(--on-low)', transition: 'color 0.2s', padding: '2px 0' }}
          >
            {sqlOpen ? <ChevronDown style={{ width: '12px', height: '12px' }} /> : <ChevronRight style={{ width: '12px', height: '12px' }} />}
            View SQL
          </button>
          {sqlOpen && (
            <pre style={{ marginTop: '8px', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', background: 'var(--surface-hi)', borderRadius: '10px', padding: '10px 14px', overflowX: 'auto', color: 'var(--on-mid)', lineHeight: 1.6, whiteSpace: 'pre-wrap', border: '1px solid var(--wire)' }}>
              {kpi.sql}
            </pre>
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
    <div style={{
      display: 'flex', gap: '14px',
      background: 'var(--surface)', border: '1px solid var(--wire)',
      borderRadius: '14px', padding: '16px 18px',
      boxShadow: '0 2px 8px rgba(43, 35, 32, 0.05)',
    }}>
      <div style={{
        width: '32px', height: '32px', borderRadius: '10px',
        background: 'var(--signal-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0, marginTop: '2px',
      }}>
        <Lightbulb style={{ width: '15px', height: '15px', color: 'var(--signal)' }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        {insight.kpi_name && (
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', fontWeight: 700, color: 'var(--signal)', marginBottom: '4px' }}>
            {insight.kpi_name}
          </p>
        )}
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-mid)', lineHeight: 1.6 }}>{text}</p>
      </div>
    </div>
  );
}

function AgentProgress({ active, agentIndex }: { active: boolean; agentIndex: number }) {
  if (!active) return null;
  return (
    <div style={{ marginTop: '16px' }}>
      <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', fontWeight: 700, color: 'var(--on-low)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: '10px' }}>
        Pipeline agents
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {AGENT_LABELS.map((label, i) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '22px', height: '22px', borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
              background: i < agentIndex ? 'rgba(91, 138, 114, 0.12)' : i === agentIndex ? 'var(--signal-dim)' : 'var(--surface-raise)',
              color: i < agentIndex ? 'var(--ok)' : i === agentIndex ? 'var(--signal)' : 'var(--on-low)',
              transition: 'all 0.3s',
            }}>
              {i < agentIndex
                ? <CheckCircle2 style={{ width: '12px', height: '12px' }} />
                : i === agentIndex
                  ? <Loader2 style={{ width: '12px', height: '12px', animation: 'spin 1s linear infinite' }} />
                  : <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'currentColor', display: 'block' }} />}
            </div>
            <span style={{
              fontFamily: 'var(--font-sans)', fontSize: '0.78rem',
              color: i < agentIndex ? 'var(--ok)' : i === agentIndex ? 'var(--on)' : 'var(--on-low)',
              fontWeight: i === agentIndex ? 600 : 400,
            }}>
              {label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

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

  const loadSources = useCallback(async () => {
    setPageState('loading_sources');
    try {
      const res = await fetch(`${BASE}/sources`);
      const data = await res.json();
      setSources(data.sources ?? []);
      setPageState('idle');
    } catch { setPageState('idle'); }
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

  useEffect(() => {
    loadSources();
    loadSchema('postgres');
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length) {
      setDataSource('csv');
      uploadFiles(e.dataTransfer.files);
    }
  }, [uploadFiles]);

  const hasSchema  = !!schema && Object.keys(schema.tables).length > 0;
  const isRunning  = pageState === 'running';
  const isBusy     = pageState === 'uploading' || pageState === 'loading_schema' || pageState === 'loading_sources';
  const canRun     = hasSchema && !isRunning && !isBusy;

  const pgSource   = sources?.find(s => s.id === 'postgres');
  const csvSource  = sources?.find(s => s.id === 'csv');

  return (
    <div style={{ minHeight: '100vh', background: 'var(--void)' }}>
      <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '32px 24px' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', marginBottom: '28px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{ width: '44px', height: '44px', borderRadius: '14px', background: 'var(--signal-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Zap style={{ width: '20px', height: '20px', color: 'var(--signal)' }} />
            </div>
            <div>
              <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.6rem', fontWeight: 700, color: 'var(--on)', marginBottom: '3px' }}>KPI Lab</h1>
              <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-mid)' }}>Agentic KPI discovery — choose a data source and run the pipeline</p>
            </div>
          </div>
          {(hasSchema || result) && (
            <button
              onClick={resetAll}
              style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                padding: '7px 14px', borderRadius: '10px',
                border: '1px solid var(--wire)', background: 'var(--surface)',
                fontFamily: 'var(--font-sans)', fontSize: '0.78rem', fontWeight: 600,
                color: 'var(--on-mid)', cursor: 'pointer', transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--signal)'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(196, 85, 58, 0.3)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--on-mid)'; (e.currentTarget as HTMLElement).style.borderColor = 'var(--wire)'; }}
            >
              <Trash2 style={{ width: '13px', height: '13px' }} />Reset
            </button>
          )}
        </div>

        {/* Data Source Selector */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '20px' }}>
          {[
            { src: 'postgres' as DataSource, Icon: Server, label: 'Frammer Database', badge: pgSource ? `${pgSource.table_count} tables` : null, badgeColor: 'var(--ok)', desc: 'Discover KPIs directly from your live Supabase PostgreSQL tables — no upload needed' },
            { src: 'csv' as DataSource, Icon: Upload, label: 'Upload CSV', badge: csvSource && csvSource.table_count > 0 ? `${csvSource.table_count} loaded` : null, badgeColor: 'var(--uplink)', desc: 'Upload your own CSV files and discover KPIs from any dataset in memory' },
          ].map(({ src, Icon, label, badge, badgeColor, desc }) => {
            const active = dataSource === src;
            return (
              <button
                key={src}
                onClick={() => handleSourceChange(src)}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: '16px',
                  padding: '16px 18px', borderRadius: '16px', textAlign: 'left',
                  border: `2px solid ${active ? 'rgba(196, 85, 58, 0.4)' : 'var(--wire)'}`,
                  background: active ? 'rgba(196, 85, 58, 0.04)' : 'var(--surface)',
                  cursor: 'pointer', transition: 'all 0.2s',
                  boxShadow: active ? '0 4px 16px rgba(196, 85, 58, 0.1)' : 'none',
                }}
              >
                <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: active ? 'var(--signal-dim)' : 'var(--surface-raise)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Icon style={{ width: '18px', height: '18px', color: active ? 'var(--signal)' : 'var(--on-low)' }} />
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.88rem', fontWeight: 700, color: active ? 'var(--signal)' : 'var(--on)' }}>{label}</span>
                    {badge && (
                      <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', fontWeight: 600, color: badgeColor, background: active ? 'rgba(91, 138, 114, 0.1)' : 'rgba(91, 138, 114, 0.08)', padding: '2px 8px', borderRadius: '20px' }}>
                        {badge}
                      </span>
                    )}
                  </div>
                  <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-mid)', lineHeight: 1.5 }}>{desc}</p>
                </div>
                {active && <CheckCircle2 style={{ width: '16px', height: '16px', color: 'var(--signal)', flexShrink: 0, marginTop: '2px' }} />}
              </button>
            );
          })}
        </div>

        {/* CSV upload zone */}
        {dataSource === 'csv' && (
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${dragOver ? 'var(--signal)' : 'var(--wire)'}`,
              borderRadius: '16px', padding: '32px',
              textAlign: 'center', cursor: 'pointer',
              background: dragOver ? 'rgba(196, 85, 58, 0.04)' : 'var(--surface)',
              transition: 'all 0.2s', marginBottom: '16px',
              transform: dragOver ? 'scale(1.01)' : 'none',
            }}
          >
            <input ref={fileInputRef} type="file" accept=".csv,.tsv,.txt" multiple style={{ display: 'none' }}
              onChange={e => { if (e.target.files?.length) uploadFiles(e.target.files); }} />
            {pageState === 'uploading' ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
                <Loader2 style={{ width: '28px', height: '28px', color: 'var(--signal)', animation: 'spin 1s linear infinite' }} />
                <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-mid)' }}>Uploading and loading into DuckDB…</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
                <div style={{ width: '48px', height: '48px', borderRadius: '14px', background: 'var(--surface-raise)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <FileText style={{ width: '22px', height: '22px', color: 'var(--on-low)' }} />
                </div>
                <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.88rem', fontWeight: 600, color: 'var(--on)' }}>Drop CSV files here or click to browse</p>
                <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-low)' }}>.csv · .tsv · .txt · multiple files supported</p>
              </div>
            )}
          </div>
        )}

        {/* Uploaded table chips */}
        {dataSource === 'csv' && uploadedTables.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '20px' }}>
            {uploadedTables.map(t => (
              <span key={t} style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px',
                fontFamily: 'var(--font-mono)', fontSize: '0.75rem',
                color: 'var(--ok)', background: 'rgba(91, 138, 114, 0.1)',
                border: '1px solid rgba(91, 138, 114, 0.25)',
                borderRadius: '8px', padding: '4px 12px',
              }}>
                <CheckCircle2 style={{ width: '13px', height: '13px' }} />{t}
              </span>
            ))}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '24px' }}>

          {/* Left: Pipeline config */}
          <div>
            <div style={{ background: 'var(--surface)', border: '1px solid var(--wire)', borderRadius: '18px', padding: '20px', boxShadow: '0 2px 12px rgba(43, 35, 32, 0.06)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
                <Play style={{ width: '15px', height: '15px', color: 'var(--signal)' }} />
                <h2 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--on)' }}>Pipeline Mode</h2>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {PIPELINE_STEPS.map(step => {
                  const Icon = step.icon;
                  const active = mode === step.id;
                  return (
                    <button
                      key={step.id}
                      onClick={() => setMode(step.id)}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'flex-start', gap: '10px',
                        padding: '10px 12px', borderRadius: '12px', textAlign: 'left',
                        border: `1.5px solid ${active ? 'rgba(196, 85, 58, 0.35)' : 'var(--wire)'}`,
                        background: active ? 'rgba(196, 85, 58, 0.05)' : 'transparent',
                        cursor: 'pointer', transition: 'all 0.2s',
                      }}
                    >
                      <div style={{ width: '28px', height: '28px', borderRadius: '8px', background: active ? 'var(--signal-dim)' : 'var(--surface-raise)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: '1px' }}>
                        <Icon style={{ width: '14px', height: '14px', color: active ? 'var(--signal)' : 'var(--on-low)' }} />
                      </div>
                      <div>
                        <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.8rem', fontWeight: 700, color: active ? 'var(--signal)' : 'var(--on)', marginBottom: '2px' }}>{step.label}</p>
                        <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', color: 'var(--on-low)', lineHeight: 1.4 }}>{step.description}</p>
                      </div>
                    </button>
                  );
                })}
              </div>

              <button
                onClick={runPipeline}
                disabled={!canRun}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                  padding: '12px', marginTop: '16px', borderRadius: '12px',
                  border: 'none', background: canRun ? 'var(--signal)' : 'var(--surface-raise)',
                  color: canRun ? '#fff' : 'var(--on-low)',
                  fontFamily: 'var(--font-sans)', fontSize: '0.88rem', fontWeight: 700,
                  cursor: canRun ? 'pointer' : 'not-allowed',
                  boxShadow: canRun ? '0 4px 14px rgba(196, 85, 58, 0.25)' : 'none',
                  transition: 'all 0.2s', opacity: canRun ? 1 : 0.6,
                }}
              >
                {isRunning
                  ? <><Loader2 style={{ width: '15px', height: '15px', animation: 'spin 1s linear infinite' }} />Running…</>
                  : <><Zap style={{ width: '15px', height: '15px' }} />Run on {dataSource === 'postgres' ? 'Frammer DB' : 'CSV'}</>}
              </button>

              <div style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                padding: '8px 12px', borderRadius: '10px', marginTop: '12px',
                fontFamily: 'var(--font-sans)', fontSize: '0.75rem',
                color: dataSource === 'postgres' ? 'var(--ok)' : 'var(--uplink)',
                background: dataSource === 'postgres' ? 'rgba(91, 138, 114, 0.08)' : 'rgba(91, 126, 161, 0.08)',
                border: `1px solid ${dataSource === 'postgres' ? 'rgba(91, 138, 114, 0.2)' : 'rgba(91, 126, 161, 0.2)'}`,
              }}>
                {dataSource === 'postgres' ? <Server style={{ width: '13px', height: '13px' }} /> : <Upload style={{ width: '13px', height: '13px' }} />}
                <span>{dataSource === 'postgres' ? 'Using Frammer PostgreSQL' : 'Using uploaded CSV tables'}</span>
              </div>

              <AgentProgress active={isRunning} agentIndex={agentIndex} />
            </div>
          </div>

          {/* Right: Schema + Results */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>

            {isBusy && !isRunning && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                  <Loader2 style={{ width: '28px', height: '28px', color: 'var(--signal)', animation: 'spin 1s linear infinite' }} />
                  <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-mid)' }}>
                    {pageState === 'loading_schema' ? `Loading ${dataSource === 'postgres' ? 'Frammer database' : 'CSV'} schema…` : 'Loading sources…'}
                  </p>
                </div>
              </div>
            )}

            {hasSchema && !isBusy && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {dataSource === 'postgres' ? <Server style={{ width: '15px', height: '15px', color: 'var(--signal)' }} /> : <Database style={{ width: '15px', height: '15px', color: 'var(--signal)' }} />}
                    <h2 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--on)' }}>
                      {dataSource === 'postgres' ? 'Frammer Database Schema' : 'Uploaded CSV Schema'}
                      <span style={{ marginLeft: '8px', fontWeight: 400, fontSize: '0.78rem', color: 'var(--on-low)' }}>
                        {Object.keys(schema!.tables).length} tables
                      </span>
                    </h2>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {schema?.cached && dataSource === 'postgres' && (
                      <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', color: 'var(--on-low)', background: 'var(--surface-raise)', padding: '2px 8px', borderRadius: '20px' }}>cached</span>
                    )}
                    <button
                      onClick={() => loadSchema(dataSource, true)}
                      style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-low)', transition: 'color 0.2s', padding: '4px 0' }}
                    >
                      <RefreshCw style={{ width: '12px', height: '12px' }} />Refresh
                    </button>
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '380px', overflowY: 'auto', paddingRight: '4px' }}>
                  {Object.entries(schema!.tables).map(([name, tbl]) => (
                    <SchemaCard key={name} name={name} schema={tbl} />
                  ))}
                </div>
              </div>
            )}

            {!hasSchema && !isBusy && pageState !== 'error' && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '64px 0', textAlign: 'center' }}>
                <div style={{ width: '56px', height: '56px', borderRadius: '16px', background: 'var(--surface)', border: '1px solid var(--wire)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '16px' }}>
                  <FlaskConical style={{ width: '24px', height: '24px', color: 'var(--on-low)', opacity: 0.5 }} />
                </div>
                <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1rem', fontWeight: 700, color: 'var(--on)', marginBottom: '8px' }}>
                  {dataSource === 'csv' ? 'No CSV files uploaded yet' : 'Could not load database schema'}
                </h3>
                <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-mid)', maxWidth: '300px', lineHeight: 1.6 }}>
                  {dataSource === 'csv' ? 'Upload one or more CSV files above to get started.' : 'Make sure the backend is running and DATABASE_URL is configured correctly.'}
                </p>
              </div>
            )}

            {result && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                {/* Summary row */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                  {[
                    { label: 'Table Groups', value: result.table_groups.length, icon: Database },
                    { label: 'Candidates',   value: result.candidate_kpis.length, icon: FlaskConical },
                    { label: 'Good KPIs',    value: result.good_kpis.length, icon: CheckCircle2 },
                    { label: 'Insights',     value: result.insights.length, icon: Lightbulb },
                  ].map(s => {
                    const Icon = s.icon;
                    return (
                      <div key={s.label} style={{ background: 'var(--surface)', border: '1px solid var(--wire)', borderRadius: '14px', padding: '16px', boxShadow: '0 2px 8px rgba(43, 35, 32, 0.05)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                          <Icon style={{ width: '14px', height: '14px', color: 'var(--signal)' }} />
                          <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', color: 'var(--on-low)' }}>{s.label}</span>
                        </div>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1.5rem', fontWeight: 700, color: 'var(--on)' }}>{s.value}</span>
                      </div>
                    );
                  })}
                </div>

                {/* Good KPIs */}
                {result.good_kpis.length > 0 && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                      <BarChart3 style={{ width: '15px', height: '15px', color: 'var(--signal)' }} />
                      <h2 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--on)' }}>
                        Discovered KPIs
                        <span style={{ marginLeft: '8px', fontWeight: 400, fontSize: '0.78rem', color: 'var(--on-low)' }}>{result.good_kpis.length} passed all filters</span>
                      </h2>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      {result.good_kpis.map((kpi, i) => <KPIResultCard key={kpi.name ?? i} kpi={kpi} index={i} />)}
                    </div>
                  </div>
                )}

                {/* Candidate KPIs */}
                {result.candidate_kpis.length > 0 && result.good_kpis.length === 0 && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                      <FlaskConical style={{ width: '15px', height: '15px', color: 'var(--signal)' }} />
                      <h2 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--on)' }}>Candidate KPIs</h2>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      {result.candidate_kpis.map((kpi, i) => (
                        <div key={kpi.name ?? i} style={{ background: 'var(--surface)', border: '1px solid var(--wire)', borderRadius: '14px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          {kpi.category && <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', fontWeight: 600, color: 'var(--signal)', background: 'var(--signal-dim)', padding: '2px 8px', borderRadius: '20px', alignSelf: 'flex-start' }}>{kpi.category}</span>}
                          <h3 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--on)' }}>{kpi.name}</h3>
                          {kpi.description && <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-mid)' }}>{kpi.description}</p>}
                          {kpi.formula && <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--on-low)', background: 'var(--surface-hi)', borderRadius: '6px', padding: '4px 10px' }}>{kpi.formula}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Table groups */}
                {result.table_groups.length > 0 && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                      <Database style={{ width: '15px', height: '15px', color: 'var(--signal)' }} />
                      <h2 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--on)' }}>Table Groups</h2>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                      {result.table_groups.map((group, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'var(--surface)', border: '1px solid var(--wire)', borderRadius: '10px', padding: '6px 14px' }}>
                          <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', color: 'var(--on-low)' }}>Group {i + 1}:</span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--on)' }}>{group.join(' · ')}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Insights */}
                {result.insights.length > 0 && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                      <Lightbulb style={{ width: '15px', height: '15px', color: 'var(--signal)' }} />
                      <h2 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--on)' }}>
                        AI Insights <span style={{ fontWeight: 400, fontSize: '0.78rem', color: 'var(--on-low)', marginLeft: '6px' }}>{result.insights.length} generated</span>
                      </h2>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {result.insights.map((ins, i) => <InsightCard key={i} insight={ins} />)}
                    </div>
                  </div>
                )}

                {/* Errors */}
                {errors.length > 0 && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                      <AlertCircle style={{ width: '15px', height: '15px', color: 'var(--signal)' }} />
                      <h2 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--on)' }}>Errors / Warnings</h2>
                    </div>
                    {errors.map((err, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', background: 'rgba(196, 85, 58, 0.05)', border: '1px solid rgba(196, 85, 58, 0.2)', borderRadius: '12px', padding: '12px 14px', marginBottom: '8px' }}>
                        <X style={{ width: '14px', height: '14px', color: 'var(--signal)', flexShrink: 0, marginTop: '2px' }} />
                        <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-mid)' }}>{err}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {pageState === 'error' && !result && errors.length > 0 && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                  <AlertCircle style={{ width: '15px', height: '15px', color: 'var(--signal)' }} />
                  <h2 style={{ fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: '0.88rem', color: 'var(--on)' }}>Something went wrong</h2>
                </div>
                {errors.map((err, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', background: 'rgba(196, 85, 58, 0.05)', border: '1px solid rgba(196, 85, 58, 0.2)', borderRadius: '12px', padding: '12px 14px', marginBottom: '8px' }}>
                    <X style={{ width: '14px', height: '14px', color: 'var(--signal)', flexShrink: 0, marginTop: '2px' }} />
                    <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-mid)' }}>{err}</p>
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
