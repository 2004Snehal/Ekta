"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useProfile } from "@/lib/profiles";
import { ChartRenderer } from "@/components/ChartRenderer";
import {
  Send,
  Code2,
  Clock,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  Sparkles,
  Plus,
  Share2,
  Trash2,
  Check,
  FlaskConical,
  Star,
} from "lucide-react";
import type { UniversalChartSpec } from "@/types/chart";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const CLIENT_ID = 1;
const USER_ID = "default-user";

// ── Types ─────────────────────────────────────────────────────────────────────

interface NLQResult {
  question: string;
  sql: string | null;
  chart_type: string;
  title: string;
  x: string;
  y: string;
  description: string;
  data: Record<string, unknown>[];
  columns: string[];
  row_count: number;
  error?: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  question?: string;
  result?: NLQResult;
  loading?: boolean;
  ts: string; // ISO string for serialisation
}

interface SessionSummary {
  session_id: string;
  title: string;
  messageCount: number;
  updatedAt: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function nlqToChartSpec(r: NLQResult): UniversalChartSpec {
  return {
    chart_type: r.chart_type as UniversalChartSpec["chart_type"],
    title: r.title,
    description: r.description,
    x: r.x,
    y: r.y,
    data: r.data,
  };
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDate(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return "Today";
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function uid() {
  return Math.random().toString(36).slice(2);
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiSaveSession(
  sessionId: string | null,
  messages: Message[],
  title?: string,
) {
  const res = await fetch(`${API_URL}/nlq/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId, userId: USER_ID, title, messages }),
  });
  if (!res.ok) throw new Error("Failed to save session");
  return (await res.json()) as { session_id: string };
}

async function apiLoadSession(sessionId: string) {
  const res = await fetch(`${API_URL}/nlq/sessions/${sessionId}`);
  if (!res.ok) throw new Error("Session not found");
  return res.json() as Promise<{
    session_id: string;
    title: string;
    messages: Message[];
  }>;
}

async function apiListSessions() {
  const res = await fetch(`${API_URL}/nlq/sessions?user_id=${USER_ID}`);
  if (!res.ok) return [];
  return res.json() as Promise<SessionSummary[]>;
}

async function apiDeleteSession(sessionId: string) {
  await fetch(`${API_URL}/nlq/sessions/${sessionId}`, { method: "DELETE" });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SqlBlock({ sql }: { sql: string }) {
  return (
    <pre className="text-xs font-mono text-green-400 bg-[#0d1117] rounded-lg p-4 overflow-x-auto whitespace-pre-wrap leading-relaxed border border-border">
      {sql}
    </pre>
  );
}

function SessionItem({
  session,
  active,
  onClick,
  onDelete,
}: {
  session: SessionSummary;
  active: boolean;
  onClick: () => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
      className={`w-full text-left rounded-lg px-3 py-2.5 transition-colors group relative cursor-pointer ${
        active
          ? "bg-primary/20 border border-primary/40"
          : "hover:bg-sidebar-accent border border-transparent"
      }`}
    >
      <div className="flex items-start gap-2 pr-6">
        <div
          className={`mt-1 shrink-0 w-1.5 h-1.5 rounded-full ${active ? "bg-primary" : "bg-muted-foreground/30"}`}
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-foreground truncate leading-snug">
            {session.title}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {formatDate(session.updatedAt)} · {session.messageCount} msgs
          </p>
        </div>
      </div>
      <button
        onClick={onDelete}
        className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 rounded hover:text-destructive transition-all"
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[70%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5">
        <p className="text-sm text-primary-foreground leading-relaxed">
          {text}
        </p>
      </div>
    </div>
  );
}

function AssistantBubble({ msg }: { msg: Message }) {
  const [sqlOpen, setSqlOpen] = useState(false);
  const [pinned, setPinned]   = useState(false);

  useEffect(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('dashboard_nlq_graphs') ?? '[]') as Array<{ id: string }>;
      setPinned(stored.some(g => g.id === msg.id));
    } catch { /* ignore */ }
  }, [msg.id]);

  function togglePin() {
    const r = msg.result;
    if (!r || r.error || !r.data?.length) return;
    try {
      const stored = JSON.parse(localStorage.getItem('dashboard_nlq_graphs') ?? '[]') as Array<{ id: string }>;
      if (pinned) {
        const next = stored.filter(g => g.id !== msg.id);
        localStorage.setItem('dashboard_nlq_graphs', JSON.stringify(next));
        setPinned(false);
      } else {
        const graph = { id: msg.id, title: r.title ?? 'NLQ Graph', chart_type: r.chart_type, x: r.x, y: r.y, data: r.data, sql: r.sql ?? null, description: r.description ?? null };
        localStorage.setItem('dashboard_nlq_graphs', JSON.stringify([...stored, graph]));
        setPinned(true);
      }
    } catch { /* ignore */ }
  }

  if (msg.loading) {
    return (
      <div className="flex items-center gap-3 text-muted-foreground py-2">
        <Loader2 className="w-4 h-4 animate-spin text-primary" />
        <span className="text-sm">Thinking…</span>
      </div>
    );
  }

  const r = msg.result;

  if (!r) {
    return (
      <div className="flex gap-3 max-w-[85%]">
        <div className="shrink-0 mt-0.5 w-7 h-7 rounded-full bg-destructive/20 flex items-center justify-center">
          <AlertCircle className="w-4 h-4 text-destructive" />
        </div>
        <div className="bg-destructive/10 border border-destructive/30 rounded-2xl rounded-tl-sm px-4 py-3">
          <p className="text-sm text-destructive font-medium">Query failed</p>
          <p className="text-xs text-muted-foreground mt-1">
            No result available
          </p>
        </div>
      </div>
    );
  }

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
        <div className="bg-card border border-border rounded-2xl rounded-tl-sm px-4 py-3">
          <p className="text-sm font-medium text-foreground">
            {r.title || "Result"}
          </p>
          {r.description && (
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              {r.description}
            </p>
          )}
          {r.row_count !== undefined && r.row_count !== null && (
            <p className="text-xs text-muted-foreground mt-1">
              {r.row_count.toLocaleString()} rows
            </p>
          )}
        </div>

        {r.data && r.data.length > 0 && (
          <>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <ChartRenderer chart={nlqToChartSpec(r)} />
            </div>
            <button onClick={togglePin}
              className={`flex items-center gap-1.5 text-xs transition-colors px-1 py-0.5 rounded ${pinned ? 'text-yellow-400' : 'text-muted-foreground hover:text-yellow-400'}`}
              title={pinned ? 'Remove from Dashboard' : 'Pin to Dashboard'}>
              <Star className={`w-3.5 h-3.5 ${pinned ? 'fill-yellow-400' : ''}`} />
              {pinned ? 'Pinned to Dashboard' : 'Pin to Dashboard'}
            </button>
          </>
        )}

        {r.sql && (
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => setSqlOpen((v) => !v)}
              className="w-full flex items-center gap-2 px-4 py-2.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <Code2 className="w-3.5 h-3.5" />
              <span>SQL</span>
              {sqlOpen ? (
                <ChevronDown className="w-3 h-3 ml-auto" />
              ) : (
                <ChevronRight className="w-3 h-3 ml-auto" />
              )}
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
  return (
    <Suspense
      fallback={
        <div
          style={{
            height: "calc(100vh - 44px)",
            background: "var(--void)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div className="scan-loader" style={{ width: "200px" }} />
        </div>
      }
    >
      <QueryPageInner />
    </Suspense>
  );
}

function QueryPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { profile, profileDef } = useProfile();

  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [exploreMode, setExploreMode] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const saveTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Load sessions list ───────────────────────────────────────────────────

  const refreshSessions = useCallback(async () => {
    try {
      const list = await apiListSessions();
      setSessions(list);
    } catch {
      /* ignore */
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  // ── Hydrate from URL ?session= param ────────────────────────────────────

  useEffect(() => {
    const urlSession = searchParams.get("session");
    if (urlSession) {
      apiLoadSession(urlSession)
        .then((data) => {
          setSessionId(data.session_id);
          setMessages(data.messages.filter((m) => !m.loading));
        })
        .catch(() => {
          /* session not found, start fresh */
        });
    }
    void refreshSessions();
  }, [searchParams, refreshSessions]);

  // ── Scroll to bottom on new messages ────────────────────────────────────

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Auto-save session after each message ────────────────────────────────

  const persistSession = useCallback(
    (msgs: Message[], sid: string | null) => {
      if (saveTimeout.current) clearTimeout(saveTimeout.current);
      saveTimeout.current = setTimeout(async () => {
        try {
          const persistable = msgs.filter((m) => !m.loading);
          if (persistable.length === 0) return;
          const { session_id } = await apiSaveSession(sid, persistable);
          if (!sid) {
            // New session created — update URL without full navigation
            setSessionId(session_id);
            window.history.replaceState({}, "", `/query?session=${session_id}`);
            void refreshSessions();
          } else {
            // Update title in sidebar
            void refreshSessions();
          }
        } catch {
          /* non-critical */
        }
      }, 600);
    },
    [refreshSessions],
  );

  // ── Send question ────────────────────────────────────────────────────────

  async function sendQuestion(question: string) {
    if (!question.trim() || isLoading) return;

    const userMsg: Message = {
      id: uid(),
      role: "user",
      question: question.trim(),
      ts: new Date().toISOString(),
    };
    const pendingId = uid();
    const pendingMsg: Message = {
      id: pendingId,
      role: "assistant",
      loading: true,
      ts: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg, pendingMsg]);
    setInput("");
    setIsLoading(true);

    let nextMessages: Message[] = [];

    try {
      const res = await fetch(`${API_URL}/nlq/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          client_id: CLIENT_ID,
          user_role: profile,
          explore: exploreMode,
        }),
      });
      const result: NLQResult = await res.json();
      const doneMsg: Message = {
        id: pendingId,
        role: "assistant",
        question: question.trim(),
        result,
        ts: new Date().toISOString(),
      };

      setMessages((prev) => {
        nextMessages = prev.map((m) => (m.id === pendingId ? doneMsg : m));
        return nextMessages;
      });

      if (!result.error) setActiveHistoryId(pendingId);
    } catch (err) {
      const errMsg: Message = {
        id: pendingId,
        role: "assistant",
        question: question.trim(),
        result: {
          question: question.trim(),
          sql: null,
          chart_type: "table",
          title: "Error",
          x: "",
          y: "",
          description: "",
          data: [],
          columns: [],
          row_count: 0,
          error:
            err instanceof Error
              ? err.message
              : "Network error — is the backend running?",
        },
        ts: new Date().toISOString(),
      };
      setMessages((prev) => {
        nextMessages = prev.map((m) => (m.id === pendingId ? errMsg : m));
        return nextMessages;
      });
    } finally {
      setIsLoading(false);
      if (nextMessages.length > 0) persistSession(nextMessages, sessionId);
    }
  }

  // ── New chat ─────────────────────────────────────────────────────────────

  function startNewChat() {
    setMessages([]);
    setSessionId(null);
    setActiveHistoryId(null);
    window.history.replaceState({}, "", "/query");
  }

  // ── Load a session from the sidebar ─────────────────────────────────────

  async function openSession(sid: string) {
    if (sid === sessionId) return;
    try {
      const data = await apiLoadSession(sid);
      setSessionId(data.session_id);
      setMessages(data.messages.filter((m) => !m.loading));
      setActiveHistoryId(null);
      window.history.replaceState({}, "", `/query?session=${sid}`);
    } catch {
      /* ignore */
    }
  }

  // ── Delete session ───────────────────────────────────────────────────────

  async function deleteSession(e: React.MouseEvent, sid: string) {
    e.stopPropagation();
    await apiDeleteSession(sid);
    setSessions((prev) => prev.filter((s) => s.session_id !== sid));
    if (sid === sessionId) startNewChat();
  }

  // ── Share ────────────────────────────────────────────────────────────────

  async function shareSession() {
    let sid = sessionId;
    if (!sid) {
      // Save first if unsaved
      const persistable = messages.filter((m) => !m.loading);
      if (persistable.length === 0) return;
      const { session_id } = await apiSaveSession(null, persistable);
      sid = session_id;
      setSessionId(sid);
    }
    const url = `${window.location.origin}/query?session=${sid}`;
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  // ── Keyboard ─────────────────────────────────────────────────────────────

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendQuestion(input);
    }
  }

  // ── Derived state ────────────────────────────────────────────────────────

  const history = messages.filter(
    (m) => m.role === "assistant" && m.result && !m.result.error,
  );
  const activeMsg = activeHistoryId
    ? messages.find((m) => m.id === activeHistoryId)
    : null;
  const sqlMsg =
    activeMsg ??
    [...messages]
      .reverse()
      .find((m) => m.role === "assistant" && m.result?.sql);

  const suggestions = [
    "Which channel had the highest publish rate last month?",
    "Show me created vs published videos by language",
    "Top 10 users by output count",
    "Monthly trend of uploads over the last 6 months",
  ];

  return (
    <div
      className="flex overflow-hidden"
      style={{ height: "calc(100vh - 44px)", background: "var(--void)" }}
    >
      {/* ── LEFT PANEL ──────────────────────────────────────────────────── */}
      <aside
        className="w-72 shrink-0 flex flex-col overflow-hidden"
        style={{
          borderRight: "1px solid var(--wire)",
          background: "var(--surface)",
        }}
      >
        {/* Header */}
        <div className="px-4 py-3 border-b border-sidebar-border">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold text-sidebar-foreground">
                Sessions
              </h2>
            </div>
            <button
              onClick={startNewChat}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground border border-border hover:border-primary/50 rounded-lg px-2.5 py-1.5 transition-colors"
            >
              <Plus className="w-3 h-3" />
              New Chat
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            Click a session to restore it
          </p>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {sessionsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center text-muted-foreground text-xs py-8 px-4 leading-relaxed">
              Your chat sessions will appear here.
            </div>
          ) : (
            sessions.map((s) => (
              <SessionItem
                key={s.session_id}
                session={s}
                active={s.session_id === sessionId}
                onClick={() => void openSession(s.session_id)}
                onDelete={(e) => void deleteSession(e, s.session_id)}
              />
            ))
          )}
        </div>

        {/* SQL preview panel */}
        <div className="border-t border-sidebar-border">
          <div className="px-4 pt-3 pb-1 flex items-center gap-2">
            <Code2 className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              SQL Preview
            </span>
          </div>
          <div className="px-3 pb-4 max-h-52 overflow-y-auto">
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
        <div className="px-6 py-4 border-b border-border shrink-0 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-primary" />
              <h1 className="text-lg font-semibold text-foreground">
                Natural Language Query
              </h1>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Ask any question · {profileDef.displayName}
            </p>
          </div>

          {messages.length > 0 && (
            <button
              onClick={() => void shareSession()}
              className="flex items-center gap-2 text-xs border border-border hover:border-primary/50 rounded-lg px-3 py-2 text-muted-foreground hover:text-foreground transition-colors shrink-0"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-green-500" />
              ) : (
                <Share2 className="w-3.5 h-3.5" />
              )}
              {copied ? "Copied!" : "Share"}
            </button>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-8 text-center">
              <div>
                <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
                  <Sparkles className="w-8 h-8 text-primary" />
                </div>
                <h2 className="text-xl font-semibold text-foreground">
                  Ask your data anything
                </h2>
                <p className="text-sm text-muted-foreground mt-2 max-w-md">
                  Type a plain-English question. The AI generates SQL, runs it,
                  and renders the result as a chart.
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

          {messages.map((msg) =>
            msg.role === "user" ? (
              <UserBubble key={msg.id} text={msg.question!} />
            ) : (
              <AssistantBubble key={msg.id} msg={msg} />
            ),
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="px-6 pb-6 shrink-0">
          <div className="relative flex items-end gap-3 bg-card border border-border rounded-2xl px-4 py-3 focus-within:border-primary/60 transition-colors">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your data… (Enter to send, Shift+Enter for new line)"
              rows={1}
              className="flex-1 bg-transparent resize-none text-sm text-foreground placeholder:text-muted-foreground outline-none leading-relaxed max-h-40 overflow-y-auto"
              style={{ fieldSizing: "content" } as React.CSSProperties}
              disabled={isLoading}
            />
            <button
              onClick={() => setExploreMode((v) => !v)}
              title={
                exploreMode
                  ? "LIDA insights ON — click to disable"
                  : "Enable LIDA insights"
              }
              className={`shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-colors ${
                exploreMode
                  ? "bg-violet-600 hover:bg-violet-700"
                  : "bg-muted hover:bg-muted/80 border border-border"
              }`}
            >
              <FlaskConical
                className={`w-4 h-4 ${exploreMode ? "text-white" : "text-muted-foreground"}`}
              />
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
            {exploreMode && (
              <span className="text-violet-400 font-medium">
                LIDA insights enabled ·{" "}
              </span>
            )}
            Queries are executed read-only against your Frammer database.
          </p>
        </div>
      </main>
    </div>
  );
}
