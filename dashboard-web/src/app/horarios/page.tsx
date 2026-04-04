'use client'

import { useEffect, useState } from 'react'
import { fetchAnalytics } from '@/lib/api'
import { AnalyticsData } from '@/types/analytics'
import { DateFilter } from '@/components/ui/DateFilter'
import { HeatmapHorarios } from '@/components/charts/HeatmapHorarios'
import { BarDiaSemana } from '@/components/charts/BarDiaSemana'

export default function HorariosPage() {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState('all')

  const load = (d?: string) => {
    setLoading(true)
    fetchAnalytics(d ?? days).then(setData).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleDaysChange = (d: string) => {
    setDays(d)
    load(d)
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-heading text-content-primary">Horários de Pico</h1>
        <div className="flex items-center gap-2">
          <DateFilter value={days} onChange={handleDaysChange} />
          <button
            onClick={() => load()}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-white hover:bg-primary-hover transition-colors"
          >
            Atualizar
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-border shadow-card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary mb-4">
          Mapa de Calor — Hora × Dia da Semana
        </h2>
        {loading ? (
          <div className="h-64 bg-gray-200 rounded-xl animate-pulse" />
        ) : (
          <HeatmapHorarios data={data?.heatmap_pedidos ?? []} />
        )}
      </div>

      <div className="bg-white rounded-xl border border-border shadow-card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary mb-4">
          Volume por Dia da Semana — Histórico
        </h2>
        {loading ? (
          <div className="h-56 bg-gray-200 rounded-xl animate-pulse" />
        ) : (
          <BarDiaSemana data={data?.pico_por_dia_semana ?? []} />
        )}
      </div>
    </div>
  )
}
