'use client';

import { useState } from 'react';
import { Calendar, X } from 'lucide-react';

interface FiltersProps {
  onApply?: (filters: FilterState) => void;
}

interface FilterState {
  dateRange: string;
  client: string;
  channel: string;
  videoType: string;
}

export function Filters({ onApply }: FiltersProps) {
  const [filters, setFilters] = useState<FilterState>({
    dateRange: 'last-7-days',
    client: 'all',
    channel: 'all',
    videoType: 'all',
  });

  const [isExpanded, setIsExpanded] = useState(true);

  const handleChange = (key: keyof FilterState, value: string) => {
    const newFilters = { ...filters, [key]: value };
    setFilters(newFilters);
    onApply?.(newFilters);
  };

  const resetFilters = () => {
    const defaultFilters = {
      dateRange: 'last-7-days',
      client: 'all',
      channel: 'all',
      videoType: 'all',
    };
    setFilters(defaultFilters);
    onApply?.(defaultFilters);
  };

  return (
    <div className="bg-card border border-border rounded-lg p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-foreground">Filters</h3>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-muted-foreground hover:text-foreground transition-colors"
        >
          {isExpanded ? '−' : '+'}
        </button>
      </div>

      {isExpanded && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Date Range */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              <Calendar className="w-4 h-4 inline mr-2" />
              Date Range
            </label>
            <select
              value={filters.dateRange}
              onChange={(e) => handleChange('dateRange', e.target.value)}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-foreground text-sm hover:border-primary/50 focus:outline-none focus:border-primary transition-colors"
            >
              <option value="last-7-days">Last 7 Days</option>
              <option value="last-30-days">Last 30 Days</option>
              <option value="last-90-days">Last 90 Days</option>
              <option value="all-time">All Time</option>
            </select>
          </div>

          {/* Client */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">Client</label>
            <select
              value={filters.client}
              onChange={(e) => handleChange('client', e.target.value)}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-foreground text-sm hover:border-primary/50 focus:outline-none focus:border-primary transition-colors"
            >
              <option value="all">All Clients</option>
              <option value="client-1">Tech Corp</option>
              <option value="client-2">Media Co</option>
              <option value="client-3">Creative Studio</option>
            </select>
          </div>

          {/* Channel */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">Channel</label>
            <select
              value={filters.channel}
              onChange={(e) => handleChange('channel', e.target.value)}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-foreground text-sm hover:border-primary/50 focus:outline-none focus:border-primary transition-colors"
            >
              <option value="all">All Channels</option>
              <option value="youtube">YouTube</option>
              <option value="tiktok">TikTok</option>
              <option value="instagram">Instagram</option>
              <option value="linkedin">LinkedIn</option>
            </select>
          </div>

          {/* Video Type */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              Video Type
            </label>
            <select
              value={filters.videoType}
              onChange={(e) => handleChange('videoType', e.target.value)}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-foreground text-sm hover:border-primary/50 focus:outline-none focus:border-primary transition-colors"
            >
              <option value="all">All Types</option>
              <option value="short">Shorts</option>
              <option value="long-form">Long-form</option>
              <option value="live">Live</option>
              <option value="premiere">Premiere</option>
            </select>
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
