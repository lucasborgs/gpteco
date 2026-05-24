'use client'

import { useMemo } from 'react'
import { useFilters } from './filters-context'
import { extractDdMm, formatTelefone } from './utils'
import type {
  PedidoIndividual,
  TaxaAtendimento,
  OuvinteEngajado,
} from '@/types/analytics'

/**
 * Deriva todas as visões filtradas a partir dos pedidos individuais + filtros
 * ativos. É a fonte única de verdade do cross-filtering bidirecional: cada
 * visão recebe os dados filtrados pelos OUTROS filtros (nunca pelo próprio).
 *
 * Consumido tanto pela página /painel (gráficos/tabelas) quanto pelo
 * InsightsPanel (resumo enviado à LLM), garantindo que a LLM enxergue
 * exatamente o mesmo recorte mostrado na tela.
 */
export function useFilteredAnalytics() {
  const {
    data,
    selectedCells,
    selectedGeneros,
    selectedDates,
    selectedMotivos,
  } = useFilters()

  const pedidos = useMemo(() => data?.pedidos_individuais ?? [], [data])

  const applyFilters = useMemo(() => {
    return (
      rows: PedidoIndividual[],
      skipCells = false,
      skipGeneros = false,
      skipDates = false,
      skipMotivos = false,
    ) => {
      let result = rows
      if (!skipCells && selectedCells.size > 0)
        result = result.filter(p => selectedCells.has(`${p.hora}-${p.dia_semana}`))
      if (!skipGeneros && selectedGeneros.size > 0)
        result = result.filter(p => selectedGeneros.has(p.genero))
      if (!skipDates && selectedDates.size > 0)
        result = result.filter(p => selectedDates.has(extractDdMm(p.data_pedido)))
      if (!skipMotivos && selectedMotivos.size > 0)
        result = result.filter(p => selectedMotivos.has(p.motivo))
      return result
    }
  }, [selectedCells, selectedGeneros, selectedDates, selectedMotivos])

  // Todos os pedidos filtrados (incluindo falhas) — base de métricas e tabelas
  const filteredAll = useMemo(() => applyFilters(pedidos), [applyFilters, pedidos])
  const filteredPedidos = useMemo(() => filteredAll.filter(p => p.sucesso), [filteredAll])

  // Heatmap: ignora seleção de células e de motivo; só sucesso
  const filteredHeatmapData = useMemo(() => {
    if (selectedGeneros.size === 0 && selectedDates.size === 0 && selectedMotivos.size === 0)
      return data?.heatmap_pedidos ?? []
    const rows = applyFilters(pedidos, true, false, false, false).filter(p => p.sucesso)
    const matrix: Record<string, number> = {}
    rows.forEach(p => {
      const key = `${p.hora}-${p.dia_semana}`
      matrix[key] = (matrix[key] || 0) + 1
    })
    return Object.entries(matrix).map(([key, count]) => {
      const [hora, dia] = key.split('-').map(Number)
      return { hora, dia_semana: dia, pedidos: count }
    })
  }, [data, pedidos, applyFilters, selectedGeneros, selectedDates, selectedMotivos])

  const filteredHeatmapDetalhe = useMemo(() => {
    if (selectedGeneros.size === 0 && selectedDates.size === 0 && selectedMotivos.size === 0)
      return data?.heatmap_detalhe ?? []
    const rows = applyFilters(pedidos, true, false, false, false)
      .filter(p => p.sucesso && p.artista && p.musica)
    const counts: Record<string, Record<string, number>> = {}
    rows.forEach(p => {
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
  }, [data, pedidos, applyFilters, selectedGeneros, selectedDates, selectedMotivos])

  // Gêneros: ignora seleção de gênero; só sucesso
  const filteredGeneros = useMemo(() => {
    if (selectedCells.size === 0 && selectedDates.size === 0 && selectedMotivos.size === 0)
      return data?.top_generos ?? []
    const rows = applyFilters(pedidos, false, true, false, false).filter(p => p.sucesso)
    const counts: Record<string, number> = {}
    rows.forEach(p => { if (p.genero) counts[p.genero] = (counts[p.genero] || 0) + 1 })
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([genero, pedidos]) => ({ genero, pedidos }))
  }, [data, pedidos, applyFilters, selectedCells, selectedDates, selectedMotivos])

  const filteredGenerosDetalhe = useMemo(() => {
    if (selectedCells.size === 0 && selectedDates.size === 0 && selectedMotivos.size === 0)
      return data?.generos_detalhe ?? []
    const rows = applyFilters(pedidos, false, true, false, false)
      .filter(p => p.sucesso && p.genero)
    const counts: Record<string, Record<string, number>> = {}
    rows.forEach(p => {
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
  }, [data, pedidos, applyFilters, selectedCells, selectedDates, selectedMotivos])

  // Volume por dia: ignora seleção de datas
  const filteredVolumeDia = useMemo(() => {
    if (selectedCells.size === 0 && selectedGeneros.size === 0 && selectedMotivos.size === 0)
      return data?.volume_dia_mes ?? []
    const rows = applyFilters(pedidos, false, false, true, false)
    // key: "yyyy/mm/dd" for correct cross-year sort; value: { display: "dd/mm", count }
    const counts: Record<string, { display: string; count: number }> = {}
    rows.forEach(p => {
      const parts = p.data_pedido.split(/[,\s]/)[0].split('/')
      const [dd, mm, yyyy] = parts
      const sortKey = `${yyyy}/${mm}/${dd}`
      const display = `${dd}/${mm}`
      if (!counts[sortKey]) counts[sortKey] = { display, count: 0 }
      counts[sortKey].count += 1
    })
    return Object.entries(counts)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([, { display, count }]) => ({ dia: display, pedidos: count }))
  }, [data, pedidos, applyFilters, selectedCells, selectedGeneros, selectedMotivos])

  // Taxa de atendimento: ignora seleção de motivo (donut bidirecional)
  const taxa = useMemo<TaxaAtendimento>(() => {
    const noOtherFilters =
      selectedCells.size === 0 && selectedGeneros.size === 0 && selectedDates.size === 0
    if (noOtherFilters && data?.taxa_atendimento) return data.taxa_atendimento
    const rows = applyFilters(pedidos, false, false, false, true)
    let sucesso = 0
    const por_motivo: Record<string, number> = {}
    rows.forEach(p => {
      if (p.sucesso) sucesso++
      else por_motivo[p.motivo] = (por_motivo[p.motivo] || 0) + 1
    })
    const total = rows.length
    return {
      total,
      sucesso,
      recusado: total - sucesso,
      taxa_sucesso_pct: total ? Math.round((sucesso / total) * 1000) / 10 : 0,
      por_motivo,
    }
  }, [data, pedidos, applyFilters, selectedCells, selectedGeneros, selectedDates])

  // Ouvintes: recalculados a partir dos pedidos com sucesso filtrados.
  // pedidos vêm ordenados por timestamp DESC → a última ocorrência é a mais antiga.
  const ouvintes = useMemo<OuvinteEngajado[]>(() => {
    const map = new Map<string, { pedidos: number; primeiro: string }>()
    filteredPedidos.forEach(p => {
      const cur = map.get(p.numero)
      if (cur) {
        cur.pedidos++
        cur.primeiro = p.data_pedido // mais antigo (lista é DESC)
      } else {
        map.set(p.numero, { pedidos: 1, primeiro: p.data_pedido })
      }
    })
    return Array.from(map.entries())
      .map(([numero, v]) => ({
        telefone_formatado: formatTelefone(numero),
        pedidos: v.pedidos,
        primeiro_pedido: v.primeiro.split(',')[0].trim(),
      }))
      .sort((a, b) => b.pedidos - a.pedidos)
  }, [filteredPedidos])

  const fasFrequentes = useMemo(
    () => ouvintes.filter(o => o.pedidos >= 2).length,
    [ouvintes],
  )

  return {
    filteredAll,
    filteredPedidos,
    filteredHeatmapData,
    filteredHeatmapDetalhe,
    filteredGeneros,
    filteredGenerosDetalhe,
    filteredVolumeDia,
    taxa,
    ouvintes,
    fasFrequentes,
  }
}
