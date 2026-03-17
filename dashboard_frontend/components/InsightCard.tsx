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
  high:   'border-l-4 border-l-[#C4553A]',
  medium: 'border-l-4 border-l-[#C68B2C]',
  low:    'border-l-4 border-l-[#5B7EA1]',
};

const SEVERITY_BADGE: Record<string, string> = {
  high:   'text-[#C4553A] bg-[rgba(196,85,58,0.08)]',
  medium: 'text-[#C68B2C] bg-[rgba(198,139,44,0.1)]',
  low:    'text-[#5B7EA1] bg-[rgba(91,126,161,0.1)]',
};

const CATEGORY_BADGE: Record<string, string> = {
  anomaly:    'text-[#8B6FA3] bg-[rgba(139,111,163,0.1)]',
  trend:      'text-[#5B7EA1] bg-[rgba(91,126,161,0.1)]',
  comparison: 'text-[#5B8A72] bg-[rgba(91,138,114,0.1)]',
  milestone:  'text-[#C68B2C] bg-[rgba(198,139,44,0.1)]',
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
      'inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full',
      isUp
        ? 'text-[#5B8A72] bg-[rgba(91,138,114,0.1)]'
        : 'text-[#C4553A] bg-[rgba(196,85,58,0.08)]'
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
      // silently ignore
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={cn(
      'rounded-2xl p-5 space-y-3 transition-all bg-white hover:shadow-md',
      SEVERITY_STYLES[card.severity],
      'border border-[#E5DFD7]',
    )}
    style={{ boxShadow: '0 2px 8px rgba(43, 35, 32, 0.06)' }}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn('inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full', CATEGORY_BADGE[card.category])}>
            <CategoryIcon className="w-3 h-3" />
            {card.category}
          </span>
          <span className={cn('text-xs font-semibold px-2.5 py-1 rounded-full uppercase tracking-wide', SEVERITY_BADGE[card.severity])}>
            {card.severity}
          </span>
        </div>
        <DeltaBadge delta_pct={card.delta_pct} />
      </div>

      {/* Title */}
      <p className="font-semibold text-sm leading-snug" style={{ color: 'var(--on)', fontFamily: 'var(--font-sans)' }}>
        {card.title}
      </p>

      {/* Body */}
      <p className="text-sm leading-relaxed" style={{ color: 'var(--on-mid)', fontFamily: 'var(--font-sans)' }}>
        {card.body}
      </p>

      {/* Metrics row */}
      <div className="flex gap-4 text-xs" style={{ color: 'var(--on-low)', fontFamily: 'var(--font-mono)' }}>
        <span>
          <span style={{ color: 'var(--on)', fontWeight: 600 }}>
            {typeof card.current_value === 'number' ? card.current_value.toFixed(2) : card.current_value}
          </span>{' '}current
        </span>
        <span>
          <span style={{ color: 'var(--on)', fontWeight: 600 }}>
            {typeof card.reference_value === 'number' ? card.reference_value.toFixed(2) : card.reference_value}
          </span>{' '}3m avg
        </span>
        <span className="ml-auto capitalize" style={{ color: 'var(--on-low)' }}>
          {card.entity_type}: {card.entity_id}
        </span>
      </div>

      {/* Root cause hint */}
      {card.root_cause_hint && (
        <p className="text-xs italic pt-2" style={{ color: 'var(--on-low)', borderTop: '1px solid var(--wire)', paddingTop: '8px', fontFamily: 'var(--font-sans)' }}>
          Possible cause: {card.root_cause_hint}
        </p>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-1">
        <span className="text-xs" style={{ color: 'var(--on-low)', fontFamily: 'var(--font-sans)' }}>
          {card.confidence === 'statistical' ? 'Statistically detected' : 'Pattern-inferred'}
          {' · '}{card.period}
        </span>
        {insightId && (
          <div className="flex gap-1">
            <button
              onClick={() => submitFeedback(1)}
              disabled={submitting || feedback !== null}
              className="p-1.5 rounded-lg transition-colors hover:bg-[rgba(91,138,114,0.1)]"
              style={{ color: feedback === 1 ? '#5B8A72' : 'var(--on-low)' }}
              aria-label="Helpful"
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => submitFeedback(-1)}
              disabled={submitting || feedback !== null}
              className="p-1.5 rounded-lg transition-colors hover:bg-[rgba(196,85,58,0.08)]"
              style={{ color: feedback === -1 ? '#C4553A' : 'var(--on-low)' }}
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
