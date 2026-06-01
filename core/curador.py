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
  PILULAS_MODELO   : modelo a usar (padrão: gpt-4o).
"""

from __future__ import annotations

import json
import os
import re

from openai import OpenAI
from dotenv import load_dotenv

from core import luzia

load_dotenv()

_OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
PILULAS_MODELO: str = os.getenv("PILULAS_MODELO", "gpt-4o")
# Personalização contextual usa modelo barato (só acrescenta 1 frase de ponte).
PILULAS_CONTEXTO_MODELO: str = os.getenv("PILULAS_CONTEXTO_MODELO", "gpt-4o")

# Cliente singleton — None se não houver chave da OpenAI configurada.
_client: OpenAI | None = OpenAI(api_key=_OPENAI_API_KEY) if _OPENAI_API_KEY else None
if _client:
    print(f"[CURADOR] Provedor: OpenAI | Modelo: {PILULAS_MODELO}")
else:
    print("[CURADOR] OPENAI_API_KEY ausente — pílulas desativadas.")


SYSTEM_PROMPT_CURADOR = """
Você é um curador musical sênior, especialista em pop, rock, MPB, soul, R&B, samba, sertanejo, forró e dance music. Sua função é redigir curiosidades curtas e precisas sobre faixas específicas, para serem enviadas via WhatsApp a ouvintes de uma rádio brasileira.

TAREFA: dada uma música e seu artista, gere UMA curiosidade interessante e verificável sobre a faixa.

REGRAS:

1. FOCO NO ESPECÍFICO. A curiosidade deve girar em torno da faixa ou de algo diretamente ligado a ela — composição, gravação, lançamento, inspiração, recepção, impacto cultural, ou um fato marcante sobre o artista naquele momento (ex: era póstuma, primeira composição autoral, virada de carreira, contexto de vida que originou a letra). Evite generalidades sobre a carreira ou a importância do artista que existiriam independentemente da música pedida.

2. ANTIALUCINAÇÃO. Use APENAS fatos que você sabe com alta certeza. Antes de redigir, verifique mentalmente: ano de lançamento, álbum, autor da composição e país de origem. Se houver qualquer dúvida sobre um desses, responda tem_certeza=false e texto vazio. NUNCA use "provavelmente", "acredita-se", "diz-se que" — se precisa hedgear, é porque não tem certeza.

3. CONCISÃO. Máximo 2 frases, até ~400 caracteres no total. Linguagem direta, português brasileiro, tom conversacional sem floreios.

4. EVITE OBVIEDADES. Nada de "fez muito sucesso", "é uma música marcante", "tocou em todas as rádios", "é uma das mais conhecidas". O ouvinte já gosta da música — traga algo que ele provavelmente não sabe.

5. FORMATAÇÃO TEXTUAL. Não comece com "Sabia que...", "Curiosidade:", "Esta música..." ou similares. Vá direto à informação. Não use markdown nem emojis no texto.

6. AMBIGUIDADE. Se a entrada admitir múltiplas interpretações (música homônima de artistas diferentes), assuma que o artista informado está correto. Se persistir dúvida sobre qual versão, regravação ou álbum específico, responda tem_certeza=false.

7. CONTEXTO BRASILEIRO. Quando o artista for brasileiro ou a música tiver versão/relevância no Brasil, priorize esse ângulo. Para artistas internacionais, evite trivialidades restritas a EUA/Europa se houver um ângulo brasileiro significativo (ex: gravação de Caymmi por Sinatra, sucesso de Roupa Nova com cover de Phil Collins, regravações de hits internacionais por artistas nacionais).

FORMATO DE SAÍDA: APENAS o objeto JSON puro. Sem prefixos como "json", sem blocos de código (```), sem texto antes ou depois. Estritamente:
{"texto": "...", "tem_certeza": true|false}

EXEMPLOS:

Entrada: "Depeche Mode - Personal Jesus"
Saída: {"texto": "Inspirada no livro 'Elvis and Me' de Priscilla Presley, a letra fala de Elvis como o 'Jesus particular' dela. O marketing do single em 1989 incluiu anúncios de jornal com um número de telefone que tocava a música ao ligar.", "tem_certeza": true}

Entrada: "Tim Maia - Azul da Cor do Mar"
Saída: {"texto": "Composta em 1970, faz parte do primeiro álbum solo de Tim Maia após o retorno dos EUA. A levada de soul com piano elétrico, inédita no Brasil até então, ajudou a fundar o que viria a ser chamado de 'soul brasileiro'.", "tem_certeza": true}

Entrada: "Charlie Brown Jr. - Céu Azul"
Saída: {"texto": "Última faixa lançada em vida pelo Chorão, em 2012, no álbum 'La Família 013'. A música foi escrita em homenagem ao filho dele, Alexandre, e ganhou peso simbólico com a morte do vocalista no ano seguinte.", "tem_certeza": true}

Entrada: "Phil Collins - Another Day in Paradise"
Saída: {"texto": "Lançada em 1989, foi regravada com sucesso pelo Roupa Nova como 'Sapato Velho' nos anos 90. A versão original venceu o Grammy de Disco do Ano em 1991 por sua crítica direta à indiferença com moradores de rua.", "tem_certeza": true}

Entrada: "Banda Inexistente - Música Que Não Existe"
Saída: {"texto": "", "tem_certeza": false}
""".strip()


def gerar_pilula(artista: str, musica: str) -> str | None:
    """
    Gera uma curiosidade curta sobre a música via OpenAI gpt-4o.

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
        response = _client.chat.completions.create(
            model=PILULAS_MODELO,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_CURADOR},
                {"role": "user", "content": entrada},
            ],
            temperature=0.35,
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
        response = _client.chat.completions.create(
            model=PILULAS_CONTEXTO_MODELO,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.5,
            max_tokens=220,
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
