import type { AnalyticsData } from '@/types/analytics'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8002'

export async function fetchAnalytics(): Promise<AnalyticsData> {
  const res = await fetch(`${API_URL}/analytics`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to fetch analytics: ${res.status}`)
  return res.json()
}
