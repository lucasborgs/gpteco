'use client'

import { useEffect, useState } from 'react'
import { fetchAnalytics } from '@/lib/api'
import { AnalyticsData } from '@/types/analytics'
import { MetricCard } from '@/components/ui/MetricCard'
import { DataTable } from '@/components/ui/DataTable'
import { DateFilter } from '@/components/ui/DateFilter'
import { BarMusicas } from '@/components/charts/BarMusicas'
import { TreemapGeneros } from '@/components/charts/TreemapGeneros'

export default function MusicasPage() {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [from, setFrom] = useState<string | null>(null)
  const [to, setTo] = useState<string | null>(null)
  const [selectedGenero, setSelectedGenero] = useState<string | null>(null)

  const load = (f?: string | null, t?: string | null) => {
    setLoading(true)
    fetchAnalytics(f ?? from, t ?? to).then(setData).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleDateChange = (f: string | null, t: string | null) => {
    setFrom(f)
    setTo(t)
    load(f, t)
  }

  const taxa = data?.taxa_atendimento

  // Filtra músicas por gênero selecionado
  const allMusicas = data?.top_musicas_all_time ?? []
  const filteredMusicas = selectedGenero
    ? allMusicas.filter(m => m.genero === selectedGenero)
    : allMusicas

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-heading text-content-primary">Músicas</h1>
        <div className="flex items-center gap-2">
          <DateFilter from={from} to={to} onChange={handleDateChange} />
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
            <BarMusicas data={allMusicas.slice(0, 10)} color="#2E86AB" />
          </div>
          <div className="bg-white rounded-xl border border-border shadow-card p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary mb-4">
              Gêneros Mais Pedidos
            </h2>
            <TreemapGeneros
              data={data?.top_generos ?? []}
              detalhe={data?.generos_detalhe ?? []}
              selectedGenero={selectedGenero}
              onGeneroClick={setSelectedGenero}
            />
          </div>
        </div>
      )}

      {!loading && (
        <div className="bg-white rounded-xl border border-border shadow-card">
          <div className="px-4 py-3 bg-gray-50 border-b border-border rounded-t-xl flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary">
              {selectedGenero ? `Músicas — ${selectedGenero}` : 'Todas as Músicas Pedidas'}
            </h2>
            {selectedGenero && (
              <button
                onClick={() => setSelectedGenero(null)}
                className="text-xs text-content-secondary hover:text-content-primary transition-colors"
              >
                Limpar filtro
              </button>
            )}
          </div>
          <DataTable
            headers={['#', 'Artista — Música', 'Gênero', 'Pedidos']}
            rows={filteredMusicas.map((m, i) => [
              <span key="i" className="font-data text-content-secondary">{i + 1}</span>,
              `${m.artista} — ${m.musica}`,
              <span key="g" className="capitalize text-content-secondary">{m.genero || '—'}</span>,
              <span key="p" className="font-data">{m.pedidos}</span>,
            ])}
          />
        </div>
      )}
    </div>
  )
}
