"""
main.py

Ponto de entrada da linha de comando do Agente Virtual Musical.
Inicializa o banco de dados e processa um pedido de ouvinte.

Uso:
    # Pedido por áudio (.ogg do WhatsApp)
    python main.py --numero 5511999999999 --ogg caminho/mensagem.ogg

    # Pedido por texto
    python main.py --numero 5511999999999 --texto "Quero ouvir Evidências do Chitãozinho e Xororó"
"""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()  # Carrega .env antes de qualquer import que use os.getenv

from core import database
from core.pipeline import processar_pedido


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Agente Virtual Musical — processa um pedido de ouvinte."
    )
    parser.add_argument(
        "--numero",
        required=True,
        help="Número de telefone do ouvinte, sem espaços (ex: 5511999999999)",
    )

    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--ogg", metavar="PATH", help="Caminho do arquivo .ogg de voz")
    grupo.add_argument("--texto", metavar="TEXTO", help="Texto do pedido entre aspas")

    args = parser.parse_args()

    # Garante que as tabelas existem antes de qualquer operação
    database.init_db()

    resultado = processar_pedido(
        numero=args.numero,
        path_ogg=args.ogg,
        texto=args.texto,
    )

    print("\n" + "=" * 60)
    print("RESULTADO DO PEDIDO")
    print("=" * 60)
    print(f"  Sucesso  : {resultado['sucesso']}")
    print(f"  Mensagem : {resultado['mensagem']}")
    if resultado["path_audio"]:
        print(f"  Arquivo  : {resultado['path_audio']}")
    print("=" * 60 + "\n")

    return 0 if resultado["sucesso"] else 1


if __name__ == "__main__":
    sys.exit(main())
