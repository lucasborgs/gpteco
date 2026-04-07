'use client'

import { useState } from 'react'
import type { HeatmapItem, HeatmapDetalhe } from '@/types/analytics'

interface Props {
  data: HeatmapItem[]
  detalhe: HeatmapDetalhe[]
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

export function HeatmapHorarios({ data, detalhe }: Props) {
  const [hovered, setHovered] = useState<{ hora: number; dia: number } | null>(null)

  const matrix: number[][] = Array.from({ length: 24 }, () => Array(7).fill(0))
  data.forEach(({ hora, dia_semana, pedidos }) => {
    matrix[hora][dia_semana] = pedidos
  })
  const max = Math.max(...data.map(d => d.pedidos), 1)

  // Agrupa detalhes por hora×dia (top 5 músicas por célula)
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

  return (
    <div className="relative">
      <div onMouseLeave={() => setHovered(null)}>
        <div className="overflow-x-auto">
          <div className="inline-grid gap-px" style={{ gridTemplateColumns: '40px repeat(7, 1fr)', minWidth: 480 }}>
            <div />
            {DIAS.map(d => (
              <div key={d} className="text-center text-xs font-semibold text-content-secondary pb-1">{d}</div>
            ))}
            {matrix.map((row, hora) => (
              <>
                <div key={`h${hora}`} className="text-right pr-2 text-xs text-content-secondary flex items-center justify-end">
                  {hora}h
                </div>
                {row.map((val, dia) => (
                  <div
                    key={`${hora}-${dia}`}
                    className="h-6 rounded-sm flex items-center justify-center cursor-pointer transition-opacity"
                    style={{
                      backgroundColor: getColor(val, max),
                      opacity: hovered && (hovered.hora !== hora || hovered.dia !== dia) ? 0.5 : 1,
                    }}
                    onMouseEnter={() => val > 0 && setHovered({ hora, dia })}
                  >
                    {val > 0 && (
                      <span className="text-[10px] font-medium" style={{ color: val / max > 0.5 ? '#fff' : '#374151' }}>
                        {val}
                      </span>
                    )}
                  </div>
                ))}
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
