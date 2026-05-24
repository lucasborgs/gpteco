import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Extrai "dd/mm" (zero-padded) da string de data localizada (ex: "21/05/2026, 14:30:00"). */
export function extractDdMm(dataPedido: string): string {
  const [dd, mm] = dataPedido.split(/[,\s]/)[0].split('/')
  return `${(dd ?? '').padStart(2, '0')}/${(mm ?? '').padStart(2, '0')}`
}

/** Formata um identificador de ouvinte (JID/telefone) como "+55 (DD) NNNNN-NNNN". */
export function formatTelefone(numeroReal: string): string {
  const base = (numeroReal || '').split('@')[0]
  if (base.length >= 12 && base.startsWith('55')) {
    const ddd = base.slice(2, 4)
    const num = base.slice(4)
    return num.length === 9
      ? `+55 (${ddd}) ${num.slice(0, 5)}-${num.slice(5)}`
      : `+55 (${ddd}) ${num.slice(0, 4)}-${num.slice(4)}`
  }
  return base
}
