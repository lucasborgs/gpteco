'use client'

import { Treemap, ResponsiveContainer, Tooltip } from 'recharts'
import type { ArtistaItem } from '@/types/analytics'

interface TreemapArtistasProps {
  data: ArtistaItem[]
}

const COLORS = [
  '#1DB954', '#16a34a', '#15803d', '#166534',
  '#059669', '#0d9488', '#0891b2', '#0284c7',
]

interface CustomContentProps {
  x?: number
  y?: number
  width?: number
  height?: number
  name?: string
  value?: number
  index?: number
}

function CustomContent({ x = 0, y = 0, width = 0, height = 0, name, value, index = 0 }: CustomContentProps) {
  const color = COLORS[index % COLORS.length]
  if (width < 40 || height < 30) return <rect x={x} y={y} width={width} height={height} fill={color} rx={4} />
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={color} rx={4} />
      <text
        x={x + width / 2}
        y={y + height / 2 - 6}
        textAnchor="middle"
        fill="#fff"
        fontSize={12}
        fontWeight={600}
        style={{ fontFamily: 'Inter, sans-serif' }}
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

export function TreemapArtistas({ data }: TreemapArtistasProps) {
  const formatted = data.map((d) => ({ name: d.artista, size: d.pedidos }))

  return (
    <ResponsiveContainer width="100%" height={280}>
      <Treemap
        data={formatted}
        dataKey="size"
        content={<CustomContent />}
      >
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid #E5E7EB', fontSize: 12 }}
          formatter={(value: unknown) => [value as number, 'Pedidos']}
        />
      </Treemap>
    </ResponsiveContainer>
  )
}
