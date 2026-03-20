'use client';

import { useState } from 'react';
import {
  ThumbsUp, ThumbsDown, TrendingUp, TrendingDown,
  AlertTriangle, GitCompare, Flag, Activity, Database,
  ExternalLink, ChevronDown, ChevronUp,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { InsightCardData, InsightStatus } from '@/types/narrator';

interface InsightCardV2Props {
  card: InsightCardData;
  apiBaseUrl?: string;
  compact?: boolean;
}

const SEVERITY_STYLES: Record<string, string> = {
  high:   'border-l-4 border-l-red-500   bg-red-950/20',
  medium: 'border-l-4 border-l-amber-500 bg-amber-950/20',
  low:    'border-l-4 border-l-blue-500  bg-blue-950/20',
};

const SEVERITY_BADGE: Record<string, string> = {
  high:   'bg-red-500/20   text-red-400   border border-red-500/30',
  medium: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  low:    'bg-blue-500/20  text-blue-400  border border-blue-500/30',
};

const STATUS_BADGE: Record<InsightStatus, { label: string; cls: string }> = {
  new:       { label: 'NEW',       cls: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' },
  ongoing:   { label: 'ONGOING',   cls: 'bg-amber-500/20 text-amber-400 border-amber-500/30' },
  worsening: { label: 'WORSENING', cls: 'bg-red-500/20 text-red-400 border-red-500/30' },
  resolved:  { label: 'RESOLVED',  cls: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
};

const CATEGORY_ICON: Record<string, typeof AlertTriangle> = {
  anomaly:      AlertTriangle,
  trend:        TrendingUp,
  comparison:   GitCompare,
  milestone:    Flag,
  operational:  Activity,
  data_quality: Database,
};

export function InsightCardV2({ card, apiBaseUrl = '', compact = false }: InsightCardV2Props) {
  const [feedback, setFeedback] = useState<1 | -1 | null>(null);
  const [expanded, setExpanded] = useState(false);
  const CategoryIcon = CATEGORY_ICON[card.category] ?? AlertTriangle;
  const statusInfo = STATUS_BADGE[card.status] ?? STATUS_BADGE.new;

  async function submitFeedback(value: 1 | -1) {
    if (feedback !== null) return;
    try {
      await fetch(`${apiBaseUrl}/narrator/feedback?insight_id=${card.id}&feedback=${value}`, { method: 'POST' });
      setFeedback(value);
    } catch { /* best-effort */ }
  }

  if (compact) {
    return (
      <div className={cn('rounded p-3 flex items-start gap-3 transition-all border border-border/40 hover:border-border/80', SEVERITY_STYLES[card.severity])}>
        <CategoryIcon className="w-4 h-4 mt-0.5 shrink-0" style={{ color: 'var(--on-mid)' }} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-foreground truncate">{card.title}</p>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{card.body}</p>
        </div>
        <span className={cn('text-[0.6rem] font-bold px-1.5 py-0.5 rounded border uppercase tracking-wider shrink-0', statusInfo.cls)}>
          {statusInfo.label}
        </span>
      </div>
    );
  }

  return (
    <div className={cn(
      'rounded-lg p-4 space-y-3 transition-all',
      SEVERITY_STYLES[card.severity],
      'border border-border/40 hover:border-border/80',
    )}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <CategoryIcon className="w-4 h-4" style={{ color: 'var(--on-mid)' }} />
          <span className={cn('text-[0.6rem] font-bold px-1.5 py-0.5 rounded border uppercase tracking-wider', statusInfo.cls)}>
            {statusInfo.label}
          </span>
          <span className={cn('text-[0.6rem] font-semibold px-1.5 py-0.5 rounded-full uppercase tracking-wide', SEVERITY_BADGE[card.severity])}>
            {card.severity}
          </span>
          {card.consecutive_periods && card.consecutive_periods > 1 && (
            <span className="text-[0.6rem] font-mono px-1.5 py-0.5 rounded bg-surface-raise text-on-mid">
              {card.consecutive_periods}mo streak
            </span>
          )}
        </div>
        {card.delta_pct !== 0 && (
          <span className={cn(
            'inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full',
            card.delta_pct > 0
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
              : 'bg-red-500/20 text-red-400 border border-red-500/30'
          )}>
            {card.delta_pct > 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {card.delta_pct > 0 ? '+' : ''}{card.delta_pct.toFixed(1)}%
          </span>
        )}
      </div>

      {/* Title */}
      <p className="font-semibold text-foreground text-sm leading-snug">{card.title}</p>

      {/* Body */}
      <p className="text-muted-foreground text-sm leading-relaxed">{card.body}</p>

      {/* Suggested action */}
      {card.suggested_action && (
        <div className="flex items-start gap-2 px-3 py-2 rounded bg-surface-raise border-l-2" style={{ borderLeftColor: 'var(--ok)' }}>
          <span className="text-xs text-on-mid font-semibold shrink-0" style={{ fontFamily: 'var(--font-condensed)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Action</span>
          <p className="text-xs text-foreground">{card.suggested_action}</p>
        </div>
      )}

      {/* Root cause breakdown (expandable) */}
      {card.root_cause_breakdown && card.root_cause_breakdown.length > 0 && (
        <div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            Root cause breakdown
          </button>
          {expanded && (
            <div className="mt-2 space-y-1">
              {card.root_cause_breakdown.map((rc, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <div className="h-1.5 rounded-full" style={{ width: `${rc.contribution_pct}%`, minWidth: 4, maxWidth: 120, background: 'var(--uplink)' }} />
                  <span className="text-foreground font-medium">{rc.driver}</span>
                  <span className="text-muted-foreground">({rc.dimension})</span>
                  <span className="font-mono text-on-mid ml-auto">{rc.contribution_pct.toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Metrics row */}
      <div className="flex gap-4 text-xs text-muted-foreground">
        <span>
          <span className="text-foreground font-medium font-mono">
            {typeof card.current_value === 'number' ? card.current_value.toFixed(1) : card.current_value}
          </span>{' '}current
        </span>
        <span>
          <span className="text-foreground font-medium font-mono">
            {typeof card.reference_value === 'number' ? card.reference_value.toFixed(1) : card.reference_value}
          </span>{' '}baseline
        </span>
        <span className="ml-auto capitalize text-muted-foreground/60">
          {card.entity_type}: {card.entity_id}
        </span>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-border/30">
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground/60">
            {card.confidence === 'statistical' ? 'Statistically detected' : 'Pattern-inferred'}
            {' · '}{card.period}
          </span>
          {card.nlq_query && (
            <a
              href={`/nlq?q=${encodeURIComponent(card.nlq_query)}`}
              className="inline-flex items-center gap-1 text-xs hover:text-foreground transition-colors"
              style={{ color: 'var(--uplink)' }}
            >
              <ExternalLink className="w-3 h-3" />
              Explore in NLQ
            </a>
          )}
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => submitFeedback(1)}
            disabled={feedback !== null}
            className={cn('p-1 rounded transition-colors', feedback === 1 ? 'text-emerald-400' : 'text-muted-foreground/40 hover:text-emerald-400')}
          >
            <ThumbsUp className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => submitFeedback(-1)}
            disabled={feedback !== null}
            className={cn('p-1 rounded transition-colors', feedback === -1 ? 'text-red-400' : 'text-muted-foreground/40 hover:text-red-400')}
          >
            <ThumbsDown className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
