'use client'

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { TaxaAtendimento } from '@/types/analytics'

interface Props {
  data: TaxaAtendimento
}

const MOTIVO_CONFIG: Record<string, { label: string; color: string }> = {
  cooldown: { label: 'Cooldown', color: '#EAB308' },
  nao_flashback: { label: 'Fora do repertório', color: '#F97316' },
  nao_identificado: { label: 'Não identificado', color: '#9CA3AF' },
  inapropriado: { label: 'Inapropriado', color: '#E53935' },
  erro_tecnico: { label: 'Erro técnico', color: '#8B5CF6' },
  desconhecido: { label: 'Outros', color: '#6B7280' },
}

export function DonutAtendimento({ data }: Props) {
  const chartData: { name: string; value: number; color: string }[] = [
    { name: 'Atendidos', value: data.sucesso, color: '#1DB954' },
  ]

  // Adiciona cada motivo de recusa como segmento separado
  Object.entries(data.por_motivo).forEach(([motivo, qtd]) => {
    if (qtd > 0) {
      const config = MOTIVO_CONFIG[motivo] || MOTIVO_CONFIG.desconhecido
      chartData.push({ name: config.label, value: qtd, color: config.color })
    }
  })

  return (
    <div className="flex flex-col items-center">
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={85}
            dataKey="value"
            paddingAngle={2}
          >
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ borderRadius: 8, border: '1px solid #E5E7EB', fontSize: 13 }}
            formatter={(v: unknown, name: unknown) => [`${v as number} pedidos`, String(name ?? '')]}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12 }}
          />
        </PieChart>
      </ResponsiveContainer>
      <p className="text-3xl font-data font-normal text-content-primary -mt-2">
        {data.taxa_sucesso_pct}%
      </p>
      <p className="text-xs text-content-secondary mt-1">taxa de atendimento</p>
    </div>
  )
}
