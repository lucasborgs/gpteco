'use client'

interface Props {
  value: string
  onChange: (days: string) => void
}

const OPTIONS = [
  { label: '7 dias', value: '7' },
  { label: '15 dias', value: '15' },
  { label: '30 dias', value: '30' },
  { label: 'Todo período', value: 'all' },
]

export function DateFilter({ value, onChange }: Props) {
  return (
    <div className="flex gap-1">
      {OPTIONS.map(opt => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
            value === opt.value
              ? 'bg-primary text-white'
              : 'bg-gray-100 text-content-secondary hover:bg-gray-200'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
