'use client';

import { Lightbulb } from 'lucide-react';

interface InsightPanelProps {
  insights: {
    title: string;
    description: string;
    actionable?: boolean;
  }[];
}

export function InsightPanel({ insights }: InsightPanelProps) {
  return (
    <div className="bg-card border border-border rounded-lg p-6">
      <div className="flex items-center gap-2 mb-4">
        <Lightbulb className="w-5 h-5 text-primary" />
        <h3 className="text-lg font-semibold text-foreground">AI Insights</h3>
      </div>

      <div className="space-y-3">
        {insights.map((insight, idx) => (
          <div
            key={idx}
            className="p-3 bg-secondary/50 border border-border/50 rounded-lg hover:border-primary/50 transition-colors"
          >
            <p className="font-semibold text-foreground text-sm">{insight.title}</p>
            <p className="text-muted-foreground text-sm mt-1">{insight.description}</p>
            {insight.actionable && (
              <button className="mt-2 text-xs font-semibold text-primary hover:text-primary/80 transition-colors">
                Take Action →
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
