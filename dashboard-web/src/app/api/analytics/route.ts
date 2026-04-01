import { NextResponse } from 'next/server'
import pool from '@/lib/db'

export const dynamic = 'force-dynamic'

const DIAS = ['Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado', 'Domingo']

export async function GET() {
  const client = await pool.connect()
  try {
    const now = new Date()
    const semana = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
    const duasSemanas = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000)

    const [
      topAllTime,
      topSemana,
      tendenciaAtual,
      tendenciaAnterior,
      picoDia,
      heatmap,
      taxa,
      ouvintes,
      dddRaw,
      artistas,
    ] = await Promise.all([
      // top_musicas_all_time
      client.query(`
        SELECT artista, musica, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE sucesso = TRUE AND artista != '' AND musica != ''
        GROUP BY artista, musica
        ORDER BY pedidos DESC
        LIMIT 10
      `),
      // top_musicas_semana
      client.query(`
        SELECT artista, musica, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE timestamp_pedido >= $1 AND sucesso = TRUE AND artista != '' AND musica != ''
        GROUP BY artista, musica
        ORDER BY pedidos DESC
        LIMIT 5
      `, [semana]),
      // tendencia - semana atual
      client.query(`
        SELECT artista, musica, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE timestamp_pedido >= $1 AND sucesso = TRUE AND artista != ''
        GROUP BY artista, musica
        ORDER BY pedidos DESC
        LIMIT 5
      `, [semana]),
      // tendencia - semana anterior
      client.query(`
        SELECT artista, musica, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE timestamp_pedido >= $1 AND timestamp_pedido < $2
          AND sucesso = TRUE AND artista != ''
        GROUP BY artista, musica
        ORDER BY pedidos DESC
      `, [duasSemanas, semana]),
      // pico_por_dia_semana (converte UTC → Brasília)
      client.query(`
        SELECT (EXTRACT(DOW FROM timestamp_pedido AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo')::int + 6) % 7 AS dia_semana,
               COUNT(*) AS pedidos
        FROM dim_pedidos
        GROUP BY dia_semana
        ORDER BY dia_semana
      `),
      // heatmap_pedidos (converte UTC → Brasília para exibição correta)
      client.query(`
        SELECT EXTRACT(HOUR FROM timestamp_pedido AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo')::int AS hora,
               (EXTRACT(DOW FROM timestamp_pedido AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo')::int + 6) % 7 AS dia_semana,
               COUNT(*) AS pedidos
        FROM dim_pedidos
        GROUP BY hora, dia_semana
      `),
      // taxa_atendimento (semanal, sem saudacoes)
      client.query(`
        SELECT sucesso, motivo_rejeicao, COUNT(*) AS qtd
        FROM dim_pedidos
        WHERE timestamp_pedido >= $1
          AND (motivo_rejeicao IS NULL OR motivo_rejeicao != 'saudacao')
        GROUP BY sucesso, motivo_rejeicao
      `, [semana]),
      // ouvintes_engajados
      client.query(`
        SELECT numero, COUNT(*) AS pedidos, MIN(timestamp_pedido) AS primeiro_pedido
        FROM dim_pedidos
        WHERE sucesso = TRUE
        GROUP BY numero
        ORDER BY pedidos DESC
        LIMIT 10
      `),
      // breakdown_ddd (prioriza telefone resolvido via WAHA, fallback para numero)
      client.query(`
        SELECT COALESCE(telefone, numero) AS numero, COUNT(*) AS pedidos
        FROM dim_pedidos
        GROUP BY COALESCE(telefone, numero)
      `),
      // top_artistas
      client.query(`
        SELECT artista, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE sucesso = TRUE AND artista != ''
        GROUP BY artista
        ORDER BY pedidos DESC
        LIMIT 15
      `),
    ])

    // --- Transform tendencia ---
    const rankingAnterior: Record<string, number> = {}
    tendenciaAnterior.rows.forEach((r, i) => {
      rankingAnterior[`${r.artista}|${r.musica}`] = i + 1
    })
    const tendencia_musicas = tendenciaAtual.rows.map((r, i) => {
      const pos = i + 1
      const chave = `${r.artista}|${r.musica}`
      const posAnt = rankingAnterior[chave]
      let tendencia: string
      if (posAnt == null) tendencia = 'new'
      else if (pos < posAnt) tendencia = 'up'
      else if (pos > posAnt) tendencia = 'down'
      else tendencia = 'same'
      return { posicao: pos, artista: r.artista, musica: r.musica, pedidos: Number(r.pedidos), tendencia }
    })

    // --- Transform taxa ---
    let total = 0, aceitos = 0
    const por_motivo: Record<string, number> = {}
    taxa.rows.forEach(r => {
      const qtd = Number(r.qtd)
      total += qtd
      if (r.sucesso) aceitos += qtd
      else {
        const motivo = r.motivo_rejeicao || 'desconhecido'
        por_motivo[motivo] = (por_motivo[motivo] || 0) + qtd
      }
    })
    const recusados = total - aceitos
    const taxa_sucesso_pct = total ? Math.round(aceitos / total * 1000) / 10 : 0

    // --- Transform ouvintes ---
    const ouvintes_engajados = ouvintes.rows.map(r => {
      const base = r.numero.split('@')[0]
      const mascarado = base.length >= 4 ? `****${base.slice(-4)}` : '****'
      return {
        numero_mascarado: mascarado,
        pedidos: Number(r.pedidos),
        primeiro_pedido: r.primeiro_pedido
          ? new Date(r.primeiro_pedido).toLocaleDateString('pt-BR')
          : null,
      }
    })

    // --- Transform DDD ---
    const dddCount: Record<string, number> = {}
    dddRaw.rows.forEach(r => {
      const base = r.numero.split('@')[0]
      const ddd = base.length >= 12 && base.startsWith('55') ? base.slice(2, 4) : '??'
      dddCount[ddd] = (dddCount[ddd] || 0) + Number(r.pedidos)
    })
    const breakdown_ddd = Object.entries(dddCount)
      .sort((a, b) => b[1] - a[1])
      .map(([ddd, pedidos]) => ({ ddd, pedidos }))

    return NextResponse.json({
      top_musicas_all_time: topAllTime.rows.map(r => ({ artista: r.artista, musica: r.musica, pedidos: Number(r.pedidos) })),
      top_musicas_semana: topSemana.rows.map(r => ({ artista: r.artista, musica: r.musica, pedidos: Number(r.pedidos) })),
      tendencia_musicas,
      pico_por_dia_semana: picoDia.rows.map(r => ({
        dia_semana: Number(r.dia_semana),
        dia_nome: DIAS[Number(r.dia_semana)] || '?',
        pedidos: Number(r.pedidos),
      })),
      heatmap_pedidos: heatmap.rows.map(r => ({
        hora: Number(r.hora),
        dia_semana: Number(r.dia_semana),
        pedidos: Number(r.pedidos),
      })),
      taxa_atendimento: { total, sucesso: aceitos, recusado: recusados, taxa_sucesso_pct, por_motivo },
      ouvintes_engajados,
      breakdown_ddd,
      top_artistas: artistas.rows.map(r => ({ artista: r.artista, pedidos: Number(r.pedidos) })),
    })
  } catch (err) {
    console.error('[API] Analytics error:', err)
    return NextResponse.json({ error: 'Erro ao buscar dados' }, { status: 500 })
  } finally {
    client.release()
  }
}
