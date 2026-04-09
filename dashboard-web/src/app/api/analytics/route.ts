import { NextRequest, NextResponse } from 'next/server'
import pool from '@/lib/db'

export const dynamic = 'force-dynamic'

const DIAS = ['Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado', 'Domingo']

export async function GET(request: NextRequest) {
  const client = await pool.connect()
  try {
    // --- Filtro de data: from/to (ISO strings) ---
    const fromParam = request.nextUrl.searchParams.get('from')
    const toParam = request.nextUrl.searchParams.get('to')
    const dataInicio = fromParam ? new Date(fromParam) : null
    const dataFim = toParam ? new Date(toParam + 'T23:59:59.999') : null

    // Monta cláusulas e parâmetros dinâmicos
    const dateConditions: string[] = []
    const dateParams: (Date)[] = []
    if (dataInicio) {
      dateParams.push(dataInicio)
      dateConditions.push(`timestamp_pedido >= $${dateParams.length}`)
    }
    if (dataFim) {
      dateParams.push(dataFim)
      dateConditions.push(`timestamp_pedido <= $${dateParams.length}`)
    }
    const dateWhere = dateConditions.length
      ? 'AND ' + dateConditions.join(' AND ')
      : ''
    const dateWhereOnly = dateConditions.length
      ? 'WHERE ' + dateConditions.join(' AND ')
      : ''

    const [
      topAllTime,
      picoDia,
      heatmap,
      heatmapDetalhe,
      taxa,
      ouvintes,
      dddRaw,
      artistas,
      generos,
      generosDetalhe,
      fasFrequentes,
    ] = await Promise.all([
      // todas as músicas pedidas com sucesso (sem LIMIT) + gênero
      client.query(`
        SELECT artista, musica, COALESCE(genero, '') AS genero, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE sucesso = TRUE AND artista != '' AND musica != ''
          ${dateWhere}
        GROUP BY artista, musica, genero
        ORDER BY pedidos DESC
      `, dateParams),
      // pico_por_dia_semana (converte UTC → Brasília)
      client.query(`
        SELECT (EXTRACT(DOW FROM timestamp_pedido AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo')::int + 6) % 7 AS dia_semana,
               COUNT(*) AS pedidos
        FROM dim_pedidos
        ${dateWhereOnly}
        GROUP BY dia_semana
        ORDER BY dia_semana
      `, dateParams),
      // heatmap_pedidos (converte UTC → Brasília)
      client.query(`
        SELECT EXTRACT(HOUR FROM timestamp_pedido AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo')::int AS hora,
               (EXTRACT(DOW FROM timestamp_pedido AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo')::int + 6) % 7 AS dia_semana,
               COUNT(*) AS pedidos
        FROM dim_pedidos
        ${dateWhereOnly}
        GROUP BY hora, dia_semana
      `, dateParams),
      // heatmap_detalhe (músicas por hora×dia, para tooltip)
      client.query(`
        SELECT EXTRACT(HOUR FROM timestamp_pedido AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo')::int AS hora,
               (EXTRACT(DOW FROM timestamp_pedido AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo')::int + 6) % 7 AS dia_semana,
               artista, musica, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE sucesso = TRUE AND artista != '' AND musica != ''
          ${dateWhere}
        GROUP BY hora, dia_semana, artista, musica
        ORDER BY hora, dia_semana, pedidos DESC
      `, dateParams),
      // taxa_atendimento (filtrado pelo período)
      client.query(`
        SELECT sucesso, motivo_rejeicao, COUNT(*) AS qtd
        FROM dim_pedidos
        WHERE (motivo_rejeicao IS NULL OR motivo_rejeicao != 'saudacao')
          ${dateWhere}
        GROUP BY sucesso, motivo_rejeicao
      `, dateParams),
      // ouvintes_engajados — sem LIMIT (todos)
      client.query(`
        SELECT COALESCE(telefone, numero) AS numero_real, COUNT(*) AS pedidos, MIN(timestamp_pedido) AS primeiro_pedido
        FROM dim_pedidos
        WHERE sucesso = TRUE
          ${dateWhere}
        GROUP BY numero_real
        ORDER BY pedidos DESC
      `, dateParams),
      // breakdown_ddd — usa COALESCE para pegar telefone real quando disponível
      client.query(`
        SELECT COALESCE(telefone, numero) AS numero_real, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE TRUE ${dateWhere}
        GROUP BY numero_real
      `, dateParams).catch(() =>
        client.query(`
          SELECT numero AS numero_real, COUNT(*) AS pedidos
          FROM dim_pedidos
          WHERE TRUE ${dateWhere}
          GROUP BY numero
        `, dateParams)
      ),
      // top_artistas (filtrado pelo período)
      client.query(`
        SELECT artista, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE sucesso = TRUE AND artista != ''
          ${dateWhere}
        GROUP BY artista
        ORDER BY pedidos DESC
        LIMIT 15
      `, dateParams),
      // top_generos
      client.query(`
        SELECT genero, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE sucesso = TRUE AND genero IS NOT NULL AND genero != ''
          ${dateWhere}
        GROUP BY genero
        ORDER BY pedidos DESC
        LIMIT 10
      `, dateParams).catch(() => ({ rows: [] })),
      // generos_detalhe (músicas por gênero, para tooltip)
      client.query(`
        SELECT genero, artista, musica, COUNT(*) AS pedidos
        FROM dim_pedidos
        WHERE sucesso = TRUE AND genero IS NOT NULL AND genero != ''
          ${dateWhere}
        GROUP BY genero, artista, musica
        ORDER BY genero, pedidos DESC
      `, dateParams).catch(() => ({ rows: [] })),
      // fãs frequentes (ouvintes com 2+ pedidos bem-sucedidos)
      client.query(`
        SELECT COUNT(*) AS total FROM (
          SELECT COALESCE(telefone, numero) AS ouvinte
          FROM dim_pedidos
          WHERE sucesso = TRUE
            ${dateWhere}
          GROUP BY ouvinte
          HAVING COUNT(*) >= 2
        ) sub
      `, dateParams),
    ])

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
      const base = (r.numero_real || '').split('@')[0]
      let telefone_formatado = base
      if (base.length >= 12 && base.startsWith('55')) {
        const ddd = base.slice(2, 4)
        const num = base.slice(4)
        telefone_formatado = num.length === 9
          ? `+55 (${ddd}) ${num.slice(0, 5)}-${num.slice(5)}`
          : `+55 (${ddd}) ${num.slice(0, 4)}-${num.slice(4)}`
      }
      return {
        telefone_formatado,
        pedidos: Number(r.pedidos),
        primeiro_pedido: r.primeiro_pedido
          ? new Date(r.primeiro_pedido).toLocaleDateString('pt-BR')
          : null,
      }
    })

    // --- Transform DDD ---
    const dddCount: Record<string, number> = {}
    dddRaw.rows.forEach(r => {
      const base = (r.numero_real || '').split('@')[0]
      const ddd = base.length >= 12 && base.startsWith('55') ? base.slice(2, 4) : '??'
      dddCount[ddd] = (dddCount[ddd] || 0) + Number(r.pedidos)
    })
    const breakdown_ddd = Object.entries(dddCount)
      .sort((a, b) => b[1] - a[1])
      .map(([ddd, pedidos]) => ({ ddd, pedidos }))

    return NextResponse.json({
      top_musicas_all_time: topAllTime.rows.map(r => ({
        artista: r.artista,
        musica: r.musica,
        genero: r.genero,
        pedidos: Number(r.pedidos),
      })),
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
      heatmap_detalhe: heatmapDetalhe.rows.map(r => ({
        hora: Number(r.hora),
        dia_semana: Number(r.dia_semana),
        artista: r.artista,
        musica: r.musica,
        pedidos: Number(r.pedidos),
      })),
      taxa_atendimento: { total, sucesso: aceitos, recusado: recusados, taxa_sucesso_pct, por_motivo },
      ouvintes_engajados,
      breakdown_ddd,
      top_artistas: artistas.rows.map(r => ({ artista: r.artista, pedidos: Number(r.pedidos) })),
      top_generos: generos.rows.map(r => ({ genero: r.genero, pedidos: Number(r.pedidos) })),
      generos_detalhe: generosDetalhe.rows.map(r => ({ genero: r.genero, artista: r.artista, musica: r.musica, pedidos: Number(r.pedidos) })),
      fas_frequentes: Number(fasFrequentes.rows[0]?.total ?? 0),
    })
  } catch (err) {
    console.error('[API] Analytics error:', err)
    return NextResponse.json({ error: 'Erro ao buscar dados' }, { status: 500 })
  } finally {
    client.release()
  }
}
