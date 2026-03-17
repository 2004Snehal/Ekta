'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useProfile } from '@/lib/profiles';
import { ChartRenderer } from '@/components/ChartRenderer';
import {
  Send, Code2, Clock, AlertCircle, Loader2,
  ChevronDown, ChevronRight, Sparkles, Plus, Share2, Trash2, Check,
} from 'lucide-react';
import type { UniversalChartSpec } from '@/types/chart';

const API_URL   = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
const CLIENT_ID = 1;
const USER_ID   = 'default-user';

interface NLQResult {
  question:    string;
  sql:         string | null;
  chart_type:  string;
  title:       string;
  x:           string;
  y:           string;
  description: string;
  data:        Record<string, unknown>[];
  columns:     string[];
  row_count:   number;
  error?:      string;
}

interface Message {
  id:        string;
  role:      'user' | 'assistant';
  question?: string;
  result?:   NLQResult;
  loading?:  boolean;
  ts:        string;
}

interface SessionSummary {
  session_id:   string;
  title:        string;
  messageCount: number;
  updatedAt:    string | null;
}

function nlqToChartSpec(r: NLQResult): UniversalChartSpec {
  return { chart_type: r.chart_type as UniversalChartSpec['chart_type'], title: r.title, description: r.description, x: r.x, y: r.y, data: r.data };
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDate(iso: string | null) {
  if (!iso) return '';
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return 'Today';
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function uid() { return Math.random().toString(36).slice(2); }

async function apiSaveSession(sessionId: string | null, messages: Message[], title?: string) {
  const res = await fetch(`${API_URL}/nlq/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sessionId, userId: USER_ID, title, messages }),
  });
  if (!res.ok) throw new Error('Failed to save session');
  return (await res.json()) as { session_id: string };
}

async function apiLoadSession(sessionId: string) {
  const res = await fetch(`${API_URL}/nlq/sessions/${sessionId}`);
  if (!res.ok) throw new Error('Session not found');
  return res.json() as Promise<{ session_id: string; title: string; messages: Message[] }>;
}

async function apiListSessions() {
  const res = await fetch(`${API_URL}/nlq/sessions?user_id=${USER_ID}`);
  if (!res.ok) return [];
  return res.json() as Promise<SessionSummary[]>;
}

async function apiDeleteSession(sessionId: string) {
  await fetch(`${API_URL}/nlq/sessions/${sessionId}`, { method: 'DELETE' });
}

function SqlBlock({ sql }: { sql: string }) {
  return (
    <pre style={{
      fontFamily: 'var(--font-mono)',
      fontSize: '0.72rem',
      color: '#5B8A72',
      background: 'var(--surface-hi)',
      borderRadius: '10px',
      padding: '14px 16px',
      overflowX: 'auto',
      whiteSpace: 'pre-wrap',
      lineHeight: 1.6,
      border: '1px solid var(--wire)',
    }}>
      {sql}
    </pre>
  );
}

function SessionItem({
  session, active, onClick, onDelete,
}: {
  session: SessionSummary;
  active: boolean;
  onClick: () => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        width: '100%',
        textAlign: 'left',
        borderRadius: '10px',
        padding: '10px 12px',
        transition: 'background 0.15s',
        position: 'relative',
        background: active ? 'rgba(196, 85, 58, 0.08)' : 'transparent',
        border: active ? '1px solid rgba(196, 85, 58, 0.25)' : '1px solid transparent',
        cursor: 'pointer',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', paddingRight: '24px' }}>
        <div style={{
          marginTop: '4px', flexShrink: 0, width: '7px', height: '7px', borderRadius: '50%',
          background: active ? 'var(--signal)' : 'var(--wire-mid)',
        }} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.82rem', color: 'var(--on)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: '2px' }}>
            {session.title}
          </p>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', color: 'var(--on-low)' }}>
            {formatDate(session.updatedAt)} · {session.messageCount} msgs
          </p>
        </div>
      </div>
      <button
        onClick={onDelete}
        style={{
          position: 'absolute', right: '8px', top: '50%', transform: 'translateY(-50%)',
          opacity: 0, background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--on-low)', padding: '4px', borderRadius: '6px',
          transition: 'all 0.15s',
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.opacity = '1'; (e.currentTarget as HTMLElement).style.color = 'var(--signal)'; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.opacity = '0'; }}
      >
        <Trash2 style={{ width: '12px', height: '12px' }} />
      </button>
    </button>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
      <div style={{
        maxWidth: '70%',
        borderRadius: '18px 18px 4px 18px',
        background: 'var(--signal)',
        padding: '10px 16px',
      }}>
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: '#fff', lineHeight: 1.5 }}>
          {text}
        </p>
      </div>
    </div>
  );
}

function AssistantBubble({ msg }: { msg: Message }) {
  const [sqlOpen, setSqlOpen] = useState(false);

  if (msg.loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: 'var(--on-low)', padding: '8px 0' }}>
        <Loader2 style={{ width: '16px', height: '16px', animation: 'spin 1s linear infinite', color: 'var(--signal)' }} />
        <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem' }}>Thinking…</span>
      </div>
    );
  }

  const r = msg.result!;

  if (r.error) {
    return (
      <div style={{ display: 'flex', gap: '12px', maxWidth: '85%' }}>
        <div style={{
          flexShrink: 0, marginTop: '2px', width: '28px', height: '28px',
          borderRadius: '50%', background: 'rgba(196, 85, 58, 0.1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <AlertCircle style={{ width: '14px', height: '14px', color: 'var(--signal)' }} />
        </div>
        <div style={{
          background: 'rgba(196, 85, 58, 0.06)',
          border: '1px solid rgba(196, 85, 58, 0.2)',
          borderRadius: '18px 18px 18px 4px',
          padding: '12px 16px',
        }}>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', fontWeight: 600, color: 'var(--signal)', marginBottom: '4px' }}>Query failed</p>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-mid)' }}>{r.error}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', gap: '12px', maxWidth: '90%' }}>
      <div style={{
        flexShrink: 0, marginTop: '2px', width: '28px', height: '28px',
        borderRadius: '50%', background: 'var(--signal-dim)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Sparkles style={{ width: '13px', height: '13px', color: 'var(--signal)' }} />
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--wire)',
          borderRadius: '18px 18px 18px 4px',
          padding: '12px 16px',
          boxShadow: '0 2px 8px rgba(43, 35, 32, 0.06)',
        }}>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.88rem', fontWeight: 600, color: 'var(--on)', marginBottom: '4px' }}>{r.title || 'Result'}</p>
          {r.description && <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-mid)', lineHeight: 1.5, marginBottom: '4px' }}>{r.description}</p>}
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--on-low)' }}>{r.row_count.toLocaleString()} rows</p>
        </div>

        {r.data.length > 0 && (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--wire)', borderRadius: '14px', overflow: 'hidden', boxShadow: '0 2px 8px rgba(43, 35, 32, 0.06)' }}>
            <ChartRenderer chart={nlqToChartSpec(r)} />
          </div>
        )}

        {r.sql && (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--wire)', borderRadius: '14px', overflow: 'hidden' }}>
            <button
              onClick={() => setSqlOpen((v) => !v)}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: '8px',
                padding: '10px 16px', background: 'none', border: 'none', cursor: 'pointer',
                fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-low)',
                transition: 'color 0.2s',
              }}
            >
              <Code2 style={{ width: '13px', height: '13px' }} />
              <span>View SQL</span>
              {sqlOpen
                ? <ChevronDown style={{ width: '12px', height: '12px', marginLeft: 'auto' }} />
                : <ChevronRight style={{ width: '12px', height: '12px', marginLeft: 'auto' }} />}
            </button>
            {sqlOpen && <div style={{ padding: '0 14px 14px' }}><SqlBlock sql={r.sql} /></div>}
          </div>
        )}
      </div>
    </div>
  );
}

export default function QueryPage() {
  return (
    <Suspense fallback={
      <div style={{ height: 'calc(100vh - 56px)', background: 'var(--void)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="scan-loader" style={{ width: '200px' }} />
      </div>
    }>
      <QueryPageInner />
    </Suspense>
  );
}

function QueryPageInner() {
  const router       = useRouter();
  const searchParams = useSearchParams();
  const { profile, profileDef } = useProfile();

  const [messages,        setMessages]        = useState<Message[]>([]);
  const [sessionId,       setSessionId]       = useState<string | null>(null);
  const [sessions,        setSessions]        = useState<SessionSummary[]>([]);
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);
  const [input,           setInput]           = useState('');
  const [isLoading,       setIsLoading]       = useState(false);
  const [copied,          setCopied]          = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(true);

  const bottomRef   = useRef<HTMLDivElement>(null);
  const saveTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshSessions = useCallback(async () => {
    try {
      const list = await apiListSessions();
      setSessions(list);
    } catch { /* ignore */ } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    const urlSession = searchParams.get('session');
    if (urlSession) {
      apiLoadSession(urlSession)
        .then((data) => {
          setSessionId(data.session_id);
          setMessages(data.messages.filter((m) => !m.loading));
        })
        .catch(() => {});
    }
    void refreshSessions();
  }, [searchParams, refreshSessions]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const persistSession = useCallback((msgs: Message[], sid: string | null) => {
    if (saveTimeout.current) clearTimeout(saveTimeout.current);
    saveTimeout.current = setTimeout(async () => {
      try {
        const persistable = msgs.filter((m) => !m.loading);
        if (persistable.length === 0) return;
        const { session_id } = await apiSaveSession(sid, persistable);
        if (!sid) {
          setSessionId(session_id);
          window.history.replaceState({}, '', `/query?session=${session_id}`);
          void refreshSessions();
        } else {
          void refreshSessions();
        }
      } catch { /* non-critical */ }
    }, 600);
  }, [refreshSessions]);

  async function sendQuestion(question: string) {
    if (!question.trim() || isLoading) return;

    const userMsg: Message    = { id: uid(), role: 'user', question: question.trim(), ts: new Date().toISOString() };
    const pendingId           = uid();
    const pendingMsg: Message = { id: pendingId, role: 'assistant', loading: true, ts: new Date().toISOString() };

    setMessages((prev) => [...prev, userMsg, pendingMsg]);
    setInput('');
    setIsLoading(true);

    let nextMessages: Message[] = [];

    try {
      const res    = await fetch(`${API_URL}/nlq/query`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ question: question.trim(), client_id: CLIENT_ID, profile }),
      });
      const result: NLQResult = await res.json();
      const doneMsg: Message  = { id: pendingId, role: 'assistant', question: question.trim(), result, ts: new Date().toISOString() };

      setMessages((prev) => {
        nextMessages = prev.map((m) => (m.id === pendingId ? doneMsg : m));
        return nextMessages;
      });

      if (!result.error) setActiveHistoryId(pendingId);
    } catch (err) {
      const errMsg: Message = {
        id: pendingId, role: 'assistant', question: question.trim(),
        result: {
          question: question.trim(), sql: null, chart_type: 'table', title: 'Error',
          x: '', y: '', description: '', data: [], columns: [], row_count: 0,
          error: err instanceof Error ? err.message : 'Network error — is the backend running?',
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

  function startNewChat() {
    setMessages([]);
    setSessionId(null);
    setActiveHistoryId(null);
    window.history.replaceState({}, '', '/query');
  }

  async function openSession(sid: string) {
    if (sid === sessionId) return;
    try {
      const data = await apiLoadSession(sid);
      setSessionId(data.session_id);
      setMessages(data.messages.filter((m) => !m.loading));
      setActiveHistoryId(null);
      window.history.replaceState({}, '', `/query?session=${sid}`);
    } catch { /* ignore */ }
  }

  async function deleteSession(e: React.MouseEvent, sid: string) {
    e.stopPropagation();
    await apiDeleteSession(sid);
    setSessions((prev) => prev.filter((s) => s.session_id !== sid));
    if (sid === sessionId) startNewChat();
  }

  async function shareSession() {
    let sid = sessionId;
    if (!sid) {
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

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendQuestion(input); }
  }

  const sqlMsg = activeHistoryId
    ? messages.find((m) => m.id === activeHistoryId)
    : [...messages].reverse().find((m) => m.role === 'assistant' && m.result?.sql);

  const suggestions = [
    'Which channel had the highest publish rate last month?',
    'Show me created vs published videos by language',
    'Top 10 users by output count',
    'Monthly trend of uploads over the last 6 months',
  ];

  return (
    <div style={{ display: 'flex', overflow: 'hidden', height: 'calc(100vh - 56px)', background: 'var(--void)' }}>

      {/* LEFT PANEL */}
      <aside style={{ width: '280px', flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', borderRight: '1px solid var(--wire)', background: 'var(--surface)' }}>

        {/* Header */}
        <div style={{ padding: '16px', borderBottom: '1px solid var(--wire)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Clock style={{ width: '14px', height: '14px', color: 'var(--on-low)' }} />
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', fontWeight: 700, color: 'var(--on)' }}>Sessions</span>
            </div>
            <button
              onClick={startNewChat}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                fontSize: '0.72rem', fontFamily: 'var(--font-sans)', fontWeight: 600,
                color: 'var(--on-mid)', background: 'var(--surface-hi)',
                border: '1px solid var(--wire)', borderRadius: '8px',
                padding: '5px 10px', cursor: 'pointer', transition: 'all 0.2s',
              }}
            >
              <Plus style={{ width: '11px', height: '11px' }} />
              New
            </button>
          </div>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.72rem', color: 'var(--on-low)' }}>
            Click a session to restore it
          </p>
        </div>

        {/* Session list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
          {sessionsLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px 0' }}>
              <Loader2 style={{ width: '16px', height: '16px', animation: 'spin 1s linear infinite', color: 'var(--on-low)' }} />
            </div>
          ) : sessions.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--on-low)', fontSize: '0.78rem', padding: '32px 16px', fontFamily: 'var(--font-sans)', lineHeight: 1.6 }}>
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
        <div style={{ borderTop: '1px solid var(--wire)' }}>
          <div style={{ padding: '12px 16px 6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Code2 style={{ width: '13px', height: '13px', color: 'var(--on-low)' }} />
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.65rem', fontWeight: 700, color: 'var(--on-low)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              SQL Preview
            </span>
          </div>
          <div style={{ padding: '0 12px 16px', maxHeight: '200px', overflowY: 'auto' }}>
            {sqlMsg?.result?.sql ? (
              <SqlBlock sql={sqlMsg.result.sql} />
            ) : (
              <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-low)', fontStyle: 'italic', padding: '4px 4px' }}>
                No query selected yet.
              </p>
            )}
          </div>
        </div>
      </aside>

      {/* RIGHT PANEL */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--void)' }}>

        {/* Top bar */}
        <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--wire)', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--surface)' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '2px' }}>
              <Sparkles style={{ width: '18px', height: '18px', color: 'var(--signal)' }} />
              <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.15rem', fontWeight: 700, color: 'var(--on)' }}>
                Natural Language Query
              </h1>
            </div>
            <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.78rem', color: 'var(--on-low)' }}>
              Ask any question · {profileDef.displayName}
            </p>
          </div>

          {messages.length > 0 && (
            <button
              onClick={() => void shareSession()}
              style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                padding: '7px 14px', borderRadius: '10px',
                border: '1px solid var(--wire)', background: 'var(--surface)',
                color: 'var(--on-mid)', fontFamily: 'var(--font-sans)',
                fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer',
                transition: 'all 0.2s', flexShrink: 0,
              }}
            >
              {copied
                ? <Check style={{ width: '13px', height: '13px', color: 'var(--ok)' }} />
                : <Share2 style={{ width: '13px', height: '13px' }} />}
              {copied ? 'Copied!' : 'Share'}
            </button>
          )}
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {messages.length === 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '32px', textAlign: 'center' }}>
              <div>
                <div style={{
                  width: '64px', height: '64px', borderRadius: '20px',
                  background: 'var(--signal-dim)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  margin: '0 auto 16px',
                }}>
                  <Sparkles style={{ width: '28px', height: '28px', color: 'var(--signal)' }} />
                </div>
                <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 700, color: 'var(--on)', marginBottom: '8px' }}>
                  Ask your data anything
                </h2>
                <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.88rem', color: 'var(--on-mid)', maxWidth: '420px', lineHeight: 1.6 }}>
                  Type a plain-English question. The AI generates SQL, runs it, and renders the result as a chart.
                </p>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', width: '100%', maxWidth: '560px' }}>
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => void sendQuestion(s)}
                    style={{
                      textAlign: 'left', borderRadius: '14px',
                      border: '1.5px solid var(--wire)', background: 'var(--surface)',
                      padding: '14px 16px',
                      fontFamily: 'var(--font-sans)', fontSize: '0.82rem',
                      color: 'var(--on-mid)', cursor: 'pointer',
                      transition: 'all 0.2s', lineHeight: 1.45,
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.borderColor = 'rgba(196, 85, 58, 0.4)';
                      (e.currentTarget as HTMLElement).style.color = 'var(--on)';
                      (e.currentTarget as HTMLElement).style.background = 'var(--surface-hi)';
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.borderColor = 'var(--wire)';
                      (e.currentTarget as HTMLElement).style.color = 'var(--on-mid)';
                      (e.currentTarget as HTMLElement).style.background = 'var(--surface)';
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

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
        <div style={{ padding: '16px 24px', flexShrink: 0 }}>
          <div style={{
            position: 'relative', display: 'flex', alignItems: 'flex-end', gap: '12px',
            background: 'var(--surface)', border: '1.5px solid var(--wire)',
            borderRadius: '16px', padding: '12px 14px',
            boxShadow: '0 2px 12px rgba(43, 35, 32, 0.06)',
            transition: 'border-color 0.2s',
          }}
          onFocusCapture={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(196, 85, 58, 0.5)'; }}
          onBlurCapture={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--wire)'; }}
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your data… (Enter to send, Shift+Enter for new line)"
              rows={1}
              style={{
                flex: 1, background: 'transparent', resize: 'none',
                fontFamily: 'var(--font-sans)', fontSize: '0.88rem', color: 'var(--on)',
                border: 'none', outline: 'none', lineHeight: 1.5,
                maxHeight: '160px', overflowY: 'auto',
              }}
              disabled={isLoading}
            />
            <button
              onClick={() => void sendQuestion(input)}
              disabled={!input.trim() || isLoading}
              style={{
                flexShrink: 0, width: '36px', height: '36px', borderRadius: '10px',
                background: input.trim() && !isLoading ? 'var(--signal)' : 'var(--surface-raise)',
                border: 'none', cursor: input.trim() && !isLoading ? 'pointer' : 'not-allowed',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.2s', opacity: !input.trim() || isLoading ? 0.5 : 1,
              }}
            >
              {isLoading
                ? <Loader2 style={{ width: '14px', height: '14px', color: '#fff', animation: 'spin 1s linear infinite' }} />
                : <Send style={{ width: '14px', height: '14px', color: input.trim() ? '#fff' : 'var(--on-low)' }} />}
            </button>
          </div>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', color: 'var(--on-low)', textAlign: 'center', marginTop: '8px' }}>
            Queries are executed read-only against your Frammer database.
          </p>
        </div>
      </main>
    </div>
  );
}
