import type {
  FilterOptions,
  Filters,
  KpiTotals,
  SummaryRow,
  ChannelHealth,
  UserPerformance,
  Insight,
  NLQResult,
} from './types'

const BASE = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000'

async function get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const url = new URL(BASE + path)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== null && v !== undefined) url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

// ── Filters ──────────────────────────────────────────────────────────────────

export function fetchFilterOptions(client_id: number): Promise<FilterOptions> {
  return get('/filters/options', { client_id })
}

// ── KPI totals ────────────────────────────────────────────────────────────────

export function fetchKpiTotals(f: Filters): Promise<KpiTotals> {
  return get('/kpis/totals', {
    client_id: f.client_id,
    channel_id: f.channel_id,
    date_from: f.date_from,
    date_to: f.date_to,
  })
}

// ── Monthly summary ──────────────────────────────────────────────────────────

export async function fetchKpiSummary(f: Filters): Promise<SummaryRow[]> {
  const res = await get<{ data: SummaryRow[] }>('/kpis/summary', {
    client_id: f.client_id,
    channel_id: f.channel_id,
    date_from: f.date_from,
    date_to: f.date_to,
  })
  return res.data
}

// ── Channel health ────────────────────────────────────────────────────────────

export async function fetchChannelsHealth(client_id: number): Promise<ChannelHealth[]> {
  const res = await get<{ data: ChannelHealth[] }>('/channels/health', { client_id })
  return res.data
}

// ── User performance ──────────────────────────────────────────────────────────

export async function fetchUsersPerformance(f: Filters): Promise<UserPerformance[]> {
  const res = await get<{ data: UserPerformance[] }>('/users/performance', {
    client_id: f.client_id,
    channel_id: f.channel_id,
  })
  return res.data
}

// ── Insights ──────────────────────────────────────────────────────────────────

export async function fetchInsights(client_id: number, insight_type?: string): Promise<Insight[]> {
  const res = await get<{ data: Insight[] }>('/insights/', { client_id, insight_type })
  return res.data
}

// ── NLQ ───────────────────────────────────────────────────────────────────────

export function queryNLQ(question: string, client_id: number): Promise<NLQResult> {
  return post('/nlq/query', { question, client_id })
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Convert date-preset string to { date_from, date_to } ISO strings. */
export function presetToDates(preset: string): { date_from: string | null; date_to: string | null } {
  const now = new Date()
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  if (preset === 'all') return { date_from: null, date_to: null }
  const days = preset === '30d' ? 30 : preset === '90d' ? 90 : 180
  const from = new Date(now)
  from.setDate(from.getDate() - days)
  return { date_from: iso(from), date_to: iso(now) }
}
