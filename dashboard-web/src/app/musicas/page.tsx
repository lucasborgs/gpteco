'use client'

import { useEffect, useState } from 'react'
import { fetchAnalytics } from '@/lib/api'
import { AnalyticsData } from '@/types/analytics'
import { MetricCard } from '@/components/ui/MetricCard'
import { DataTable } from '@/components/ui/DataTable'
import { BarMusicas } from '@/components/charts/BarMusicas'
import { TreemapArtistas } from '@/components/charts/TreemapArtistas'

const TENDENCIA_CONFIG = {
  up:   { label: '↑ subiu',   className: 'text-green-600 font-medium' },
  down: { label: '↓ caiu',    className: 'text-red-600 font-medium' },
  same: { label: '= estável', className: 'text-gray-500' },
  new:  { label: '★ novo',    className: 'text-[#1DB954] font-medium' },
}

export default function MusicasPage() {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    fetchAnalytics().then(d => { setData(d) }).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const taxa = data?.taxa_atendimento

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-heading text-content-primary">Músicas</h1>
        <button
          onClick={load}
          className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-white hover:bg-primary-hover transition-colors"
        >
          Atualizar
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-28 bg-gray-200 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <MetricCard label="Total de Pedidos" value={taxa?.total ?? 0} />
          <MetricCard label="Atendidos" value={taxa?.sucesso ?? 0} />
          <MetricCard label="Taxa de Sucesso" value={`${taxa?.taxa_sucesso_pct ?? 0}%`} />
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
              Top 10 Histórico
            </h2>
            <BarMusicas data={data?.top_musicas_all_time ?? []} color="#2E86AB" />
          </div>
          <div className="bg-white rounded-xl border border-border shadow-card p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary mb-4">
              Artistas Mais Pedidos
            </h2>
            <TreemapArtistas data={data?.top_artistas ?? []} />
          </div>
        </div>
      )}

      {!loading && (
        <div className="bg-white rounded-xl border border-border shadow-card">
          <div className="px-4 py-3 bg-gray-50 border-b border-border rounded-t-xl">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary">
              Trending — Top 5 Esta Semana vs. Semana Anterior
            </h2>
          </div>
          <DataTable
            headers={['Tendência', 'Artista — Música', 'Pedidos']}
            rows={(data?.tendencia_musicas ?? []).map(t => {
              const cfg = TENDENCIA_CONFIG[t.tendencia as keyof typeof TENDENCIA_CONFIG]
              return [
                <span key="t" className={cfg.className}>{cfg.label}</span>,
                `${t.artista} — ${t.musica}`,
                <span key="p" className="font-data">{t.pedidos}</span>,
              ]
            })}
          />
        </div>
      )}
    </div>
  )
}
