# ============================================================
# Agente Virtual Musical — Dockerfile
# ============================================================
# Build:  docker compose build servidor
# Run:    docker compose up -d
# ============================================================

FROM python:3.13-slim

# --- Dependências do sistema ---
# ffmpeg: conversão e mixagem de áudio (pydub, yt-dlp)
# build-essential: gcc/g++ para compilar extensões C (audioop-lts, etc.)
# nodejs: runtime JavaScript exigido pelo yt-dlp para extrair formatos do YouTube
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        build-essential \
        nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Dependências Python (camada separada para cache eficiente) ---
# Copiamos apenas o requirements.txt primeiro para que o Docker
# só reinstale pacotes quando ele mudar, não a cada mudança de código.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --upgrade "yt-dlp[default,deno]"

# --- Código da aplicação ---
COPY . .

# --- Diretórios de trabalho (fallback; em produção são montados como volumes) ---
RUN mkdir -p workspace/musicas/acervo_limpo workspace/musicas/fila_zara workspace/temp

# --- Perfil padrão da assistente (fallback; em produção o cliente monta o
# próprio assistente.md por cima via bind mount em ASSISTANT_PROFILE_PATH) ---
RUN mkdir -p /app/config && cp core/luzia/luzia.md /app/config/assistente.md

# --- Lista de bloqueio eleitoral (mesmo esquema: a emissora edita a dela no
# host e monta por cima via ELEITORAL_LISTA_PATH). Esta cópia é o padrão a ser
# extraído pelo instalar.bat; a de core/ é o fallback de core/eleitoral.py ---
RUN cp core/eleitoral.json /app/config/eleitoral.json

# Porta do servidor webhook
EXPOSE 8002

# Produção: 1 worker (pipeline não é thread-safe para múltiplos workers)
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
