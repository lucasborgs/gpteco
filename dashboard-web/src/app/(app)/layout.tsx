'use client'

import { FiltersProvider } from '@/lib/filters-context'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <FiltersProvider>
      <main className="min-h-screen bg-app-bg">{children}</main>
    </FiltersProvider>
  )
}
