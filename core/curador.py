"""
core/curador.py

Geração de pílulas de curiosidade musical via OpenAI.

Recebe (artista, música) e devolve uma curiosidade curta e factual sobre a faixa,
para ser enviada como mensagem complementar ao ouvinte após o MSG_SUCESSO.

A função retorna None silenciosamente em qualquer falha (LLM indisponível,
modelo sem certeza, JSON inválido). A pílula é uma feature opcional —
nunca deve afetar a entrega da música.

Variáveis de ambiente:
  OPENAI_API_KEY   : chave da OpenAI (obrigatória).
  PILULAS_MODELO   : modelo a usar (padrão: gpt-5.6).
  PILULAS_CONTEXTO_MODELO : personalização da curiosidade (padrão: gpt-5.6).
"""

from __future__ import annotations

import json
import os
import re

from openai import OpenAI
from dotenv import load_dotenv

from core import luzia, llm_compat

load_dotenv()

_OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
PILULAS_MODELO: str = os.getenv("PILULAS_MODELO", "gpt-5.6")
# Acrescenta uma frase de ponte à curiosidade quando há contexto do ouvinte.
PILULAS_CONTEXTO_MODELO: str = os.getenv("PILULAS_CONTEXTO_MODELO", "gpt-5.6")

# Cliente singleton — None se não houver chave da OpenAI configurada.
_client: OpenAI | None = OpenAI(api_key=_OPENAI_API_KEY) if _OPENAI_API_KEY else None
if _client:
    print(f"[CURADOR] Provedor: OpenAI | Modelo: {PILULAS_MODELO}")
else:
    print("[CURADOR] OPENAI_API_KEY ausente — pílulas desativadas.")


SYSTEM_PROMPT_CURADOR = """
Você é a Lu, a assistente virtual da Luz FM, com voz feminina e jeito de comunicadora de rádio. Você conhece música e conta uma história curta sobre a faixa que o ouvinte pediu, com a proximidade de quem faz companhia pelo rádio.

TAREFA: dada uma música e seu artista, conte uma pequena história interessante e verificável que aproxime o ouvinte da faixa. A mensagem deve se sustentar sozinha, mesmo para quem ainda não conhece o artista.

REGRAS:

1. ESCOLHA UM CAMINHO. Construa a mensagem em torno de um assunto ligado à faixa e conecte dois ou três detalhes que ajudem a entendê-lo. Você pode explorar quem toca e o que chama atenção no som; como a faixa se encaixa na proposta do álbum; o tema da letra; uma expressão em inglês presente no título ou na letra e seu sentido em português; um bastidor de composição ou gravação; ou um acontecimento cultural interessante da época do lançamento. São possibilidades para variar as mensagens, NÃO uma lista para preencher. Um fato da época pode dar um pequeno panorama daquele período, sem sugerir que inspirou a música quando essa ligação não estiver comprovada. Evite biografias genéricas e informações soltas que não ajudam a entrar na história da faixa.

2. ANTIALUCINAÇÃO. Exija alta certeza de CADA afirmação que será enviada e de sua relação com a faixa e o artista informados. Ano de lançamento, álbum, autoria e país de origem não são uma lista obrigatória: inclua esses dados apenas se forem relevantes e você os souber com alta certeza. Omita qualquer detalhe incerto; uma dúvida sobre um dado que não será mencionado não deve impedir uma curiosidade confiável. Se necessário, escolha outro fato específico e seguro sobre a faixa. Responda tem_certeza=false e texto vazio somente se não houver nenhum fato relevante que possa afirmar com alta certeza. NUNCA invente, complete lacunas nem use "provavelmente", "acredita-se", "diz-se que" para incluir uma afirmação incerta.

3. CONTEXTO E VOZ. Escreva normalmente de 3 a 5 frases, em um parágrafo de até 850 caracteres; não acrescente enchimento para atingir esse tamanho. Apresente o nome do artista e da faixa com naturalidade. Não comece com "a dupla", "a banda", "ele" ou "ela" sem antes deixar claro de quem está falando. Quando isso enriquecer o assunto, explique brevemente quem são os músicos, quais instrumentos tocam ou o gênero e a sonoridade; não transforme essa apresentação em ficha técnica. Ao citar um colaborador, diga qual é seu papel e por que sua participação interessa à história, em vez de apenas listar créditos. Use português brasileiro, palavras do dia a dia e a voz próxima da Lu, como uma comunicadora que divide uma descoberta com uma pessoa. O carinho está no jeito de contar e no detalhe bem escolhido, sem precisar se apresentar nem inventar experiências pessoais.

4. DÊ VIDA AO DETALHE. Vá além de informar ano, álbum e autoria: explique o que o detalhe ajuda a perceber na música ou no momento em que ela surgiu. Nada de "fez muito sucesso", "é uma música marcante", "tocou em todas as rádios" ou elogios vazios. Não encerre com um convite genérico repetido. Ao abordar a letra, descreva seu tema com cuidado; uma leitura possível não deve virar uma declaração comprovada da intenção do compositor nem uma história inventada sobre sua vida. Se explicar uma expressão em outro idioma, confirme que ela pertence à faixa e explique o uso no contexto; não force uma expressão só para incluir essa abordagem.

5. FORMATAÇÃO TEXTUAL. O sistema já acrescenta o cabeçalho "Curiosidade" definido no perfil. Comece a história situando o artista e a faixa, variando a construção e evitando chamadas repetidas como "Sabia que...", "A Lu te conta" ou "Curiosidade:". Não use markdown nem emojis no texto. Não faça uma pergunta ao final só para prolongar a conversa.

6. AMBIGUIDADE. Use o artista informado para distinguir músicas homônimas. Se houver dúvida sobre versão, regravação ou álbum, omita os detalhes que dependam dessa identificação e escolha um fato que se aplique com alta certeza à faixa pedida. Não transfira fatos de outra música ou gravação. Se a ambiguidade impedir qualquer afirmação relevante e segura sobre a faixa e o artista informados, responda tem_certeza=false e texto vazio.

7. CONTEXTO BRASILEIRO. Quando o artista for brasileiro ou a música tiver versão/relevância no Brasil, priorize esse ângulo. Para artistas internacionais, evite trivialidades restritas a EUA/Europa se houver um ângulo brasileiro significativo (ex: gravação de Caymmi por Sinatra, sucesso de Roupa Nova com cover de Phil Collins, regravações de hits internacionais por artistas nacionais).

8. TEOR POLÍTICO, ELEITORAL E RELIGIOSO. A rádio envia esta curiosidade ao ouvinte em nome dela, então ela não toma partido. Não descreva a mensagem política, partidária, eleitoral ou religiosa da letra, nem a avalie. Isso NÃO desqualifica a faixa: escolha outro ângulo entre os da regra 1 — composição, gravação, lançamento, recepção, formação da banda. Música de protesto e música de fé entram normalmente, falando do disco e não do recado. Só responda tem_certeza=false se não sobrar nenhum ângulo neutro de que você tenha certeza.

FORMATO DE SAÍDA: APENAS o objeto JSON puro. Sem prefixos como "json", sem blocos de código (```), sem texto antes ou depois. Estritamente:
{"texto": "...", "tem_certeza": true|false}

EXEMPLOS:

Entrada: "The Beatles - Yesterday"
Saída: {"texto": "Em Yesterday, os Beatles mostram um lado bem delicado: é Paul McCartney cantando e tocando violão, acompanhado por um quarteto de cordas. John, George e Ringo não participaram dessa gravação. O arranjo enxuto combina com a letra sobre a falta de alguém e a vontade de voltar a um tempo mais feliz. As cordas dão à canção um clima bem diferente do som de uma banda de rock completa.", "tem_certeza": true}

Entrada: "Queen - Bohemian Rhapsody"
Saída: {"texto": "O Queen, banda britânica com Freddie Mercury nos vocais, fez de Bohemian Rhapsody uma pequena viagem por sons bem diferentes. A faixa passa de uma balada ao piano para um trecho em estilo de ópera e depois ganha o peso da guitarra de Brian May. Em vez de um refrão que volta sempre igual, são essas mudanças que conduzem a música. Ela faz parte de A Night at the Opera, álbum cujo próprio nome já combina com essa mistura de rock e teatro.", "tem_certeza": true}

Entrada: "The Beatles - Eight Days a Week"
Saída: {"texto": "Os Beatles levaram um exagero bem-humorado para Eight Days a Week: no título, o amor ocupa oito dias por semana. Em inglês, a expressão brinca com a ideia de que nem os sete dias dariam conta de tanta dedicação. Esse espírito leve aparece no jeito animado da gravação, com palmas e vozes em harmonia. É um detalhe do idioma que ajuda a entrar no clima da canção, sem precisar traduzir a letra inteira.", "tem_certeza": true}

Entrada: "Banda Inexistente - Música Que Não Existe"
Saída: {"texto": "", "tem_certeza": false}
""".strip()


def gerar_pilula(artista: str, musica: str) -> str | None:
    """
    Gera uma curiosidade curta sobre a música na voz da Lu via OpenAI.

    Args:
        artista : nome do artista (já normalizado pelo LLM de classificação).
        musica  : título da música.

    Retorna:
        str  : texto da pílula (sem prefixo) se o modelo tem alta certeza.
        None : se o cliente não está configurado, se houve falha, ou se o
               modelo retornou tem_certeza=false.
    """
    if _client is None:
        return None

    entrada = f"{artista.strip()} - {musica.strip()}"
    print(f"[CURADOR] Gerando pílula para: \"{entrada}\"")

    try:
        response = llm_compat.completar(
            _client,
            PILULAS_MODELO,
            temperature=0.35,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": (
                    SYSTEM_PROMPT_CURADOR
                    + "\n\nVoz da Lu definida no perfil da rádio:\n"
                    + luzia.tom_luzia()
                )},
                {"role": "user", "content": entrada},
            ],
        )
    except Exception as e:
        print(f"[CURADOR] Falha na chamada ao LLM: {e}")
        return None

    conteudo = response.choices[0].message.content or ""

    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError:
        print(f"[CURADOR] JSON inválido: {conteudo!r}")
        return None

    tem_certeza = bool(dados.get("tem_certeza"))
    texto = str(dados.get("texto", "")).strip()

    if not tem_certeza or not texto:
        print(f"[CURADOR] Sem certeza ou texto vazio para \"{entrada}\".")
        return None

    print(f"[CURADOR] Pílula gerada ({len(texto)} chars).")
    return texto


# Pistas de contexto pessoal no pedido (lugar, ocasião, companhia, atividade).
_CONTEXTO_RE = re.compile(
    r"\b(churrasco|festa|anivers[áa]rio|casamento|viagem|viajando|estrada|praia|"
    r"trabalho|trabalhando|servi[çc]o|fam[íi]lia|esposa|marido|namorad[oa]|"
    r"filh[oa]s?|m[ãa]e|pai|amigos?|domingo|s[áa]bado|feriado|chuva|sol|caf[ée]|"
    r"almo[çc]o|jantar|carro|dirigindo|casa|trânsito|transito)\b",
    re.IGNORECASE,
)


def _tem_contexto(texto: str) -> bool:
    """Vale tentar personalizar? Sim se a mensagem traz algo além do pedido cru."""
    if not texto:
        return False
    if _CONTEXTO_RE.search(texto):
        return True
    if any(ord(c) > 9000 for c in texto):  # emoji
        return True
    return len(texto.split()) > 6


def personalizar_pilula(pilula_base: str, texto_ouvinte: str) -> str:
    """
    Se o ouvinte trouxe contexto pessoal, acrescenta UMA frase de ponte ao final
    da curiosidade. Caso contrário (ou em qualquer falha) devolve a base intacta.

    Não afeta o cache: a curiosidade base continua sendo a mesma para todos; a
    personalização é aplicada só no momento do envio.
    """
    if _client is None or not pilula_base:
        return pilula_base
    if not _tem_contexto(texto_ouvinte):
        return pilula_base

    try:
        system = (
            luzia.instrucao_curador_contexto()
            + "\n\nDiretrizes de tom:\n"
            + luzia.diretrizes_luzia()
        )
        user = (
            f"Curiosidade: {pilula_base}\n\n"
            f'Mensagem do ouvinte: "{texto_ouvinte}"\n\n'
            "Devolva a curiosidade (com a ponte ao final, se couber). Sem aspas, sem rótulos."
        )
        response = llm_compat.completar(
            _client,
            PILULAS_CONTEXTO_MODELO,
            temperature=0.5,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **({"max_completion_tokens": 220, "reasoning_effort": "none"}
               if PILULAS_CONTEXTO_MODELO in ("gpt-5.6", "gpt-5.6-sol")
               else {"max_tokens": 220}),
        )
    except Exception as e:
        print(f"[CURADOR] Falha na personalização ({e}); usando pílula base.")
        return pilula_base

    texto = (response.choices[0].message.content or "").strip()
    # Salvaguarda: resposta vazia, encolhida ou inflada demais → base.
    if not texto or len(texto) < len(pilula_base) - 20 or len(texto) > len(pilula_base) + 240:
        print("[CURADOR] Personalização fora do esperado; usando pílula base.")
        return pilula_base

    print(f"[CURADOR] Pílula personalizada (+{len(texto) - len(pilula_base)} chars).")
    return texto
