import { NextRequest, NextResponse } from 'next/server'
import OpenAI from 'openai'

export const dynamic = 'force-dynamic'

const MODELO = process.env.INSIGHTS_MODELO || 'gpt-4o-mini'

type ChatMsg = { role: 'user' | 'assistant'; content: string }

const SYSTEM_PROMPT = `Você é um analista de dados da rádio Luz FM, que recebe pedidos de música por WhatsApp.
Fale sempre em português do Brasil, de forma direta, objetiva e amigável.

Regras:
- Para NÚMEROS, baseie-se exclusivamente nos dados (JSON) fornecidos. Nunca invente valores.
- Para perguntas CONCEITUAIS (como o sistema funciona, o que significa um motivo de recusa, o que é "repertório"), use a seção CONHECIMENTO DO SISTEMA abaixo.
- Se um filtro estiver ativo, deixe claro que a análise é sobre aquele recorte.
- Use os termos do domínio: pedidos, atendidos, taxa de atendimento, gêneros, artistas, ouvintes, picos de horário.
- Quando os dados não trouxerem a resposta, diga isso honestamente (ex.: o recorte atual não inclui esse detalhe).
- Seja conciso. Destaque o que importa em vez de repetir listas inteiras que já estão na tela.

CONHECIMENTO DO SISTEMA (sempre válido — use para perguntas conceituais):
- A Luz FM é especializada em FLASHBACKS dos gêneros: pop, rock, MPB, samba e sertanejo. No sertanejo, NÃO são aceitos (não são flashback): piseiro, sofrência eletrônica, feminejo, sertanejo funk e arrocha.
- "Dentro do repertório" significa que a música é um flashback de um desses gêneros aceitos. "Fora do repertório" é o motivo de recusa "nao_flashback".
- Cada pedido é atendido ou recusado por um motivo:
  • Atendidos — pedido aceito e enviado para tocar.
  • Fora do repertório (nao_flashback) — a música não é um flashback de gênero aceito.
  • Não identificado (nao_identificado) — não foi possível reconhecer o artista/música com confiança.
  • Cooldown — o ouvinte já havia pedido recentemente (limite padrão de 1 pedido a cada 6 horas por ouvinte).
  • Inapropriado — o conteúdo do pedido foi considerado inadequado.
  • Erro técnico (erro_tecnico) — falha ao processar/enfileirar o pedido.
- Saudações ("oi", "bom dia", "obrigado") não contam como pedido e ficam fora das métricas.
- Taxa de atendimento = pedidos atendidos ÷ total de pedidos válidos (sem saudações).
- Os ouvintes são identificados pelo número de WhatsApp; "fãs frequentes" são os que tiveram 2 ou mais pedidos atendidos.`

function promptInsightsAuto(): string {
  return `Gere uma análise curta dos dados a seguir, em markdown, com exatamente duas seções:

**Fatos** — 3 a 4 bullets com os números mais relevantes do recorte.
**Insights** — 2 a 3 bullets com interpretações ou recomendações acionáveis para a rádio (ex.: melhor horário para tocar certo gênero, lacunas de repertório, ouvintes fiéis).

Não use títulos além desses dois. Não escreva introdução nem conclusão.`
}

export async function POST(request: NextRequest) {
  if (!process.env.OPENAI_API_KEY) {
    return NextResponse.json({
      text: '⚠️ A análise por IA não está configurada. Defina `OPENAI_API_KEY` no ambiente do dashboard para ativar os insights.',
      configured: false,
    })
  }

  let body: { summary?: unknown; filterLabel?: string; messages?: ChatMsg[] }
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: 'Payload inválido' }, { status: 400 })
  }

  const { summary, filterLabel, messages } = body
  const isChat = Array.isArray(messages) && messages.length > 0

  const contexto =
    `Recorte atual: ${filterLabel || 'todos os pedidos do período selecionado'}.\n` +
    `Dados (JSON):\n${JSON.stringify(summary ?? {}, null, 2)}`

  const chatMessages: { role: 'system' | 'user' | 'assistant'; content: string }[] = [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: contexto },
  ]

  if (isChat) {
    chatMessages.push({
      role: 'assistant',
      content: 'Entendido. Tenho os dados do recorte atual em mãos. Pode perguntar.',
    })
    messages!.forEach(m => chatMessages.push({ role: m.role, content: m.content }))
  } else {
    chatMessages.push({ role: 'user', content: promptInsightsAuto() })
  }

  try {
    const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })
    const completion = await client.chat.completions.create({
      model: MODELO,
      messages: chatMessages,
      temperature: 0.4,
      max_tokens: isChat ? 600 : 450,
    })
    const text = completion.choices[0]?.message?.content?.trim() || 'Sem resposta.'
    return NextResponse.json({ text, configured: true })
  } catch (err) {
    console.error('[API] Insights error:', err)
    return NextResponse.json(
      { text: 'Não consegui gerar a análise agora. Tente novamente em instantes.', configured: true },
      { status: 200 },
    )
  }
}
