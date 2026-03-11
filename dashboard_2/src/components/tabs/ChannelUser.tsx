import { useEffect, useState } from 'react'
import { fetchChannelsHealth, fetchUsersPerformance } from '../../api'
import type { Filters, ChannelHealth, UserPerformance } from '../../types'

interface Props { filters: Filters }

function statusBadge(rate: number) {
  if (rate >= 70) return 'bg-green-900/40 text-green-400'
  if (rate >= 40) return 'bg-yellow-900/40 text-yellow-400'
  return 'bg-red-900/40 text-red-400'
}

const fmtSecs = (s: number) => {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export function ChannelUser({ filters }: Props) {
  const [channels, setChannels] = useState<ChannelHealth[]>([])
  const [users, setUsers] = useState<UserPerformance[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchChannelsHealth(filters.client_id),
      fetchUsersPerformance(filters),
    ])
      .then(([ch, us]) => { setChannels(ch); setUsers(us) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [filters])

  if (loading) return <div className="text-gray-500 text-sm">Loading…</div>

  return (
    <div className="space-y-8">
      {/* Channel health table */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Channel Health</h2>
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-xs text-gray-400 uppercase tracking-wide">
                <th className="px-4 py-3 text-left">Channel</th>
                <th className="px-4 py-3 text-right">Created</th>
                <th className="px-4 py-3 text-right">Published</th>
                <th className="px-4 py-3 text-right">Publish Rate</th>
                <th className="px-4 py-3 text-right">Active Users</th>
                <th className="px-4 py-3 text-left">Last Activity</th>
              </tr>
            </thead>
            <tbody>
              {channels.map(ch => (
                <tr key={ch.channel_id} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="font-medium text-white">{ch.channel_name}</div>
                    <div className="text-xs text-gray-500">{ch.channel_code} · {ch.primary_language}</div>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-300">{ch.total_created.toLocaleString()}</td>
                  <td className="px-4 py-3 text-right text-gray-300">{ch.total_published.toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${statusBadge(ch.publish_rate_pct)}`}>
                      {ch.publish_rate_pct}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-300">{ch.active_users}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{ch.last_activity ? ch.last_activity.slice(0, 10) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* User performance table */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">User Performance</h2>
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-xs text-gray-400 uppercase tracking-wide">
                <th className="px-4 py-3 text-left">User</th>
                <th className="px-4 py-3 text-left">Channel</th>
                <th className="px-4 py-3 text-right">Created</th>
                <th className="px-4 py-3 text-right">Published</th>
                <th className="px-4 py-3 text-right">Publish Rate</th>
                <th className="px-4 py-3 text-right">Uploaded Duration</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={`${u.user_id}-${u.channel_id}`} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="font-medium text-white">{u.user_name}</div>
                    <div className="text-xs text-gray-500">{u.role}{u.is_bot ? ' · bot' : ''}</div>
                  </td>
                  <td className="px-4 py-3 text-gray-400">{u.channel_code}</td>
                  <td className="px-4 py-3 text-right text-gray-300">{u.created_count.toLocaleString()}</td>
                  <td className="px-4 py-3 text-right text-gray-300">{u.published_count.toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${statusBadge(u.publish_rate_pct)}`}>
                      {u.publish_rate_pct}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-400 text-xs">{fmtSecs(u.total_uploaded_duration_secs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
