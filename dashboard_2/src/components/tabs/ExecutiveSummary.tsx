import { useEffect, useState } from 'react'
import { Video, Layers, Send, BarChart3 } from 'lucide-react'
import { fetchKpiTotals, fetchInsights, fetchKpiSummary } from '../../api'
import type { Filters, KpiTotals, Insight, SummaryRow } from '../../types'
import { KPICard } from '../KPICard'
import { ChartRenderer } from '../ChartRenderer'

interface Props { filters: Filters }

export function ExecutiveSummary({ filters }: Props) {
  const [totals, setTotals] = useState<KpiTotals | null>(null)
  const [insights, setInsights] = useState<Insight[]>([])
  const [summary, setSummary] = useState<SummaryRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchKpiTotals(filters),
      fetchInsights(filters.client_id),
      fetchKpiSummary(filters),
    ])
      .then(([t, ins, sum]) => { setTotals(t); setInsights(ins); setSummary(sum) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [filters])

  // Aggregate monthly trend
  const trendData = (() => {
    const map = new Map<string, { month: string; created: number; published: number }>()
    for (const r of summary) {
      const key = r.month.slice(0, 7)
      if (!map.has(key)) map.set(key, { month: key, created: 0, published: 0 })
      const cur = map.get(key)!
      cur.created   += r.created_count
      cur.published += r.published_count
    }
    return Array.from(map.values()).sort((a, b) => a.month.localeCompare(b.month)).slice(-12)
  })()

  const fmtNum = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title="Source Uploads"    value={loading ? '—' : fmtNum(totals?.total_uploads ?? 0)}    icon={<Video className="w-4 h-4" />}    loading={loading} />
        <KPICard title="Outputs Created"   value={loading ? '—' : fmtNum(totals?.total_outputs ?? 0)}    icon={<Layers className="w-4 h-4" />}   loading={loading} />
        <KPICard title="Published"         value={loading ? '—' : fmtNum(totals?.total_published ?? 0)}  icon={<Send className="w-4 h-4" />}     loading={loading} />
        <KPICard title="Publish Rate"      value={loading ? '—' : `${totals?.publish_rate_pct ?? 0}%`}   icon={<BarChart3 className="w-4 h-4" />} loading={loading} />
      </div>

      {/* Trend chart */}
      <ChartRenderer spec={{
        chart_type: 'line',
        title: 'Monthly Output vs Published',
        data: trendData,
        x: 'month',
        y: 'created',
      }} />

      {/* Insights */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Recent Insights</h2>
        {insights.length === 0 ? (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-gray-500 text-sm text-center">
            No insights yet — they'll appear here once the Insight Narrator runs.
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {insights.slice(0, 4).map(ins => (
              <div key={ins.insight_id} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    ins.severity === 'critical' ? 'bg-red-900/50 text-red-400' :
                    ins.severity === 'warning'  ? 'bg-yellow-900/50 text-yellow-400' :
                    'bg-blue-900/50 text-blue-400'
                  }`}>{ins.insight_type}</span>
                </div>
                <p className="font-medium text-white text-sm mb-1">{ins.title}</p>
                <p className="text-gray-400 text-xs leading-relaxed">{ins.body}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
