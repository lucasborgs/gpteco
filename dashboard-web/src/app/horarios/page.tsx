'use client'

import { useEffect, useState } from 'react'
import { fetchAnalytics } from '@/lib/api'
import { AnalyticsData } from '@/types/analytics'
import { HeatmapHorarios } from '@/components/charts/HeatmapHorarios'
import { BarDiaSemana } from '@/components/charts/BarDiaSemana'

export default function HorariosPage() {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    fetchAnalytics().then(d => { setData(d); setLoading(false) })
  }

  useEffect(() => { load() }, [])

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-heading text-content-primary">Horários de Pico</h1>
        <button
          onClick={load}
          className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-white hover:bg-primary-hover transition-colors"
        >
          Atualizar
        </button>
      </div>

      <div className="bg-white rounded-xl border border-border shadow-card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary mb-1">
          Mapa de Calor — Hora × Dia da Semana
        </h2>
        <p className="text-xs text-content-secondary mb-4">
          Identifique os blocos mais quentes para precificar cotas de anúncio.
        </p>
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
