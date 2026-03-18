import type { Metadata } from 'next'
import './globals.css'
import AppSidebar from '@/components/layout/AppSidebar'

export const metadata: Metadata = {
  title: 'Rádio Dashboard',
  description: 'Analytics da rádio FM',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="pt-BR">
      <body className="flex min-h-screen bg-app-bg">
        <AppSidebar />
        <main className="flex-1 min-w-0 overflow-auto">{children}</main>
      </body>
    </html>
  )
}
