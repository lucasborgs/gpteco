'use client'

import { useEffect, useMemo, useState } from 'react'
import { fetchAnalytics } from '@/lib/api'
import { AnalyticsData } from '@/types/analytics'
import { MetricCard } from '@/components/ui/MetricCard'
import { DataTable } from '@/components/ui/DataTable'
import { DateFilter } from '@/components/ui/DateFilter'
import { HeatmapHorarios } from '@/components/charts/HeatmapHorarios'
import { TreemapGeneros } from '@/components/charts/TreemapGeneros'
import { LineVolumeDia } from '@/components/charts/LineVolumeDia'

const DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

function extractDdMm(dataPedido: string): string {
  return dataPedido.split(/[,\s]/)[0].slice(0, 5)
}

export default function GeralPage() {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [from, setFrom] = useState<string | null>(null)
  const [to, setTo] = useState<string | null>(null)
  const [selectedCells, setSelectedCells] = useState<Set<string>>(new Set())
  const [selectedGeneros, setSelectedGeneros] = useState<Set<string>>(new Set())
  const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set())

  const load = (f?: string | null, t?: string | null) => {
    setLoading(true)
    fetchAnalytics(f ?? from, t ?? to).then(setData).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleDateChange = (f: string | null, t: string | null) => {
    setFrom(f)
    setTo(t)
    setSelectedCells(new Set())
    setSelectedGeneros(new Set())
    setSelectedDates(new Set())
    load(f, t)
  }

  const taxa = data?.taxa_atendimento
  const hasFilters = selectedCells.size > 0 || selectedGeneros.size > 0 || selectedDates.size > 0

  // --- Cross-filtering bidirecional ---
  // Cada visualização recebe dados filtrados pelos OUTROS filtros (não pelo próprio)

  // Aplica filtros dimensionais sobre todos os pedidos (incluindo falhas)
  const applyFilters = (pedidos: typeof data extends null ? never : NonNullable<typeof data>['pedidos_individuais'],
    skipCells = false, skipGeneros = false, skipDates = false) => {
    let result = pedidos
    if (!skipCells && selectedCells.size > 0)
      result = result.filter(p => selectedCells.has(`${p.hora}-${p.dia_semana}`))
    if (!skipGeneros && selectedGeneros.size > 0)
      result = result.filter(p => selectedGeneros.has(p.genero))
    if (!skipDates && selectedDates.size > 0)
      result = result.filter(p => selectedDates.has(extractDdMm(p.data_pedido)))
    return result
  }

  // Todos os pedidos filtrados (incluindo falhas) — para MetricCards
  const filteredAll = useMemo(() => {
    return applyFilters(data?.pedidos_individuais ?? [])
  }, [data, selectedCells, selectedGeneros, selectedDates])

  // Apenas pedidos com sucesso filtrados — para tabela e visualizações
  const filteredPedidos = useMemo(() => {
    return filteredAll.filter(p => p.sucesso)
  }, [filteredAll])

  // Heatmap: filtrado por gênero + datas (NÃO por cells), apenas sucesso
  const filteredHeatmapData = useMemo(() => {
    if (selectedGeneros.size === 0 && selectedDates.size === 0) return data?.heatmap_pedidos ?? []
    const pedidos = applyFilters(data?.pedidos_individuais ?? [], true, false, false)
      .filter(p => p.sucesso)
    const matrix: Record<string, number> = {}
    pedidos.forEach(p => {
      const key = `${p.hora}-${p.dia_semana}`
      matrix[key] = (matrix[key] || 0) + 1
    })
    return Object.entries(matrix).map(([key, count]) => {
      const [hora, dia] = key.split('-').map(Number)
      return { hora, dia_semana: dia, pedidos: count }
    })
  }, [data, selectedGeneros, selectedDates])

  // Heatmap detalhe: filtrado por gênero + datas, apenas sucesso
  const filteredHeatmapDetalhe = useMemo(() => {
    if (selectedGeneros.size === 0 && selectedDates.size === 0) return data?.heatmap_detalhe ?? []
    const pedidos = applyFilters(data?.pedidos_individuais ?? [], true, false, false)
      .filter(p => p.sucesso && p.artista && p.musica)
    const counts: Record<string, Record<string, number>> = {}
    pedidos.forEach(p => {
      const cellKey = `${p.hora}-${p.dia_semana}`
      if (!counts[cellKey]) counts[cellKey] = {}
      const songKey = `${p.artista}|||${p.musica}`
      counts[cellKey][songKey] = (counts[cellKey][songKey] || 0) + 1
    })
    return Object.entries(counts).flatMap(([cellKey, songs]) => {
      const [hora, dia] = cellKey.split('-').map(Number)
      return Object.entries(songs)
        .sort((a, b) => b[1] - a[1])
        .map(([songKey, count]) => {
          const [artista, musica] = songKey.split('|||')
          return { hora, dia_semana: dia, artista, musica, pedidos: count }
        })
    })
  }, [data, selectedGeneros, selectedDates])

  // Treemap: filtrado por heatmap + datas (NÃO por gêneros), apenas sucesso
  const filteredGeneros = useMemo(() => {
    if (selectedCells.size === 0 && selectedDates.size === 0) return data?.top_generos ?? []
    const pedidos = applyFilters(data?.pedidos_individuais ?? [], false, true, false)
      .filter(p => p.sucesso)
    const counts: Record<string, number> = {}
    pedidos.forEach(p => {
      if (p.genero) counts[p.genero] = (counts[p.genero] || 0) + 1
    })
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([genero, pedidos]) => ({ genero, pedidos }))
  }, [data, selectedCells, selectedDates])

  // Treemap detalhe: filtrado por heatmap + datas, apenas sucesso
  const filteredGenerosDetalhe = useMemo(() => {
    if (selectedCells.size === 0 && selectedDates.size === 0) return data?.generos_detalhe ?? []
    const pedidos = applyFilters(data?.pedidos_individuais ?? [], false, true, false)
      .filter(p => p.sucesso && p.genero)
    const counts: Record<string, Record<string, number>> = {}
    pedidos.forEach(p => {
      if (!p.genero) return
      if (!counts[p.genero]) counts[p.genero] = {}
      const key = `${p.artista}|||${p.musica}`
      counts[p.genero][key] = (counts[p.genero][key] || 0) + 1
    })
    return Object.entries(counts).flatMap(([genero, songs]) =>
      Object.entries(songs)
        .sort((a, b) => b[1] - a[1])
        .map(([key, pedidos]) => {
          const [artista, musica] = key.split('|||')
          return { genero, artista, musica, pedidos }
        })
    )
  }, [data, selectedCells, selectedDates])

  // Volume dia: filtrado por heatmap + gênero (NÃO por datas)
  const filteredVolumeDia = useMemo(() => {
    if (selectedCells.size === 0 && selectedGeneros.size === 0) return data?.volume_dia_mes ?? []
    const pedidos = applyFilters(data?.pedidos_individuais ?? [], false, false, true)
    const counts: Record<string, number> = {}
    pedidos.forEach(p => {
      const ddmm = extractDdMm(p.data_pedido)
      counts[ddmm] = (counts[ddmm] || 0) + 1
    })
    return Object.entries(counts)
      .sort((a, b) => {
        const [da, ma] = a[0].split('/')
        const [db, mb] = b[0].split('/')
        return (ma + da).localeCompare(mb + db)
      })
      .map(([dia, pedidos]) => ({ dia, pedidos }))
  }, [data, selectedCells, selectedGeneros])

  // --- Chips de filtros ativos ---
  const filterChips = useMemo(() => {
    const chips: { label: string; onRemove: () => void }[] = []

    const selectedHoras = new Set<number>()
    const selectedDias = new Set<number>()
    selectedCells.forEach(key => {
      const [h, d] = key.split('-').map(Number)
      selectedHoras.add(h)
      selectedDias.add(d)
    })

    for (const dia of Array.from(selectedDias)) {
      const allHoras = Array.from({ length: 24 }, (_, h) => `${h}-${dia}`)
      if (allHoras.every(k => selectedCells.has(k))) {
        chips.push({
          label: DIAS[dia],
          onRemove: () => {
            const next = new Set(selectedCells)
            allHoras.forEach(k => next.delete(k))
            setSelectedCells(next)
          },
        })
      }
    }

    for (const hora of Array.from(selectedHoras)) {
      const allDias = Array.from({ length: 7 }, (_, d) => `${hora}-${d}`)
      if (allDias.every(k => selectedCells.has(k))) {
        chips.push({
          label: `${hora}h`,
          onRemove: () => {
            const next = new Set(selectedCells)
            allDias.forEach(k => next.delete(k))
            setSelectedCells(next)
          },
        })
      }
    }

    selectedCells.forEach(key => {
      const [h, d] = key.split('-').map(Number)
      const isFullHora = Array.from({ length: 7 }, (_, di) => `${h}-${di}`).every(k => selectedCells.has(k))
      const isFullDia = Array.from({ length: 24 }, (_, hi) => `${hi}-${d}`).every(k => selectedCells.has(k))
      if (!isFullHora && !isFullDia) {
        chips.push({
          label: `${DIAS[d]} ${h}h`,
          onRemove: () => {
            const next = new Set(selectedCells)
            next.delete(key)
            setSelectedCells(next)
          },
        })
      }
    })

    selectedGeneros.forEach(g => {
      chips.push({
        label: g,
        onRemove: () => {
          const next = new Set(selectedGeneros)
          next.delete(g)
          setSelectedGeneros(next)
        },
      })
    })

    selectedDates.forEach(d => {
      chips.push({
        label: d,
        onRemove: () => {
          const next = new Set(selectedDates)
          next.delete(d)
          setSelectedDates(next)
        },
      })
    })

    return chips
  }, [selectedCells, selectedGeneros, selectedDates])

  const clearFilters = () => {
    setSelectedCells(new Set())
    setSelectedGeneros(new Set())
    setSelectedDates(new Set())
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-heading text-content-primary">Geral</h1>
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
          <MetricCard
            label="Total de Pedidos"
            value={hasFilters ? filteredAll.length : (taxa?.total ?? 0)}
          />
          <MetricCard
            label="Atendidos"
            value={hasFilters ? filteredPedidos.length : (taxa?.sucesso ?? 0)}
          />
          <MetricCard
            label="Taxa de Sucesso"
            value={(() => {
              if (!hasFilters) return `${taxa?.taxa_sucesso_pct ?? 0}%`
              const total = filteredAll.length
              if (total === 0) return '0%'
              return `${Math.round(filteredPedidos.length / total * 1000) / 10}%`
            })()}
          />
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="lg:row-span-2 h-[500px] bg-gray-200 rounded-xl animate-pulse" />
          <div className="h-60 bg-gray-200 rounded-xl animate-pulse" />
          <div className="h-60 bg-gray-200 rounded-xl animate-pulse" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="lg:row-span-2 bg-white rounded-xl border border-border shadow-card p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary mb-4">
              Mapa da Audiência
            </h2>
            <HeatmapHorarios
              data={filteredHeatmapData}
              detalhe={filteredHeatmapDetalhe}
              selectedCells={selectedCells}
              onSelectionChange={setSelectedCells}
            />
          </div>
          <div className="bg-white rounded-xl border border-border shadow-card p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary mb-4">
              Gêneros Mais Pedidos
            </h2>
            <TreemapGeneros
              data={filteredGeneros}
              detalhe={filteredGenerosDetalhe}
              selectedGeneros={selectedGeneros}
              onGeneroClick={setSelectedGeneros}
            />
          </div>
          <div className="bg-white rounded-xl border border-border shadow-card p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary mb-4">
              Volume por Dia
            </h2>
            <LineVolumeDia
              data={filteredVolumeDia}
              selectedDates={selectedDates}
              onSelectionChange={setSelectedDates}
            />
          </div>
        </div>
      )}

      {!loading && (
        <div className="bg-white rounded-xl border border-border shadow-card">
          <div className="px-4 py-3 bg-gray-50 border-b border-border rounded-t-xl">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-content-secondary">
                Todos os Pedidos
              </h2>
              {hasFilters && (
                <button
                  onClick={clearFilters}
                  className="text-xs text-content-secondary hover:text-content-primary transition-colors"
                >
                  Limpar filtros
                </button>
              )}
            </div>
            {filterChips.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {filterChips.map((chip, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full capitalize"
                  >
                    {chip.label}
                    <button
                      onClick={chip.onRemove}
                      className="hover:text-primary-hover font-bold ml-0.5"
                    >
                      x
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
          <DataTable
            headers={['#', 'Data/Hora', 'Artista — Música', 'Gênero']}
            rows={filteredPedidos.map((p, i) => [
              <span key="i" className="font-data text-content-secondary">{i + 1}</span>,
              <span key="d" className="font-data text-content-secondary whitespace-nowrap">{p.data_pedido}</span>,
              `${p.artista} — ${p.musica}`,
              <span key="g" className="capitalize text-content-secondary">{p.genero || '—'}</span>,
            ])}
          />
        </div>
      )}
    </div>
  )
}
