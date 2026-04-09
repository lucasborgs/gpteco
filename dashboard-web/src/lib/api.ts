import type { AnalyticsData } from '@/types/analytics'

export async function fetchAnalytics(from?: string | null, to?: string | null): Promise<AnalyticsData> {
  const params = new URLSearchParams()
  if (from) params.set('from', from)
  if (to) params.set('to', to)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`/api/analytics${qs}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to fetch analytics: ${res.status}`)
  return res.json()
}
