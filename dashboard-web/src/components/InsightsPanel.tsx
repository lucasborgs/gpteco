'use client'

import { useEffect, useMemo, useRef, useState, Fragment } from 'react'
import { useFilters } from '@/lib/filters-context'
import { useFilteredAnalytics } from '@/lib/useFilteredAnalytics'

const DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
const MOTIVO_LABELS: Record<string, string> = {
  sucesso: 'Atendidos',
  cooldown: 'Cooldown',
  nao_flashback: 'Fora do repertório',
  nao_identificado: 'Não identificado',
  inapropriado: 'Inapropriado',
  erro_tecnico: 'Erro técnico',
  desconhecido: 'Outros',
}

type ChatMsg = { role: 'user' | 'assistant'; content: string }

function renderInline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-semibold text-content-primary">{part.slice(2, -2)}</strong>
    }
    return <Fragment key={i}>{part}</Fragment>
  })
}

function Markdownish({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <div className="space-y-1 text-sm text-content-secondary leading-relaxed">
      {lines.map((line, i) => {
        const trimmed = line.trim()
        if (!trimmed) return <div key={i} className="h-1" />
        const heading = trimmed.match(/^\*\*(.+?)\*\*:?$/)
        if (heading) {
          return (
            <p key={i} className="font-semibold text-content-primary uppercase text-xs tracking-wider mt-3 first:mt-0">
              {heading[1]}
            </p>
          )
        }
        const bullet = trimmed.match(/^[-*•]\s+(.*)/)
        if (bullet) {
          return (
            <div key={i} className="flex gap-2">
              <span className="text-primary mt-0.5">•</span>
              <span>{renderInline(bullet[1])}</span>
            </div>
          )
        }
        return <p key={i}>{renderInline(trimmed)}</p>
      })}
    </div>
  )
}

export function InsightsPanel() {
  const {
    from, to,
    selectedCells, selectedGeneros, selectedDates, selectedMotivos,
  } = useFilters()
  const {
    filteredAll, filteredPedidos, filteredGeneros, filteredHeatmapData,
    taxa, ouvintes, fasFrequentes,
  } = useFilteredAnalytics()

  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  const filterLabel = useMemo(() => {
    const parts: string[] = []
    if (selectedGeneros.size > 0) parts.push(`Gêneros: ${Array.from(selectedGeneros).join(', ')}`)
    if (selectedCells.size > 0) {
      const cells = Array.from(selectedCells).slice(0, 6).map(k => {
        const [h, d] = k.split('-').map(Number)
        return `${DIAS[d]} ${h}h`
      })
      const extra = selectedCells.size > 6 ? ` (+${selectedCells.size - 6})` : ''
      parts.push(`Horários: ${cells.join(', ')}${extra}`)
    }
    if (selectedDates.size > 0) parts.push(`Datas: ${Array.from(selectedDates).join(', ')}`)
    if (selectedMotivos.size > 0)
      parts.push(`Status: ${Array.from(selectedMotivos).map(m => MOTIVO_LABELS[m] || m).join(', ')}`)
    if (from || to) parts.push(`Período: ${from || '...'} a ${to || '...'}`)
    return parts.length ? parts.join(' · ') : ''
  }, [from, to, selectedCells, selectedGeneros, selectedDates, selectedMotivos])

  const summary = useMemo(() => {
    const topMusicasMap: Record<string, number> = {}
    const topArtistasMap: Record<string, number> = {}
    const porDiaSemana = Array(7).fill(0)
    filteredPedidos.forEach(p => {
      if (p.artista && p.musica) {
        topMusicasMap[`${p.artista} — ${p.musica}`] = (topMusicasMap[`${p.artista} — ${p.musica}`] || 0) + 1
      }
      if (p.artista) topArtistasMap[p.artista] = (topArtistasMap[p.artista] || 0) + 1
      porDiaSemana[p.dia_semana]++
    })
    const top_musicas = Object.entries(topMusicasMap)
      .sort((a, b) => b[1] - a[1]).slice(0, 10)
      .map(([nome, pedidos]) => ({ nome, pedidos }))
    const top_artistas = Object.entries(topArtistasMap)
      .sort((a, b) => b[1] - a[1]).slice(0, 10)
      .map(([artista, pedidos]) => ({ artista, pedidos }))

    const top_ouvintes = ouvintes.slice(0, 10).map(o => ({
      ouvinte: o.telefone_formatado, pedidos: o.pedidos, desde: o.primeiro_pedido,
    }))

    const picos = [...filteredHeatmapData]
      .sort((a, b) => b.pedidos - a.pedidos).slice(0, 5)
      .map(c => ({ dia: DIAS[c.dia_semana], hora: `${c.hora}h`, pedidos: c.pedidos }))

    const pedidos_por_dia_semana = porDiaSemana.map((pedidos, i) => ({ dia: DIAS[i], pedidos }))

    const recusas = Object.fromEntries(
      Object.entries(taxa.por_motivo).map(([m, q]) => [MOTIVO_LABELS[m] || m, q]),
    )

    return {
      periodo: from || to ? { de: from, ate: to } : 'todo o período',
      total_pedidos: filteredAll.length,
      atendidos: filteredPedidos.length,
      taxa_atendimento_pct: taxa.taxa_sucesso_pct,
      recusas_por_motivo: recusas,
      ouvintes_unicos: ouvintes.length,
      fas_frequentes: fasFrequentes,
      top_generos: filteredGeneros.slice(0, 8),
      top_artistas,
      top_musicas,
      top_ouvintes,
      picos_horario: picos,
      pedidos_por_dia_semana,
    }
  }, [from, to, filteredAll, filteredPedidos, filteredGeneros, filteredHeatmapData, taxa, ouvintes, fasFrequentes])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, chatLoading])

  const sendChat = async () => {
    const pergunta = input.trim()
    if (!pergunta || chatLoading) return
    const next = [...messages, { role: 'user' as const, content: pergunta }]
    setMessages(next)
    setInput('')
    setChatLoading(true)
    try {
      const res = await fetch('/api/insights', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ summary, filterLabel, messages: next }),
      })
      const json = await res.json()
      setMessages(m => [...m, { role: 'assistant', content: json.text || 'Sem resposta.' }])
    } catch {
      setMessages(m => [...m, { role: 'assistant', content: 'Erro ao responder. Tente novamente.' }])
    } finally {
      setChatLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="px-4 py-3 border-b border-border shrink-0">
        <h2 className="font-heading font-bold text-content-primary text-sm">Análise por IA</h2>
        {filterLabel && (
          <p className="text-[11px] text-content-secondary truncate max-w-[320px] mt-0.5" title={filterLabel}>
            {filterLabel}
          </p>
        )}
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.length === 0 && (
            <p className="text-xs text-content-secondary">
              Pergunte algo sobre os dados — ex.: <em>&quot;qual o melhor horário para sertanejo?&quot;</em>
            </p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
              <div
                className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                  m.role === 'user'
                    ? 'bg-primary text-white rounded-br-sm'
                    : 'bg-gray-100 text-content-primary rounded-bl-sm'
                }`}
              >
                {m.role === 'assistant' ? <Markdownish text={m.content} /> : m.content}
              </div>
            </div>
          ))}
          {chatLoading && (
            <div className="flex justify-start">
              <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-3 py-2 text-sm text-content-secondary">
                Pensando…
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        <div className="border-t border-border p-3 shrink-0">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat() }
              }}
              rows={1}
              placeholder="Pergunte aos dados…"
              className="flex-1 resize-none rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 max-h-28"
            />
            <button
              onClick={sendChat}
              disabled={chatLoading || !input.trim()}
              className="rounded-lg bg-primary text-white px-3 py-2 text-sm font-medium hover:bg-primary-hover transition-colors disabled:opacity-50 shrink-0"
            >
              Enviar
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
