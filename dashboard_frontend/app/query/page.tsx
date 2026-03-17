'use client';

import { useEffect, useRef, useState } from 'react';
import { ChartRenderer } from '@/components/ChartRenderer';
import { VegaChart } from '@/components/VegaChart';
import { Send, Code2, Clock, AlertCircle, Loader2, ChevronDown, ChevronRight, Sparkles, FlaskConical, TrendingUp, Users, Settings, Pen, Cpu } from 'lucide-react';
import type { UniversalChartSpec } from '@/types/chart';

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
const CLIENT_ID = 1;

// ── Types ─────────────────────────────────────────────────────────────────────

// ── Role configuration ────────────────────────────────────────────────────────

interface RoleOption {
  key: string;
  display_name: string;
  suggested_questions: string[];
}

const ROLE_META: Record<string, { icon: React.ReactNode; color: string; description: string }> = {
  founder:        { icon: <TrendingUp className="w-4 h-4" />, color: 'text-amber-400 border-amber-400/40 bg-amber-400/10',   description: 'Growth, KPIs, strategic overview' },
  client_success: { icon: <Users className="w-4 h-4" />,     color: 'text-blue-400 border-blue-400/40 bg-blue-400/10',       description: 'Client delivery, SLA, health' },
  operations:     { icon: <Settings className="w-4 h-4" />,   color: 'text-green-400 border-green-400/40 bg-green-400/10',   description: 'Throughput, efficiency, workflow' },
  editorial:      { icon: <Pen className="w-4 h-4" />,        color: 'text-purple-400 border-purple-400/40 bg-purple-400/10', description: 'Content, language, team output' },
  tech:           { icon: <Cpu className="w-4 h-4" />,        color: 'text-cyan-400 border-cyan-400/40 bg-cyan-400/10',      description: 'System metrics, data quality' },
};

const DEFAULT_ROLES: RoleOption[] = [
  { key: 'founder',        display_name: 'Founder / CEO',        suggested_questions: ['What is our overall publish rate?', 'Show month-over-month growth', 'Which channel is performing best?', 'Top 5 clients by output volume'] },
  { key: 'client_success', display_name: 'Client Success',       suggested_questions: ['Which clients have the lowest publish rate?', 'Show published vs created per client', 'Which clients have the most unpublished videos?', 'Average time to publish by client'] },
  { key: 'operations',     display_name: 'Operations Team',      suggested_questions: ['What is the average upload duration by channel?', 'Show total uploaded hours by team', 'Which content type takes longest to publish?', 'Daily upload volume trend'] },
  { key: 'editorial',      display_name: 'Editorial / Production', suggested_questions: ['Show created vs published videos by language', 'Which content type has the highest publish rate?', 'Top 10 users by output count', 'Compare publish rate across channels'] },
  { key: 'tech',           display_name: 'Tech / Product',       suggested_questions: ['Show data quality issue counts', 'Monthly trend of uploads over 6 months', 'Which channels have missing language data?', 'Billable vs non-billable video distribution'] },
];

interface LidaInsight {
  title: string;
  chart_spec: Record<string, unknown>;
}

interface NLQResult {
  question:   string;
  sql:        string | null;
  chart_type: string | null;
  title:      string | null;
  x:          string | null;
  y:          string | null;
  description: string;
  data:       Record<string, unknown>[];
  columns:    string[];
  row_count:  number;
  insights:   LidaInsight[];
  processing_time_ms?: number;
  error?:     string;
}

interface Message {
  id:        string;
  role:      'user' | 'assistant';
  question?: string;
  result?:   NLQResult;
  loading?:  boolean;
  ts:        Date;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function nlqToChartSpec(r: NLQResult): UniversalChartSpec {
  return {
    chart_type:  (r.chart_type ?? 'table') as UniversalChartSpec['chart_type'],
    title:       r.title ?? undefined,
    description: r.description,
    x:           r.x ?? undefined,
    y:           r.y ?? undefined,
    data:        r.data,
  };
}

function formatTime(d: Date) {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function uid() {
  return Math.random().toString(36).slice(2);
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SqlBlock({ sql }: { sql: string }) {
  return (
    <pre className="text-xs font-mono text-green-400 bg-[#0d1117] rounded-lg p-4 overflow-x-auto whitespace-pre-wrap leading-relaxed border border-border">
      {sql}
    </pre>
  );
}

function HistoryItem({
  msg,
  active,
  onClick,
}: {
  msg: Message;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-lg px-3 py-2.5 transition-colors group ${
        active ? 'bg-primary/20 border border-primary/40' : 'hover:bg-sidebar-accent border border-transparent'
      }`}
    >
      <div className="flex items-start gap-2">
        <div className={`mt-0.5 shrink-0 w-2 h-2 rounded-full ${active ? 'bg-primary' : 'bg-muted-foreground/40 group-hover:bg-muted-foreground'}`} />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-foreground truncate leading-snug">{msg.question}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{formatTime(msg.ts)}</p>
        </div>
      </div>
    </button>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[70%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5">
        <p className="text-sm text-primary-foreground leading-relaxed">{text}</p>
      </div>
    </div>
  );
}

function ElapsedTimer() {
  const [ms, setMs] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => setMs(Date.now() - start), 100);
    return () => clearInterval(id);
  }, []);
  const label = ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
  return <span className="text-xs text-muted-foreground tabular-nums">{label}</span>;
}

function AssistantBubble({ msg }: { msg: Message }) {
  const [sqlOpen, setSqlOpen] = useState(false);

  if (msg.loading) {
    return (
      <div className="flex items-center gap-3 text-muted-foreground py-2">
        <Loader2 className="w-4 h-4 animate-spin text-primary" />
        <span className="text-sm">Thinking…</span>
        <ElapsedTimer />
      </div>
    );
  }

  const r = msg.result!;

  if (r.error) {
    return (
      <div className="flex gap-3 max-w-[85%]">
        <div className="shrink-0 mt-0.5 w-7 h-7 rounded-full bg-destructive/20 flex items-center justify-center">
          <AlertCircle className="w-4 h-4 text-destructive" />
        </div>
        <div className="bg-destructive/10 border border-destructive/30 rounded-2xl rounded-tl-sm px-4 py-3">
          <p className="text-sm text-destructive font-medium">Query failed</p>
          <p className="text-xs text-muted-foreground mt-1">{r.error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 max-w-[90%]">
      <div className="shrink-0 mt-0.5 w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center">
        <Sparkles className="w-3.5 h-3.5 text-primary" />
      </div>
      <div className="flex-1 space-y-3">
        {/* Header */}
        <div className="bg-card border border-border rounded-2xl rounded-tl-sm px-4 py-3">
          <p className="text-sm font-medium text-foreground">{r.title || 'Result'}</p>
          {r.description && (
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{r.description}</p>
          )}
          <div className="flex items-center gap-3 mt-1">
            <p className="text-xs text-muted-foreground">{r.row_count.toLocaleString()} rows</p>
            {r.processing_time_ms != null && (
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {r.processing_time_ms >= 1000
                  ? `${(r.processing_time_ms / 1000).toFixed(1)}s`
                  : `${Math.round(r.processing_time_ms)}ms`}
              </p>
            )}
          </div>
        </div>

        {/* Chart */}
        {r.data.length > 0 && (
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <ChartRenderer chart={nlqToChartSpec(r)} />
          </div>
        )}

        {/* LIDA insights */}
        {r.insights && r.insights.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <FlaskConical className="w-3.5 h-3.5 text-primary" />
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Explore Insights ({r.insights.length})
              </span>
            </div>
            {r.insights.map((ins, i) =>
              ins.chart_spec && Object.keys(ins.chart_spec).length > 0 ? (
                <VegaChart key={i} spec={ins.chart_spec} title={ins.title} />
              ) : (
                <div key={i} className="bg-card border border-border rounded-lg px-4 py-3 text-sm text-muted-foreground">
                  {ins.title}
                </div>
              )
            )}
          </div>
        )}

        {/* SQL toggle */}
        {r.sql && (
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => setSqlOpen((v) => !v)}
              className="w-full flex items-center gap-2 px-4 py-2.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <Code2 className="w-3.5 h-3.5" />
              <span>SQL</span>
              {sqlOpen ? <ChevronDown className="w-3 h-3 ml-auto" /> : <ChevronRight className="w-3 h-3 ml-auto" />}
            </button>
            {sqlOpen && (
              <div className="px-4 pb-4">
                <SqlBlock sql={r.sql} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function QueryPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [exploreMode, setExploreMode] = useState(false);
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // history = only assistant messages that have a result
  const history = messages.filter((m) => m.role === 'assistant' && m.result && !m.result.error);
  const activeMsg = activeHistoryId ? messages.find((m) => m.id === activeHistoryId) : null;

  // SQL shown in left panel = active history item, or last successful assistant message
  const sqlMsg = activeMsg ?? [...messages].reverse().find((m) => m.role === 'assistant' && m.result?.sql);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function sendQuestion(question: string) {
    if (!question.trim() || isLoading) return;

    const userMsg: Message = { id: uid(), role: 'user', question: question.trim(), ts: new Date() };
    const pendingId = uid();
    const pendingMsg: Message = { id: pendingId, role: 'assistant', loading: true, ts: new Date() };

    setMessages((prev) => [...prev, userMsg, pendingMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await fetch(`${API_URL}/nlq/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim(), client_id: CLIENT_ID, explore: exploreMode, user_role: selectedRole }),
      });

      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try { detail = (await res.json()).detail ?? detail; } catch {}
        throw new Error(detail);
      }

      const result: NLQResult = await res.json();
      const doneMsg: Message = { id: pendingId, role: 'assistant', question: question.trim(), result, ts: new Date() };

      setMessages((prev) => prev.map((m) => (m.id === pendingId ? doneMsg : m)));
      if (!result.error) {
        setActiveHistoryId(pendingId);
      }
    } catch (err) {
      const errMsg: Message = {
        id: pendingId,
        role: 'assistant',
        question: question.trim(),
        result: {
          question: question.trim(), sql: null, chart_type: 'table', title: 'Error',
          x: '', y: '', description: '', data: [], columns: [], row_count: 0, insights: [],
          error: err instanceof Error ? err.message : 'Network error — is the backend running?',
        },
        ts: new Date(),
      };
      setMessages((prev) => prev.map((m) => (m.id === pendingId ? errMsg : m)));
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void sendQuestion(input);
    }
  }

  const activeRole = selectedRole ? DEFAULT_ROLES.find((r) => r.key === selectedRole) ?? null : null;
  const suggestions = activeRole?.suggested_questions ?? [
    'Which channel had the highest publish rate last month?',
    'Show me created vs published videos by language',
    'Top 10 users by output count',
    'Monthly trend of uploads over the last 6 months',
  ];

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── LEFT PANEL ──────────────────────────────────────────────────── */}
      <aside className="w-80 shrink-0 border-r border-border bg-sidebar flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-sidebar-border">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold text-sidebar-foreground">Query History</h2>
          </div>
          <p className="text-xs text-muted-foreground mt-1">Click a query to preview its SQL</p>
        </div>

        {/* Role selector */}
        <div className="px-3 py-3 border-b border-sidebar-border space-y-2">
          <p className="text-xs font-semibold text-muted-foreground px-1 uppercase tracking-wide">Your role</p>
          <div className="space-y-1">
            {DEFAULT_ROLES.map((role) => {
              const meta = ROLE_META[role.key];
              const isActive = selectedRole === role.key;
              return (
                <button
                  key={role.key}
                  onClick={() => setSelectedRole(isActive ? null : role.key)}
                  className={`w-full text-left rounded-lg px-3 py-2 flex items-center gap-2.5 transition-colors border text-xs ${
                    isActive
                      ? `${meta.color} border-current`
                      : 'border-transparent text-muted-foreground hover:bg-sidebar-accent hover:text-foreground'
                  }`}
                >
                  <span className={isActive ? '' : 'opacity-60'}>{meta.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{role.display_name}</div>
                    <div className={`text-[10px] truncate ${isActive ? 'opacity-80' : 'opacity-60'}`}>{meta.description}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* History list */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {history.length === 0 ? (
            <div className="text-center text-muted-foreground text-xs py-8 px-4 leading-relaxed">
              Your queries will appear here. Ask something to get started.
            </div>
          ) : (
            [...history].reverse().map((msg) => (
              <HistoryItem
                key={msg.id}
                msg={msg}
                active={activeHistoryId === msg.id}
                onClick={() => setActiveHistoryId(msg.id === activeHistoryId ? null : msg.id)}
              />
            ))
          )}
        </div>

        {/* SQL preview panel */}
        <div className="border-t border-sidebar-border">
          <div className="px-4 pt-3 pb-1 flex items-center gap-2">
            <Code2 className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">SQL Preview</span>
          </div>
          <div className="px-3 pb-4 max-h-64 overflow-y-auto">
            {sqlMsg?.result?.sql ? (
              <SqlBlock sql={sqlMsg.result.sql} />
            ) : (
              <p className="text-xs text-muted-foreground italic px-1 py-2">
                No query selected yet.
              </p>
            )}
          </div>
        </div>
      </aside>

      {/* ── RIGHT PANEL ─────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col overflow-hidden bg-background">
        {/* Top bar */}
        <div className="px-6 py-4 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            <h1 className="text-lg font-semibold text-foreground">Natural Language Query</h1>
            {activeRole && (
              <span className={`ml-auto flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-medium ${ROLE_META[activeRole.key].color}`}>
                {ROLE_META[activeRole.key].icon}
                {activeRole.display_name}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {activeRole
              ? `Answering as ${activeRole.display_name} — ${ROLE_META[activeRole.key].description}`
              : 'Ask any question about your video operations data — the AI generates SQL and visualises the result.'}
          </p>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
          {/* Empty state */}
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-8 text-center">
              <div>
                <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
                  <Sparkles className="w-8 h-8 text-primary" />
                </div>
                <h2 className="text-xl font-semibold text-foreground">
                  {activeRole ? `Hello, ${activeRole.display_name}` : 'Ask your data anything'}
                </h2>
                <p className="text-sm text-muted-foreground mt-2 max-w-md">
                  {activeRole
                    ? `Insights tailored for ${activeRole.display_name}. ${ROLE_META[activeRole.key].description}.`
                    : 'Type a plain-English question. The AI will generate SQL, run it against your Frammer database, and render the result as a chart.'}
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => void sendQuestion(s)}
                    className="text-left rounded-xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground hover:text-foreground hover:border-primary/50 hover:bg-card/80 transition-all"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Conversation */}
          {messages.map((msg) =>
            msg.role === 'user' ? (
              <UserBubble key={msg.id} text={msg.question!} />
            ) : (
              <AssistantBubble key={msg.id} msg={msg} />
            )
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="px-6 pb-6 shrink-0">
          <div className="relative flex items-end gap-3 bg-card border border-border rounded-2xl px-4 py-3 focus-within:border-primary/60 transition-colors">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your data… (Enter to send, Shift+Enter for new line)"
              rows={1}
              className="flex-1 bg-transparent resize-none text-sm text-foreground placeholder:text-muted-foreground outline-none leading-relaxed max-h-40 overflow-y-auto"
              style={{ fieldSizing: 'content' } as React.CSSProperties}
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={() => setExploreMode((v) => !v)}
              title={exploreMode ? 'Explore mode ON — LIDA will generate extra insight charts' : 'Enable Explore mode for additional AI-generated charts'}
              className={`shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-colors border ${
                exploreMode
                  ? 'bg-primary/20 border-primary text-primary'
                  : 'border-border text-muted-foreground hover:text-foreground hover:border-border/80'
              }`}
            >
              <FlaskConical className="w-4 h-4" />
            </button>
            <button
              onClick={() => void sendQuestion(input)}
              disabled={!input.trim() || isLoading}
              className="shrink-0 w-9 h-9 rounded-xl bg-primary flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary/90 transition-colors"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 text-primary-foreground animate-spin" />
              ) : (
                <Send className="w-4 h-4 text-primary-foreground" />
              )}
            </button>
          </div>
          <p className="text-xs text-muted-foreground text-center mt-2">
            {exploreMode
              ? '🔬 Explore mode on — LIDA will generate extra insight charts after each query'
              : 'Queries are executed read-only against your Frammer database.'}
          </p>
        </div>
      </main>
    </div>
  );
}
