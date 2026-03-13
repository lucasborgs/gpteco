'use client'

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { DDDItem } from '@/types/analytics'

interface Props {
  data: DDDItem[]
}

export function BarDDD({ data }: Props) {
  const top = data.filter(d => d.ddd !== '??').slice(0, 10)
  const max = Math.max(...top.map(d => d.pedidos))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={top} barCategoryGap="30%">
        <XAxis
          dataKey="ddd"
          tick={{ fontSize: 12, fill: '#6B7280' }}
          tickFormatter={v => `(${v})`}
          axisLine={false}
          tickLine={false}
        />
        <YAxis hide />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid #E5E7EB', fontSize: 13 }}
          formatter={(v: unknown) => [`${v as number} pedidos`, 'DDD']}
          labelFormatter={l => `(${l})`}
        />
        <Bar dataKey="pedidos" radius={[4, 4, 0, 0]}>
          {top.map((entry, i) => (
            <Cell key={i} fill={entry.pedidos === max ? '#1DB954' : '#2E86AB'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
