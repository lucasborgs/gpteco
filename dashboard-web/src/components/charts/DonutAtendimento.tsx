'use client'

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { TaxaAtendimento } from '@/types/analytics'

interface Props {
  data: TaxaAtendimento
}

export function DonutAtendimento({ data }: Props) {
  const chartData = [
    { name: 'Atendidos', value: data.sucesso },
    { name: 'Recusados', value: data.recusado },
  ]

  return (
    <div className="flex flex-col items-center">
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={90}
            dataKey="value"
            paddingAngle={3}
          >
            <Cell fill="#1DB954" />
            <Cell fill="#E53935" />
          </Pie>
          <Tooltip
            contentStyle={{ borderRadius: 8, border: '1px solid #E5E7EB', fontSize: 13 }}
            formatter={(v: unknown) => [`${v as number} pedidos`]}
          />
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 13 }} />
        </PieChart>
      </ResponsiveContainer>
      <p className="text-3xl font-data font-normal text-content-primary -mt-2">
        {data.taxa_sucesso_pct}%
      </p>
      <p className="text-xs text-content-secondary mt-1">taxa de atendimento</p>
    </div>
  )
}
