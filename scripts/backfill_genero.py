"""
scripts/backfill_genero.py

Preenche a coluna 'genero' em dim_pedidos para registros existentes.

Agrupa pedidos por (artista, musica) únicos, classifica cada combinação
via LLM e atualiza todos os registros do grupo em batch.

Uso:
    python -m scripts.backfill_genero
"""

import json
import os
import sys
import time

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

_USAR_GROQ = bool(GROQ_API_KEY) and not bool(OPENAI_API_KEY)

if _USAR_GROQ:
    client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
else:
    client = OpenAI(api_key=OPENAI_API_KEY)
    MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = """Você é um classificador de gênero musical.
Dado um artista e uma música, retorne APENAS um JSON com a chave "genero" contendo o gênero musical em minúsculas.
Valores esperados: "pop", "rock", "sertanejo", "mpb", "pagode", "samba", "forró", "axé", "eletrônica", "r&b", "soul", "country", "reggae", "jazz", "blues", "bossa nova", "hip hop", "metal", "punk", "folk", "dance", "disco", "new wave", "indie", "clássico", "romântico", "infantil".
Se não conseguir identificar, use "outro".
Retorne APENAS o JSON, sem markdown."""


def classificar_genero(artista: str, musica: str) -> str:
    try:
        response = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Artista: {artista}\nMúsica: {musica}"},
            ],
            temperature=0.1,
        )
        dados = json.loads(response.choices[0].message.content)
        return str(dados.get("genero", "outro")).strip().lower()
    except Exception as e:
        print(f"  ERRO ao classificar '{artista} - {musica}': {e}")
        return ""


def main():
    if not DATABASE_URL:
        print("DATABASE_URL não configurada. Defina no .env.")
        sys.exit(1)

    con = psycopg2.connect(DATABASE_URL)
    try:
        with con.cursor() as cur:
            # Busca combinações únicas sem gênero
            cur.execute("""
                SELECT DISTINCT artista, musica
                FROM dim_pedidos
                WHERE (genero IS NULL OR genero = '')
                  AND artista != '' AND musica != ''
            """)
            combinacoes = cur.fetchall()

        total = len(combinacoes)
        if total == 0:
            print("Nenhum pedido sem gênero encontrado.")
            return

        print(f"Encontradas {total} combinações únicas para classificar.\n")

        for i, (artista, musica) in enumerate(combinacoes, 1):
            print(f"[{i}/{total}] {artista} - {musica}...", end=" ")
            genero = classificar_genero(artista, musica)

            if genero:
                with con.cursor() as cur:
                    cur.execute("""
                        UPDATE dim_pedidos
                        SET genero = %s
                        WHERE artista = %s AND musica = %s
                          AND (genero IS NULL OR genero = '')
                    """, [genero, artista, musica])
                con.commit()
                print(f"→ {genero}")
            else:
                print("→ FALHOU")

            # Rate limit: evitar throttling da API
            if _USAR_GROQ:
                time.sleep(0.5)
            else:
                time.sleep(0.2)

        print(f"\nBackfill concluído. {total} combinações processadas.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
