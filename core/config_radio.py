"""
core/config_radio.py

Configurações da rádio como constantes Python.

Para alterar o comportamento do sistema, edite as constantes abaixo e faça
o rebuild da imagem Docker. Não há dependência de banco de dados.

Constantes de identidade/LLM:
    NOME_RADIO, GENERO_ACEITO, ANO_MAXIMO, PUBLICO_ALVO

Constantes de mensagens ao ouvinte:
    MSG_SUCESSO, MSG_COOLDOWN, MSG_INAPROPRIADO, MSG_NAO_REPERTORIO,
    MSG_NAO_ID, MSG_CONFIRMACAO, MSG_SAUDACAO

Função pública:
    build_system_prompt() -> str
"""

# ---------------------------------------------------------------------------
# Identidade e regras do LLM
# ---------------------------------------------------------------------------

NOME_RADIO    = "Luz FM"
GENERO_ACEITO = (
    "todos os gêneros musicais, exceto funk brasileiro atual, "
    "rap nacional/brasileiro e gospel; sertanejo raiz, modão e universitário "
    "lançados até 2012 são aceitos"
)
ANO_MAXIMO    = "sem_restricao"  # ou ex: "2010", "1995"
PUBLICO_ALVO  = "adulto 30+"

# ---------------------------------------------------------------------------
# Mensagens enviadas ao ouvinte
# ---------------------------------------------------------------------------

MSG_SUCESSO = (
    "Obrigado pela sua indicação! {artista} - {musica} já está na fila."
    "\n\nLuz FM, sempre ligada em você! 💡"
)
MSG_COOLDOWN = (
    "Você já fez um pedido nas últimas 6 horas. Tente novamente mais tarde."
    "\n\nLuz FM, sempre ligada em você! 💡"
)
MSG_INAPROPRIADO = (
    "Não foi possível atender esse pedido. Mande uma mensagem respeitosa."
    "\n\nLuz FM, sempre ligada em você! 💡"
)
MSG_NAO_REPERTORIO = (
    "Infelizmente '{musica}' de {artista} não está no repertório da Luz FM."
    "\n\nQuer pedir outro sucesso?"
    "\n\nLuz FM, sempre ligada em você! 💡"
)
MSG_NAO_ID = (
    "Não consegui identificar a música. Pode repetir o pedido?"
    "\n\nLuz FM, sempre ligada em você! 💡"
)
MSG_CONFIRMACAO = (
    "Entendi '{musica}' de '{artista}', mas não encontrei essa música.\n"
    "Pode digitar o nome correto da música e do artista?"
    "\n\nLuz FM, sempre ligada em você! 💡"
)
MSG_SAUDACAO = (
    "Oi! Eu sou a LuzIA, a assistente virtual da Luz FM. 😊\n"
    "Quer pedir um sucesso da sua época? É só me mandar o nome da música e do artista!"
    "\n\nLuz FM, sempre ligada em você! 💡"
)


# ---------------------------------------------------------------------------
# System prompt do LLM (construído a partir das constantes acima)
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    """
    Constrói o SYSTEM_PROMPT do LLM dinamicamente a partir das constantes da rádio.
    """
    restricao_ano = (
        ""
        if ANO_MAXIMO == "sem_restricao"
        else f"Músicas lançadas após {ANO_MAXIMO} NÃO se qualificam para a programação desta rádio.\n"
    )

    return f"""
Você é o assistente de triagem de pedidos da {NOME_RADIO}, uma rádio FM brasileira.
Público: {PUBLICO_ALVO}. Programação aceita: {GENERO_ACEITO}.
{restricao_ano}
Retorne APENAS um JSON válido (sem markdown, sem comentários) com estas chaves:

- "is_pedido_musical": true se é pedido de música; false para saudações, elogios, perguntas, etc.
- "musica": título da música ("" se não identificado)
- "artista": nome do artista/banda ("" se não identificado)
- "is_flashback": true se o gênero é permitido ({GENERO_ACEITO}). Avalie gênero, nunca idioma.
- "is_apropriado": true se a mensagem é respeitosa
- "is_confiante": true se identificou artista/música com confiança; false se a transcrição parece ter erros (ex: "ACEDS" → "AC/DC", "Hell to Hell" → "Highway to Hell"). Para texto digitado, use true salvo se ininteligível.
- "is_saudacao": true se é saudação/cumprimento/agradecimento sem pedido musical. Só quando is_pedido_musical=false.

Regras:
0. Determine PRIMEIRO se é pedido musical. Se false, demais campos assumem defaults ("","",false,true,false). is_saudacao=true apenas para saudações ("bom dia","oi","obrigado"); false para perguntas fora de escopo.
1. Sem identificação → strings vazias + is_flashback:false. Baixa confiança → retorne o que extraiu + is_confiante:false.
2. is_apropriado avalia APENAS o tom da mensagem, NUNCA títulos de músicas ou nomes de artistas. False somente para xingamentos/ofensas ao rádio, ou nomes próprios de pessoa que sejam trocadilhos grosseiros em português.
3. Normalize artista/música: capitalização correta, título oficial (ex: "me pirou o cabeção" → "A Cera", "Charlie Brown Jr."). Padrões orais:
   - "música do [artista], [título]" → extraia o título
   - "[frase-título] do [artista]" → extraia ambos
   Se um termo for artista/banda reconhecido, classifique como artista. Use conhecimento musical para distinguir.
4. Mais de uma música → identifique APENAS a primeira.
5. Artista sem título específico (ex: "toca uma do Zé Ramalho") → escolha um hit popular. ATENÇÃO: se qualquer título foi mencionado (mesmo com grafia errada ou apelido), retorne-o normalizado. NUNCA substitua por outro hit. Se baixa confiança, mantenha o título + is_confiante:false.
6. Sertanejo: is_flashback=true somente se lançada até 2012. Pós-2012 = false. Na dúvida, false.
7. Mensagens curtas com nome de artista/título são pedidos implícitos (ex: "Exaltasamba Nem de Graça" → true). Exceção: saudações e perguntas fora de contexto musical.
""".strip()
