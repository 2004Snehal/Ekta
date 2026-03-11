import { useEffect, useState } from 'react'
import { BarChart3, TrendingUp, Users, Layers, MessageSquare } from 'lucide-react'
import { fetchFilterOptions, presetToDates } from './api'
import type { FilterOptions, Filters } from './types'
import { FiltersBar } from './components/FiltersBar'
import { ExecutiveSummary } from './components/tabs/ExecutiveSummary'
import { Trends } from './components/tabs/Trends'
import { ChannelUser } from './components/tabs/ChannelUser'
import { TypeMix } from './components/tabs/TypeMix'
import { NLQTab } from './components/tabs/NLQTab'

const TABS = [
  { id: 'summary',  label: 'Executive Summary', Icon: BarChart3 },
  { id: 'trends',   label: 'Trends',             Icon: TrendingUp },
  { id: 'channels', label: 'Channels & Users',   Icon: Users },
  { id: 'types',    label: 'Type Mix',           Icon: Layers },
  { id: 'nlq',      label: 'Ask AI',             Icon: MessageSquare },
] as const

type TabId = (typeof TABS)[number]['id']

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('summary')
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null)
  const [filters, setFilters] = useState<Filters>({
    client_id: 1,
    channel_id: null,
    ...presetToDates('all'),
  })

  useEffect(() => {
    fetchFilterOptions(filters.client_id)
      .then(setFilterOptions)
      .catch(console.error)
  }, [filters.client_id])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900 px-6 py-4">
        <div className="max-w-screen-2xl mx-auto flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center font-bold text-white text-sm">F</div>
          <h1 className="text-lg font-semibold text-white">Frammer AI Analytics</h1>
        </div>
      </header>

      <main className="max-w-screen-2xl mx-auto px-6 py-6">
        {/* Filters */}
        <FiltersBar
          options={filterOptions}
          filters={filters}
          onChange={setFilters}
        />

        {/* Tab nav */}
        <div className="flex gap-1 mb-6 border-b border-gray-800">
          {TABS.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-400 hover:text-gray-200'
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === 'summary'  && <ExecutiveSummary filters={filters} />}
        {activeTab === 'trends'   && <Trends filters={filters} />}
        {activeTab === 'channels' && <ChannelUser filters={filters} />}
        {activeTab === 'types'    && <TypeMix filters={filters} />}
        {activeTab === 'nlq'      && <NLQTab clientId={filters.client_id} />}
      </main>
    </div>
  )
}
