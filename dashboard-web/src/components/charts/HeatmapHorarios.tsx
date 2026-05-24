'use client'

import { useState } from 'react'
import type { HeatmapItem, HeatmapDetalhe } from '@/types/analytics'

interface Props {
  data: HeatmapItem[]
  detalhe: HeatmapDetalhe[]
  selectedCells?: Set<string>
  onSelectionChange?: (cells: Set<string>) => void
}

const DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

function getColor(value: number, max: number): string {
  if (value === 0 || max === 0) return '#f3f4f6'
  const ratio = value / max
  if (ratio < 0.2) return '#dcfce7'
  if (ratio < 0.4) return '#86efac'
  if (ratio < 0.6) return '#22c55e'
  if (ratio < 0.8) return '#16a34a'
  return '#166534'
}

export function HeatmapHorarios({ data, detalhe, selectedCells, onSelectionChange }: Props) {
  const [hovered, setHovered] = useState<{ hora: number; dia: number } | null>(null)
  const hasSelection = selectedCells && selectedCells.size > 0

  const matrix: number[][] = Array.from({ length: 24 }, () => Array(7).fill(0))
  data.forEach(({ hora, dia_semana, pedidos }) => {
    matrix[hora][dia_semana] = pedidos
  })
  const max = Math.max(...data.map(d => d.pedidos), 1)

  const detalhePorCelula: Record<string, HeatmapDetalhe[]> = {}
  detalhe.forEach(d => {
    const key = `${d.hora}-${d.dia_semana}`
    if (!detalhePorCelula[key]) detalhePorCelula[key] = []
    if (detalhePorCelula[key].length < 5) {
      detalhePorCelula[key].push(d)
    }
  })

  const tooltipKey = hovered ? `${hovered.hora}-${hovered.dia}` : null
  const tooltipItems = tooltipKey ? detalhePorCelula[tooltipKey] || [] : []

  const toggleCell = (hora: number, dia: number) => {
    if (!onSelectionChange || !selectedCells) return
    const key = `${hora}-${dia}`
    const next = new Set(selectedCells)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    onSelectionChange(next)
  }

  const toggleHora = (hora: number) => {
    if (!onSelectionChange || !selectedCells) return
    const keys = Array.from({ length: 7 }, (_, dia) => `${hora}-${dia}`)
    const allSelected = keys.every(k => selectedCells.has(k))
    const next = new Set(selectedCells)
    keys.forEach(k => allSelected ? next.delete(k) : next.add(k))
    onSelectionChange(next)
  }

  const toggleDia = (dia: number) => {
    if (!onSelectionChange || !selectedCells) return
    const keys = Array.from({ length: 24 }, (_, hora) => `${hora}-${dia}`)
    const allSelected = keys.every(k => selectedCells.has(k))
    const next = new Set(selectedCells)
    keys.forEach(k => allSelected ? next.delete(k) : next.add(k))
    onSelectionChange(next)
  }

  const isSelected = (hora: number, dia: number) => selectedCells?.has(`${hora}-${dia}`) ?? false

  return (
    <div className="relative">
      <div onMouseLeave={() => setHovered(null)}>
        <div>
          <div className="grid gap-px w-full" style={{ gridTemplateColumns: '40px repeat(7, 1fr)' }}>
            <div />
            {DIAS.map((d, i) => (
              <div
                key={d}
                className="text-center text-xs font-semibold text-content-secondary pb-1 cursor-pointer hover:text-primary select-none"
                onClick={() => toggleDia(i)}
              >
                {d}
              </div>
            ))}
            {matrix.map((row, hora) => (
              <>
                <div
                  key={`h${hora}`}
                  className="text-right pr-2 text-xs text-content-secondary flex items-center justify-end cursor-pointer hover:text-primary select-none"
                  onClick={() => toggleHora(hora)}
                >
                  {hora}h
                </div>
                {row.map((val, dia) => {
                  const selected = isSelected(hora, dia)
                  return (
                    <div
                      key={`${hora}-${dia}`}
                      className="h-6 rounded-sm flex items-center justify-center cursor-pointer transition-all"
                      style={{
                        backgroundColor: getColor(val, max),
                        opacity: hasSelection && !selected ? 0.3 : 1,
                        outline: selected ? '2px solid #111' : 'none',
                        outlineOffset: '-1px',
                      }}
                      onClick={() => toggleCell(hora, dia)}
                      onMouseEnter={() => val > 0 && setHovered({ hora, dia })}
                    >
                      {val > 0 && (
                        <span className="text-[10px] font-medium" style={{ color: val / max > 0.5 ? '#fff' : '#374151' }}>
                          {val}
                        </span>
                      )}
                    </div>
                  )
                })}
              </>
            ))}
          </div>
          <div className="flex items-center gap-2 mt-3">
            <span className="text-xs text-content-secondary">Menos</span>
            {['#f3f4f6', '#dcfce7', '#86efac', '#22c55e', '#16a34a', '#166534'].map(c => (
              <div key={c} className="w-5 h-3 rounded-sm" style={{ backgroundColor: c }} />
            ))}
            <span className="text-xs text-content-secondary">Mais</span>
          </div>
        </div>
      </div>

      {hovered && tooltipItems.length > 0 && (
        <div className="absolute top-2 right-2 bg-white border border-border rounded-lg shadow-lg p-3 z-10 min-w-[200px] max-w-[280px] pointer-events-none">
          <p className="text-xs font-semibold uppercase text-content-secondary mb-2">
            {DIAS[hovered.dia]} {hovered.hora}h
          </p>
          <ul className="space-y-1">
            {tooltipItems.map((item, i) => (
              <li key={i} className="text-xs text-content-primary flex justify-between gap-2">
                <span className="truncate">{item.artista} — {item.musica}</span>
                <span className="font-data text-content-secondary shrink-0">{item.pedidos}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
