"""A migracao usada pelo instalador preserva o perfil personalizado da radio."""

import os
from pathlib import Path
import re
import subprocess
import sys

import pytest


RAIZ = Path(__file__).resolve().parents[1]
INSTALADOR = (RAIZ / "scripts/atualizar-curiosidades.ps1").read_text(encoding="utf-8")
PREPARAR = re.search(r"(?ms)^    @'\n(.*?)\n'@ \| docker run", INSTALADOR).group(1)


def preparar(pasta):
    ambiente = dict(os.environ, PYTHONPATH=str(RAIZ),
                    NOVA_IMAGEM="iamlucb/gpteco:main-teste",
                    NOVO_PERFIL="perfil.novo.cliente.md")
    return subprocess.run([sys.executable, "-B", "-", str(pasta)], input=PREPARAR,
                          text=True, capture_output=True, env=ambiente)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_migracao_altera_so_prefixo_e_referencias_de_versao(tmp_path, encoding):
    perfil = (RAIZ / "core/luzia/luzia.md").read_text(encoding="utf-8")
    perfil = perfil.replace("*Curiosidade:*", "*A Lu te conta:*")
    perfil = perfil.replace("nome_radio: Luz FM", "nome_radio: Rádio do Cliente")
    perfil = perfil.replace("Boa escolha!", "Pedido recebido com carinho!")
    perfil += "\n# Anotações da rádio\nTexto personalizado que deve continuar aqui.\n"
    ambiente = "GPTECO_IMAGE=imagem-antiga\nASSISTANT_PROFILE_FILE=./antigo.md\nYT_PLAYER_CLIENT=default\nOBSERVACAO=ação do cliente\n"
    (tmp_path / "perfil.original.md").write_bytes(perfil.replace("\n", "\r\n").encode(encoding))
    original_env = ambiente.replace("\n", "\r\n").encode(encoding)
    (tmp_path / "env.original").write_bytes(original_env)

    resultado = preparar(tmp_path)

    assert resultado.returncode == 0, resultado.stderr
    assert (tmp_path / "perfil.novo.md").read_text(encoding="utf-8") == perfil.replace(
        "*A Lu te conta:*", "*Curiosidade:*")
    assert (tmp_path / "env.novo").read_text(encoding="utf-8") == ambiente.replace(
        "GPTECO_IMAGE=imagem-antiga", "GPTECO_IMAGE=iamlucb/gpteco:main-teste").replace(
        "ASSISTANT_PROFILE_FILE=./antigo.md", "ASSISTANT_PROFILE_FILE=./perfil.novo.cliente.md")
    assert (tmp_path / "env.original").read_bytes() == original_env


@pytest.mark.parametrize("problema", ["ausente", "duplicado"])
def test_migracao_recusa_prefixo_ausente_ou_duplicado(tmp_path, problema):
    perfil = (RAIZ / "core/luzia/luzia.md").read_text(encoding="utf-8")
    if problema == "ausente":
        perfil = perfil.replace("## pilula_prefixo", "## outro_nome")
    else:
        perfil += "\n## pilula_prefixo\nOutro prefixo\n"
    (tmp_path / "perfil.original.md").write_text(perfil, encoding="utf-8")

    resultado = preparar(tmp_path)

    assert resultado.returncode != 0
    assert 'Secao pilula_prefixo ausente ou duplicada' in resultado.stderr
    assert not (tmp_path / "env.novo").exists()
    assert not (tmp_path / "perfil.novo.md").exists()
    assert (tmp_path / "perfil.original.md").read_text(encoding="utf-8") == perfil
