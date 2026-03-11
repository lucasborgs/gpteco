"""
dashboard.py

Dashboard de analytics da rádio com interface web via Gradio.
Lê os dados diretamente do DuckDB através dos módulos de relatório.

Iniciar:
    python dashboard.py

Acesso: http://localhost:7860
"""

import os

import matplotlib
import matplotlib.pyplot as plt
import gradio as gr
from dotenv import load_dotenv

load_dotenv()

# Backend não-interativo: necessário para gerar figuras sem display
matplotlib.use("Agg")

from core import database, relatorio

# Paleta de cores consistente
COR_PRINCIPAL  = "#2E86AB"
COR_DESTAQUE   = "#FF6B35"
COR_SUCESSO    = "#4CAF50"
COR_REJEICAO   = "#E53935"
COR_FUNDO      = "#F8F9FA"
FONTE_TITULO   = {"fontsize": 13, "fontweight": "bold", "color": "#333333"}


# ---------------------------------------------------------------------------
# Funções de geração de gráficos
# ---------------------------------------------------------------------------

def _fig_top_musicas_all_time():
    dados = relatorio.top_musicas_all_time(10)
    if not dados:
        return _fig_vazia("Nenhum pedido registrado ainda.")

    labels = [f"{d['artista'][:20]} - {d['musica'][:20]}" for d in dados]
    valores = [d["pedidos"] for d in dados]

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor(COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    bars = ax.barh(labels[::-1], valores[::-1], color=COR_PRINCIPAL, edgecolor="white")
    for bar, val in zip(bars, valores[::-1]):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=9, color="#555555")

    ax.set_xlabel("Pedidos", fontsize=10)
    ax.set_title("Top 10 Músicas — Histórico Completo", **FONTE_TITULO)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(left=False)
    plt.tight_layout()
    return fig


def _fig_top_musicas_semana():
    dados = relatorio.top_musicas_semana(5)
    if not dados:
        return _fig_vazia("Nenhum pedido nos últimos 7 dias.")

    labels = [f"{d['artista'][:20]} - {d['musica'][:20]}" for d in dados]
    valores = [d["pedidos"] for d in dados]

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.patch.set_facecolor(COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    bars = ax.barh(labels[::-1], valores[::-1], color=COR_DESTAQUE, edgecolor="white")
    for bar, val in zip(bars, valores[::-1]):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=9, color="#555555")

    ax.set_xlabel("Pedidos", fontsize=10)
    ax.set_title("Top 5 Músicas — Últimos 7 Dias", **FONTE_TITULO)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(left=False)
    plt.tight_layout()
    return fig


def _fig_horarios_pico():
    dados = relatorio.top_horarios_semana(24)
    if not dados:
        return _fig_vazia("Nenhum dado de horário disponível.")

    # Garante todas as 24h representadas
    contagem = {d["hora"]: d["pedidos"] for d in dados}
    horas = list(range(24))
    valores = [contagem.get(h, 0) for h in horas]
    labels = [f"{h}h" for h in horas]

    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor(COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    cores = [COR_DESTAQUE if v == max(valores) else COR_PRINCIPAL for v in valores]
    ax.bar(labels, valores, color=cores, edgecolor="white", width=0.7)
    ax.set_xlabel("Hora do dia", fontsize=10)
    ax.set_ylabel("Pedidos", fontsize=10)
    ax.set_title("Pedidos por Horário — Últimos 7 Dias", **FONTE_TITULO)
    ax.spines[["top", "right"]].set_visible(False)
    plt.xticks(rotation=45, fontsize=8)
    plt.tight_layout()
    return fig


def _fig_pico_dia_semana():
    dados = relatorio.pico_por_dia_semana()
    if not dados:
        return _fig_vazia("Nenhum dado de dia da semana disponível.")

    # Garante todos os 7 dias
    _DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
    contagem = {d["dia_semana"]: d["pedidos"] for d in dados}
    valores = [contagem.get(i, 0) for i in range(7)]

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.patch.set_facecolor(COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    cores = [COR_DESTAQUE if v == max(valores) else COR_PRINCIPAL for v in valores]
    ax.bar(_DIAS, valores, color=cores, edgecolor="white", width=0.6)
    ax.set_ylabel("Pedidos", fontsize=10)
    ax.set_title("Pedidos por Dia da Semana — Histórico", **FONTE_TITULO)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig


def _fig_taxa_atendimento():
    taxa = relatorio.taxa_atendimento()
    if taxa["total"] == 0:
        return _fig_vazia("Nenhum pedido registrado ainda.")

    labels = ["Atendidos", "Recusados"]
    valores = [taxa["sucesso"], taxa["recusado"]]
    cores = [COR_SUCESSO, COR_REJEICAO]

    fig, ax = plt.subplots(figsize=(5, 5))
    fig.patch.set_facecolor(COR_FUNDO)

    wedges, texts, autotexts = ax.pie(
        valores,
        labels=labels,
        colors=cores,
        autopct="%1.1f%%",
        startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 2},
    )
    for text in autotexts:
        text.set_fontsize(11)
        text.set_fontweight("bold")
        text.set_color("white")

    ax.set_title(f"Taxa de Atendimento\n{taxa['total']} pedidos totais", **FONTE_TITULO)
    plt.tight_layout()
    return fig


def _tabela_ouvintes():
    dados = relatorio.ouvintes_engajados(10)
    if not dados:
        return []
    return [
        [d["numero_mascarado"], d["pedidos"], d["primeiro_pedido"]]
        for d in dados
    ]


def _cards_taxa():
    taxa = relatorio.taxa_atendimento()
    por_motivo = taxa.get("por_motivo", {})

    linhas = [
        f"Total de pedidos:    {taxa['total']}",
        f"Atendidos:           {taxa['sucesso']}",
        f"Recusados:           {taxa['recusado']}",
        f"Taxa de sucesso:     {taxa['taxa_sucesso_pct']}%",
        "",
        "Motivos de rejeicao:",
    ]
    for motivo, qtd in sorted(por_motivo.items(), key=lambda x: -x[1]):
        linhas.append(f"  {motivo}: {qtd}")

    return "\n".join(linhas)


def _fig_vazia(mensagem: str):
    fig, ax = plt.subplots(figsize=(6, 3))
    fig.patch.set_facecolor(COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)
    ax.text(0.5, 0.5, mensagem, ha="center", va="center",
            fontsize=12, color="#888888", transform=ax.transAxes)
    ax.axis("off")
    return fig


def atualizar_tudo():
    """Regenera todos os gráficos e dados — chamado pelo botão Atualizar."""
    return (
        _fig_top_musicas_all_time(),
        _fig_top_musicas_semana(),
        _fig_horarios_pico(),
        _fig_pico_dia_semana(),
        _fig_taxa_atendimento(),
        _cards_taxa(),
        _tabela_ouvintes(),
    )


# ---------------------------------------------------------------------------
# Interface Gradio
# ---------------------------------------------------------------------------

with gr.Blocks(
    title="Dashboard — Agente Virtual Musical",
    theme=gr.themes.Soft(primary_hue="blue"),
    css=".gradio-container { max-width: 1100px; margin: auto; }",
) as demo:

    gr.Markdown("# Agente Virtual Musical — Dashboard Analytics")
    gr.Markdown("Dados em tempo real do banco DuckDB local.")

    btn_atualizar = gr.Button("Atualizar dados", variant="primary", scale=0)

    with gr.Tabs():

        # --- Aba 1: Músicas ---
        with gr.Tab("Musicas"):
            with gr.Row():
                plot_all_time = gr.Plot(label="Histórico completo")
                plot_semana   = gr.Plot(label="Últimos 7 dias")

        # --- Aba 2: Horários ---
        with gr.Tab("Horarios de Pico"):
            plot_horarios  = gr.Plot(label="Por hora do dia")
            plot_dia_semana = gr.Plot(label="Por dia da semana")

        # --- Aba 3: Audiência ---
        with gr.Tab("Audiencia"):
            with gr.Row():
                plot_taxa = gr.Plot(label="Taxa de atendimento")
                with gr.Column():
                    txt_taxa = gr.Textbox(
                        label="Resumo de atendimento",
                        lines=10,
                        interactive=False,
                    )
            gr.Markdown("### Ouvintes mais engajados")
            tabela_ouvintes = gr.Dataframe(
                headers=["Numero (mascarado)", "Pedidos", "Primeiro pedido"],
                interactive=False,
            )

    # Outputs na mesma ordem que atualizar_tudo() retorna
    _outputs = [
        plot_all_time,
        plot_semana,
        plot_horarios,
        plot_dia_semana,
        plot_taxa,
        txt_taxa,
        tabela_ouvintes,
    ]

    btn_atualizar.click(fn=atualizar_tudo, outputs=_outputs)

    # Carrega os dados automaticamente na abertura do dashboard
    demo.load(fn=atualizar_tudo, outputs=_outputs)


if __name__ == "__main__":
    database.init_db()
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("DASHBOARD_PORT", "7860")),
        show_api=False,
    )
