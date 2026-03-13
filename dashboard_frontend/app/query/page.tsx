'use client';

import { useEffect, useRef, useState } from 'react';
import { ChartRenderer } from '@/components/ChartRenderer';
import { Send, Code2, Clock, AlertCircle, Loader2, ChevronDown, ChevronRight, Sparkles } from 'lucide-react';
import type { UniversalChartSpec } from '@/types/chart';

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
const CLIENT_ID = 1;

// ── Types ─────────────────────────────────────────────────────────────────────

interface NLQResult {
  question:   string;
  sql:        string | null;
  chart_type: string;
  title:      string;
  x:          string;
  y:          string;
  description: string;
  data:       Record<string, unknown>[];
  columns:    string[];
  row_count:  number;
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
    chart_type:  r.chart_type as UniversalChartSpec['chart_type'],
    title:       r.title,
    description: r.description,
    x:           r.x,
    y:           r.y,
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

function AssistantBubble({ msg }: { msg: Message }) {
  const [sqlOpen, setSqlOpen] = useState(false);

  if (msg.loading) {
    return (
      <div className="flex items-center gap-3 text-muted-foreground py-2">
        <Loader2 className="w-4 h-4 animate-spin text-primary" />
        <span className="text-sm">Thinking…</span>
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
          <p className="text-xs text-muted-foreground mt-1">{r.row_count.toLocaleString()} rows</p>
        </div>

        {/* Chart */}
        {r.data.length > 0 && (
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <ChartRenderer chart={nlqToChartSpec(r)} />
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
        body: JSON.stringify({ question: question.trim(), client_id: CLIENT_ID }),
      });

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
          x: '', y: '', description: '', data: [], columns: [], row_count: 0,
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

  const suggestions = [
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
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Ask any question about your video operations data — the AI generates SQL and visualises the result.
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
                <h2 className="text-xl font-semibold text-foreground">Ask your data anything</h2>
                <p className="text-sm text-muted-foreground mt-2 max-w-md">
                  Type a plain-English question. The AI will generate SQL, run it against your Frammer database, and render the result as a chart.
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
            Queries are executed read-only against your Frammer database.
          </p>
        </div>
      </main>
    </div>
  );
}
