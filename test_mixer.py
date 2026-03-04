"""
test_mixer.py

Testa o audio_mixer em isolamento, sem WhatsApp, LLM ou banco de dados.

Uso:
    python test_mixer.py --voz workspace/temp/voz.ogg --musica workspace/acervo_limpo/musica.mp3
    python test_mixer.py --voz voz.ogg --musica musica.mp3 --saida saida.mp3
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from core.audio_mixer import mixar


def main() -> int:
    parser = argparse.ArgumentParser(description="Testa o mixer de áudio isoladamente.")
    parser.add_argument("--voz",    required=True, metavar="PATH", help="Arquivo de voz (.ogg/.mp3/.wav)")
    parser.add_argument("--musica", required=True, metavar="PATH", help="Arquivo de música (.mp3)")
    parser.add_argument(
        "--saida",
        default=str(Path(__file__).parent / "workspace" / "temp" / "teste_mix.mp3"),
        metavar="PATH",
        help="Destino do .mp3 mixado (padrão: workspace/temp/teste_mix.mp3)",
    )
    args = parser.parse_args()

    for label, path in [("voz", args.voz), ("musica", args.musica)]:
        if not os.path.isfile(path):
            print(f"[ERRO] Arquivo de {label} não encontrado: {path}")
            return 1

    print(f"Voz   : {args.voz}")
    print(f"Música: {args.musica}")
    print(f"Saída : {args.saida}\n")

    try:
        path_final = mixar(args.voz, args.musica, args.saida)
        tamanho_mb = os.path.getsize(path_final) / (1024 * 1024)
        print(f"\nMixagem concluída: {path_final} ({tamanho_mb:.2f} MB)")
        return 0
    except Exception as e:
        print(f"\n[ERRO] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
