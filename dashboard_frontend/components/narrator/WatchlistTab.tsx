'use client';

import type { NarratorResponseV2, InsightCardData } from '@/types/narrator';
import { InsightCardV2 } from './InsightCardV2';
import { EmptyState } from './EmptyState';
import { Info } from 'lucide-react';

interface WatchlistTabProps {
  data: NarratorResponseV2;
  apiBaseUrl: string;
}

export function WatchlistTab({ data, apiBaseUrl }: WatchlistTabProps) {
  const flagged = data.flagged_metrics ?? [];
  const trends = data.consecutive_trends ?? [];
  const crossDim = data.cross_dimension ?? [];
  const miles = data.milestones ?? [];
  const hasV2Content = flagged.length > 0 || trends.length > 0 || crossDim.length > 0 || miles.length > 0;

  // v1 fallback — show ALL v1 insights here (anomaly, trend, comparison types)
  // These are NOT shown in Pulse anymore, so no duplication
  const v1Insights = (data.insights ?? []) as InsightCardData[];
  const v1Cards = !hasV2Content ? v1Insights.filter(c =>
    c.category === 'anomaly' || c.category === 'trend' || c.category === 'comparison'
  ) : [];

  const hasContent = hasV2Content || v1Cards.length > 0;

  if (!hasContent) {
    return (
      <EmptyState
        title="No active watchlist items"
        description="All metrics are within expected ranges. No multi-month trends, surprising cross-dimension patterns, or flagged anomalies were detected this period."
        lastResolved={(data.last_resolved ?? []).filter(c => c.tab_destination === 'watchlist')}
        checksRun={data.checks_run ?? []}
      />
    );
  }

  return (
    <div className="space-y-8">
      {/* v1 fallback — shown only before v2 pipeline has run */}
      {v1Cards.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="section-id">Flagged Metrics</h3>
            <span className="text-xs font-mono" style={{ color: 'var(--on-low)' }}>{v1Cards.length} item{v1Cards.length !== 1 ? 's' : ''}</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 rounded text-xs border border-border/30" style={{ background: 'var(--surface)', color: 'var(--on-low)' }}>
            <Info className="w-3.5 h-3.5 shrink-0" />
            These are from the previous analysis run. Click <strong className="mx-1">Run Now</strong> to get deeper pattern analysis including multi-month trends and cross-dimension patterns.
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {v1Cards.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </div>
      )}

      {/* v2 sections */}
      {flagged.length > 0 && (
        <Section
          title="Flagged Metrics"
          count={flagged.length}
          description="Individual metrics that moved significantly outside their historical baseline this period."
        >
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {flagged.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </Section>
      )}

      {trends.length > 0 && (
        <Section
          title="Multi-month Trends"
          count={trends.length}
          description="Metrics that have consistently moved in the same direction for 3 or more months in a row — these represent structural shifts, not one-off spikes."
        >
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {trends.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </Section>
      )}

      {crossDim.length > 0 && (
        <Section
          title="Cross-Dimension Patterns"
          count={crossDim.length}
          description="Surprising combinations — e.g. a specific language × output type that produces significantly more or less than expected based on overall fleet patterns."
        >
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {crossDim.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </Section>
      )}

      {miles.length > 0 && (
        <Section
          title="Milestones"
          count={miles.length}
          description="Positive achievements — first-time records broken, thresholds crossed for the first time, or best months ever for a channel or metric."
        >
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {miles.map(card => (
              <InsightCardV2 key={card.id} card={card} apiBaseUrl={apiBaseUrl} />
            ))}
          </div>
        </Section>
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
