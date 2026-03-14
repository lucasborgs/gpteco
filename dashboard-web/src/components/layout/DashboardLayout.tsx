'use client'

import AppSidebar from './AppSidebar'

interface DashboardLayoutProps {
  title: string
  onRefresh?: () => void
  children: React.ReactNode
}

export default function DashboardLayout({ title, onRefresh, children }: DashboardLayoutProps) {
  return (
    <div className="flex min-h-screen bg-app-bg">
      <AppSidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 bg-white border-b border-border flex items-center justify-between px-6 shrink-0">
          <h1 className="font-heading font-bold text-content-primary text-lg">{title}</h1>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="text-sm font-medium text-content-secondary hover:text-content-primary border border-border rounded-lg px-3 py-1.5 hover:bg-gray-50 transition-colors"
            >
              Atualizar
            </button>
          )}
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  )
}
