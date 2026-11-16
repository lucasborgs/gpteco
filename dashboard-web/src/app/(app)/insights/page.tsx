'use client'

import { InsightsPanel } from '@/components/InsightsPanel'

// Aba mobile dedicada à IA. No desktop o painel já aparece no rail à direita
// de /painel; aqui ele ocupa a tela inteira (descontando a bottom nav).
export default function InsightsPage() {
  return (
    <div className="h-[calc(100dvh-3.5rem)] md:h-screen flex flex-col bg-white">
      <InsightsPanel />
    </div>
  )
}
