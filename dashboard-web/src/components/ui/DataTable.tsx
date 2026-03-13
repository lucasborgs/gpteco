import { ReactNode } from 'react'

interface DataTableProps {
  headers: string[]
  rows: ReactNode[][]
}

export function DataTable({ headers, rows }: DataTableProps) {
  return (
    <table className="w-full text-sm">
      <thead className="bg-gray-50 border-b border-border">
        <tr>
          {headers.map((h, i) => (
            <th key={i} className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-content-secondary text-left">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {rows.length === 0 ? (
          <tr>
            <td colSpan={headers.length} className="px-4 py-12 text-center text-content-secondary">
              Nenhum dado disponível.
            </td>
          </tr>
        ) : (
          rows.map((row, i) => (
            <tr key={i} className="hover:bg-gray-50 transition-colors">
              {row.map((cell, j) => (
                <td key={j} className="px-4 py-3.5 text-content-primary">{cell}</td>
              ))}
            </tr>
          ))
        )}
      </tbody>
    </table>
  )
}
