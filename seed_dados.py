"""
seed_dados.py

Popula o banco com 100 pedidos sintéticos para visualizar o dashboard.
Executa localmente — não afeta nenhum serviço em execução.

Uso:
    python seed_dados.py
"""

import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from core import database

# ---------------------------------------------------------------------------
# Dados sintéticos realistas (flashback brasileiro)
# ---------------------------------------------------------------------------

MUSICAS = [
    ("Roberto Carlos",           "Detalhes"),
    ("Roberto Carlos",           "Emoções"),
    ("Roberto Carlos",           "Como É Grande o Meu Amor por Você"),
    ("Chitãozinho e Xororó",     "Evidências"),
    ("Chitãozinho e Xororó",     "Eu Quero Só Você"),
    ("Leandro e Leonardo",       "Por Um Minuto"),
    ("Leandro e Leonardo",       "Temporal de Amor"),
    ("Zezé Di Camargo e Luciano","É o Amor"),
    ("Zezé Di Camargo e Luciano","Pra Sempre Apaixonado"),
    ("Raul Seixas",              "Metamorfose Ambulante"),
    ("Raul Seixas",              "Ouro de Tolo"),
    ("Legião Urbana",            "Tempo Perdido"),
    ("Legião Urbana",            "Monte Castelo"),
    ("Legião Urbana",            "Como é Grande o Meu Amor por Você"),
    ("Cazuza",                   "Preciso me Encontrar"),
    ("Cazuza",                   "O Tempo Não Para"),
    ("Titãs",                    "Comida"),
    ("Titãs",                    "Epitáfio"),
    ("Engenheiros do Hawaii",    "Refrão de Bolero"),
    ("Skank",                    "Garota Nacional"),
    ("Skank",                    "Jackie Tequila"),
    ("Paralamas do Sucesso",     "Alagados"),
    ("Paralamas do Sucesso",     "Lanterna dos Afogados"),
    ("Djavan",                   "Flor de Lis"),
    ("Djavan",                   "Samurai"),
    ("Caetano Veloso",           "Sozinho"),
    ("Gilberto Gil",             "Esperando na Janela"),
    ("Tim Maia",                 "Você"),
    ("Tim Maia",                 "Azul da Cor do Mar"),
    ("Elis Regina",              "Como Nossos Pais"),
    ("Ivan Lins",                "Começar de Novo"),
    ("Roupa Nova",               "Whisky a Go Go"),
    ("Sandy e Junior",           "Maria Chiquinha"),
    ("Sandy e Junior",           "Aquela dos Parabéns"),
    ("Wando",                    "Meiga e Abusada"),
    ("Fábio Jr.",                "Pai"),
    ("Fábio Jr.",                "Alma Gêmea"),
    ("Ana Carolina",             "Quem de Nós Dois"),
    ("Ivete Sangalo",            "Sorte Grande"),
    ("Ivete Sangalo",            "Careless Whisper"),
]

NUMEROS = [f"5534{900000000 + i * 7 + random.randint(0, 6)}" for i in range(30)]

MOTIVOS = ["cooldown", "nao_flashback", "inapropriado", "nao_identificado"]
PESO_MOTIVOS = [50, 30, 12, 8]  # % de cada motivo entre os rejeitados


def _timestamp_aleatorio(dias_atras_max: int = 30) -> datetime:
    """Gera timestamp aleatório nos últimos N dias, com horários realistas."""
    dias = random.randint(0, dias_atras_max)
    # Horários de pico: tarde/noite (70% entre 17h-23h, 30% outros horários)
    if random.random() < 0.70:
        hora = random.choice([17, 18, 19, 20, 21, 22, 23])
    else:
        hora = random.randint(7, 16)
    minuto = random.randint(0, 59)
    base = datetime.now() - timedelta(days=dias)
    return base.replace(hour=hora, minute=minuto, second=random.randint(0, 59), microsecond=0)


def popular():
    database.init_db()
    con = database._get_connection()

    inseridos = 0
    rejeitados = 0

    try:
        for i in range(100):
            numero = random.choice(NUMEROS)
            artista, musica = random.choice(MUSICAS)
            ts = _timestamp_aleatorio()

            # ~72% de sucesso, ~28% de rejeição (taxa realista)
            if random.random() < 0.72:
                sucesso = True
                motivo = None
            else:
                sucesso = False
                motivo = random.choices(MOTIVOS, weights=PESO_MOTIVOS, k=1)[0]
                if motivo in ("nao_identificado",):
                    artista, musica = "", ""

            con.execute("""
                INSERT INTO dim_pedidos
                    (numero, artista, musica, timestamp_pedido, sucesso, motivo_rejeicao)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [numero, artista, musica, ts, sucesso, motivo])

            if sucesso:
                inseridos += 1
            else:
                rejeitados += 1

        con.commit()
        print(f"[SEED] 100 pedidos inseridos: {inseridos} aceitos, {rejeitados} rejeitados.")
        print("[SEED] Abra o dashboard para visualizar: python dashboard.py")

    finally:
        con.close()


if __name__ == "__main__":
    popular()
