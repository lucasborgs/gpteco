'use client'

import { useState } from 'react'
import { Treemap, ResponsiveContainer } from 'recharts'
import type { GeneroItem, GeneroDetalhe } from '@/types/analytics'

interface Props {
  data: GeneroItem[]
  detalhe: GeneroDetalhe[]
  selectedGenero?: string | null
  onGeneroClick?: (genero: string | null) => void
}

const COLORS = [
  '#1DB954', '#16a34a', '#15803d', '#166534',
  '#059669', '#0d9488', '#0891b2', '#0284c7',
  '#6366f1', '#8b5cf6',
]

interface CustomContentProps {
  x?: number
  y?: number
  width?: number
  height?: number
  name?: string
  value?: number
  index?: number
  isSelected?: boolean
}

function CustomContent({ x = 0, y = 0, width = 0, height = 0, name, value, index = 0, isSelected }: CustomContentProps) {
  const color = COLORS[index % COLORS.length]
  const strokeProps = isSelected ? { stroke: '#111', strokeWidth: 3 } : {}
  if (width < 40 || height < 30) return <rect x={x} y={y} width={width} height={height} fill={color} rx={4} {...strokeProps} />
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={color} rx={4} {...strokeProps} />
      <text
        x={x + width / 2}
        y={y + height / 2 - 6}
        textAnchor="middle"
        fill="#fff"
        fontSize={12}
        fontWeight={600}
        style={{ fontFamily: 'Inter, sans-serif', textTransform: 'capitalize' }}
      >
        {name}
      </text>
      <text
        x={x + width / 2}
        y={y + height / 2 + 10}
        textAnchor="middle"
        fill="rgba(255,255,255,0.85)"
        fontSize={11}
        style={{ fontFamily: 'Fragment Mono, monospace' }}
      >
        {value}
      </text>
    </g>
  )
}

export function TreemapGeneros({ data, detalhe, selectedGenero, onGeneroClick }: Props) {
  const [hoveredGenero, setHoveredGenero] = useState<string | null>(null)

  const formatted = data.map((d) => ({
    name: d.genero,
    size: d.pedidos,
    isSelected: d.genero === selectedGenero,
  }))

  // Agrupa detalhes por gênero (top 5 músicas por gênero)
  const detalhesPorGenero: Record<string, GeneroDetalhe[]> = {}
  detalhe.forEach(d => {
    if (!detalhesPorGenero[d.genero]) detalhesPorGenero[d.genero] = []
    if (detalhesPorGenero[d.genero].length < 5) {
      detalhesPorGenero[d.genero].push(d)
    }
  })

  const tooltipItems = hoveredGenero ? detalhesPorGenero[hoveredGenero] || [] : []

  const handleClick = (node: { name?: string }) => {
    if (!onGeneroClick || !node?.name) return
    // Toggle: clique no mesmo limpa, clique em outro filtra
    onGeneroClick(node.name === selectedGenero ? null : node.name)
  }

  return (
    <div className="relative">
      <div
        onMouseLeave={() => setHoveredGenero(null)}
      >
        <ResponsiveContainer width="100%" height={280}>
          <Treemap
            data={formatted}
            dataKey="size"
            content={<CustomContent />}
            onMouseEnter={(node: { name?: string }) => {
              if (node?.name) setHoveredGenero(node.name)
            }}
            onClick={handleClick}
            style={{ cursor: onGeneroClick ? 'pointer' : undefined }}
          />
        </ResponsiveContainer>
      </div>

      {hoveredGenero && tooltipItems.length > 0 && (
        <div className="absolute top-2 right-2 bg-white border border-border rounded-lg shadow-lg p-3 z-10 min-w-[200px] max-w-[280px] pointer-events-none">
          <p className="text-xs font-semibold uppercase text-content-secondary mb-2 capitalize">
            {hoveredGenero}
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
