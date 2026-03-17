import {
  LineChart, Line,
  BarChart, Bar,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'

export interface ChartSpec {
  chart_type: 'bar' | 'line' | 'pie' | 'table' | 'stacked_bar' | string | null | undefined
  title?: string
  description?: string
  data: Record<string, unknown>[]
  x?: string | null
  y?: string | null
  colors?: string[]
}

const COLORS = ['#FF4D5A', '#3B82F6', '#06B6D4', '#FB923C', '#8B5CF6', '#10B981', '#F59E0B', '#EC4899']

const TOOLTIP_STYLE = {
  backgroundColor: '#1f2937',
  border: '1px solid #374151',
  borderRadius: '8px',
  color: '#f9fafb',
}

export function ChartRenderer({ spec }: { spec: ChartSpec }) {
  const colors = spec.colors ?? COLORS

  const renderChart = () => {
    if (!spec.data?.length) {
      return <p className="text-gray-500 text-sm text-center py-8">No data</p>
    }

    // Auto-detect x/y keys from data when not provided
    const allKeys = Object.keys(spec.data[0])
    const numericKeys = allKeys.filter(k => typeof spec.data[0][k] === 'number')
    const textKeys = allKeys.filter(k => typeof spec.data[0][k] !== 'number')
    const xKey: string = spec.x || textKeys[0] || allKeys[0]
    const yKey: string = spec.y || numericKeys.find(k => k !== xKey) || numericKeys[0] || allKeys[1] || allKeys[0]

    switch (spec.chart_type) {
      case 'line':
        return (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={spec.data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey={xKey} stroke="#6b7280" tick={{ fontSize: 11 }} />
              <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey={yKey} stroke={colors[0]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )

      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={spec.data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey={xKey} stroke="#6b7280" tick={{ fontSize: 11 }} />
              <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey={yKey} fill={colors[0]} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )

      case 'stacked_bar': {
        const seriesKeys = Object.keys(spec.data[0] ?? {}).filter(k => k !== xKey)
        return (
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={spec.data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey={xKey} stroke="#6b7280" tick={{ fontSize: 11 }} />
              <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {seriesKeys.map((key, i) => (
                <Bar key={key} dataKey={key} stackId="a" fill={colors[i % colors.length]}
                  radius={i === seriesKeys.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )
      }

      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={spec.data} dataKey={yKey} nameKey={xKey}
                cx="50%" cy="50%" outerRadius={100}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {spec.data.map((_, i) => (
                  <Cell key={i} fill={colors[i % colors.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} />
            </PieChart>
          </ResponsiveContainer>
        )

      case 'table':
      default: {
        const cols = Object.keys(spec.data[0])
        return (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-gray-700">
                  {cols.map(c => (
                    <th key={c} className="px-3 py-2 text-xs text-gray-400 font-semibold uppercase tracking-wide">
                      {c.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {spec.data.map((row, i) => (
                  <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                    {cols.map(c => (
                      <td key={c} className="px-3 py-2 text-gray-300">{String(row[c] ?? '—')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
    }
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      {spec.title && <h3 className="font-semibold text-white mb-1">{spec.title}</h3>}
      {spec.description && <p className="text-xs text-gray-400 mb-4">{spec.description}</p>}
      {renderChart()}
    </div>
  )
}
