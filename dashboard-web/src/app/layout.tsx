import type { Metadata } from 'next'
import './globals.css'
import { FiltersProvider } from '@/lib/filters-context'

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
      <body className="min-h-screen bg-app-bg">
        <FiltersProvider>
          <main className="min-h-screen">{children}</main>
        </FiltersProvider>
      </body>
    </html>
  )
}
