from core import eleitoral


# --- contem_candidato (usado apenas para texto transcrito de áudio) ---

def test_contem_candidato_detecta_nome_simples():
    assert eleitoral.contem_candidato("vou votar no Bolsonaro esse ano") is True


def test_contem_candidato_detecta_nome_composto():
    assert eleitoral.contem_candidato("acho o Pablo Marçal um showman") is True


def test_contem_candidato_ignora_acento_e_caixa():
    assert eleitoral.contem_candidato("VOTA CAIADO 22") is True
    assert eleitoral.contem_candidato("o aurea carolina disse isso") is True


def test_contem_candidato_nao_bate_substring_de_outra_palavra():
    # "pt" não deve casar dentro de "adaptado" — mas aqui testamos com um nome
    # de candidato para não confundir com a lista de música proibida.
    assert eleitoral.contem_candidato("zemanta e cia") is False  # não é "Zema"


def test_contem_candidato_falso_positivo_conhecido_lula_molusco():
    """Risco documentado no módulo: 'lula' também é o molusco. Aceito como
    erro de recusa (o requisito legal é errar para o lado do bloqueio)."""
    assert eleitoral.contem_candidato("manda uma musica pra comer lula frita") is True


def test_contem_candidato_texto_neutro_nao_bloqueia():
    assert eleitoral.contem_candidato("quero pedir evidencias do chitaozinho e xororo") is False


def test_contem_candidato_texto_vazio():
    assert eleitoral.contem_candidato("") is False
    assert eleitoral.contem_candidato(None) is False


# --- eh_musica_proibida (vale para qualquer canal, casa só pelo título) ---

def test_eh_musica_proibida_bate_por_titulo_exato():
    assert eleitoral.eh_musica_proibida("Vai dar PT") is True
    assert eleitoral.eh_musica_proibida("Lula Lá") is True
    assert eleitoral.eh_musica_proibida("Diretas Já") is True


def test_eh_musica_proibida_ignora_acento_e_caixa():
    assert eleitoral.eh_musica_proibida("vai dar pt") is True
    assert eleitoral.eh_musica_proibida("DIRETAS JA") is True


def test_eh_musica_proibida_bloqueia_independente_do_artista():
    # A lista original tem "Léo Santana — Vai dar PT", mas o bloqueio é só
    # pelo título — qualquer artista cantando essa música é bloqueado.
    assert eleitoral.eh_musica_proibida("Vai dar PT") is True


def test_eh_musica_proibida_nao_bate_titulo_parecido_mas_diferente():
    """Falso positivo plausível: título ambíguo que apenas contém uma palavra
    da lista não deve bloquear — o casamento é pelo título inteiro."""
    assert eleitoral.eh_musica_proibida("Vai dar Certo") is False
    assert eleitoral.eh_musica_proibida("Lula Lá no Fundo do Mar") is False


def test_eh_musica_proibida_musica_normal_nao_bloqueia():
    assert eleitoral.eh_musica_proibida("Evidências") is False


def test_eh_musica_proibida_titulo_vazio():
    assert eleitoral.eh_musica_proibida("") is False
    assert eleitoral.eh_musica_proibida(None) is False
