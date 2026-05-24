'use client'

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  ReactNode,
} from 'react'
import { fetchAnalytics } from './api'
import type { AnalyticsData } from '@/types/analytics'

interface FiltersContextValue {
  data: AnalyticsData | null
  loading: boolean
  from: string | null
  to: string | null
  /** Altera o período, limpa os cross-filters e recarrega. */
  setDateRange: (from: string | null, to: string | null) => void
  reload: () => void
  selectedCells: Set<string>
  setSelectedCells: (s: Set<string>) => void
  selectedGeneros: Set<string>
  setSelectedGeneros: (s: Set<string>) => void
  selectedDates: Set<string>
  setSelectedDates: (s: Set<string>) => void
  selectedMotivos: Set<string>
  setSelectedMotivos: (s: Set<string>) => void
  hasCrossFilters: boolean
  clearCrossFilters: () => void
}

const FiltersContext = createContext<FiltersContextValue | null>(null)

function syncDateToUrl(from: string | null, to: string | null) {
  if (typeof window === 'undefined') return
  const params = new URLSearchParams(window.location.search)
  from ? params.set('from', from) : params.delete('from')
  to ? params.set('to', to) : params.delete('to')
  const qs = params.toString()
  window.history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname)
}

export function FiltersProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [from, setFrom] = useState<string | null>(null)
  const [to, setTo] = useState<string | null>(null)
  const [selectedCells, setSelectedCells] = useState<Set<string>>(new Set())
  const [selectedGeneros, setSelectedGeneros] = useState<Set<string>>(new Set())
  const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set())
  const [selectedMotivos, setSelectedMotivos] = useState<Set<string>>(new Set())

  const fetchFor = useCallback((f: string | null, t: string | null) => {
    setLoading(true)
    fetchAnalytics(f, t)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  // Carrega na montagem, lendo o período inicial da URL (compartilhável).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const f = params.get('from')
    const t = params.get('to')
    setFrom(f)
    setTo(t)
    fetchFor(f, t)
  }, [fetchFor])

  const setDateRange = useCallback((f: string | null, t: string | null) => {
    setFrom(f)
    setTo(t)
    setSelectedCells(new Set())
    setSelectedGeneros(new Set())
    setSelectedDates(new Set())
    setSelectedMotivos(new Set())
    syncDateToUrl(f, t)
    fetchFor(f, t)
  }, [fetchFor])

  const reload = useCallback(() => fetchFor(from, to), [fetchFor, from, to])

  const clearCrossFilters = useCallback(() => {
    setSelectedCells(new Set())
    setSelectedGeneros(new Set())
    setSelectedDates(new Set())
    setSelectedMotivos(new Set())
  }, [])

  const hasCrossFilters =
    selectedCells.size > 0 ||
    selectedGeneros.size > 0 ||
    selectedDates.size > 0 ||
    selectedMotivos.size > 0

  const value = useMemo<FiltersContextValue>(() => ({
    data, loading, from, to, setDateRange, reload,
    selectedCells, setSelectedCells,
    selectedGeneros, setSelectedGeneros,
    selectedDates, setSelectedDates,
    selectedMotivos, setSelectedMotivos,
    hasCrossFilters, clearCrossFilters,
  }), [
    data, loading, from, to, setDateRange, reload,
    selectedCells, selectedGeneros, selectedDates, selectedMotivos,
    hasCrossFilters, clearCrossFilters,
  ])

  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>
}

export function useFilters(): FiltersContextValue {
  const ctx = useContext(FiltersContext)
  if (!ctx) throw new Error('useFilters deve ser usado dentro de <FiltersProvider>')
  return ctx
}
