import type { ReactNode } from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'

interface Props {
  title: string
  value: string | number
  icon: ReactNode
  trend?: number      // percentage change, positive = good
  subtitle?: string
  loading?: boolean
}

export function KPICard({ title, value, icon, trend, subtitle, loading }: Props) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <p className="text-sm text-gray-400 font-medium">{title}</p>
        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
          {icon}
        </div>
      </div>

      {loading ? (
        <div className="h-8 w-24 bg-gray-800 rounded animate-pulse mb-2" />
      ) : (
        <p className="text-3xl font-bold text-white mb-1">{value}</p>
      )}

      {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}

      {trend !== undefined && (
        <div className={`flex items-center gap-1 mt-2 text-xs font-medium ${trend >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {trend >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          <span>{Math.abs(trend)}% vs prev period</span>
        </div>
      )}
    </div>
  )
}
