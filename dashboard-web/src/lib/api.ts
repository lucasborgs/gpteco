import type { AnalyticsData } from '@/types/analytics'

export async function fetchAnalytics(days?: string): Promise<AnalyticsData> {
  const params = days && days !== 'all' ? `?days=${days}` : ''
  const res = await fetch(`/api/analytics${params}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to fetch analytics: ${res.status}`)
  return res.json()
}
