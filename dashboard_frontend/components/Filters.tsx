'use client';

import { Calendar, Plus, X } from 'lucide-react';
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

const DEFAULT_FILTER_KEYS = ['client', 'channel', 'user', 'language', 'type', 'platform'];

function formatOptionLabel(option: FilterOption): string {
  return option.count ? `${option.label} (${option.count})` : option.label;
}

export function Filters({
  filters,
  filterFields,
  filterOptions,
  isExpanded,
  onExpandedChange,
  onApply,
}: FiltersProps) {
  const handleDefaultFilterChange = (key: keyof DashboardFilters, value: string) => {
    onApply?.({ ...filters, [key]: value });
  };

  const handleExtraFilterChange = (filterId: string, nextValue: Partial<{ field: string; value: string }>) => {
    onApply?.({
      ...filters,
      extraFilters: filters.extraFilters.map((filter) =>
        filter.id === filterId
          ? {
              ...filter,
              ...nextValue,
              value: nextValue.field && nextValue.field !== filter.field ? 'all' : nextValue.value ?? filter.value,
            }
          : filter
      ),
    });
  };

  const removeExtraFilter = (filterId: string) => {
    onApply?.({
      ...filters,
      extraFilters: filters.extraFilters.filter((filter) => filter.id !== filterId),
    });
  };

  const addableFields = filterFields.filter(
    (field) => !DEFAULT_FILTER_KEYS.includes(field.key) && !filters.extraFilters.some((extra) => extra.field === field.key)
  );

  const addExtraFilter = () => {
    const nextField = addableFields[0];
    if (!nextField) {
      return;
    }

    onApply?.({
      ...filters,
      extraFilters: [
        ...filters.extraFilters,
        {
          id: `${nextField.key}-${Date.now()}`,
          field: nextField.key,
          value: 'all',
        },
      ],
    });
  };

  const resetFilters = () => {
    onApply?.({
      dateRange: 'last-90-days',
      client: 'all',
      channel: 'all',
      user: 'all',
      language: 'all',
      type: 'all',
      platform: 'all',
      extraFilters: [],
    });
  };

  return (
    <div className="bg-card border border-border rounded-lg p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-foreground">Filters</h3>
        <button onClick={() => onExpandedChange?.(!isExpanded)} className="text-muted-foreground hover:text-foreground transition-colors">
          {isExpanded ? '−' : '+'}
        </button>
      </div>

      {isExpanded && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-4">
          {/* Date Range */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              <Calendar className="w-4 h-4 inline mr-2" />
              Date Range
            </label>
            <select
              value={filters.dateRange}
              onChange={(e) => handleDefaultFilterChange('dateRange', e.target.value)}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-foreground text-sm hover:border-primary/50 focus:outline-none focus:border-primary transition-colors"
            >
              <option value="last-7-days">Last 7 Days</option>
              <option value="last-30-days">Last 30 Days</option>
              <option value="last-90-days">Last 90 Days</option>
              <option value="all-time">All Time</option>
            </select>
          </div>

            {DEFAULT_FILTER_KEYS.map((fieldKey) => {
              const fieldConfig = filterFields.find((field) => field.key === fieldKey);
              const options = filterOptions[fieldKey] ?? [{ value: 'all', label: 'All' }];

              return (
                <div key={fieldKey}>
                  <label className="block text-sm font-medium text-muted-foreground mb-2">
                    {fieldConfig?.label ?? fieldKey}
                  </label>
                  <select
                    value={String(filters[fieldKey as keyof DashboardFilters] ?? 'all')}
                    onChange={(event) => handleDefaultFilterChange(fieldKey as keyof DashboardFilters, event.target.value)}
                    className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-foreground text-sm hover:border-primary/50 focus:outline-none focus:border-primary transition-colors"
                  >
                    {options.map((option) => (
                      <option key={`${fieldKey}-${option.value}`} value={option.value}>
                        {formatOptionLabel(option)}
                      </option>
                    ))}
                  </select>
                </div>
              );
            })}
          </div>

          <div className="border border-dashed border-border rounded-lg p-4 bg-secondary/20">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-4">
              <div>
                <h4 className="text-sm font-semibold text-foreground">Additional Filters</h4>
                <p className="text-sm text-muted-foreground">
                  Add frontend-visible data columns as filters without reloading the cached dataset.
                </p>
              </div>
              <button
                onClick={addExtraFilter}
                disabled={!addableFields.length}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-foreground transition-colors hover:border-primary/50 hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus className="w-4 h-4" />
                Add Filter
              </button>
            </div>

            {filters.extraFilters.length ? (
              <div className="space-y-3">
                {filters.extraFilters.map((filter) => {
                  const options = filterOptions[filter.field] ?? [{ value: 'all', label: 'All' }];
                  const selectableFields = filterFields.filter(
                    (field) => !DEFAULT_FILTER_KEYS.includes(field.key) && (field.key === filter.field || !filters.extraFilters.some((extra) => extra.field === field.key))
                  );

                  return (
                    <div key={filter.id} className="grid grid-cols-1 md:grid-cols-[minmax(0,220px)_minmax(0,1fr)_auto] gap-3">
                      <select
                        value={filter.field}
                        onChange={(event) => handleExtraFilterChange(filter.id, { field: event.target.value })}
                        className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-foreground text-sm hover:border-primary/50 focus:outline-none focus:border-primary transition-colors"
                      >
                        {selectableFields.map((field) => (
                          <option key={field.key} value={field.key}>
                            {field.label}
                          </option>
                        ))}
                      </select>

                      <select
                        value={filter.value}
                        onChange={(event) => handleExtraFilterChange(filter.id, { value: event.target.value })}
                        className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-foreground text-sm hover:border-primary/50 focus:outline-none focus:border-primary transition-colors"
                      >
                        {options.map((option) => (
                          <option key={`${filter.id}-${option.value}`} value={option.value}>
                            {formatOptionLabel(option)}
                          </option>
                        ))}
                      </select>

                      <button
                        onClick={() => removeExtraFilter(filter.id)}
                        className="inline-flex items-center justify-center rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary"
                        aria-label={`Remove ${filter.field} filter`}
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No extra filters selected yet.</p>
            )}
          </div>
        </div>
      )}

      {isExpanded && (
        <button
          onClick={resetFilters}
          className="mt-4 flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <X className="w-4 h-4" />
          Reset Filters
        </button>
      )}
    </div>
  );
}
