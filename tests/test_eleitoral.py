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


# --- Lista consolidada do apêndice A (110 entradas) ---

def test_eh_musica_proibida_bate_por_alias():
    assert eleitoral.eh_musica_proibida("Lula Lá") is True
    assert eleitoral.eh_musica_proibida("Sem Medo de Ser Feliz") is True


def test_eh_musica_proibida_exige_artista():
    assert eleitoral.eh_musica_proibida("Brasil", "Cazuza") is True
    assert eleitoral.eh_musica_proibida("Brasil", "Rosa de Saron") is False
    assert eleitoral.eh_musica_proibida("Brasil", "") is False


def test_eh_musica_proibida_normaliza_artista_nos_dois_sentidos():
    assert eleitoral.eh_musica_proibida("Negro Drama", "Racionais") is True


def test_eh_musica_proibida_caso_degenerado_titulo_de_uma_letra():
    assert eleitoral.eh_musica_proibida("É", "Gonzaguinha") is True
    assert eleitoral.eh_musica_proibida("É", "Ivete Sangalo") is False


def test_eh_musica_proibida_faixas_sertanejas():
    assert eleitoral.eh_musica_proibida("Para e Reflete") is True
    assert eleitoral.eh_musica_proibida("Olha o Trem") is True
    assert eleitoral.eh_musica_proibida("O Prato do Dia") is True
    assert eleitoral.eh_musica_proibida("A Viola e a Bíblia") is True
    assert eleitoral.eh_musica_proibida("Capitão do Povo") is True


def test_eh_musica_proibida_racionais_mcs():
    assert eleitoral.eh_musica_proibida("Diário de um Detento") is True
    assert eleitoral.eh_musica_proibida("Fim de Semana no Parque") is True
    assert eleitoral.eh_musica_proibida("Capítulo 4 Versículo 3") is True
    assert eleitoral.eh_musica_proibida("Jesus Chorou") is True
    assert eleitoral.eh_musica_proibida("Negro Drama") is True
    assert eleitoral.eh_musica_proibida("Vida Loka") is False


def test_musicas_proibidas_sem_titulo_duplicado_entre_entradas():
    """Teste de integridade: nenhum título normalizado pode casar com mais
    de uma entrada — colisão quase sempre significa alias duplicado."""
    vistos: dict[str, int] = {}
    for indice, entrada in enumerate(eleitoral.MUSICAS_PROIBIDAS):
        for titulo in entrada.titulos:
            titulo_norm = eleitoral._normalizar(titulo)
            assert titulo_norm not in vistos, (
                f"título '{titulo_norm}' duplicado entre as entradas "
                f"{vistos.get(titulo_norm)} e {indice}"
            )
            vistos[titulo_norm] = indice


def test_musicas_proibidas_exige_artista_tem_artistas_nao_vazio():
    """Teste de integridade: toda entrada que exige artista precisa ter ao
    menos um artista conhecido para casar — senão ela nunca bloqueia."""
    for indice, entrada in enumerate(eleitoral.MUSICAS_PROIBIDAS):
        if entrada.exige_artista:
            assert entrada.artistas, (
                f"entrada {indice} ({entrada.titulos!r}) tem exige_artista=True "
                "mas artistas vazio"
            )
