'use client'

import { useEffect, useState } from 'react'
import { fetchAnalytics } from '@/lib/api'
import { AnalyticsData } from '@/types/analytics'
import { MetricCard } from '@/components/ui/MetricCard'
import { DataTable } from '@/components/ui/DataTable'
import { DateFilter } from '@/components/ui/DateFilter'
import { DonutAtendimento } from '@/components/charts/DonutAtendimento'
import { BarDDD } from '@/components/charts/BarDDD'

export default function AudienciaPage() {
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

  const taxa = data?.taxa_atendimento
  const ouvinteUnicos = new Set(data?.ouvintes_engajados.map(o => o.telefone_formatado)).size
  const fanFrequentes = taxa?.por_motivo?.cooldown ?? 0
  const demandaReprimida = taxa?.por_motivo?.nao_flashback ?? 0

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-heading text-content-primary">Audiência</h1>
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

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-28 bg-gray-200 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <MetricCard label="Ouvintes na Tabela" value={ouvinteUnicos} />
          <MetricCard label="Fãs Frequentes" value={fanFrequentes} hint="Tentaram pedir mais de uma vez" />
          <MetricCard label="Demanda Reprimida" value={demandaReprimida} hint="Fora do repertório atual" />
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="h-72 bg-gray-200 rounded-xl animate-pulse" />
          <div className="h-72 bg-gray-200 rounded-xl animate-pulse" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="bg-white rounded-xl border border-border shadow-card p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary mb-4">
              Taxa de Atendimento
            </h2>
            {taxa && <DonutAtendimento data={taxa} />}
          </div>
          <div className="bg-white rounded-xl border border-border shadow-card p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary mb-4">
              Alcance por DDD
            </h2>
            <BarDDD data={data?.breakdown_ddd ?? []} />
          </div>
        </div>
      )}

      {!loading && (
        <div className="bg-white rounded-xl border border-border shadow-card">
          <div className="px-4 py-3 bg-gray-50 border-b border-border rounded-t-xl">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary">
              Ouvintes Mais Engajados
            </h2>
          </div>
          <DataTable
            headers={['Número', 'Pedidos', 'Primeiro Pedido']}
            rows={(data?.ouvintes_engajados ?? []).map(o => [
              <span key="n" className="font-data text-content-secondary">{o.telefone_formatado}</span>,
              <span key="p" className="font-data">{o.pedidos}</span>,
              o.primeiro_pedido ?? '—',
            ])}
          />
        </div>
      )}
    </div>
  )
}
