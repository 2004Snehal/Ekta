import { useEffect, useState } from 'react'
import { fetchKpiSummary } from '../../api'
import type { Filters, SummaryRow } from '../../types'
import { ChartRenderer } from '../ChartRenderer'

interface Props { filters: Filters }

export function Trends({ filters }: Props) {
  const [summary, setSummary] = useState<SummaryRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetchKpiSummary(filters)
      .then(setSummary)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [filters])

  // Monthly trend (aggregated across all channels)
  const monthlyTrend = (() => {
    const map = new Map<string, { month: string; outputs: number; published: number }>()
    for (const r of summary) {
      const key = r.month.slice(0, 7)
      if (!map.has(key)) map.set(key, { month: key, outputs: 0, published: 0 })
      const cur = map.get(key)!
      cur.outputs   += r.created_count
      cur.published += r.published_count
    }
    return Array.from(map.values()).sort((a, b) => a.month.localeCompare(b.month))
  })()

  // Channel breakdown (total across all time in filtered period)
  const channelBreakdown = (() => {
    const map = new Map<string, { channel: string; outputs: number; published: number }>()
    for (const r of summary) {
      const key = r.channel_name
      if (!map.has(key)) map.set(key, { channel: key, outputs: 0, published: 0 })
      const cur = map.get(key)!
      cur.outputs   += r.created_count
      cur.published += r.published_count
    }
    return Array.from(map.values()).sort((a, b) => b.outputs - a.outputs)
  })()

  // Monthly publish rate trend
  const publishRateTrend = (() => {
    const map = new Map<string, { month: string; created: number; published: number }>()
    for (const r of summary) {
      const key = r.month.slice(0, 7)
      if (!map.has(key)) map.set(key, { month: key, created: 0, published: 0 })
      const cur = map.get(key)!
      cur.created   += r.created_count
      cur.published += r.published_count
    }
    return Array.from(map.values())
      .sort((a, b) => a.month.localeCompare(b.month))
      .map(r => ({ month: r.month, publish_rate: r.created ? Math.round(r.published / r.created * 100) : 0 }))
  })()

  if (loading) return <div className="text-gray-500 text-sm">Loading trends…</div>

  return (
    <div className="space-y-6">
      <div className="grid md:grid-cols-2 gap-6">
        <ChartRenderer spec={{
          chart_type: 'line',
          title: 'Monthly Outputs & Published',
          description: 'Total created outputs per month',
          data: monthlyTrend,
          x: 'month',
          y: 'outputs',
        }} />

        <ChartRenderer spec={{
          chart_type: 'line',
          title: 'Monthly Publish Rate (%)',
          description: 'Percentage of created outputs that were published',
          data: publishRateTrend,
          x: 'month',
          y: 'publish_rate',
        }} />
      </div>

      <ChartRenderer spec={{
        chart_type: 'bar',
        title: 'Outputs by Channel',
        description: 'Total outputs created per channel for the selected period',
        data: channelBreakdown,
        x: 'channel',
        y: 'outputs',
      }} />
    </div>
  )
}
