"""
tests/test_eleitoral_lista.py

A lista de bloqueio eleitoral saiu do código e virou `core/eleitoral.json`,
editável no cliente sem rebuild (2026-10-10). O que o código garantia por
construção — só entrada bem formada existe, porque o Python não compilaria
outra coisa — agora depende de validação na carga, porque o arquivo passa a
ser editado à mão por quem não roda os testes.

O que estes testes cobrem é, portanto, o pior caso operacional: alguém edita
o JSON na pasta do cliente, erra, e o filtro eleitoral tem que continuar
bloqueando em vez de abrir. A exigência do projeto é errar para o lado da
recusa — uma música eleitoral que vai ao ar em nome da rádio é o dano que
este módulo existe para evitar.
"""

import json
from pathlib import Path

import pytest

from core import eleitoral


_LISTA_MINIMA = {
    "candidatos": ["Candidato Fulano"],
    "musicas_proibidas": [
        {"titulos": ["Jingle do Fulano"], "artistas": ["Banda Qualquer"]},
    ],
}


@pytest.fixture(autouse=True)
def _cache_limpo():
    """O cache dura a vida do processo de propósito; entre testes, não pode
    vazar — senão um caso serve a lista do anterior."""
    original = dict(eleitoral._cache)
    eleitoral._cache.update(data=None, mtime=None, path=None)
    yield
    eleitoral._cache.update(original)


def _escrever(tmp_path: Path, doc, nome="eleitoral.json") -> Path:
    caminho = tmp_path / nome
    conteudo = doc if isinstance(doc, str) else json.dumps(doc, ensure_ascii=False)
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


# --- Resolução do caminho ---------------------------------------------------

def test_sem_a_variavel_usa_a_lista_embutida(monkeypatch):
    monkeypatch.delenv("ELEITORAL_LISTA_PATH", raising=False)

    assert eleitoral.eh_musica_proibida("Lula Lá") is True
    assert eleitoral._cache["path"] == eleitoral._JSON_PATH


def test_lista_do_cliente_substitui_a_embutida(monkeypatch, tmp_path):
    caminho = _escrever(tmp_path, _LISTA_MINIMA)
    monkeypatch.setenv("ELEITORAL_LISTA_PATH", str(caminho))

    assert eleitoral.eh_musica_proibida("Jingle do Fulano") is True
    # Substitui, não soma: título da embutida que não está na do cliente passa.
    assert eleitoral.eh_musica_proibida("Lula Lá") is False
    assert eleitoral.contem_candidato("vai o candidato fulano") is True


def test_caminho_inexistente_cai_na_embutida(monkeypatch, tmp_path):
    """Variável apontando para arquivo que não existe (erro de digitação no
    .env, mount que não pegou) não pode desligar o filtro."""
    monkeypatch.setenv("ELEITORAL_LISTA_PATH", str(tmp_path / "nao-existe.json"))

    assert eleitoral.eh_musica_proibida("Lula Lá") is True
    assert eleitoral._cache["path"] == eleitoral._JSON_PATH


def test_pasta_no_lugar_do_arquivo_cai_na_embutida(monkeypatch, tmp_path):
    """Caso real do bind mount: sem o arquivo no host, o Docker cria uma
    PASTA com esse nome dentro do container (é o que o instalar.bat evita
    extraindo o padrão). O filtro tem que seguir valendo."""
    pasta = tmp_path / "eleitoral.json"
    pasta.mkdir()
    monkeypatch.setenv("ELEITORAL_LISTA_PATH", str(pasta))

    assert eleitoral.eh_musica_proibida("Lula Lá") is True
    assert eleitoral._cache["path"] == eleitoral._JSON_PATH


# --- Releitura a quente -----------------------------------------------------

def test_edicao_no_arquivo_vale_sem_restart(monkeypatch, tmp_path):
    """É a razão de existir desta mudança: a rádio adiciona um título e ele
    passa a bloquear no pedido seguinte, sem rebuild e sem restart."""
    caminho = _escrever(tmp_path, _LISTA_MINIMA)
    monkeypatch.setenv("ELEITORAL_LISTA_PATH", str(caminho))

    assert eleitoral.eh_musica_proibida("Messias", "Dead Fish") is False

    novo = json.loads(json.dumps(_LISTA_MINIMA))
    novo["musicas_proibidas"].append(
        {"titulos": ["Messias"], "artistas": ["Dead Fish"], "exige_artista": True}
    )
    caminho.write_text(json.dumps(novo, ensure_ascii=False), encoding="utf-8")
    import os
    os.utime(caminho, (0, 0))  # mtime diferente sem depender de resolução do clock

    assert eleitoral.eh_musica_proibida("Messias", "Dead Fish") is True
    # exige_artista continua valendo: o mesmo título com outro artista passa.
    assert eleitoral.eh_musica_proibida("Messias", "Coral Qualquer") is False


def test_arquivo_quebrado_na_releitura_mantem_a_versao_anterior(monkeypatch, tmp_path):
    """Edição que salvou JSON inválido no meio do expediente: o servidor
    segue com a última lista boa, não com lista nenhuma."""
    caminho = _escrever(tmp_path, _LISTA_MINIMA)
    monkeypatch.setenv("ELEITORAL_LISTA_PATH", str(caminho))
    assert eleitoral.eh_musica_proibida("Jingle do Fulano") is True

    caminho.write_text('{"musicas_proibidas": [', encoding="utf-8")
    import os
    os.utime(caminho, (0, 0))

    assert eleitoral.eh_musica_proibida("Jingle do Fulano") is True


def test_arquivo_quebrado_desde_o_inicio_cai_na_embutida(monkeypatch, tmp_path):
    """Sem versão boa em memória (servidor subindo), o fallback é a embutida
    — nunca lista vazia, nunca exceção que impede o boot."""
    caminho = _escrever(tmp_path, "isto não é json")
    monkeypatch.setenv("ELEITORAL_LISTA_PATH", str(caminho))

    assert eleitoral.eh_musica_proibida("Lula Lá") is True
    assert eleitoral._cache["path"] == eleitoral._JSON_PATH


def test_lista_vazia_e_estado_legitimo(monkeypatch, tmp_path):
    """Esvaziar as listas é como o filtro é desligado ao fim do período
    eleitoral (ver docstring do módulo) — não pode ser tratado como erro e
    cair na embutida, senão não há como desligar sem rebuild."""
    caminho = _escrever(tmp_path, {"candidatos": [], "musicas_proibidas": []})
    monkeypatch.setenv("ELEITORAL_LISTA_PATH", str(caminho))

    assert eleitoral.eh_musica_proibida("Lula Lá") is False
    assert eleitoral.contem_candidato("vota lula") is False
    assert eleitoral._cache["path"] == caminho


# --- Validação (o que o `python -m core.eleitoral` reporta) -----------------

def test_recusa_exige_artista_sem_artista():
    """Era teste de integridade do código-fonte; vale na carga agora que o
    arquivo é editado à mão. A entrada nunca bloquearia nada."""
    with pytest.raises(ValueError, match="exige_artista"):
        eleitoral._parse(json.dumps({
            "musicas_proibidas": [{"titulos": ["Sinônimos"], "exige_artista": True}],
        }))


def test_recusa_titulo_duplicado_entre_entradas():
    """Idem: colisão quase sempre é alias duplicado, e a segunda entrada
    ficaria inalcançável (ou com exige_artista divergente da primeira)."""
    with pytest.raises(ValueError, match="já aparece na entrada 0"):
        eleitoral._parse(json.dumps({
            "musicas_proibidas": [
                {"titulos": ["Faz o L"], "artistas": ["A"]},
                {"titulos": ["faz  o  l"], "artistas": ["B"]},
            ],
        }))


def test_recusa_entrada_sem_titulo():
    with pytest.raises(ValueError, match="'titulos'"):
        eleitoral._parse(json.dumps({"musicas_proibidas": [{"artistas": ["X"]}]}))


def test_recusa_titulo_em_branco():
    with pytest.raises(ValueError, match="'titulos'"):
        eleitoral._parse(json.dumps({"musicas_proibidas": [{"titulos": ["  "]}]}))


def test_recusa_exige_artista_que_nao_e_booleano():
    with pytest.raises(ValueError, match="'exige_artista'"):
        eleitoral._parse(json.dumps({
            "musicas_proibidas": [
                {"titulos": ["X"], "artistas": ["Y"], "exige_artista": "sim"}
            ],
        }))


def test_recusa_candidatos_que_nao_sao_texto():
    with pytest.raises(ValueError, match="'candidatos'"):
        eleitoral._parse(json.dumps({"candidatos": [{"nome": "Fulano"}]}))


def test_mensagem_de_erro_aponta_a_entrada():
    """A mensagem é o único canal pelo qual o cliente descobre o que corrigir
    num arquivo de 111 entradas."""
    with pytest.raises(ValueError) as erro:
        eleitoral._parse(json.dumps({
            "musicas_proibidas": [
                {"titulos": ["Primeira"], "artistas": []},
                {"titulos": ["Segunda"], "artistas": "Fulano"},
            ],
        }))

    assert "entrada 1" in str(erro.value)
    assert "Segunda" in str(erro.value)


# --- A lista que vai na imagem ---------------------------------------------

def test_lista_embutida_e_valida():
    """Guarda do arquivo versionado: ele é a rede de segurança de todos os
    fallbacks acima, então um erro nele desarma o módulo inteiro."""
    data = eleitoral._parse(eleitoral._JSON_PATH.read_text(encoding="utf-8"))

    assert len(data["musicas_proibidas"]) == 111
    assert len(data["candidatos"]) == 31
