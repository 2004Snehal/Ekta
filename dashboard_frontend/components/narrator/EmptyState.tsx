'use client';

import { CheckCircle, Clock, ShieldCheck, Cpu } from 'lucide-react';
import type { InsightCardData } from '@/types/narrator';
import { InsightCardV2 } from './InsightCardV2';

interface EmptyStateProps {
  title: string;
  description: string;
  lastResolved?: InsightCardData[];
  checksRun?: string[];
}

/** Animated concentric pulse rings — gives visual weight to empty states. */
function PulseRings() {
  return (
    <div className="relative w-20 h-20 mx-auto mb-4">
      {[0, 1, 2].map(i => (
        <div
          key={i}
          className="absolute inset-0 rounded-full border"
          style={{
            borderColor: 'var(--ok)',
            opacity: 0.12 - i * 0.03,
            animation: `pulse-ring 3s ease-out ${i * 0.6}s infinite`,
          }}
        />
      ))}
      <div className="absolute inset-0 flex items-center justify-center">
        <ShieldCheck className="w-8 h-8" style={{ color: 'var(--ok)', opacity: 0.6 }} />
      </div>
      <style>{`
        @keyframes pulse-ring {
          0% { transform: scale(0.8); opacity: 0.15; }
          70% { transform: scale(1.4); opacity: 0; }
          100% { transform: scale(1.4); opacity: 0; }
        }
      `}</style>
    </div>
  );
}

export function EmptyState({ title, description, lastResolved = [], checksRun = [] }: EmptyStateProps) {
  return (
    <div className="space-y-6 py-8">
      {/* Animated icon + status text */}
      <div className="text-center">
        <PulseRings />
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="text-xs mt-1 max-w-md mx-auto leading-relaxed" style={{ color: 'var(--on-low)' }}>{description}</p>
      </div>

      {/* Checks run — displayed as scan metadata chips */}
      {checksRun.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-2">
          {checksRun.map((c, i) => (
            <div
              key={i}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[0.65rem]"
              style={{ borderColor: 'var(--wire)', color: 'var(--on-low)', background: 'var(--surface)' }}
            >
              {i === 0 ? <Cpu className="w-3 h-3" style={{ color: 'var(--uplink)' }} /> : <CheckCircle className="w-3 h-3" style={{ color: 'var(--ok)', opacity: 0.5 }} />}
              {c}
            </div>
          ))}
        </div>
      )}

      {/* Last scan timestamp placeholder */}
      {checksRun.length === 0 && (
        <div className="flex items-center justify-center gap-2 text-xs" style={{ color: 'var(--on-low)' }}>
          <Clock className="w-3 h-3" />
          <span>Awaiting first v2 pipeline run</span>
        </div>
      )}

      {/* Recently resolved cards */}
      {lastResolved.length > 0 && (
        <div className="space-y-3 max-w-xl mx-auto">
          <p className="text-xs uppercase tracking-widest text-center font-bold" style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)', letterSpacing: '0.15em' }}>
            Recently Resolved
          </p>
          {lastResolved.map(card => (
            <InsightCardV2 key={card.id} card={card} compact />
          ))}
        </div>
      )}
    </div>
  );
}
