'use client'

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Dot } from 'recharts'
import type { VolumeDiaMes } from '@/types/analytics'

interface Props {
  data: VolumeDiaMes[]
  selectedDates?: Set<string>
  onSelectionChange?: (dates: Set<string>) => void
  height?: number | string
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function CustomDot(props: any) {
  const { cx, cy, payload, selectedDates, hasSelection } = props
  if (cx == null || cy == null) return null
  const isSelected = selectedDates?.has(payload.dia)
  const opacity = hasSelection && !isSelected ? 0.3 : 1
  return (
    <circle
      cx={cx}
      cy={cy}
      r={isSelected ? 6 : 3}
      fill={isSelected ? '#1DB954' : '#2E86AB'}
      stroke={isSelected ? '#111' : 'none'}
      strokeWidth={isSelected ? 2 : 0}
      opacity={opacity}
      style={{ cursor: 'pointer' }}
    />
  )
}

export function LineVolumeDia({ data, selectedDates, onSelectionChange, height = 200 }: Props) {
  const hasSelection = selectedDates && selectedDates.size > 0

  const handleClick = (point: any) => {
    if (!onSelectionChange || !selectedDates || !point?.activePayload?.[0]) return
    const dia = point.activePayload[0].payload.dia as string
    const next = new Set(selectedDates)
    if (next.has(dia)) next.delete(dia)
    else next.add(dia)
    onSelectionChange(next)
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} onClick={handleClick}>
        <XAxis
          dataKey="dia"
          tick={{ fontSize: 10, fill: '#6B7280' }}
          axisLine={false}
          tickLine={false}
          angle={-45}
          textAnchor="end"
          height={40}
          interval="preserveStartEnd"
        />
        <YAxis hide />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid #E5E7EB', fontSize: 13 }}
          formatter={(v: unknown) => [`${v as number} pedidos`, 'Volume']}
        />
        <Line
          type="monotone"
          dataKey="pedidos"
          stroke="#2E86AB"
          strokeWidth={2}
          connectNulls
          dot={<CustomDot selectedDates={selectedDates} hasSelection={hasSelection} />}
          activeDot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
