'use client';

import { cn } from '@/lib/utils';
import type { EntityHealthScore, HealthGrade } from '@/types/narrator';

interface HealthLeaderboardProps {
  entities: EntityHealthScore[];
  title?: string;
}

const GRADE_CONFIG: Record<HealthGrade, { color: string; bg: string; border: string }> = {
  A: { color: 'var(--ok)',     bg: 'rgba(29, 185, 84, 0.08)',  border: 'rgba(29, 185, 84, 0.25)' },
  B: { color: 'var(--uplink)', bg: 'rgba(45, 156, 219, 0.08)', border: 'rgba(45, 156, 219, 0.25)' },
  C: { color: 'var(--warn)',   bg: 'rgba(242, 161, 26, 0.08)', border: 'rgba(242, 161, 26, 0.25)' },
  D: { color: 'var(--signal)', bg: 'rgba(229, 0, 26, 0.08)',   border: 'rgba(229, 0, 26, 0.25)' },
};

const COMPONENT_LABELS: Record<string, string> = {
  publish_rate: 'Publish',
  activity: 'Activity',
  trend: 'Trend',
  dq: 'DQ',
};

function HealthBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-1.5 rounded-full w-full" style={{ background: 'var(--wire)' }}>
      <div
        className="h-1.5 rounded-full"
        style={{
          width: `${Math.min(value, 100)}%`,
          background: color,
          transition: 'width 0.8s ease-out',
        }}
      />
    </div>
  );
}

export function HealthLeaderboard({ entities, title = 'Entity Health' }: HealthLeaderboardProps) {
  if (entities.length === 0) return null;

  const sorted = [...entities].sort((a, b) => b.score - a.score);

  return (
    <div className="space-y-4">
      <h3
        className="section-id"
        style={{ fontFamily: 'var(--font-condensed)' }}
      >
        {title}
      </h3>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {sorted.map((entity) => {
          const gc = GRADE_CONFIG[entity.grade];
          return (
            <div
              key={`${entity.entity_type}-${entity.entity_id}`}
              className="rounded-lg p-4 space-y-3 border transition-all hover:border-opacity-60"
              style={{ background: gc.bg, borderColor: gc.border }}
            >
              {/* Header */}
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground truncate">{entity.entity_label}</p>
                  <p className="text-xs capitalize" style={{ color: 'var(--on-low)' }}>{entity.entity_type}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="font-mono text-2xl font-bold" style={{ color: gc.color }}>{entity.score}</span>
                  <span
                    className="text-xs font-bold w-6 h-6 rounded flex items-center justify-center"
                    style={{ background: gc.border, color: gc.color }}
                  >
                    {entity.grade}
                  </span>
                </div>
              </div>

              {/* Component bars */}
              <div className="space-y-1.5">
                {Object.entries(entity.components).map(([key, value]) => (
                  <div key={key} className="flex items-center gap-2">
                    <span
                      className="text-[0.6rem] w-12 shrink-0 text-right uppercase tracking-wider"
                      style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)' }}
                    >
                      {COMPONENT_LABELS[key] ?? key}
                    </span>
                    <HealthBar value={value} color={gc.color} />
                    <span className="text-[0.6rem] font-mono w-6 text-right" style={{ color: 'var(--on-mid)' }}>
                      {value}
                    </span>
                  </div>
                ))}
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between pt-1 border-t" style={{ borderColor: gc.border }}>
                {entity.delta_vs_last != null && (
                  <span
                    className="text-xs font-mono"
                    style={{ color: entity.delta_vs_last > 0 ? 'var(--ok)' : entity.delta_vs_last < 0 ? 'var(--signal)' : 'var(--on-low)' }}
                  >
                    {entity.delta_vs_last > 0 ? '+' : ''}{entity.delta_vs_last} vs last
                  </span>
                )}
                {entity.signal_count > 0 && (
                  <span className="text-xs" style={{ color: 'var(--on-low)' }}>
                    {entity.signal_count} signal{entity.signal_count > 1 ? 's' : ''}
                  </span>
                )}
              </div>

              {/* Top signal */}
              {entity.top_signal && (
                <p className="text-xs italic" style={{ color: 'var(--on-low)' }}>
                  {entity.top_signal}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
