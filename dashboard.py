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
import matplotlib.cm as cm
import numpy as np
import gradio as gr
from dotenv import load_dotenv

load_dotenv()

# Backend não-interativo: necessário para gerar figuras sem display
matplotlib.use("Agg")

from core import database, relatorio

try:
    import squarify
    _SQUARIFY = True
except ImportError:
    _SQUARIFY = False

# Paleta de cores consistente
COR_PRINCIPAL = "#2E86AB"
COR_DESTAQUE  = "#FF6B35"
COR_SUCESSO   = "#4CAF50"
COR_REJEICAO  = "#E53935"
COR_FUNDO     = "#F8F9FA"
FONTE_TITULO  = {"fontsize": 13, "fontweight": "bold", "color": "#333333"}

_SETAS = {"up": "↑ subiu", "down": "↓ caiu", "same": "= estável", "new": "★ novo"}
_DIAS  = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]


# ---------------------------------------------------------------------------
# Gráficos — Aba Músicas
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


def _fig_treemap_artistas():
    dados = relatorio.top_artistas(15)
    if not dados:
        return _fig_vazia("Nenhum dado de artistas ainda.")

    valores = [d["pedidos"] for d in dados]
    labels  = [f"{d['artista']}\n({d['pedidos']})" for d in dados]

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    if _SQUARIFY:
        cores = [cm.Blues(0.35 + 0.55 * i / len(valores)) for i in range(len(valores))]
        squarify.plot(sizes=valores, label=labels, color=cores, ax=ax,
                      text_kwargs={"fontsize": 9, "fontweight": "bold", "color": "white",
                                   "wrap": True})
        ax.axis("off")
    else:
        # Fallback: barra horizontal simples
        ax.barh(
            [d["artista"][:25] for d in reversed(dados)],
            [d["pedidos"] for d in reversed(dados)],
            color=COR_PRINCIPAL, edgecolor="white",
        )
        ax.spines[["top", "right", "left"]].set_visible(False)

    ax.set_title("Artistas Mais Pedidos", **FONTE_TITULO)
    plt.tight_layout()
    return fig


def _tabela_tendencia():
    dados = relatorio.tendencia_musicas(5)
    if not dados:
        return []
    return [
        [_SETAS[d["tendencia"]], f"{d['artista']} - {d['musica']}", d["pedidos"]]
        for d in dados
    ]


# ---------------------------------------------------------------------------
# Gráficos — Aba Horários
# ---------------------------------------------------------------------------

def _fig_heatmap():
    dados = relatorio.heatmap_pedidos()
    if not dados:
        return _fig_vazia("Nenhum dado de horário disponível.")

    # Monta matriz 24h × 7 dias
    matriz = np.zeros((24, 7))
    for d in dados:
        matriz[d["hora"]][d["dia_semana"]] += d["pedidos"]

    fig, ax = plt.subplots(figsize=(10, 8))
    fig.patch.set_facecolor(COR_FUNDO)

    im = ax.pcolormesh(matriz, cmap="YlOrRd", edgecolors="white", linewidth=0.5)

    ax.set_xticks(np.arange(7) + 0.5)
    ax.set_xticklabels(_DIAS, fontsize=11)
    ax.set_yticks(np.arange(24) + 0.5)
    ax.set_yticklabels([f"{h:02d}h" for h in range(24)], fontsize=8)
    ax.invert_yaxis()  # 00h no topo, 23h embaixo (leitura natural)

    # Anota valores nas células com pelo menos 1 pedido
    for hora in range(24):
        for dia in range(7):
            val = int(matriz[hora][dia])
            if val > 0:
                ax.text(dia + 0.5, hora + 0.5, str(val),
                        ha="center", va="center", fontsize=8,
                        color="white" if val >= matriz.max() * 0.5 else "#555555")

    plt.colorbar(im, ax=ax, label="Pedidos", shrink=0.8)
    ax.set_title("Mapa de Calor — Horário × Dia da Semana\n(concentração real da audiência)",
                 **FONTE_TITULO)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Gráficos — Aba Audiência
# ---------------------------------------------------------------------------

def _fig_taxa_atendimento():
    taxa = relatorio.taxa_atendimento()
    if taxa["total"] == 0:
        return _fig_vazia("Nenhum pedido registrado ainda.")

    labels = ["Atendidos", "Recusados"]
    valores = [taxa["sucesso"], taxa["recusado"]]
    cores   = [COR_SUCESSO, COR_REJEICAO]

    fig, ax = plt.subplots(figsize=(5, 5))
    fig.patch.set_facecolor(COR_FUNDO)

    wedges, _, autotexts = ax.pie(
        valores, labels=labels, colors=cores,
        autopct="%1.1f%%", startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 2},
    )
    for at in autotexts:
        at.set_fontsize(11)
        at.set_fontweight("bold")
        at.set_color("white")

    ax.set_title(f"Taxa de Atendimento\n{taxa['total']} pedidos totais", **FONTE_TITULO)
    plt.tight_layout()
    return fig


def _fig_ddd():
    dados = relatorio.breakdown_ddd()
    dados = [d for d in dados if d["ddd"] != "??"][:12]
    if not dados:
        return _fig_vazia("Nenhum dado de DDD disponível.")

    labels  = [f"({d['ddd']})" for d in dados]
    valores = [d["pedidos"] for d in dados]
    cores   = [COR_PRINCIPAL if i > 0 else COR_DESTAQUE for i in range(len(dados))]

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.patch.set_facecolor(COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    bars = ax.bar(labels, valores, color=cores, edgecolor="white", width=0.6)
    for bar, val in zip(bars, valores):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                str(val), ha="center", va="bottom", fontsize=9, color="#555555")

    ax.set_ylabel("Pedidos", fontsize=10)
    ax.set_title("Alcance por DDD — Região dos Ouvintes", **FONTE_TITULO)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig


def _cards_taxa():
    taxa = relatorio.taxa_atendimento()
    por_motivo = taxa.get("por_motivo", {})

    _LABELS = {
        "cooldown":         "Fas frequentes (tentaram mais de uma vez)",
        "nao_flashback":    "Demanda reprimida (fora do repertorio)",
        "inapropriado":     "Mensagens inapropriadas",
        "nao_identificado": "Nao identificados",
        "erro_tecnico":     "Erros tecnicos",
    }

    linhas = [
        f"Total de pedidos:    {taxa['total']}",
        f"Atendidos:           {taxa['sucesso']}",
        f"Recusados:           {taxa['recusado']}",
        f"Taxa de sucesso:     {taxa['taxa_sucesso_pct']}%",
        "",
        "Detalhamento das recusas:",
    ]
    for motivo, qtd in sorted(por_motivo.items(), key=lambda x: -x[1]):
        label = _LABELS.get(motivo, motivo)
        linhas.append(f"  {label}: {qtd}")

    # Insights automáticos
    insights = []
    demanda = por_motivo.get("nao_flashback", 0)
    if demanda >= 3:
        insights.append(f"{demanda} pedidos fora do repertorio — considere um programa especial!")
    fidelidade = por_motivo.get("cooldown", 0)
    if fidelidade >= 3:
        insights.append(f"{fidelidade} ouvintes tentaram pedir mais de uma vez — alta fidelizacao!")

    if insights:
        linhas.append("")
        linhas.append("Insights:")
        for i in insights:
            linhas.append(f"  * {i}")

    return "\n".join(linhas)


def _tabela_ouvintes():
    dados = relatorio.ouvintes_engajados(10)
    if not dados:
        return []
    return [
        [d["numero_mascarado"], d["pedidos"], d["primeiro_pedido"]]
        for d in dados
    ]


def _fig_vazia(mensagem: str):
    fig, ax = plt.subplots(figsize=(6, 3))
    fig.patch.set_facecolor(COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)
    ax.text(0.5, 0.5, mensagem, ha="center", va="center",
            fontsize=12, color="#888888", transform=ax.transAxes)
    ax.axis("off")
    return fig


# ---------------------------------------------------------------------------
# Atualização central
# ---------------------------------------------------------------------------

def atualizar_tudo():
    """Regenera todos os gráficos e dados — chamado pelo botão Atualizar."""
    return (
        _fig_top_musicas_all_time(),   # plot_all_time
        _fig_treemap_artistas(),        # plot_treemap
        _tabela_tendencia(),            # tabela_tendencia
        _fig_heatmap(),                 # plot_heatmap
        _fig_taxa_atendimento(),        # plot_taxa
        _fig_ddd(),                     # plot_ddd
        _cards_taxa(),                  # txt_taxa
        _tabela_ouvintes(),             # tabela_ouvintes
    )


# ---------------------------------------------------------------------------
# Interface Gradio
# ---------------------------------------------------------------------------

with gr.Blocks(title="Dashboard — Agente Virtual Musical") as demo:

    gr.Markdown("# Agente Virtual Musical — Dashboard Analytics")
    gr.Markdown("Visão completa da audiência para decisões de programação e comercialização.")

    btn_atualizar = gr.Button("Atualizar dados", variant="primary", scale=0)

    with gr.Tabs():

        # --- Aba 1: Músicas ---
        with gr.Tab("Musicas"):
            with gr.Row():
                plot_all_time = gr.Plot(label="Histórico completo")
                plot_treemap  = gr.Plot(label="Artistas mais pedidos")
            gr.Markdown("### Trending — Top 5 desta semana vs. semana anterior")
            tabela_tendencia = gr.Dataframe(
                headers=["Tendencia", "Artista - Musica", "Pedidos esta semana"],
                interactive=False,
            )

        # --- Aba 2: Horários de Pico ---
        with gr.Tab("Horarios de Pico"):
            gr.Markdown("Identifique os horários de maior audiência para vender cotas de anúncio.")
            plot_heatmap = gr.Plot(label="Mapa de calor")

        # --- Aba 3: Audiência ---
        with gr.Tab("Audiencia"):
            with gr.Row():
                plot_taxa = gr.Plot(label="Taxa de atendimento")
                plot_ddd  = gr.Plot(label="Alcance por DDD")
            with gr.Row():
                txt_taxa = gr.Textbox(
                    label="Resumo e insights",
                    lines=12,
                    interactive=False,
                )
            gr.Markdown("### Ouvintes mais engajados")
            tabela_ouvintes = gr.Dataframe(
                headers=["Numero (mascarado)", "Pedidos", "Primeiro pedido"],
                interactive=False,
            )

    _outputs = [
        plot_all_time,
        plot_treemap,
        tabela_tendencia,
        plot_heatmap,
        plot_taxa,
        plot_ddd,
        txt_taxa,
        tabela_ouvintes,
    ]

    btn_atualizar.click(fn=atualizar_tudo, outputs=_outputs)
    demo.load(fn=atualizar_tudo, outputs=_outputs)


if __name__ == "__main__":
    database.init_db()
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("DASHBOARD_PORT", "7860")),
    )
