'use client'

import { HeatmapItem } from '@/types/analytics'

interface Props {
  data: HeatmapItem[]
}

const DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

function getColor(value: number, max: number): string {
  if (value === 0 || max === 0) return '#f3f4f6'
  const ratio = value / max
  if (ratio < 0.2) return '#fed7aa'
  if (ratio < 0.4) return '#fb923c'
  if (ratio < 0.6) return '#f97316'
  if (ratio < 0.8) return '#ea580c'
  return '#c2410c'
}

export function HeatmapHorarios({ data }: Props) {
  const matrix: number[][] = Array.from({ length: 24 }, () => Array(7).fill(0))
  data.forEach(({ hora, dia_semana, pedidos }) => {
    matrix[hora][dia_semana] = pedidos
  })
  const max = Math.max(...data.map(d => d.pedidos), 1)

  return (
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
                className="h-6 rounded-sm flex items-center justify-center"
                style={{ backgroundColor: getColor(val, max) }}
                title={`${DIAS[dia]} ${hora}h — ${val} pedidos`}
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
        {['#f3f4f6', '#fed7aa', '#fb923c', '#f97316', '#ea580c', '#c2410c'].map(c => (
          <div key={c} className="w-5 h-3 rounded-sm" style={{ backgroundColor: c }} />
        ))}
        <span className="text-xs text-content-secondary">Mais</span>
      </div>
    </div>
  )
}
