'use client';

import { useEffect, useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { ChartRenderer } from '@/components/ChartRenderer';
import {
  Loader2, TrendingUp, TrendingDown, Info, BarChart3, Lightbulb, Code2, ChevronDown, ChevronRight,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ExpandStat { label: string; value: string; }

interface ExpandChart {
  chart_type: string;
  title: string;
  data: Record<string, unknown>[];
  axes?: { x: { field: string; label?: string }; y: { field: string; label?: string } };
  category?: string;
  value?: string;
}

interface ExpandDetail {
  interpretation: string;
  value_range: string;
  high_value_means: string;
  low_value_means: string;
  stats: ExpandStat[];
  charts: ExpandChart[];
}

interface RegistryKPI {
  id: string;
  name: string;
  description?: string;
  formula?: string;
  sql_expression?: string;
  columns_used: string[];
  tables_used: string[];
  category?: string;
  current_value?: unknown;
  unit?: string;
  usefulness_score?: number;
  source: string;
  has_expand: boolean;
  created_at: string;
  expand_detail?: ExpandDetail;
}

interface Props {
  open: boolean;
  kpiId: string | null;
  onOpenChange: (open: boolean) => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(val: unknown): string {
  if (val === undefined || val === null) return '—';
  const n = typeof val === 'string' ? parseFloat(val) : (val as number);
  if (isNaN(n as number)) return String(val);
  if (Math.abs(n as number) >= 1_000_000) return ((n as number) / 1_000_000).toFixed(2) + 'M';
  if (Math.abs(n as number) >= 1_000) return ((n as number) / 1_000).toFixed(1) + 'K';
  if (Number.isInteger(n)) return (n as number).toLocaleString();
  return (n as number).toFixed(2);
}

const CATEGORY_COLORS: Record<string, string> = {
  growth:     'bg-green-500/10 text-green-400 border-green-500/20',
  quality:    'bg-blue-500/10 text-blue-400 border-blue-500/20',
  efficiency: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  engagement: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
  volume:     'bg-pink-500/10 text-pink-400 border-pink-500/20',
};

function categoryStyle(cat?: string) {
  if (!cat) return 'bg-secondary text-muted-foreground border-border';
  return CATEGORY_COLORS[cat.toLowerCase()] ?? 'bg-primary/10 text-primary border-primary/20';
}

const SOURCE_LABELS: Record<string, string> = {
  manual:     'Manual',
  agent:      'AI Agent',
  discovered: 'Auto-discovered',
};

// ── Sub-components ────────────────────────────────────────────────────────────

function InsightRow({ icon: Icon, label, text }: { icon: React.ElementType; label: string; text: string }) {
  if (!text || text === 'N/A') return null;
  return (
    <div className="flex gap-3 items-start">
      <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Icon className="w-3.5 h-3.5 text-primary" />
      </div>
      <div>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-0.5">{label}</p>
        <p className="text-sm text-foreground leading-relaxed">{text}</p>
      </div>
    </div>
  );
}

function SqlBlock({ sql }: { sql?: string }) {
  const [open, setOpen] = useState(false);
  if (!sql) return null;
  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <Code2 className="w-3.5 h-3.5" />
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        View SQL
      </button>
      {open && (
        <pre className="mt-2 text-xs bg-secondary/50 rounded-lg p-3 overflow-x-auto text-muted-foreground font-mono leading-relaxed whitespace-pre-wrap">
          {sql}
        </pre>
      )}
    </div>
  );
}

// ── Main Modal ────────────────────────────────────────────────────────────────

export function KPILabExpandModal({ open, kpiId, onOpenChange }: Props) {
  const [kpi, setKpi]       = useState<RegistryKPI | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    if (!open || !kpiId) return;
    setKpi(null);
    setError(null);
    setLoading(true);

    fetch(`${API_URL}/kpi-lab/registry/${kpiId}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => { setKpi(data); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [open, kpiId]);

  const detail = kpi?.expand_detail;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-5xl bg-background border-border">
        {loading && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="w-8 h-8 text-primary animate-spin" />
            <p className="text-sm text-muted-foreground">Loading KPI detail…</p>
          </div>
        )}

        {error && !loading && (
          <div className="flex flex-col items-center justify-center py-20 gap-2">
            <p className="text-sm text-destructive font-medium">Failed to load KPI</p>
            <p className="text-xs text-muted-foreground">{error}</p>
          </div>
        )}

        {kpi && !loading && (
          <>
            {/* ── Header ──────────────────────────────────────────── */}
            <DialogHeader className="gap-2">
              <div className="flex items-center gap-2 flex-wrap">
                {kpi.category && (
                  <span className={`text-xs border rounded-full px-2.5 py-0.5 font-medium ${categoryStyle(kpi.category)}`}>
                    {kpi.category}
                  </span>
                )}
                <span className="text-xs border border-border rounded-full px-2.5 py-0.5 text-muted-foreground">
                  {SOURCE_LABELS[kpi.source] ?? kpi.source}
                </span>
              </div>
              <DialogTitle className="text-xl font-bold leading-tight">{kpi.name}</DialogTitle>
              {kpi.description && (
                <DialogDescription className="text-sm leading-relaxed">
                  {kpi.description}
                </DialogDescription>
              )}
            </DialogHeader>

            {/* ── Current value + formula ──────────────────────────── */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="bg-card border border-border rounded-xl p-4">
                <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Current Value</p>
                <p className="text-3xl font-bold text-foreground tabular-nums">
                  {fmt(kpi.current_value)}
                  {kpi.unit && <span className="text-lg text-muted-foreground ml-1.5">{kpi.unit}</span>}
                </p>
              </div>
              {kpi.formula && (
                <div className="bg-card border border-border rounded-xl p-4">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Formula</p>
                  <p className="text-sm font-mono text-foreground leading-relaxed break-all">{kpi.formula}</p>
                </div>
              )}
            </div>

            {/* ── Insight block ────────────────────────────────────── */}
            {detail && (detail.interpretation || detail.value_range || detail.high_value_means) ? (
              <div className="bg-card border border-border rounded-xl p-5 space-y-4">
                <div className="flex items-center gap-2">
                  <Lightbulb className="w-4 h-4 text-primary" />
                  <h3 className="font-semibold text-sm text-foreground">KPI Insight</h3>
                </div>
                <InsightRow icon={Info}         label="What this measures" text={detail.interpretation} />
                <InsightRow icon={BarChart3}     label="Value range"        text={detail.value_range} />
                <InsightRow icon={TrendingUp}    label="High value means"   text={detail.high_value_means} />
                <InsightRow icon={TrendingDown}  label="Low value means"    text={detail.low_value_means} />
              </div>
            ) : !kpi.has_expand ? (
              <div className="bg-secondary/30 border border-border rounded-xl p-5 text-center">
                <Lightbulb className="w-6 h-6 text-muted-foreground/40 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">Expand detail is being generated. Reopen this KPI in a moment.</p>
              </div>
            ) : null}

            {/* ── Stats grid ───────────────────────────────────────── */}
            {detail && detail.stats.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {detail.stats.map((s, i) => (
                  <div key={i} className="bg-card border border-border rounded-xl p-4">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">{s.label}</p>
                    <p className="text-xl font-bold text-foreground tabular-nums">{s.value}</p>
                  </div>
                ))}
              </div>
            )}

            {/* ── Charts ──────────────────────────────────────────── */}
            {detail && detail.charts.length > 0 ? (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {detail.charts.map((chart, i) => (
                  <div key={i} className="bg-card border border-border rounded-xl p-4">
                    <h4 className="text-sm font-semibold text-foreground mb-3">{chart.title}</h4>
                    <ChartRenderer chart={chart as Parameters<typeof ChartRenderer>[0]['chart']} />
                  </div>
                ))}
              </div>
            ) : detail && kpi.has_expand ? (
              <div className="bg-secondary/30 border border-border rounded-xl p-6 text-center">
                <BarChart3 className="w-8 h-8 text-muted-foreground/30 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No chart data available — the queries returned no rows for this KPI.</p>
              </div>
            ) : null}

            {/* ── SQL + columns metadata ──────────────────────────── */}
            <div className="bg-card border border-border rounded-xl p-4 space-y-3">
              {kpi.columns_used?.length > 0 && (
                <div>
                  <p className="text-xs uppercase tracking-wide text-muted-foreground mb-2">Columns used</p>
                  <div className="flex flex-wrap gap-1.5">
                    {kpi.columns_used.map(col => (
                      <span key={col} className="text-xs font-mono bg-secondary border border-border rounded px-2 py-0.5 text-foreground">
                        {col}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <SqlBlock sql={kpi.sql_expression} />
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
