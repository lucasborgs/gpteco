'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { MusicaItem } from '@/types/analytics'

interface BarMusicasProps {
  data: MusicaItem[]
  color?: string
}

export function BarMusicas({ data, color = '#1DB954' }: BarMusicasProps) {
  const formatted = data.map((d) => ({
    name: `${d.musica} — ${d.artista}`,
    pedidos: d.pedidos,
  }))

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={formatted} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E5E7EB" />
        <XAxis type="number" tick={{ fontSize: 11, fontFamily: 'Fragment Mono' }} />
        <YAxis
          type="category"
          dataKey="name"
          width={180}
          tick={{ fontSize: 11 }}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid #E5E7EB', fontSize: 12 }}
          cursor={{ fill: '#F3F4F6' }}
        />
        <Bar dataKey="pedidos" fill={color} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
