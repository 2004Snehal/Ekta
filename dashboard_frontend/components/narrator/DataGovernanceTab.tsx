'use client';

import type { NarratorResponseV2, InsightCardData } from '@/types/narrator';
import { DQScorecardViz } from './DQScorecardViz';
import { InsightCardV2 } from './InsightCardV2';
import { EmptyState } from './EmptyState';
import { Database, FileX, Copy, Link2 } from 'lucide-react';

interface DataGovernanceTabProps {
  data: NarratorResponseV2;
  apiBaseUrl: string;
}

export function DataGovernanceTab({ data, apiBaseUrl }: DataGovernanceTabProps) {
  const issues = data.dq_issues ?? [];
  const hasDQScorecard = !!data.dq_scorecard;

  // v1 fallback
  const v1Insights = (data.insights ?? []) as InsightCardData[];
  const v1DQ = issues.length === 0
    ? v1Insights.filter(c => c.category === 'data_quality').slice(0, 6)
    : [];

  return (
    <div className="space-y-8">
      {/* DQ Scorecard — always shown when v2 ran */}
      {hasDQScorecard && (
        <DQScorecardViz scorecard={data.dq_scorecard!} trend={data.dq_trend ?? []} />
      )}

      {/* When scorecard hasn't run yet, explain what this tab checks */}
      {!hasDQScorecard && issues.length === 0 && v1DQ.length === 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            {
              icon: Database,
              color: 'var(--uplink)',
              title: 'Field Completeness',
              desc: 'Checks every important field (language, output type, team, platform) for NULL or "Unknown" values. Shows what % of your records are fully populated.'
            },
            {
              icon: Copy,
              color: 'var(--warn)',
              title: 'Duplicate Detection',
              desc: 'Finds video IDs that appear more than once in your data — usually caused by ingestion bugs or double-uploads.'
            },
            {
              icon: Link2,
              color: 'var(--signal)',
              title: 'Invalid Publish URLs',
              desc: 'Scans published_url field for malformed or missing URLs on videos marked as published — these break downstream links.'
            },
            {
              icon: FileX,
              color: 'var(--on-low)',
              title: 'Unknown Buckets',
              desc: 'Records where dimension values are literally "Unknown" or "unknown" — these inflate your "Other" categories and skew all analysis.'
            },
          ].map(({ icon: Icon, color, title, desc }) => (
            <div key={title} className="rounded-lg p-4 border border-border/40 space-y-3" style={{ background: 'var(--surface)' }}>
              <div className="flex items-center gap-2">
                <Icon className="w-4 h-4" style={{ color }} />
                <span className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--on-mid)', fontFamily: 'var(--font-condensed)' }}>{title}</span>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--on-low)' }}>{desc}</p>
            </div>
          ))}
        </div>
      )}

      {/* v1 DQ fallback */}
      {v1DQ.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="section-id">Data Quality Insights</h3>
            <span className="text-xs font-mono" style={{ color: 'var(--on-low)' }}>{v1DQ.length} item{v1DQ.length !== 1 ? 's' : ''}</span>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {v1DQ.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </div>
      )}

      {/* v2 DQ issues */}
      {issues.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="section-id">Data Quality Issues</h3>
            <span className="text-xs font-mono" style={{ color: 'var(--on-low)' }}>{issues.length} issue{issues.length !== 1 ? 's' : ''}</span>
          </div>
          <p className="text-xs" style={{ color: 'var(--on-low)' }}>
            Fields or records that are missing, duplicated, or malformed — fixing these improves the accuracy of all reports and AI analysis.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            {issues.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </div>
      )}

      {/* Empty state — only when scorecard ran and found nothing */}
      {hasDQScorecard && issues.length === 0 && (
        <EmptyState
          title="No data quality issues"
          description="All monitored fields meet completeness thresholds. No duplicate video IDs or invalid publish URLs detected."
          lastResolved={(data.last_resolved ?? []).filter(c => c.tab_destination === 'data_governance')}
          checksRun={data.checks_run ?? []}
        />
      )}
    </div>
  );
}
