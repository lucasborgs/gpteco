'use client'

import { useMemo, useState } from 'react'
import { useFilters } from '@/lib/filters-context'
import { useFilteredAnalytics } from '@/lib/useFilteredAnalytics'
import { DataTable } from '@/components/ui/DataTable'
import { DateFilter } from '@/components/ui/DateFilter'
import { HeatmapHorarios } from '@/components/charts/HeatmapHorarios'
import { BarGeneros } from '@/components/charts/BarGeneros'
import { LineVolumeDia } from '@/components/charts/LineVolumeDia'
import { DonutAtendimento } from '@/components/charts/DonutAtendimento'
import { InsightsPanel } from '@/components/InsightsPanel'

const DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
const MOTIVO_LABELS: Record<string, string> = {
  sucesso: 'Atendidos',
  cooldown: 'Cooldown',
  nao_flashback: 'Fora do repertório',
  nao_identificado: 'Não identificado',
  inapropriado: 'Inapropriado',
  erro_tecnico: 'Erro técnico',
  desconhecido: 'Outros',
}

export default function PainelPage() {
  const {
    from, to, setDateRange, reload, loading,
    selectedCells, setSelectedCells,
    selectedGeneros, setSelectedGeneros,
    selectedDates, setSelectedDates,
    selectedMotivos, setSelectedMotivos,
    hasCrossFilters, clearCrossFilters,
  } = useFilters()
  const {
    filteredAll, filteredPedidos, filteredHeatmapData, filteredHeatmapDetalhe,
    filteredGeneros, filteredGenerosDetalhe, filteredVolumeDia,
    taxa, ouvintes,
  } = useFilteredAnalytics()

  const [tabela, setTabela] = useState<'pedidos' | 'ouvintes'>('pedidos')
  const [chatOpen, setChatOpen] = useState(false)

  const filterChips = useMemo(() => {
    const chips: { label: string; onRemove: () => void }[] = []
    const selectedHoras = new Set<number>()
    const selectedDias = new Set<number>()
    selectedCells.forEach(key => {
      const [h, d] = key.split('-').map(Number)
      selectedHoras.add(h); selectedDias.add(d)
    })
    for (const dia of Array.from(selectedDias)) {
      const allHoras = Array.from({ length: 24 }, (_, h) => `${h}-${dia}`)
      if (allHoras.every(k => selectedCells.has(k))) {
        chips.push({ label: DIAS[dia], onRemove: () => {
          const next = new Set(selectedCells); allHoras.forEach(k => next.delete(k)); setSelectedCells(next)
        } })
      }
    }
    for (const hora of Array.from(selectedHoras)) {
      const allDias = Array.from({ length: 7 }, (_, d) => `${hora}-${d}`)
      if (allDias.every(k => selectedCells.has(k))) {
        chips.push({ label: `${hora}h`, onRemove: () => {
          const next = new Set(selectedCells); allDias.forEach(k => next.delete(k)); setSelectedCells(next)
        } })
      }
    }
    selectedCells.forEach(key => {
      const [h, d] = key.split('-').map(Number)
      const isFullHora = Array.from({ length: 7 }, (_, di) => `${h}-${di}`).every(k => selectedCells.has(k))
      const isFullDia = Array.from({ length: 24 }, (_, hi) => `${hi}-${d}`).every(k => selectedCells.has(k))
      if (!isFullHora && !isFullDia) {
        chips.push({ label: `${DIAS[d]} ${h}h`, onRemove: () => {
          const next = new Set(selectedCells); next.delete(key); setSelectedCells(next)
        } })
      }
    })
    selectedGeneros.forEach(g => chips.push({ label: g, onRemove: () => {
      const next = new Set(selectedGeneros); next.delete(g); setSelectedGeneros(next)
    } }))
    selectedDates.forEach(d => chips.push({ label: d, onRemove: () => {
      const next = new Set(selectedDates); next.delete(d); setSelectedDates(next)
    } }))
    selectedMotivos.forEach(m => chips.push({ label: MOTIVO_LABELS[m] || m, onRemove: () => {
      const next = new Set(selectedMotivos); next.delete(m); setSelectedMotivos(next)
    } }))
    return chips
  }, [selectedCells, selectedGeneros, selectedDates, selectedMotivos, setSelectedCells, setSelectedGeneros, setSelectedDates, setSelectedMotivos])

  const metrics = [
    { label: 'Total de Pedidos', value: filteredAll.length },
    { label: 'Atendidos', value: filteredPedidos.length },
    {
      label: 'Taxa de Sucesso',
      value: `${filteredAll.length ? Math.round((filteredPedidos.length / filteredAll.length) * 1000) / 10 : 0}%`,
    },
    { label: 'Ouvintes', value: ouvintes.length },
    { label: 'Fãs Frequentes', value: ouvintes.filter(o => o.pedidos >= 2).length, hint: '2+ atendidos' },
  ]

  return (
    <div className="flex flex-col bg-app-bg" style={{ minHeight: '100dvh' }}>

      {/* Header */}
      <header className="h-14 shrink-0 bg-white border-b border-border flex items-center justify-between px-6 gap-3">
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-7 h-7 rounded-md bg-primary flex items-center justify-center">
            <span className="text-white font-heading font-bold text-xs">R</span>
          </div>
          <span className="font-heading font-bold text-content-primary text-base">Rádio FM</span>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <DateFilter from={from} to={to} onChange={setDateRange} />
          <button
            onClick={reload}
            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-white hover:bg-primary-hover transition-colors shrink-0"
          >
            Atualizar
          </button>
          <button
            onClick={() => setChatOpen(o => !o)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors shrink-0 ${
              chatOpen
                ? 'bg-primary text-white border-primary'
                : 'border-border text-content-secondary hover:bg-gray-50 hover:text-content-primary'
            }`}
          >
            ✦ IA
          </button>
        </div>
      </header>

      {/* Linha 1 — Totalizadores compactos */}
      <div className="shrink-0 px-6 py-2 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {loading
          ? [...Array(5)].map((_, i) => (
              <div key={i} className="h-[54px] bg-gray-200 rounded-lg animate-pulse" />
            ))
          : metrics.map(({ label, value, hint }) => (
              <div key={label} className="bg-white rounded-lg border border-border px-3 py-2 relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-0.5 bg-primary" />
                <p className="text-[10px] font-semibold uppercase tracking-wider text-content-secondary leading-tight">{label}</p>
                <p className="font-data text-2xl text-content-primary leading-tight mt-0.5">{value}</p>
                {hint && <p className="text-[10px] text-content-secondary leading-none">{hint}</p>}
              </div>
            ))}
      </div>

      {/* Linhas 2 e 3 — Gráficos (cabem na tela) */}
      <div className="flex-1 min-h-0 px-6 pb-3">
        {loading ? (
          <div className="h-full grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="bg-gray-200 rounded-xl animate-pulse" />
            <div className="flex flex-col gap-4">
              <div className="flex-1 bg-gray-200 rounded-xl animate-pulse" />
              <div className="h-[270px] grid grid-cols-2 gap-4">
                <div className="bg-gray-200 rounded-xl animate-pulse" />
                <div className="bg-gray-200 rounded-xl animate-pulse" />
              </div>
            </div>
          </div>
        ) : (
          <div className="h-full grid grid-cols-1 gap-4 lg:grid-cols-2">

            {/* Esquerda — Mapa da Audiência */}
            <div className="bg-white rounded-xl border border-border p-4 flex flex-col overflow-hidden">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-content-secondary mb-3 shrink-0">
                Mapa da Audiência
              </h2>
              <div className="flex-1 overflow-y-auto min-h-0">
                <HeatmapHorarios
                  data={filteredHeatmapData}
                  detalhe={filteredHeatmapDetalhe}
                  selectedCells={selectedCells}
                  onSelectionChange={setSelectedCells}
                />
              </div>
            </div>

            {/* Direita — Volume e Donut + Gêneros */}
            <div className="flex flex-col gap-4 min-h-0">

              {/* Volume + Taxa — altura fixa, lado a lado */}
              <div className="shrink-0 h-[290px] grid grid-cols-2 gap-4">
                <div className="bg-white rounded-xl border border-border p-4 flex flex-col">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-content-secondary mb-2 shrink-0">
                    Volume por Dia
                  </h2>
                  <div className="flex-1 min-h-0">
                    <LineVolumeDia
                      data={filteredVolumeDia}
                      selectedDates={selectedDates}
                      onSelectionChange={setSelectedDates}
                      height="100%"
                    />
                  </div>
                </div>
                <div className="bg-white rounded-xl border border-border p-4 flex flex-col">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-content-secondary mb-2 shrink-0">
                    Taxa de Atendimento
                  </h2>
                  <div className="flex-1 min-h-0 flex items-center">
                    <DonutAtendimento
                      data={taxa}
                      selectedMotivos={selectedMotivos}
                      onMotivoClick={setSelectedMotivos}
                      compact
                    />
                  </div>
                </div>
              </div>

              {/* Gêneros Mais Pedidos — preenche o espaço disponível */}
              <div className="flex-1 min-h-0 bg-white rounded-xl border border-border p-4 overflow-y-auto">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-content-secondary mb-3">
                  Gêneros Mais Pedidos
                </h2>
                <BarGeneros
                  data={filteredGeneros}
                  detalhe={filteredGenerosDetalhe}
                  selectedGeneros={selectedGeneros}
                  onGeneroClick={setSelectedGeneros}
                />
              </div>

            </div>
          </div>
        )}
      </div>

      {/* Linha 4 — Tabela (scroll para acessar) */}
      {!loading && (
        <div className="px-6 pb-6">
          <div className="bg-white rounded-xl border border-border shadow-card">
            <div className="px-4 py-3 bg-gray-50 border-b border-border rounded-t-xl">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex gap-1">
                  {(['pedidos', 'ouvintes'] as const).map(t => (
                    <button
                      key={t}
                      onClick={() => setTabela(t)}
                      className={`px-3 py-1.5 text-xs font-semibold uppercase tracking-wider rounded-lg transition-colors ${
                        tabela === t ? 'bg-primary/10 text-primary' : 'text-content-secondary hover:bg-gray-100'
                      }`}
                    >
                      {t === 'pedidos' ? 'Pedidos' : 'Ouvintes'}
                    </button>
                  ))}
                </div>
                {hasCrossFilters && (
                  <button
                    onClick={clearCrossFilters}
                    className="text-xs text-content-secondary hover:text-content-primary transition-colors"
                  >
                    Limpar filtros
                  </button>
                )}
              </div>
              {filterChips.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {filterChips.map((chip, i) => (
                    <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full capitalize">
                      {chip.label}
                      <button onClick={chip.onRemove} className="hover:text-primary-hover font-bold ml-0.5">x</button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            {tabela === 'pedidos' ? (
              <DataTable
                headers={['#', 'Data/Hora', 'Artista — Música', 'Gênero']}
                rows={filteredPedidos.map((p, i) => [
                  <span key="i" className="font-data text-content-secondary">{i + 1}</span>,
                  <span key="d" className="font-data text-content-secondary whitespace-nowrap">{p.data_pedido}</span>,
                  `${p.artista} — ${p.musica}`,
                  <span key="g" className="capitalize text-content-secondary">{p.genero || '—'}</span>,
                ])}
              />
            ) : (
              <DataTable
                headers={['Número', 'Pedidos', 'Primeiro Pedido']}
                rows={ouvintes.map(o => [
                  <span key="n" className="font-data text-content-secondary">{o.telefone_formatado}</span>,
                  <span key="p" className="font-data">{o.pedidos}</span>,
                  o.primeiro_pedido ?? '—',
                ])}
              />
            )}
          </div>
        </div>
      )}

      {/* Drawer de chat — slide-over da direita */}
      <div
        className={`fixed inset-0 z-30 transition-opacity duration-200 bg-black/20 ${
          chatOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        onClick={() => setChatOpen(false)}
      />
      <div
        className={`fixed right-0 top-0 h-full w-[400px] bg-white border-l border-border shadow-2xl z-40 flex flex-col transition-transform duration-200 ${
          chatOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <InsightsPanel />
      </div>

    </div>
  )
}
