# Agente Virtual Musical

> Ouvintes pedem músicas pelo WhatsApp. A rádio toca automaticamente.

---

## Situação

Uma rádio FM com foco no público 30+ recebia dezenas de pedidos musicais por dia via WhatsApp — mensagens de voz e texto chegando de forma desordenada, sem triagem, sem automação.

O processo era 100% manual: o locutor ouvia cada áudio, identificava a música, buscava no acervo, e ainda precisava responder ao ouvinte. Nos horários de pico, pedidos se perdiam. A experiência do ouvinte era inconsistente.

---

## Tarefa

Construir um agente de IA que fechasse o ciclo completo de ponta a ponta:

- Receber pedidos via WhatsApp (voz ou texto)
- Entender o que o ouvinte quer, mesmo com sotaque e ruído de fundo
- Validar se o pedido está dentro do repertório da rádio (flashback 30+)
- Buscar ou baixar a música automaticamente
- Mixar a voz do ouvinte com a música pedida, com transição suave
- Entregar o arquivo diretamente na fila do software de transmissão
- Responder ao ouvinte com confirmação em tempo real

Tudo isso sem intervenção humana.

---

## Acao

### Pipeline de 7 Etapas

```mermaid
flowchart TD
    A([WhatsApp\nOuvinte]) -->|voz .ogg ou texto| B[WAHA\nWhatsApp API]
    B -->|webhook POST| C[FastAPI\nserver.py]

    C --> D{Tipo?}
    D -->|audio| E[STT\nWhisper local]
    D -->|texto| F[Bypass STT]
    E --> G
    F --> G

    G[LLM\nOpenAI / Gemini\nExtracao de metadados]
    G --> H{Validacoes}
    H -->|nao eh pedido musical| Z1([Silencio\nsem resposta])
    H -->|inapropriado| Z2([Resposta\nautomatica])
    H -->|nao eh flashback| Z3([Sugestao\nde repertorio])
    H -->|aprovado| I

    I[DuckDB\nBusca no acervo local]
    I -->|ja existe| J
    I -->|nao existe| K[yt-dlp\nDownload YouTube]
    K -->|ffmpeg\nnormalizacao -14 LUFS\ncorte de silencio| J

    J{Entrada\nde voz?}
    J -->|sim| L[pydub Mixer\noverlay + fade_in\n3s antes do fim da voz]
    J -->|nao| M

    L --> M[fila_zara/\nZaraRadio\ntoca automaticamente]
    M --> N[DuckDB\nRegistra pedido\ncooldown 6h]
    N --> O([WhatsApp\nConfirmacao\nao ouvinte])

    style A fill:#25D366,color:#fff
    style B fill:#128C7E,color:#fff
    style C fill:#009688,color:#fff
    style G fill:#4A90D9,color:#fff
    style K fill:#FF6B35,color:#fff
    style L fill:#7B68EE,color:#fff
    style M fill:#2E86AB,color:#fff
    style O fill:#25D366,color:#fff
```

### Arquitetura de Servicos

```mermaid
graph LR
    subgraph Docker["Docker Compose"]
        WAHA["WAHA\n:3001\nWhatsApp NOWEB engine"]
        API["FastAPI\n:8002\nPipeline Python"]
        WAHA -->|webhook interno| API
    end

    subgraph Windows["Host Windows / ZaraRadio"]
        ZARA["ZaraRadio\nmonitor de pasta"]
        ACERVO["acervo_limpo/\nMP3s processados"]
        FILA["fila_zara/\nautomaticamente tocado"]
    end

    subgraph External["Servicos Externos"]
        YT["YouTube\nyt-dlp"]
        LLM["OpenAI / Gemini\nanalise de pedido"]
        WPP["WhatsApp\nouvintes"]
    end

    WPP --> WAHA
    API --> LLM
    API --> YT
    API --> ACERVO
    API --> FILA
    FILA --> ZARA

    style Docker fill:#E3F2FD
    style Windows fill:#FFF3E0
    style External fill:#F3E5F5
```

---

## Resultados

- Pipeline end-to-end validado: voz do ouvinte → pedido identificado → musica baixada → mixagem → fila do ZaraRadio, sem intervencao humana
- Tempo medio por pedido de texto: **~15–30s** (sem download) / **~60–90s** (com download do YouTube)
- Acervo com cache local: downloads futuros da mesma musica sao instantaneos
- Resposta automatica ao ouvinte com confirmacao ou motivo de recusa
- Sistema containerizado: `docker compose up -d` e esta pronto

---

## Stack

```
Python 3.12       FastAPI          pydub
Whisper (local)   yt-dlp           ffmpeg
DuckDB            OpenAI / Gemini  WAHA (Baileys)
Docker Compose    ZaraRadio (FM)
```

---

## Estrutura do Projeto

```
gpteco/
├── core/
│   ├── pipeline.py       # orquestrador principal (7 etapas)
│   ├── stt.py            # transcricao Whisper local
│   ├── intelligence.py   # LLM: extracao de metadados + validacoes
│   ├── downloader.py     # yt-dlp + ffmpeg (loudnorm -14 LUFS)
│   ├── audio_mixer.py    # pydub: overlay + fade_in
│   ├── database.py       # DuckDB: acervo + pedidos + cooldown
│   ├── queue_watcher.py  # fila FIFO para o ZaraRadio
│   └── whatsapp.py       # cliente WAHA (download audio + envio)
├── server.py             # FastAPI: webhook + background tasks
├── main.py               # CLI entry point
├── docker-compose.yml
├── .env.example
└── requirements.txt
```
