"""
scripts/backfill_telefone.py

Resolve LID → telefone real para pedidos existentes no banco.

Busca todos os números @lid distintos que ainda não têm telefone resolvido,
consulta a API WAHA e atualiza a coluna 'telefone' em dim_pedidos.

Uso:
    python -m scripts.backfill_telefone
"""

import os
import sys
import time

import httpx
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3001")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")


def _headers():
    return {"Authorization": f"Bearer {WAHA_API_KEY}"} if WAHA_API_KEY else {}


def resolver_lid(lid_numero: str) -> str | None:
    """Consulta a API WAHA para resolver um LID em telefone real."""
    lid = lid_numero.split("@")[0]
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"{WAHA_URL}/api/{WAHA_SESSION}/lids/{lid}",
                headers=_headers(),
            )
            if response.status_code == 200:
                return response.json().get("phoneNumber")
    except Exception as e:
        print(f"  ERRO ao resolver {lid_numero}: {e}")
    return None


def main():
    if not DATABASE_URL:
        print("DATABASE_URL não configurada. Defina no .env.")
        sys.exit(1)

    con = psycopg2.connect(DATABASE_URL)
    try:
        with con.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT numero
                FROM dim_pedidos
                WHERE numero LIKE '%@lid'
                  AND (telefone IS NULL OR telefone = '')
            """)
            lids = [row[0] for row in cur.fetchall()]

        total = len(lids)
        if total == 0:
            print("Nenhum LID pendente de resolução.")
            return

        print(f"Encontrados {total} LIDs para resolver.\n")
        resolvidos = 0

        for i, lid_numero in enumerate(lids, 1):
            print(f"[{i}/{total}] {lid_numero}...", end=" ")
            telefone = resolver_lid(lid_numero)

            if telefone:
                with con.cursor() as cur:
                    cur.execute(
                        "UPDATE dim_pedidos SET telefone = %s WHERE numero = %s AND (telefone IS NULL OR telefone = '')",
                        [telefone, lid_numero],
                    )
                con.commit()
                resolvidos += 1
                print(f"→ {telefone}")
            else:
                print("→ NÃO RESOLVIDO")

            time.sleep(0.3)

        print(f"\nBackfill concluído. {resolvidos}/{total} LIDs resolvidos.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
