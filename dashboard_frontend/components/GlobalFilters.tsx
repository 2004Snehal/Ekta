'use client';

import { Filters } from '@/components/Filters';
import type { DashboardFilters, DashboardFilterField, FilterOption } from '@/types/dashboard';

interface GlobalFiltersProps {
  filters: DashboardFilters;
  filterFields: DashboardFilterField[];
  filterOptions: Record<string, FilterOption[]>;
  isExpanded: boolean;
  onExpandedChange?: (expanded: boolean) => void;
  onApply?: (filters: DashboardFilters) => void;
  granularity?: 'day' | 'week' | 'month';
  onGranularityChange?: (g: 'day' | 'week' | 'month') => void;
  showGranularity?: boolean;
}

const GRAN_OPTS: { value: 'day' | 'week' | 'month'; label: string }[] = [
  { value: 'day', label: 'DAY' },
  { value: 'week', label: 'WEEK' },
  { value: 'month', label: 'MONTH' },
];

export function GlobalFilters({
  filters, filterFields, filterOptions, isExpanded,
  onExpandedChange, onApply,
  granularity = 'month', onGranularityChange, showGranularity = false,
}: GlobalFiltersProps) {
  return (
    <div>
      <Filters
        filters={filters}
        filterFields={filterFields}
        filterOptions={filterOptions}
        isExpanded={isExpanded}
        onExpandedChange={onExpandedChange}
        onApply={onApply}
      />
      {showGranularity && (
        <div
          className="flex items-center gap-0 px-6 py-1.5"
          style={{ borderBottom: '1px solid var(--wire)', background: 'var(--void)' }}
        >
          <span
            style={{
              fontFamily: 'var(--font-condensed)',
              fontSize: '0.55rem',
              fontWeight: 700,
              letterSpacing: '0.14em',
              color: 'var(--on-low)',
              marginRight: '10px',
              textTransform: 'uppercase',
            }}
          >
            Granularity
          </span>
          {GRAN_OPTS.map((opt, i) => (
            <span key={opt.value} className="flex items-center gap-0">
              <span
                className={`range-opt${granularity === opt.value ? ' selected' : ''}`}
                onClick={() => onGranularityChange?.(opt.value)}
              >
                {opt.label}
              </span>
              {i < GRAN_OPTS.length - 1 && (
                <span style={{ color: 'var(--wire-mid)', margin: '0 5px', fontSize: '0.55rem' }}>·</span>
              )}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
