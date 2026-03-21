'use client';

import type {
  DashboardFilterField,
  DashboardFilters,
  FilterOption,
} from '@/types/dashboard';

interface FiltersProps {
  filters: DashboardFilters;
  filterFields: DashboardFilterField[];
  filterOptions: Record<string, FilterOption[]>;
  isExpanded: boolean;
  onExpandedChange?: (expanded: boolean) => void;
  onApply?: (filters: DashboardFilters) => void;
}

const DATE_OPTS: { value: DashboardFilters['dateRange']; label: string }[] = [
  { value: 'last-7-days',  label: '7D'  },
  { value: 'last-30-days', label: '30D' },
  { value: 'last-90-days', label: '90D' },
  { value: 'all-time',     label: 'ALL' },
];

const DEFAULT_FILTER_KEYS = ['client_type', 'channel', 'user', 'language', 'type', 'platform'];

export function Filters({ filters, filterFields, filterOptions, isExpanded, onExpandedChange, onApply }: FiltersProps) {

  const set = (key: keyof DashboardFilters, val: string) =>
    onApply?.({ ...filters, [key]: val });

  const addableFields = filterFields.filter(
    (f) => !DEFAULT_FILTER_KEYS.includes(f.key) && !filters.extraFilters.some((e) => e.field === f.key)
  );

  const addExtra = () => {
    const next = addableFields[0];
    if (!next) return;
    onApply?.({
      ...filters,
      extraFilters: [...filters.extraFilters, { id: `${next.key}-${Date.now()}`, field: next.key, value: 'all' }],
    });
  };

  const removeExtra = (id: string) =>
    onApply?.({ ...filters, extraFilters: filters.extraFilters.filter((f) => f.id !== id) });

  const changeExtra = (id: string, patch: Partial<{ field: string; value: string }>) =>
    onApply?.({
      ...filters,
      extraFilters: filters.extraFilters.map((f) =>
        f.id === id ? { ...f, ...patch, value: patch.field && patch.field !== f.field ? 'all' : (patch.value ?? f.value) } : f
      ),
    });

  const reset = () =>
    onApply?.({ dateRange: 'last-90-days', client_type: '', client: '', channel: '', user: '', language: '', type: '', platform: '', extraFilters: [] });

  /* Active filter tokens (non-date, non-empty) */
  const activeTokens = DEFAULT_FILTER_KEYS
    .filter((k) => {
      const v = filters[k as keyof DashboardFilters] as string;
      return v && v !== 'all' && v !== '';
    })
    .map((k) => ({
      key: k,
      label: `${(filterFields.find((f) => f.key === k)?.label ?? k).toUpperCase()}: ${(filters[k as keyof DashboardFilters] as string).toUpperCase()}`,
    }));

  const extraTokens = filters.extraFilters
    .filter((ef) => ef.value && ef.value !== 'all')
    .map((ef) => ({
      id: ef.id,
      label: `${ef.field.toUpperCase()}: ${ef.value.toUpperCase()}`,
    }));

  return (
    <div id="dashboard-filters-section" style={{ borderBottom: '1px solid var(--wire)', background: 'var(--void)' }}>

      {/* ── Collapsed / summary strip ────────────────────── */}
      <div className="flex items-center gap-4 px-6 py-2.5 flex-wrap">

        {/* Date range inline options */}
        <div className="flex items-center gap-0">
          {DATE_OPTS.map((opt, i) => (
            <span key={opt.value} className="flex items-center gap-0">
              <span
                className={`range-opt${filters.dateRange === opt.value ? ' selected' : ''}`}
                onClick={() => set('dateRange', opt.value)}
              >
                {opt.label}
              </span>
              {i < DATE_OPTS.length - 1 && (
                <span style={{ color: 'var(--wire-mid)', margin: '0 5px', fontSize: '0.55rem' }}>·</span>
              )}
            </span>
          ))}
        </div>

        <div className="wire-v" style={{ height: '14px' }} />

        {/* Active filter tokens */}
        {activeTokens.map((tok) => (
          <span key={tok.key} className="filter-token">
            {tok.label}
            <span className="filter-token-x" onClick={() => set(tok.key as keyof DashboardFilters, '')}>×</span>
          </span>
        ))}
        {extraTokens.map((tok) => (
          <span key={tok.id} className="filter-token">
            {tok.label}
            <span className="filter-token-x" onClick={() => removeExtra(tok.id)}>×</span>
          </span>
        ))}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Toggle expand */}
        <span className="action-text" onClick={() => onExpandedChange?.(!isExpanded)}>
          {isExpanded ? '− LESS' : '+ FILTERS'}
        </span>

        {(activeTokens.length > 0 || extraTokens.length > 0) && (
          <>
            <span style={{ color: 'var(--wire-mid)', fontSize: '0.55rem' }}>·</span>
            <span className="action-text danger" onClick={reset}>↺ RESET</span>
          </>
        )}
      </div>

      {/* ── Expanded filter panel ────────────────────────── */}
      {isExpanded && (
        <div
          className="px-6 pb-4 pt-1"
          style={{ borderTop: '1px solid var(--wire)' }}
        >
          <div className="flex flex-wrap gap-x-6 gap-y-3 items-end">

            {DEFAULT_FILTER_KEYS.map((fieldKey) => {
              const config  = filterFields.find((f) => f.key === fieldKey);
              const options = filterOptions[fieldKey] ?? [];
              const current = (filters[fieldKey as keyof DashboardFilters] as string) || 'all';

              return (
                <div key={fieldKey} className="flex flex-col gap-1" style={{ minWidth: '110px' }}>
                  <span
                    style={{
                      fontFamily: 'var(--font-condensed)',
                      fontSize: '0.55rem',
                      fontWeight: 700,
                      letterSpacing: '0.18em',
                      textTransform: 'uppercase',
                      color: 'var(--on-low)',
                    }}
                  >
                    {config?.label ?? fieldKey}
                  </span>
                  <select
                    className="bare-select"
                    value={current}
                    onChange={(e) => set(fieldKey as keyof DashboardFilters, e.target.value)}
                  >
                    <option value="all">All</option>
                    {options.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}{o.count ? ` (${o.count})` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              );
            })}

            {/* Extra filters */}
            {filters.extraFilters.map((ef) => {
              const options = filterOptions[ef.field] ?? [];
              const selectableFields = filterFields.filter(
                (f) => !DEFAULT_FILTER_KEYS.includes(f.key) && (f.key === ef.field || !filters.extraFilters.some((e) => e.field === f.key))
              );
              return (
                <div key={ef.id} className="flex items-end gap-2">
                  <div className="flex flex-col gap-1">
                    <span style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--on-low)' }}>
                      Dimension
                    </span>
                    <select className="bare-select" value={ef.field} onChange={(e) => changeExtra(ef.id, { field: e.target.value })}>
                      {selectableFields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span style={{ fontFamily: 'var(--font-condensed)', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--on-low)' }}>
                      Value
                    </span>
                    <select className="bare-select" value={ef.value} onChange={(e) => changeExtra(ef.id, { value: e.target.value })}>
                      <option value="all">All</option>
                      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                  <span className="action-text danger pb-0.5" onClick={() => removeExtra(ef.id)}>× REMOVE</span>
                </div>
              );
            })}

            {addableFields.length > 0 && (
              <div className="flex flex-col justify-end pb-0.5">
                <span className="action-text" onClick={addExtra}>+ DIM</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
