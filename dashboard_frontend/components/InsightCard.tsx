'use client';

import { useState } from 'react';
import { ThumbsUp, ThumbsDown, TrendingUp, TrendingDown, AlertTriangle, GitCompare, Flag } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface InsightCardData {
  id: string;
  title: string;
  body: string;
  category: 'anomaly' | 'trend' | 'comparison' | 'milestone';
  severity: 'high' | 'medium' | 'low';
  metric_name: string;
  entity_type: 'channel' | 'user' | 'language' | 'input_type';
  entity_id: string;
  current_value: number;
  reference_value: number;
  delta_pct: number;
  period: string;
  confidence: 'statistical' | 'contextual';
  root_cause_hint?: string | null;
}

interface InsightCardProps {
  card: InsightCardData;
  insightId?: number;
  apiBaseUrl?: string;
}

const SEVERITY_STYLES = {
  high:   'border-l-4 border-l-red-500   bg-red-950/20',
  medium: 'border-l-4 border-l-amber-500 bg-amber-950/20',
  low:    'border-l-4 border-l-blue-500  bg-blue-950/20',
};

const SEVERITY_BADGE = {
  high:   'bg-red-500/20   text-red-400   border border-red-500/30',
  medium: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  low:    'bg-blue-500/20  text-blue-400  border border-blue-500/30',
};

const CATEGORY_BADGE = {
  anomaly:    'bg-purple-500/20 text-purple-300 border border-purple-500/30',
  trend:      'bg-cyan-500/20   text-cyan-300   border border-cyan-500/30',
  comparison: 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30',
  milestone:  'bg-green-500/20  text-green-300  border border-green-500/30',
};

const CATEGORY_ICON = {
  anomaly:    AlertTriangle,
  trend:      TrendingUp,
  comparison: GitCompare,
  milestone:  Flag,
};

function DeltaBadge({ delta_pct }: { delta_pct: number }) {
  const isUp = delta_pct > 0;
  const Icon = isUp ? TrendingUp : TrendingDown;
  return (
    <span className={cn(
      'inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full',
      isUp
        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
        : 'bg-red-500/20 text-red-400 border border-red-500/30'
    )}>
      <Icon className="w-3 h-3" />
      {isUp ? '+' : ''}{delta_pct.toFixed(1)}%
    </span>
  );
}

export function InsightCard({ card, insightId, apiBaseUrl = '' }: InsightCardProps) {
  const [feedback, setFeedback] = useState<1 | -1 | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const CategoryIcon = CATEGORY_ICON[card.category];

  async function submitFeedback(value: 1 | -1) {
    if (feedback !== null || !insightId) return;
    setSubmitting(true);
    try {
      await fetch(
        `${apiBaseUrl}/narrator/feedback?insight_id=${insightId}&feedback=${value}`,
        { method: 'POST' },
      );
      setFeedback(value);
    } catch {
      // silently ignore — feedback is best-effort
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={cn(
      'rounded-lg p-4 space-y-3 transition-all',
      SEVERITY_STYLES[card.severity],
      'border border-border/40 hover:border-border/80',
    )}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn('inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full', CATEGORY_BADGE[card.category])}>
            <CategoryIcon className="w-3 h-3" />
            {card.category}
          </span>
          <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide', SEVERITY_BADGE[card.severity])}>
            {card.severity}
          </span>
        </div>
        <DeltaBadge delta_pct={card.delta_pct} />
      </div>

      {/* Title */}
      <p className="font-semibold text-foreground text-sm leading-snug">{card.title}</p>

      {/* Body */}
      <p className="text-muted-foreground text-sm leading-relaxed">{card.body}</p>

      {/* Metrics row */}
      <div className="flex gap-4 text-xs text-muted-foreground">
        <span>
          <span className="text-foreground font-medium">
            {typeof card.current_value === 'number' ? card.current_value.toFixed(2) : card.current_value}
          </span>{' '}current
        </span>
        <span>
          <span className="text-foreground font-medium">
            {typeof card.reference_value === 'number' ? card.reference_value.toFixed(2) : card.reference_value}
          </span>{' '}3m avg
        </span>
        <span className="ml-auto capitalize text-muted-foreground/60">
          {card.entity_type}: {card.entity_id}
        </span>
      </div>

      {/* Root cause hint */}
      {card.root_cause_hint && (
        <p className="text-xs text-muted-foreground/80 italic border-t border-border/30 pt-2">
          Possible cause: {card.root_cause_hint}
        </p>
      )}

      {/* Footer: confidence + feedback */}
      <div className="flex items-center justify-between pt-1">
        <span className="text-xs text-muted-foreground/60">
          {card.confidence === 'statistical' ? 'Statistically detected' : 'Pattern-inferred'}
          {' · '}{card.period}
        </span>
        {insightId && (
          <div className="flex gap-1">
            <button
              onClick={() => submitFeedback(1)}
              disabled={submitting || feedback !== null}
              className={cn(
                'p-1 rounded transition-colors',
                feedback === 1
                  ? 'text-emerald-400'
                  : 'text-muted-foreground/40 hover:text-emerald-400',
              )}
              aria-label="Helpful"
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => submitFeedback(-1)}
              disabled={submitting || feedback !== null}
              className={cn(
                'p-1 rounded transition-colors',
                feedback === -1
                  ? 'text-red-400'
                  : 'text-muted-foreground/40 hover:text-red-400',
              )}
              aria-label="Not helpful"
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
