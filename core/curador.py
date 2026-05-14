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

import json
import os

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
PILULAS_MODELO: str = os.getenv("PILULAS_MODELO", "gpt-4o")

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

1. FOCO NA MÚSICA. Fale sobre composição, gravação, lançamento, inspiração, recepção ou impacto cultural da faixa específica. Cite o artista apenas quando a informação sobre ele for indispensável para a curiosidade (ex: era póstuma, primeira composição autoral, marcou uma virada de carreira).

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
            temperature=0.3,
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
