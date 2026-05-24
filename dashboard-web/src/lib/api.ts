import type { AnalyticsData } from '@/types/analytics'

export async function fetchAnalytics(from?: string | null, to?: string | null): Promise<AnalyticsData> {
  const params = new URLSearchParams()
  if (from) params.set('from', from)
  if (to) params.set('to', to)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`/api/analytics${qs}`, { cache: 'no-store' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.error ?? `HTTP ${res.status}`)
  }
  return res.json()
}
