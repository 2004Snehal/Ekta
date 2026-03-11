import { useEffect, useState } from 'react'
import { fetchKpiSummary } from '../../api'
import type { Filters, SummaryRow } from '../../types'
import { ChartRenderer } from '../ChartRenderer'

interface Props { filters: Filters }

function aggregate<T extends Record<string, unknown>>(
  rows: SummaryRow[],
  keyFn: (r: SummaryRow) => string | null,
  label: string,
): T[] {
  const map = new Map<string, { name: string; value: number }>()
  for (const r of rows) {
    const key = keyFn(r) ?? 'Unknown'
    if (!map.has(key)) map.set(key, { name: key, value: 0 })
    map.get(key)!.value += r.created_count
  }
  return Array.from(map.values())
    .filter(d => d.name !== 'Unknown' || d.value > 0)
    .sort((a, b) => b.value - a.value) as T[]
}

export function TypeMix({ filters }: Props) {
  const [summary, setSummary] = useState<SummaryRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetchKpiSummary(filters)
      .then(setSummary)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [filters])

  const inputTypeData  = aggregate(summary, r => r.input_type,  'input_type')
  const outputTypeData = aggregate(summary, r => r.output_type, 'output_type')
  const languageData   = aggregate(summary, r => r.language_code, 'language')

  // Input type funnel: publish rate per input type
  const funnelData = (() => {
    const map = new Map<string, { type: string; created: number; published: number }>()
    for (const r of summary) {
      if (!r.input_type) continue
      if (!map.has(r.input_type)) map.set(r.input_type, { type: r.input_type, created: 0, published: 0 })
      const cur = map.get(r.input_type)!
      cur.created   += r.created_count
      cur.published += r.published_count
    }
    return Array.from(map.values())
      .map(d => ({ ...d, publish_rate: d.created ? Math.round(d.published / d.created * 100) : 0 }))
      .sort((a, b) => b.publish_rate - a.publish_rate)
  })()

  if (loading) return <div className="text-gray-500 text-sm">Loading…</div>

  return (
    <div className="space-y-6">
      <div className="grid md:grid-cols-2 gap-6">
        <ChartRenderer spec={{
          chart_type: 'pie',
          title: 'Input Type Distribution',
          description: 'Outputs created by source content type',
          data: inputTypeData,
          x: 'name',
          y: 'value',
        }} />

        <ChartRenderer spec={{
          chart_type: 'pie',
          title: 'Output Type Distribution',
          description: 'What types of outputs are being created',
          data: outputTypeData,
          x: 'name',
          y: 'value',
        }} />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <ChartRenderer spec={{
          chart_type: 'bar',
          title: 'Language Breakdown',
          description: 'Outputs by language',
          data: languageData,
          x: 'name',
          y: 'value',
        }} />

        {/* Funnel table */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="font-semibold text-white mb-1">Publish Rate by Input Type</h3>
          <p className="text-xs text-gray-400 mb-4">Sorted by publish rate descending</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-xs text-gray-400">
                <th className="pb-2 text-left">Input Type</th>
                <th className="pb-2 text-right">Created</th>
                <th className="pb-2 text-right">Published</th>
                <th className="pb-2 text-right">Rate</th>
              </tr>
            </thead>
            <tbody>
              {funnelData.map(d => (
                <tr key={d.type} className="border-b border-gray-800">
                  <td className="py-2 text-gray-300 capitalize">{d.type}</td>
                  <td className="py-2 text-right text-gray-400">{d.created}</td>
                  <td className="py-2 text-right text-gray-400">{d.published}</td>
                  <td className="py-2 text-right">
                    <span className={`text-xs font-medium ${d.publish_rate >= 60 ? 'text-green-400' : d.publish_rate >= 30 ? 'text-yellow-400' : 'text-red-400'}`}>
                      {d.publish_rate}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
