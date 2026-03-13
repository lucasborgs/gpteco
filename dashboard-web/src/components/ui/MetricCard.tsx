interface MetricCardProps {
  label: string
  value: string | number
  hint?: string
}

export function MetricCard({ label, value, hint }: MetricCardProps) {
  return (
    <div className="bg-white rounded-xl shadow-card border border-border p-5 pt-6 relative overflow-hidden">
      <div className="absolute top-0 left-0 right-0 h-1 bg-primary" />
      <p className="text-xs font-semibold uppercase tracking-wider text-content-secondary mb-2">
        {label}
      </p>
      <p className="font-data text-3xl text-content-primary">{value}</p>
      {hint && <p className="text-xs text-content-secondary mt-1">{hint}</p>}
    </div>
  )
}
