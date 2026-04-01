import type { AnalyticsData } from '@/types/analytics'

export async function fetchAnalytics(): Promise<AnalyticsData> {
  const res = await fetch('/api/analytics', { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to fetch analytics: ${res.status}`)
  return res.json()
}
