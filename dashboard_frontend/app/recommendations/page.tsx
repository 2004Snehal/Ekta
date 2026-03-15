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

const PRIORITY_COLOR: Record<string, string> = {
  high:   'border-red-500/40 bg-red-500/5',
  medium: 'border-yellow-500/40 bg-yellow-500/5',
  low:    'border-green-500/40 bg-green-500/5',
};

const PRIORITY_BADGE: Record<string, string> = {
  high:   'bg-red-500/20 text-red-400',
  medium: 'bg-yellow-500/20 text-yellow-400',
  low:    'bg-green-500/20 text-green-400',
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
    <div className="p-8 min-h-screen">
      <h1 className="text-3xl font-bold mb-1">Recommendation Agent</h1>
      <p className="text-muted-foreground mb-6 text-sm">
        Test the context-aware recommendation engine. Pick a preset or edit the payload manually.
      </p>

      {/* Presets */}
      <div className="flex flex-wrap gap-2 mb-4">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => setPayload(JSON.stringify(p.payload, null, 2))}
            className="px-3 py-1.5 rounded-full border border-border text-sm hover:border-primary/60 hover:text-foreground transition-colors text-muted-foreground"
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Payload editor */}
      <div className="mb-4">
        <label className="text-xs text-muted-foreground uppercase tracking-wider mb-1 block">
          Request payload (JSON)
        </label>
        <textarea
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
          rows={14}
          className="w-full font-mono text-sm bg-card border border-border rounded-lg p-4 text-foreground focus:outline-none focus:border-primary/60 resize-y"
        />
      </div>

      <button
        onClick={() => void run()}
        disabled={loading}
        className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90 disabled:opacity-50 transition-opacity mb-8"
      >
        {loading && <Loader2 className="w-4 h-4 animate-spin" />}
        {loading ? 'Calling agent…' : 'Get Recommendations'}
      </button>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-400 text-sm mb-6">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div>
          <div className="flex items-center gap-3 mb-4 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{result.entity_name}</span>
            <span>·</span>
            <span>{result.context_view}</span>
            <span>·</span>
            <span>{result.recommendations.length} recommendations</span>
            {result.cached && (
              <span className="px-2 py-0.5 rounded-full bg-muted text-muted-foreground text-xs">cached</span>
            )}
          </div>

          <div className="flex flex-col gap-4">
            {result.recommendations.map((rec, i) => (
              <div
                key={i}
                className={`rounded-lg border p-5 ${PRIORITY_COLOR[rec.priority] ?? 'border-border'}`}
              >
                <div className="flex items-start justify-between gap-3 mb-2">
                  <span className="font-semibold text-foreground">{rec.title}</span>
                  <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${PRIORITY_BADGE[rec.priority] ?? ''}`}>
                    {rec.priority}
                  </span>
                </div>

                <p className="text-sm text-primary font-medium mb-2">→ {rec.action}</p>
                <p className="text-sm text-muted-foreground mb-3">{rec.rationale}</p>

                {Object.keys(rec.supporting_metrics).length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(rec.supporting_metrics).map(([k, v]) => (
                      <span key={k} className="text-xs bg-muted rounded px-2 py-1 text-muted-foreground">
                        {k}: <span className="text-foreground">{String(v)}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
