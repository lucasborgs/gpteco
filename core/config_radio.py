"""
core/config_radio.py

Configurações da rádio armazenadas no DuckDB (tabela dim_configuracoes).

Permite que cada instalação defina seu próprio comportamento sem alterar código:
  - Nome da rádio, gênero aceito, faixa de anos, público-alvo
  - Mensagens de resposta ao ouvinte (sucesso, cooldown, rejeições)

O SYSTEM_PROMPT do LLM é construído dinamicamente a partir dessas configurações,
tornando o sistema agnóstico ao formato de programação da rádio.

Funções públicas:
    get_config(chave)          -> str
    set_config(chave, valor)   -> None
    get_all_config()           -> dict[str, str]
    seed_defaults()            -> None
    build_system_prompt()      -> str
"""

from core import database

# Valores padrão — usados como fallback se a chave não existir no banco
_DEFAULTS: dict[str, str] = {
    "nome_radio":       "Luz FM",
    "genero_aceito":    "todos os gêneros musicais, exceto funk brasileiro atual e gospel; sertanejo raiz, modão e universitário lançados até 2012 são aceitos",
    "ano_maximo":       "sem_restricao",
    "publico_alvo":     "adulto 30+",
    "msg_sucesso":      "Obrigado pela sua indicação! {artista} - {musica} já está na fila.\nLuz FM, sempre ligada em você!",
    "msg_cooldown":     "Você já fez um pedido nas últimas 6 horas. Tente novamente mais tarde.\nLuz FM, sempre ligada em você!",
    "msg_inapropriado": "Não foi possível atender esse pedido. Mande uma mensagem respeitosa.\nLuz FM, sempre ligada em você!",
    "msg_nao_repertorio": "'{musica}' não está no repertório da rádio. Que tal outro clássico?\nLuz FM, sempre ligada em você!",
    "msg_nao_id":       "Não consegui identificar a música. Pode repetir o pedido?\nLuz FM, sempre ligada em você!",
}


def get_config(chave: str) -> str:
    """
    Retorna o valor de uma configuração.
    Se a chave não existir no banco, retorna o valor padrão de _DEFAULTS.
    """
    con = database._get_connection()
    try:
        row = con.execute(
            "SELECT valor FROM dim_configuracoes WHERE chave = ?", [chave]
        ).fetchone()
        return row[0] if row else _DEFAULTS.get(chave, "")
    finally:
        con.close()


def set_config(chave: str, valor: str) -> None:
    """
    Insere ou atualiza uma configuração no banco.
    Só aceita chaves conhecidas para evitar poluição do banco.
    """
    if chave not in _DEFAULTS:
        print(f"[CONFIG] Chave desconhecida ignorada: '{chave}'")
        return

    con = database._get_connection()
    try:
        con.execute("""
            INSERT INTO dim_configuracoes (chave, valor)
            VALUES (?, ?)
            ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor
        """, [chave, valor])
        con.commit()
        print(f"[CONFIG] Configuração atualizada: {chave} = '{valor}'")
    finally:
        con.close()


def get_all_config() -> dict[str, str]:
    """
    Retorna todas as configurações como dicionário.
    Chaves sem registro no banco usam o valor padrão.
    """
    con = database._get_connection()
    try:
        rows = con.execute("SELECT chave, valor FROM dim_configuracoes").fetchall()
        config = dict(_DEFAULTS)  # começa com defaults
        config.update({row[0]: row[1] for row in rows})  # sobrescreve com valores do banco
        return config
    finally:
        con.close()


def seed_defaults() -> None:
    """
    Insere as chaves padrão que ainda não existem no banco.
    Chamado pelo init_db() no startup — nunca sobrescreve valores existentes.
    """
    con = database._get_connection()
    try:
        existentes = {
            row[0]
            for row in con.execute("SELECT chave FROM dim_configuracoes").fetchall()
        }
        novos = 0
        for chave, valor in _DEFAULTS.items():
            if chave not in existentes:
                con.execute(
                    "INSERT INTO dim_configuracoes (chave, valor) VALUES (?, ?)",
                    [chave, valor],
                )
                novos += 1
        if novos:
            con.commit()
            print(f"[CONFIG] {novos} configurações padrão inseridas.")
    finally:
        con.close()


def build_system_prompt() -> str:
    """
    Constrói o SYSTEM_PROMPT do LLM dinamicamente a partir das configurações da rádio.

    Lê: nome_radio, genero_aceito, ano_maximo, publico_alvo
    """
    nome_radio   = get_config("nome_radio")
    genero       = get_config("genero_aceito")
    ano_maximo   = get_config("ano_maximo")
    publico_alvo = get_config("publico_alvo")

    restricao_ano = (
        ""
        if ano_maximo == "sem_restricao"
        else f"Músicas lançadas após {ano_maximo} NÃO se qualificam para a programação desta rádio.\n"
    )

    return f"""
Você é o assistente de triagem de pedidos da {nome_radio}, uma rádio FM brasileira.
O público é {publico_alvo} e a programação aceita {genero}.
{restricao_ano}
Analise a mensagem do ouvinte e retorne APENAS um objeto JSON válido com estas chaves:

- "is_pedido_musical": boolean — true se a mensagem é um pedido de música para a rádio;
                       false para qualquer outra coisa (saudações, agradecimentos,
                       perguntas gerais, elogios, conversas, etc.)
- "musica"           : string com o título da música mencionada (ou "" se não identificado)
- "artista"          : string com o nome do artista/banda (ou "" se não identificado)
- "is_flashback"     : boolean — true se a música se encaixa na programação da rádio
- "is_apropriado"    : boolean — true se a mensagem é respeitosa; false caso contrário

Regras importantes:
0. Determine PRIMEIRO se é um pedido de música. Se is_pedido_musical for false, os outros
   campos podem assumir seus valores padrão ("", "", false, true) — não force identificação.
1. Se não conseguir identificar música ou artista com confiança, retorne strings vazias
   e is_flashback: false.
2. is_apropriado é false se a mensagem contiver xingamentos, ofensas ou conteúdo impróprio;
   OU se qualquer nome próprio na mensagem (remetente ou destinatário) for um trocadilho,
   nome-piada ou apelido com conotação sexual ou grosseira quando lido foneticamente em
   português (ex: nomes que soam como expressões obscenas ou palavrões).
3. Normalize artista e música: capitalize corretamente, remova ruído da transcrição,
   e use o título oficial da música mesmo que o ouvinte use uma letra, apelido popular
   ou nome coloquial (ex: "me pirou o cabeção" → musica: "A Cera", artista: "Charlie Brown Jr.").
4. Retorne SOMENTE o JSON, sem markdown, sem comentários, sem texto adicional.
5. Se o ouvinte mencionar mais de uma música, identifique APENAS a primeira
   mencionada na mensagem. Ignore as demais completamente.
6. Se o ouvinte pedir uma música de um artista sem especificar o título
   (ex: "toca uma do Zé Ramalho", "coloca uma música do Charlie Brown"), escolha
   uma música popular desse artista e preencha `musica` com o título oficial escolhido.
7. Para músicas sertanejas: is_flashback só é true se a música foi lançada até 2012.
   Sertanejo lançado após 2012 (ex: sertanejo pop moderno) deve ter is_flashback: false.
   Em caso de dúvida sobre o ano, prefira false para sertanejo.
""".strip()
