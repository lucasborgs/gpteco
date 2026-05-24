'use client'

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { TaxaAtendimento } from '@/types/analytics'

interface Props {
  data: TaxaAtendimento
  selectedMotivos?: Set<string>
  onMotivoClick?: (motivos: Set<string>) => void
  compact?: boolean
}

const MOTIVO_CONFIG: Record<string, { label: string; color: string }> = {
  sucesso: { label: 'Atendidos', color: '#1DB954' },
  cooldown: { label: 'Cooldown', color: '#EAB308' },
  nao_flashback: { label: 'Fora do repertório', color: '#F97316' },
  nao_identificado: { label: 'Não identificado', color: '#9CA3AF' },
  inapropriado: { label: 'Inapropriado', color: '#E53935' },
  erro_tecnico: { label: 'Erro técnico', color: '#8B5CF6' },
  desconhecido: { label: 'Outros', color: '#6B7280' },
}

function configFor(key: string) {
  return MOTIVO_CONFIG[key] || MOTIVO_CONFIG.desconhecido
}

export function DonutAtendimento({ data, selectedMotivos, onMotivoClick, compact = false }: Props) {
  const hasSelection = selectedMotivos && selectedMotivos.size > 0

  const chartData: { motivoKey: string; name: string; value: number; color: string }[] = [
    { motivoKey: 'sucesso', name: 'Atendidos', value: data.sucesso, color: MOTIVO_CONFIG.sucesso.color },
  ]
  Object.entries(data.por_motivo).forEach(([motivo, qtd]) => {
    if (qtd > 0) {
      const cfg = configFor(motivo)
      chartData.push({ motivoKey: motivo, name: cfg.label, value: qtd, color: cfg.color })
    }
  })

  const toggle = (key: string) => {
    if (!onMotivoClick || !selectedMotivos) return
    const next = new Set(selectedMotivos)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    onMotivoClick(next)
  }

  const pie = compact
    ? { h: 110, inner: 28, outer: 44 }
    : { h: 240, inner: 58, outer: 88 }

  const pieChart = (
    <PieChart>
      <Pie
        data={chartData}
        cx="50%"
        cy="50%"
        innerRadius={pie.inner}
        outerRadius={pie.outer}
        dataKey="value"
        paddingAngle={2}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        onClick={(entry: any) => entry?.motivoKey && toggle(entry.motivoKey)}
        style={{ cursor: onMotivoClick ? 'pointer' : undefined }}
        isAnimationActive={false}
      >
        {chartData.map((entry, i) => {
          const selected = selectedMotivos?.has(entry.motivoKey) ?? false
          return (
            <Cell
              key={i}
              fill={entry.color}
              opacity={hasSelection && !selected ? 0.3 : 1}
              stroke={selected ? '#111' : '#fff'}
              strokeWidth={selected ? 2 : 1}
            />
          )
        })}
      </Pie>
      <Tooltip
        contentStyle={{ borderRadius: 8, border: '1px solid #E5E7EB', fontSize: 13 }}
        formatter={(v: unknown, name: unknown) => [`${v as number} pedidos`, String(name ?? '')]}
      />
    </PieChart>
  )

  const legend = (
    <ul className={compact ? 'space-y-0.5 text-xs w-full' : 'space-y-1.5 text-xs'}>
      {chartData.map(entry => {
        const selected = selectedMotivos?.has(entry.motivoKey) ?? false
        return (
          <li key={entry.motivoKey}>
            <button
              onClick={() => toggle(entry.motivoKey)}
              disabled={!onMotivoClick}
              className={`flex items-center gap-2 w-full text-left rounded px-1.5 py-0.5 transition-colors ${
                onMotivoClick ? 'hover:bg-gray-100 cursor-pointer' : 'cursor-default'
              } ${selected ? 'bg-gray-100 font-semibold' : ''} ${
                hasSelection && !selected ? 'opacity-50' : ''
              }`}
            >
              <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: entry.color }} />
              <span className="text-content-secondary truncate">{entry.name}</span>
              <span className="font-data text-content-primary ml-auto pl-1 shrink-0">{entry.value}</span>
            </button>
          </li>
        )
      })}
    </ul>
  )

  if (compact) {
    return (
      <div className="flex flex-col items-center w-full gap-1">
        <div className="w-[110px] shrink-0">
          <ResponsiveContainer width="100%" height={pie.h}>
            {pieChart}
          </ResponsiveContainer>
        </div>
        {legend}
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center gap-4 flex-wrap">
      <div className="w-[200px]">
        <ResponsiveContainer width="100%" height={pie.h}>
          {pieChart}
        </ResponsiveContainer>
      </div>
      {legend}
    </div>
  )
}
