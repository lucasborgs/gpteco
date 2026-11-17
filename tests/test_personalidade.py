"""A voz editável da rádio chega às três formas de escrever para o ouvinte."""

import os
from unittest.mock import Mock

import pytest

from core import composer, curador, luzia


@pytest.mark.parametrize("fluxo", ["resposta", "curiosidade", "ponte"])
def test_escrita_acompanha_mudancas_no_tom_do_perfil(tmp_path, monkeypatch, fluxo):
    perfil_original = luzia._MD_PATH.read_text(encoding="utf-8")
    tom_original = luzia._parse(perfil_original)["secoes"]["tom"]["_text"]
    perfil = tmp_path / "assistente.md"
    monkeypatch.setenv("ASSISTANT_PROFILE_PATH", str(perfil))

    base = "A faixa saiu em 1975, no álbum A Night at the Opera."
    if fluxo == "curiosidade":
        conteudo = '{"texto": "Fato sobre a música.", "tem_certeza": true}'
    elif fluxo == "ponte":
        conteudo = base + " Que ela faça companhia pra você na estrada!"
    else:
        conteudo = "Me conta o nome da música e do artista?"

    cliente = Mock()
    cliente.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content=conteudo))]
    )
    monkeypatch.setattr(composer, "_client", cliente)
    monkeypatch.setattr(curador, "_client", cliente)

    for indice, tom in enumerate([
        "Você é a Lu, uma comunicadora de rádio próxima e acolhedora.",
        "Você é a Lu, uma comunicadora de rádio serena e bem-humorada.",
    ]):
        perfil.write_text(perfil_original.replace(tom_original, tom), encoding="utf-8")
        # Garante a invalidação mesmo em sistemas de arquivos de baixa resolução.
        instante = perfil.stat().st_mtime + indice + 1
        os.utime(perfil, (instante, instante))

        if fluxo == "resposta":
            assert composer.compor("nao_id", {}, "quero uma música") == conteudo
        elif fluxo == "curiosidade":
            assert curador.gerar_pilula("Queen", "Bohemian Rhapsody") == "Fato sobre a música."
        else:
            assert curador.personalizar_pilula(base, "vou pegar a estrada") == conteudo

        mensagens = cliente.chat.completions.create.call_args.kwargs["messages"]
        assert mensagens[0]["role"] == "system"
        assert tom in mensagens[0]["content"]
