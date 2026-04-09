'use client'

interface Props {
  from: string | null
  to: string | null
  onChange: (from: string | null, to: string | null) => void
}

export function DateFilter({ from, to, onChange }: Props) {
  const isAllTime = !from && !to

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <label className="flex items-center gap-1 text-xs text-content-secondary">
        De
        <input
          type="date"
          value={from ?? ''}
          onChange={e => onChange(e.target.value || null, to)}
          className="px-2 py-1.5 text-xs rounded-lg border border-border bg-white text-content-primary"
        />
      </label>
      <label className="flex items-center gap-1 text-xs text-content-secondary">
        Até
        <input
          type="date"
          value={to ?? ''}
          onChange={e => onChange(from, e.target.value || null)}
          className="px-2 py-1.5 text-xs rounded-lg border border-border bg-white text-content-primary"
        />
      </label>
      <button
        onClick={() => onChange(null, null)}
        className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
          isAllTime
            ? 'bg-primary text-white'
            : 'bg-gray-100 text-content-secondary hover:bg-gray-200'
        }`}
      >
        Todo período
      </button>
    </div>
  )
}
