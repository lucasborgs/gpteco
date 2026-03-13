'use client'

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { DiaSemanaItem } from '@/types/analytics'

interface Props {
  data: DiaSemanaItem[]
}

const DIAS_ABREV = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

export function BarDiaSemana({ data }: Props) {
  const filled = DIAS_ABREV.map((nome, i) => ({
    nome,
    pedidos: data.find(d => d.dia_semana === i)?.pedidos ?? 0,
  }))
  const max = Math.max(...filled.map(d => d.pedidos))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={filled} barCategoryGap="30%">
        <XAxis dataKey="nome" tick={{ fontSize: 12, fill: '#6B7280' }} axisLine={false} tickLine={false} />
        <YAxis hide />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid #E5E7EB', fontSize: 13 }}
          formatter={(v: unknown) => [`${v as number} pedidos`, 'Volume']}
        />
        <Bar dataKey="pedidos" radius={[4, 4, 0, 0]}>
          {filled.map((entry, i) => (
            <Cell key={i} fill={entry.pedidos === max ? '#1DB954' : '#2E86AB'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
