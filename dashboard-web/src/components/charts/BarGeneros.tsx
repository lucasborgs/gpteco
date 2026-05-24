'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { GeneroItem, GeneroDetalhe } from '@/types/analytics'

interface Props {
  data: GeneroItem[]
  detalhe: GeneroDetalhe[]
  selectedGeneros?: Set<string>
  onGeneroClick?: (generos: Set<string>) => void
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function makeTooltip(detalhesPorGenero: Record<string, GeneroDetalhe[]>) {
  return function CustomTooltip({ active, label }: any) {
    if (!active || !label) return null
    const itens = detalhesPorGenero[label] || []
    return (
      <div className="bg-white border border-border rounded-lg shadow-lg p-3 min-w-[200px] max-w-[280px]">
        <p className="text-xs font-semibold uppercase text-content-secondary mb-2 capitalize">
          {label}
        </p>
        {itens.length > 0 ? (
          <ul className="space-y-1">
            {itens.map((item, i) => (
              <li key={i} className="text-xs text-content-primary flex justify-between gap-2">
                <span className="truncate">{item.artista} — {item.musica}</span>
                <span className="font-data text-content-secondary shrink-0">{item.pedidos}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-content-secondary">Sem detalhes</p>
        )}
      </div>
    )
  }
}

export function BarGeneros({ data, detalhe, selectedGeneros, onGeneroClick }: Props) {
  const hasSelection = selectedGeneros && selectedGeneros.size > 0

  // Ordena do mais ao menos pedido
  const formatted = [...data]
    .sort((a, b) => b.pedidos - a.pedidos)
    .map(d => ({ name: d.genero, pedidos: d.pedidos }))

  const detalhesPorGenero: Record<string, GeneroDetalhe[]> = {}
  detalhe.forEach(d => {
    if (!detalhesPorGenero[d.genero]) detalhesPorGenero[d.genero] = []
    if (detalhesPorGenero[d.genero].length < 5) detalhesPorGenero[d.genero].push(d)
  })

  const handleClick = (entry: { name?: string }) => {
    if (!onGeneroClick || !selectedGeneros || !entry?.name) return
    const next = new Set(selectedGeneros)
    if (next.has(entry.name)) next.delete(entry.name)
    else next.add(entry.name)
    onGeneroClick(next)
  }

  // Altura proporcional ao nº de barras, mantendo rótulos legíveis
  const height = Math.max(formatted.length * 34 + 16, 140)

  if (formatted.length === 0) {
    return (
      <div className="h-[200px] flex items-center justify-center text-sm text-content-secondary">
        Nenhum dado disponível.
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={formatted} layout="vertical" margin={{ left: 4, right: 28, top: 4, bottom: 4 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="name"
          width={96}
          tick={{ fontSize: 11, fill: '#6B7280' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: string) => v.charAt(0).toUpperCase() + v.slice(1)}
        />
        <Tooltip cursor={{ fill: '#F3F4F6' }} content={makeTooltip(detalhesPorGenero)} />
        <Bar
          dataKey="pedidos"
          radius={[0, 4, 4, 0]}
          onClick={handleClick}
          style={{ cursor: onGeneroClick ? 'pointer' : undefined }}
          label={{ position: 'right', fontSize: 11, fill: '#6B7280', fontFamily: 'Fragment Mono' }}
          isAnimationActive={false}
        >
          {formatted.map((entry, i) => {
            const selected = selectedGeneros?.has(entry.name) ?? false
            return (
              <Cell
                key={i}
                fill="#1DB954"
                opacity={hasSelection && !selected ? 0.3 : 1}
                stroke={selected ? '#111' : undefined}
                strokeWidth={selected ? 2 : 0}
              />
            )
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
