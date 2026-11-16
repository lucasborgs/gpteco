import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AKAPO — Assistente Virtual Musical para Rádios',
  description:
    'Transforme o WhatsApp da sua rádio em engajamento. Assistente virtual musical white-label com automação de pedidos, curadoria inteligente e analytics.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="pt-BR" className="motion-safe:scroll-smooth">
      <body className="min-h-screen bg-white text-content-primary font-sans antialiased">
        {children}
      </body>
    </html>
  )
}
