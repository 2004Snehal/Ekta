'use client';

import type { NarratorResponseV2, InsightCardData } from '@/types/narrator';
import { FunnelViz } from './FunnelViz';
import { InsightCardV2 } from './InsightCardV2';
import { EmptyState } from './EmptyState';
import { GitBranch, AlertTriangle, Clock } from 'lucide-react';

interface PipelineTabProps {
  data: NarratorResponseV2;
  apiBaseUrl: string;
}

export function PipelineTab({ data, apiBaseUrl }: PipelineTabProps) {
  const gaps = data.funnel_gaps ?? [];
  const risks = data.operational_risks ?? [];
  const stalled = data.stalled_content ?? [];
  const hasV2Issues = gaps.length > 0 || risks.length > 0 || stalled.length > 0;

  // v1 fallback for operational insights
  const v1Insights = (data.insights ?? []) as InsightCardData[];
  const v1Ops = !hasV2Issues
    ? v1Insights.filter(c => c.category === 'operational' || c.category === 'comparison').slice(0, 6)
    : [];

  const hasFunnel = !!data.funnel;

  return (
    <div className="space-y-8">
      {/* Funnel visualization — always shown when v2 has run */}
      {hasFunnel && <FunnelViz funnel={data.funnel!} />}

      {/* When funnel hasn't run yet, show an explanation of what this tab does */}
      {!hasFunnel && !hasV2Issues && v1Ops.length === 0 && (
        <div className="grid gap-4 md:grid-cols-3">
          {[
            {
              icon: GitBranch,
              color: 'var(--uplink)',
              title: 'Publishing Funnel',
              desc: 'Tracks how many videos move from uploaded → processed → published per channel. Identifies channels with chronic low publish rates.'
            },
            {
              icon: AlertTriangle,
              color: 'var(--warn)',
              title: 'Operational Risks',
              desc: 'Detects structural risks: dormant channels with no activity, single-user dependencies (if one person leaves, output drops to zero), and workload concentration.'
            },
            {
              icon: Clock,
              color: 'var(--on-low)',
              title: 'Stalled Content',
              desc: 'Videos that were processed but never published after 7+ days. These represent pipeline blockages that need editorial or technical investigation.'
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

      {/* v1 fallback for operational insights */}
      {v1Ops.length > 0 && (
        <Section
          title="Operational Insights"
          count={v1Ops.length}
          description="Insights about content distribution patterns and channel comparisons from the previous analysis run."
        >
          <div className="grid gap-4 md:grid-cols-2">
            {v1Ops.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </Section>
      )}

      {gaps.length > 0 && (
        <Section
          title="Funnel Gaps"
          count={gaps.length}
          description="Channels where a large proportion of uploaded videos never get published — either stuck in processing or blocked at the editorial gate."
        >
          <div className="grid gap-4 md:grid-cols-2">
            {gaps.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </Section>
      )}

      {risks.length > 0 && (
        <Section
          title="Operational Risks"
          count={risks.length}
          description="Structural vulnerabilities in how your platform operates — these won't show up in normal KPI dashboards but can cause sudden drops if left unaddressed."
        >
          <div className="grid gap-4 md:grid-cols-2">
            {risks.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </Section>
      )}

      {stalled.length > 0 && (
        <Section
          title="Stalled Content"
          count={stalled.length}
          description="Videos that completed processing but have not been published for 7+ days. These may indicate editorial backlog or technical publish failures."
        >
          <div className="grid gap-4 md:grid-cols-2">
            {stalled.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </Section>
      )}

      {/* Clean empty state only if there's genuinely nothing to show */}
      {!hasV2Issues && !hasFunnel && v1Ops.length === 0 && (
        <EmptyState
          title="No pipeline issues detected"
          description="All channels are operating within normal parameters. No stalled content, dormant channels, or concentration risks found."
          lastResolved={(data.last_resolved ?? []).filter(c => c.tab_destination === 'pipeline')}
          checksRun={data.checks_run ?? []}
        />
      )}
    </div>
  );
}

function Section({ title, count, description, children }: {
  title: string;
  count: number;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-3">
      <div>
        <div className="flex items-center justify-between">
          <h3 className="section-id">{title}</h3>
          <span className="text-xs font-mono" style={{ color: 'var(--on-low)' }}>{count} item{count !== 1 ? 's' : ''}</span>
        </div>
        {description && (
          <p className="text-xs mt-1 leading-relaxed" style={{ color: 'var(--on-low)' }}>{description}</p>
        )}
      </div>
      {children}
    </div>
  );
}
