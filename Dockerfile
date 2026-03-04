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
RUN pip install --no-cache-dir -r requirements.txt

# --- Código da aplicação ---
COPY . .

# --- Diretórios de trabalho (fallback; em produção são montados como volumes) ---
RUN mkdir -p workspace/acervo_limpo workspace/fila_zara workspace/temp data

# Porta do servidor webhook
EXPOSE 8002

# Produção: 1 worker (DuckDB não suporta múltiplos writers simultâneos)
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
