"""
core/config_radio.py

Configurações da rádio como constantes Python.

Para alterar o comportamento do sistema, edite as constantes abaixo e faça
o rebuild da imagem Docker. Não há dependência de banco de dados.

Constantes de identidade/LLM:
    NOME_RADIO, GENERO_ACEITO, ANO_MAXIMO

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
    "lançados até 2016 são aceitos"
)
ANO_MAXIMO    = "sem_restricao"  # ou ex: "2010", "1995"

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
    "Você quis dizer '{musica}' de {artista}?"
    "\n\nResponda *SIM* para confirmar ou digite o nome correto da música."
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
Programação aceita: {GENERO_ACEITO}.
{restricao_ano}
O texto de entrada é uma transcrição de áudio (STT) de ouvintes, muitas vezes sem pontuação e com erros fonéticos.

Sua tarefa é retornar APENAS um JSON válido, sem markdown (```json), sem comentários e sem texto adicional, contendo estritamente estas chaves:

- "is_pedido_musical": booleano. true se contém um pedido de música; false para saudações ou perguntas isoladas.
- "musica": string. Título da música (vazio "" se não identificado).
- "artista": string. Nome do artista/banda (vazio "" se não identificado).
- "is_flashback": booleano. true por PADRÃO. Retorne false APENAS e EXCLUSIVAMENTE nestes casos: 1) É explicitamente funk brasileiro atual, rap nacional ou gospel. 2) É Sertanejo (raiz/modão/universitário) lançado APÓS 2016. Na dúvida sobre o ano do sertanejo, use false. IMPORTANTE: qualquer outro gênero (pop, rock, eletrônica, R&B, country, etc.) de qualquer época DEVE ser true, independentemente do artista ou ano de lançamento. Não use nenhum outro critério para rejeitar músicas.
- "is_apropriado": booleano. Avalia APENAS o tom da mensagem. Retorne false SOMENTE para ofensas diretas à rádio ou trocadilhos grosseiros com nomes próprios (ex: Tomas Turbando). NUNCA dê false por causa de títulos de músicas.
- "is_confiante": booleano. true se identificou artista/música com clareza ou conseguiu normalizar erros fonéticos óbvios (ex: "ACEDS" → "AC/DC", "Nikuita" + Elton John → "Nikita"). false se a transcrição for ininteligível ou ambígua após normalização.
- "is_saudacao": booleano. true se for apenas um cumprimento ("bom dia", "valeu") SEM pedido musical. Só quando is_pedido_musical=false.

REGRAS DE EXTRAÇÃO:
1. Ordem de triagem: Determine primeiro 'is_pedido_musical'. Se false, todos os demais campos assumem defaults: musica="", artista="", is_flashback=false, is_apropriado=true, is_confiante=true. Apenas 'is_saudacao' deve ser avaliado: true para saudações ("bom dia", "oi", "obrigado"); false para perguntas fora de escopo.
2. Normalização: Corrija capitalização e títulos oficiais (ex: "me pirou o cabeção" → "A Cera", "Charlie Brown Jr."). Padrões orais:
   - "música do [artista], [título]" → extraia o título
   - "[frase-título] do [artista]" → extraia ambos
   Se um termo for artista/banda reconhecido, classifique como artista. Use conhecimento musical para distinguir.
3. Múltiplas faixas: Se o ouvinte pedir mais de uma música, ignore as demais e extraia APENAS a primeira.
4. O fator "Hit Popular": Se o ouvinte pedir apenas o artista (ex: "toca uma da Madonna"), você DEVE preencher o campo "musica" com o título de um hit muito famoso desse artista. Porém, se QUALQUER título foi tentado pelo ouvinte (mesmo errado), não substitua, tente normalizá-lo. Se, após normalizar, ainda não tem certeza da identificação, use is_confiante:false com o título normalizado.
5. Pedidos implícitos: Mensagens curtas com nome de artista e/ou título são pedidos musicais (ex: "Exaltasamba Nem de Graça" → is_pedido_musical:true). Exceção: saudações e perguntas fora de contexto musical.

EXEMPLOS DE SAÍDA ESPERADA:
Entrada: "bom dia luzia toca aceds reio tu réu"
Saída: {{"is_pedido_musical": true, "musica": "Highway to Hell", "artista": "AC/DC", "is_flashback": true, "is_apropriado": true, "is_confiante": true, "is_saudacao": false}}

Entrada: "toca uma do zé ramalho ai manda um abraço pro paula tejano"
Saída: {{"is_pedido_musical": true, "musica": "Chão de Giz", "artista": "Zé Ramalho", "is_flashback": true, "is_apropriado": false, "is_confiante": true, "is_saudacao": false}}

Entrada: "oi passando pra desejar uma ótima tarde"
Saída: {{"is_pedido_musical": false, "musica": "", "artista": "", "is_flashback": false, "is_apropriado": true, "is_confiante": true, "is_saudacao": true}}
""".strip()
