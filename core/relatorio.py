"""
core/relatorio.py

Geração de relatórios e analytics da rádio.

Funções analíticas:
    top_musicas_semana(limit)   -> list[dict]  — top músicas últimos 7 dias
    top_horarios_semana(limit)  -> list[dict]  — horários de pico últimos 7 dias
    top_musicas_all_time(limit) -> list[dict]  — top músicas histórico completo
    pico_por_dia_semana()       -> list[dict]  — pedidos por dia da semana
    taxa_atendimento()          -> dict        — taxa de sucesso vs. rejeição
    ouvintes_engajados(limit)   -> list[dict]  — ouvintes mais ativos (número mascarado)

Relatório semanal:
    formatar_relatorio_semanal() -> str        — texto para envio via WhatsApp
"""

from datetime import datetime, timedelta

from core import database


# ---------------------------------------------------------------------------
# Funções analíticas
# ---------------------------------------------------------------------------

def top_musicas_semana(limit: int = 5) -> list[dict]:
    """
    Top músicas mais pedidas nos últimos 7 dias (somente pedidos com sucesso).
    Retorna lista de dicts: {artista, musica, pedidos}
    """
    con = database._get_connection()
    try:
        inicio = datetime.now() - timedelta(days=7)
        rows = con.execute("""
            SELECT artista, musica, COUNT(*) AS pedidos
            FROM dim_pedidos
            WHERE timestamp_pedido >= ?
              AND sucesso = TRUE
              AND artista != ''
              AND musica  != ''
            GROUP BY artista, musica
            ORDER BY pedidos DESC
            LIMIT ?
        """, [inicio, limit]).fetchall()
        return [{"artista": r[0], "musica": r[1], "pedidos": r[2]} for r in rows]
    finally:
        con.close()


def top_horarios_semana(limit: int = 5) -> list[dict]:
    """
    Top horários de pico nos últimos 7 dias (todos os pedidos, incluindo rejeições).
    Reflete a demanda real dos ouvintes, não apenas o que foi atendido.
    Retorna lista de dicts: {hora, pedidos}
    """
    con = database._get_connection()
    try:
        inicio = datetime.now() - timedelta(days=7)
        rows = con.execute("""
            SELECT hour(timestamp_pedido) AS hora, COUNT(*) AS pedidos
            FROM dim_pedidos
            WHERE timestamp_pedido >= ?
            GROUP BY hora
            ORDER BY pedidos DESC
            LIMIT ?
        """, [inicio, limit]).fetchall()
        return [{"hora": r[0], "pedidos": r[1]} for r in rows]
    finally:
        con.close()


def top_musicas_all_time(limit: int = 10) -> list[dict]:
    """
    Top músicas mais pedidas de todo o histórico (somente pedidos com sucesso).
    Retorna lista de dicts: {artista, musica, pedidos}
    """
    con = database._get_connection()
    try:
        rows = con.execute("""
            SELECT artista, musica, COUNT(*) AS pedidos
            FROM dim_pedidos
            WHERE sucesso = TRUE
              AND artista != ''
              AND musica  != ''
            GROUP BY artista, musica
            ORDER BY pedidos DESC
            LIMIT ?
        """, [limit]).fetchall()
        return [{"artista": r[0], "musica": r[1], "pedidos": r[2]} for r in rows]
    finally:
        con.close()


def pico_por_dia_semana() -> list[dict]:
    """
    Volume de pedidos por dia da semana (histórico completo).
    Retorna lista de dicts: {dia_semana (0=seg, 6=dom), dia_nome, pedidos}
    """
    _DIAS = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"]
    con = database._get_connection()
    try:
        # DuckDB: dayofweek retorna 0=domingo ... 6=sábado → convertemos para 0=segunda
        rows = con.execute("""
            SELECT (dayofweek(timestamp_pedido) + 6) % 7 AS dia_semana,
                   COUNT(*) AS pedidos
            FROM dim_pedidos
            GROUP BY dia_semana
            ORDER BY dia_semana
        """).fetchall()
        return [
            {"dia_semana": r[0], "dia_nome": _DIAS[r[0]], "pedidos": r[1]}
            for r in rows
        ]
    finally:
        con.close()


def taxa_atendimento() -> dict:
    """
    Taxa de sucesso vs. rejeição do pipeline.
    Retorna dict: {total, sucesso, recusado, taxa_sucesso_pct, por_motivo}
    """
    con = database._get_connection()
    try:
        rows = con.execute("""
            SELECT sucesso, motivo_rejeicao, COUNT(*) AS qtd
            FROM dim_pedidos
            GROUP BY sucesso, motivo_rejeicao
        """).fetchall()

        total = 0
        aceitos = 0
        por_motivo: dict[str, int] = {}

        for sucesso, motivo, qtd in rows:
            total += qtd
            if sucesso:
                aceitos += qtd
            else:
                motivo = motivo or "desconhecido"
                por_motivo[motivo] = por_motivo.get(motivo, 0) + qtd

        recusados = total - aceitos
        taxa = round(aceitos / total * 100, 1) if total else 0.0

        return {
            "total": total,
            "sucesso": aceitos,
            "recusado": recusados,
            "taxa_sucesso_pct": taxa,
            "por_motivo": por_motivo,
        }
    finally:
        con.close()


def ouvintes_engajados(limit: int = 10) -> list[dict]:
    """
    Ouvintes mais ativos (somente pedidos com sucesso).
    Número de telefone mascarado: exibe apenas os últimos 4 dígitos antes do @.
    Retorna lista de dicts: {numero_mascarado, pedidos, primeiro_pedido}
    """
    con = database._get_connection()
    try:
        rows = con.execute("""
            SELECT numero, COUNT(*) AS pedidos, MIN(timestamp_pedido) AS primeiro_pedido
            FROM dim_pedidos
            WHERE sucesso = TRUE
            GROUP BY numero
            ORDER BY pedidos DESC
            LIMIT ?
        """, [limit]).fetchall()

        resultado = []
        for numero, pedidos, primeiro_pedido in rows:
            # Mascara: pega os 4 dígitos antes do @ (ou do fim da string)
            base = numero.split("@")[0]
            mascarado = f"****{base[-4:]}" if len(base) >= 4 else "****"
            resultado.append({
                "numero_mascarado": mascarado,
                "pedidos": pedidos,
                "primeiro_pedido": primeiro_pedido.strftime("%d/%m/%Y") if primeiro_pedido else None,
            })
        return resultado
    finally:
        con.close()


def heatmap_pedidos() -> list[dict]:
    """
    Volume de pedidos por hora e dia da semana (histórico completo).
    Retorna lista de dicts: {hora, dia_semana, pedidos}
    """
    con = database._get_connection()
    try:
        rows = con.execute("""
            SELECT hour(timestamp_pedido)              AS hora,
                   (dayofweek(timestamp_pedido) + 6) % 7 AS dia_semana,
                   COUNT(*) AS pedidos
            FROM dim_pedidos
            GROUP BY hora, dia_semana
        """).fetchall()
        return [{"hora": r[0], "dia_semana": r[1], "pedidos": r[2]} for r in rows]
    finally:
        con.close()


def tendencia_musicas(limit: int = 5) -> list[dict]:
    """
    Top músicas desta semana com indicador de tendência vs. semana anterior.
    Retorna lista de dicts: {posicao, artista, musica, pedidos, tendencia}
    onde tendencia é: "up", "down", "same", "new"
    """
    con = database._get_connection()
    try:
        agora = datetime.now()
        inicio_semana      = agora - timedelta(days=7)
        inicio_sem_anterior = agora - timedelta(days=14)

        rows_atual = con.execute("""
            SELECT artista, musica, COUNT(*) AS pedidos
            FROM dim_pedidos
            WHERE timestamp_pedido >= ? AND sucesso = TRUE AND artista != ''
            GROUP BY artista, musica
            ORDER BY pedidos DESC
            LIMIT ?
        """, [inicio_semana, limit]).fetchall()

        rows_anterior = con.execute("""
            SELECT artista, musica, COUNT(*) AS pedidos
            FROM dim_pedidos
            WHERE timestamp_pedido >= ? AND timestamp_pedido < ?
              AND sucesso = TRUE AND artista != ''
            GROUP BY artista, musica
            ORDER BY pedidos DESC
        """, [inicio_sem_anterior, inicio_semana]).fetchall()

        ranking_anterior = {
            f"{artista}|{musica}": pos
            for pos, (artista, musica, _) in enumerate(rows_anterior, 1)
        }

        resultado = []
        for pos, (artista, musica, pedidos) in enumerate(rows_atual, 1):
            chave = f"{artista}|{musica}"
            pos_ant = ranking_anterior.get(chave)
            if pos_ant is None:
                tendencia = "new"
            elif pos < pos_ant:
                tendencia = "up"
            elif pos > pos_ant:
                tendencia = "down"
            else:
                tendencia = "same"
            resultado.append({
                "posicao": pos, "artista": artista,
                "musica": musica, "pedidos": pedidos,
                "tendencia": tendencia,
            })
        return resultado
    finally:
        con.close()


def breakdown_ddd() -> list[dict]:
    """
    Volume de pedidos por DDD (código de área do ouvinte).
    Retorna lista de dicts: {ddd, pedidos}, ordenado por pedidos desc.
    """
    con = database._get_connection()
    try:
        rows = con.execute("""
            SELECT numero, COUNT(*) AS pedidos
            FROM dim_pedidos
            GROUP BY numero
        """).fetchall()

        ddd_count: dict[str, int] = {}
        for numero, pedidos in rows:
            base = numero.split("@")[0]
            ddd = base[2:4] if len(base) >= 12 and base.startswith("55") else "??"
            ddd_count[ddd] = ddd_count.get(ddd, 0) + pedidos

        return [
            {"ddd": k, "pedidos": v}
            for k, v in sorted(ddd_count.items(), key=lambda x: -x[1])
        ]
    finally:
        con.close()


def top_artistas(limit: int = 15) -> list[dict]:
    """
    Top artistas por volume de pedidos com sucesso (para treemap).
    Retorna lista de dicts: {artista, pedidos}
    """
    con = database._get_connection()
    try:
        rows = con.execute("""
            SELECT artista, COUNT(*) AS pedidos
            FROM dim_pedidos
            WHERE sucesso = TRUE AND artista != ''
            GROUP BY artista
            ORDER BY pedidos DESC
            LIMIT ?
        """, [limit]).fetchall()
        return [{"artista": r[0], "pedidos": r[1]} for r in rows]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Relatório semanal formatado
# ---------------------------------------------------------------------------

def formatar_relatorio_semanal() -> str:
    """
    Gera o texto do relatório semanal para envio via WhatsApp.
    Usa as funções analíticas acima — sem emojis, por convenção do projeto.
    """
    hoje = datetime.now()
    inicio_semana = hoje - timedelta(days=7)
    periodo = f"{inicio_semana.strftime('%d/%m')} a {hoje.strftime('%d/%m/%Y')}"

    musicas = top_musicas_semana(5)
    horarios = top_horarios_semana(5)
    taxa = taxa_atendimento()

    linhas = [
        "=== Relatorio Semanal ===",
        f"Periodo: {periodo}",
        "",
    ]

    # Top músicas
    linhas.append("Top 5 musicas mais pedidas:")
    if musicas:
        for i, m in enumerate(musicas, 1):
            linhas.append(f"  {i}. {m['artista']} - {m['musica']} ({m['pedidos']} pedidos)")
    else:
        linhas.append("  Nenhum pedido registrado na semana.")

    linhas.append("")

    # Top horários
    linhas.append("Top 5 horarios de pico:")
    if horarios:
        for i, h in enumerate(horarios, 1):
            linhas.append(f"  {i}. {h['hora']}h - {h['pedidos']} pedidos")
    else:
        linhas.append("  Sem dados de horario na semana.")

    linhas.append("")

    # Resumo de atendimento
    linhas.append(
        f"Atendimento: {taxa['sucesso']} aceitos / {taxa['recusado']} recusados "
        f"({taxa['taxa_sucesso_pct']}% de taxa de sucesso)"
    )

    return "\n".join(linhas)
