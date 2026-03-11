import { SlidersHorizontal } from 'lucide-react'
import type { FilterOptions, Filters } from '../types'
import { presetToDates } from '../api'

interface Props {
  options: FilterOptions | null
  filters: Filters
  onChange: (f: Filters) => void
}

const DATE_PRESETS = [
  { label: 'All time', value: 'all' },
  { label: 'Last 30 days', value: '30d' },
  { label: 'Last 90 days', value: '90d' },
  { label: 'Last 6 months', value: '180d' },
]

export function FiltersBar({ options, filters, onChange }: Props) {
  const handlePreset = (preset: string) => {
    onChange({ ...filters, ...presetToDates(preset) })
  }

  const handleChannel = (val: string) => {
    onChange({ ...filters, channel_id: val === '' ? null : Number(val) })
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 mb-6">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2 text-gray-400">
          <SlidersHorizontal className="w-4 h-4" />
          <span className="text-sm font-medium">Filters</span>
        </div>

        {/* Channel */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">Channel</label>
          <select
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-primary"
            value={filters.channel_id ?? ''}
            onChange={e => handleChannel(e.target.value)}
          >
            <option value="">All channels</option>
            {options?.channels.map(c => (
              <option key={c.id} value={c.id}>{c.name} ({c.code})</option>
            ))}
          </select>
        </div>

        {/* Date preset */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">Period</label>
          <div className="flex gap-1">
            {DATE_PRESETS.map(p => {
              const active =
                p.value === 'all'
                  ? !filters.date_from
                  : filters.date_from === presetToDates(p.value).date_from
              return (
                <button
                  key={p.value}
                  onClick={() => handlePreset(p.value)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    active
                      ? 'bg-primary text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {p.label}
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
