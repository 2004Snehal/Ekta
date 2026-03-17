'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? 'http://localhost:8000';

const PRESETS = [
  {
    label: 'Channel Detail',
    payload: {
      client_id: 1, view: 'channel_detail', entity_type: 'channel',
      entity_id: 2, entity_name: 'CNN Hindi', metric_in_focus: 'publish_rate_pct',
      current_value: 21.9, time_range: null, user_role: 'ops_lead',
    },
  },
  {
    label: 'User Detail',
    payload: {
      client_id: 1, view: 'user_detail', entity_type: 'user',
      entity_id: 1, entity_name: 'Test User', metric_in_focus: 'published_count',
      current_value: 5, time_range: null, user_role: 'editor',
    },
  },
  {
    label: 'Content Mix',
    payload: {
      client_id: 1, view: 'content_mix', entity_type: 'input_type',
      entity_id: 1, entity_name: 'Interview', metric_in_focus: 'publish_rate_pct',
      current_value: 65.0, time_range: null, user_role: 'ops_lead',
    },
  },
  {
    label: 'Executive Summary',
    payload: {
      client_id: 1, view: 'executive_summary', entity_type: 'network',
      entity_id: null, entity_name: 'All Channels', metric_in_focus: 'publish_rate_pct',
      current_value: null, time_range: null, user_role: 'exec',
    },
  },
];

const PRIORITY_STYLES: Record<string, { border: string; bg: string }> = {
  high:   { border: 'rgba(196, 85, 58, 0.3)', bg: 'rgba(196, 85, 58, 0.04)' },
  medium: { border: 'rgba(198, 139, 44, 0.3)', bg: 'rgba(198, 139, 44, 0.04)' },
  low:    { border: 'rgba(91, 138, 114, 0.3)', bg: 'rgba(91, 138, 114, 0.04)' },
};

const PRIORITY_BADGE: Record<string, { color: string; bg: string }> = {
  high:   { color: 'var(--signal)', bg: 'rgba(196, 85, 58, 0.1)' },
  medium: { color: 'var(--warn)',   bg: 'rgba(198, 139, 44, 0.1)' },
  low:    { color: 'var(--ok)',     bg: 'rgba(91, 138, 114, 0.1)' },
};

type Rec = {
  title: string;
  action: string;
  rationale: string;
  priority: string;
  scope: string;
  supporting_metrics: Record<string, unknown>;
};

type RecResponse = {
  recommendations: Rec[];
  context_view: string;
  entity_name: string;
  generated_at: string;
  cached: boolean;
};

export default function RecommendationsPage() {
  const [payload, setPayload] = useState(JSON.stringify(PRESETS[0].payload, null, 2));
  const [result, setResult] = useState<RecResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const body = JSON.parse(payload);
      const res = await fetch(`${API}/recommendations/contextual`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`${res.status} — ${text}`);
      }
      setResult(await res.json() as RecResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--void)', padding: '32px' }}>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.8rem', fontWeight: 700, color: 'var(--on)', marginBottom: '6px' }}>
        Recommendation Agent
      </h1>
      <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-mid)', marginBottom: '28px', lineHeight: 1.6 }}>
        Test the context-aware recommendation engine. Pick a preset or edit the payload manually.
      </p>

      {/* Presets */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '20px' }}>
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => setPayload(JSON.stringify(p.payload, null, 2))}
            style={{
              padding: '6px 16px',
              borderRadius: '20px',
              border: '1.5px solid var(--wire)',
              background: 'var(--surface)',
              fontFamily: 'var(--font-sans)',
              fontSize: '0.8rem',
              fontWeight: 600,
              color: 'var(--on-mid)',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = 'rgba(196, 85, 58, 0.4)';
              (e.currentTarget as HTMLElement).style.color = 'var(--on)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = 'var(--wire)';
              (e.currentTarget as HTMLElement).style.color = 'var(--on-mid)';
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Payload editor */}
      <div style={{ marginBottom: '16px' }}>
        <label style={{ fontFamily: 'var(--font-sans)', fontSize: '0.7rem', fontWeight: 700, color: 'var(--on-low)', letterSpacing: '0.08em', textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>
          Request payload (JSON)
        </label>
        <textarea
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
          rows={14}
          style={{
            width: '100%', fontFamily: 'var(--font-mono)', fontSize: '0.82rem',
            background: 'var(--surface)', border: '1.5px solid var(--wire)',
            borderRadius: '14px', padding: '16px', color: 'var(--on)',
            outline: 'none', resize: 'vertical',
            transition: 'border-color 0.2s', lineHeight: 1.6,
          }}
          onFocus={(e) => { (e.target as HTMLElement).style.borderColor = 'rgba(196, 85, 58, 0.5)'; }}
          onBlur={(e) => { (e.target as HTMLElement).style.borderColor = 'var(--wire)'; }}
        />
      </div>

      <button
        onClick={() => void run()}
        disabled={loading}
        style={{
          display: 'flex', alignItems: 'center', gap: '10px',
          padding: '11px 24px', borderRadius: '12px',
          border: 'none', background: 'var(--signal)', color: '#fff',
          fontFamily: 'var(--font-sans)', fontSize: '0.88rem', fontWeight: 700,
          cursor: loading ? 'not-allowed' : 'pointer',
          opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s', marginBottom: '32px',
          boxShadow: '0 4px 14px rgba(196, 85, 58, 0.25)',
        }}
      >
        {loading && <Loader2 style={{ width: '16px', height: '16px', animation: 'spin 1s linear infinite' }} />}
        {loading ? 'Calling agent…' : 'Get Recommendations'}
      </button>

      {/* Error */}
      {error && (
        <div style={{
          borderRadius: '12px', border: '1px solid rgba(196, 85, 58, 0.3)',
          background: 'rgba(196, 85, 58, 0.06)', padding: '14px 18px',
          color: 'var(--signal)', fontFamily: 'var(--font-sans)', fontSize: '0.85rem',
          marginBottom: '24px',
        }}>
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px', flexWrap: 'wrap' }}>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: '1rem', fontWeight: 700, color: 'var(--on)' }}>
              {result.entity_name}
            </span>
            <span style={{ color: 'var(--on-low)', fontSize: '0.7rem' }}>·</span>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.82rem', color: 'var(--on-mid)' }}>{result.context_view}</span>
            <span style={{ color: 'var(--on-low)', fontSize: '0.7rem' }}>·</span>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.82rem', color: 'var(--on-mid)' }}>{result.recommendations.length} recommendations</span>
            {result.cached && (
              <span style={{ padding: '2px 10px', borderRadius: '20px', background: 'var(--surface-raise)', fontFamily: 'var(--font-sans)', fontSize: '0.72rem', color: 'var(--on-low)' }}>
                cached
              </span>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {result.recommendations.map((rec, i) => {
              const style = PRIORITY_STYLES[rec.priority] ?? { border: 'var(--wire)', bg: 'var(--surface)' };
              const badge = PRIORITY_BADGE[rec.priority] ?? { color: 'var(--on-low)', bg: 'var(--surface-raise)' };
              return (
                <div
                  key={i}
                  style={{
                    borderRadius: '16px',
                    border: `1px solid ${style.border}`,
                    background: style.bg,
                    padding: '20px 24px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px', marginBottom: '10px' }}>
                    <span style={{ fontFamily: 'var(--font-display)', fontSize: '1rem', fontWeight: 700, color: 'var(--on)', lineHeight: 1.35 }}>
                      {rec.title}
                    </span>
                    <span style={{
                      flexShrink: 0, fontFamily: 'var(--font-sans)', fontSize: '0.7rem', fontWeight: 700,
                      letterSpacing: '0.06em', textTransform: 'uppercase',
                      color: badge.color, background: badge.bg,
                      padding: '3px 10px', borderRadius: '20px',
                    }}>
                      {rec.priority}
                    </span>
                  </div>

                  <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', fontWeight: 600, color: 'var(--signal)', marginBottom: '8px' }}>
                    → {rec.action}
                  </p>
                  <p style={{ fontFamily: 'var(--font-sans)', fontSize: '0.85rem', color: 'var(--on-mid)', lineHeight: 1.6, marginBottom: '14px' }}>
                    {rec.rationale}
                  </p>

                  {Object.keys(rec.supporting_metrics).length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                      {Object.entries(rec.supporting_metrics).map(([k, v]) => (
                        <span key={k} style={{
                          fontFamily: 'var(--font-mono)', fontSize: '0.72rem',
                          background: 'var(--surface)', border: '1px solid var(--wire)',
                          borderRadius: '8px', padding: '3px 10px', color: 'var(--on-mid)',
                        }}>
                          {k}: <span style={{ color: 'var(--on)', fontWeight: 600 }}>{String(v)}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
