# SDD — Landing Page Comercial AKAPO

## 1. Visão Geral

Produto white-label: assistente virtual musical para rádios FM.
Empresa: **AKAPO**.
O sistema permite que ouvintes peçam músicas via WhatsApp de forma automatizada,
com curadoria inteligente (repertório da rádio, cooldown, restrições) e análise
de dados em tempo real.

**Propósito da landing page:** Apresentar o produto, converter visitantes em
clientes e direcionar clientes existentes para o dashboard (`/painel`).

---

## 2. Requisitos Funcionais

### 2.1 Seções da Página

| # | Seção | Conteúdo |
|---|-------|----------|
| 1 | **Hero** | Headline principal, subtítulo, CTA "Quero para minha rádio" (âncora para preços) |
| 2 | **O que é** | Descrição do assistente virtual musical. Produto white-label, personalizável com a marca da rádio. |
| 3 | **Como funciona** | 3-4 steps visuais com ícones: (1) Ouvinte envia música no WhatsApp (2) Sistema valida curadoria (3) Música toca na rádio (4) Dados e insights |
| 4 | **Benefícios** | Cards: Aproximação com o ouvinte, Curadoria inteligente, Automação 24/7, Dados em tempo real |
| 5 | **Preços** | 3 planos (Basic, Pro, Pro Max) conforme tabela abaixo |
| 6 | **Fale Conosco** | Link direto para WhatsApp |
| 7 | **Footer** | Logo AKAPO, links, copyright |

### 2.2 Tabela de Preços

| Plano | Recursos | Preço |
|-------|----------|-------|
| **Basic** | Automação de pedidos via WhatsApp | R$ 1.997 integração + R$ 297/mês |
| **Pro** | Basic + Análise de marketing | R$ 1.997 integração + R$ 397/mês |
| **Pro Max** | Pro + Curadoria de notícias diárias + Benchmark mensal | R$ 1.997 integração + R$ 597/mês |

> **Nota:** O valor de integração (R$ X) e os preços mensais serão validados
> pelo sub-agente especialista em precificação.

### 2.3 Navegação

- Header fixo com: Logo AKAPO | Links das seções (scroll suave) | Botão "Área do Cliente" → `/painel`
- Link "Fale Conosco" → WhatsApp (link direto)
- Footer com: Logo | Links | Redes | Copyright AKAPO

### 2.4 Restrições

- Página 100% pública (sem autenticação)
- Sem dependência de dados do banco
- Performance: Lighthouse > 90 em todas as categorias
- Mobile-first

---

## 3. Arquitetura

### 3.1 Rotas

```
/              → Landing page (HOME)
/painel        → Dashboard (existente, inalterado)
/insights      → Insights (existente, inalterado)
```

### 3.2 Layout Tree

```
RootLayout (html, body, globals.css)
├── LandingPage (/) — sem FiltersProvider
│   ├── LandingHeader
│   ├── HeroSection
│   ├── HowItWorksSection
│   ├── BenefitsSection
│   ├── PricingSection
│   └── LandingFooter
│
└── AppLayout (/painel, /insights) — com FiltersProvider
    ├── DashboardLayout (sidebar + header)
    └── página específica
```

### 3.3 Mudanças Necessárias no Layout Atual

1. **`layout.tsx` (root):** Remover `FiltersProvider` — manter apenas html, body, globals.css.
2. **Painel:** Envolver em `FiltersProvider` localmente ou criar `AppLayout` wrapper.
3. **`LandingHeader`** tem navegação própria, não compartilha com dashboard.

---

## 4. Design System (Homepage)

### 4.1 Princípios

- Tema **claro profissional** (landing page SaaS)
- Consistente com o dashboard atual (Inter, Tailwind)
- Green `#1DB954` como cor de CTA/accent
- Clean, espaçado, tipografia clara

### 4.2 Paleta

| Token | Cor | Uso |
|-------|-----|-----|
| `--brand` | `#1DB954` | CTAs, destaques, badges |
| `--brand-hover` | `#1ED760` | Hover de CTAs |
| `--bg` | `#FFFFFF` | Fundo |
| `--bg-alt` | `#F9FAFB` | Seções alternadas |
| `--text-primary` | `#111827` | Títulos |
| `--text-secondary` | `#6B7280` | Corpo |
| `--border` | `#E5E7EB` | Bordas |

### 4.3 Tipografia (mesma do dashboard)

| Uso | Fonte | Weight | Size |
|-----|-------|--------|------|
| Título hero | Cabinet Grotesk | 800 | 3rem (mobile: 2rem) |
| Seção título | Cabinet Grotesk | 700 | 1.5rem |
| Corpo | Inter | 400 | 1rem |
| Botão | Inter | 600 | 0.875rem |
| Preço | Cabinet Grotesk | 800 | 2.5rem |

### 4.4 Componentes Compartilhados

**Card:**
- `bg-white`, `rounded-xl`, `border border-border`, `shadow-card`
- Padding: `p-6`

**Botão Primário:**
- `bg-primary`, `text-white`, `rounded-lg`, `px-6 py-2.5`
- `hover:bg-primary-hover`

**Botão Secundário:**
- `border border-border`, `text-content-secondary`, `rounded-lg`, `px-6 py-2.5`
- `hover:bg-gray-50`

**Ícones steps:**
- Círculo com fundo verde e número/ícone
- 48x48px (mobile: 40x40px)

---

## 5. Componentes

### 5.1 LandingHeader

- Fixed top, `bg-white/80 backdrop-blur-md`
- Logo "AKAPO" + nome do produto (configurável)
- Nav: links para seções (scroll suave)
- Botão: "Área do Cliente" → `/painel`

### 5.2 HeroSection

- Headline: ex: "Transforme o WhatsApp da sua rádio em uma máquina de engajamento"
- Subtexto: ex: "Assistente virtual musical que automatiza pedidos, fideliza ouvintes e entrega dados em tempo real — com a cara da sua rádio."
- CTA: "Quero para minha rádio" (scroll para preços)
- Imagem/ilustração decorativa (placeholder)

### 5.3 HowItWorksSection

- 4 steps:
  1. 🙋 Ouvinte envia "quero ouvir [música]" no WhatsApp
  2. 🤖 Sistema valida: repertório, cooldown, restrições da rádio
  3. 🔊 Música entra na fila e toca na programação
  4. 📊 Dashboard mostra tudo: pedidos, ouvintes, horários, tendências
- Cada step: ícone + título + descrição
- Grid: 2x2 desktop, 1 coluna mobile

### 5.4 BenefitsSection

- 4 cards: Aproximação com o ouvinte, Curadoria inteligente,
  Automação 24/7, Dados em tempo real
- Cada card: ícone + título + texto curto

### 5.5 PricingSection

- 3 cards lado a lado (desktop), empilhados (mobile)
- Pro em destaque ("Mais popular")
- Cada card: nome, preço, bullet list de recursos, CTA
- CTA dos planos: link para WhatsApp de contato

### 5.6 ContactSection

- Título "Fale Conosco"
- Texto e CTA → WhatsApp
- Pode incluir email de contato

### 5.7 LandingFooter

- Grid com: Logo + descrição, Links rápidos, Contato (WhatsApp)
- Copyright "© 2024 AKAPO. Todos os direitos reservados."

---

## 6. Critérios de Aceitação

- [ ] Homepage acessível em `/` sem redirect
- [ ] Header fixo com scroll suave para seções
- [ ] Botão "Área do Cliente" navega para `/painel`
- [ ] Seções: Hero, O que é, Como funciona, Benefícios, Preços, Contato
- [ ] Responsivo: mobile e desktop sem quebra
- [ ] Performance: Lighthouse > 90
- [ ] Dashboard `/painel` e `/insights` continuam funcionando
- [ ] Preços refletem validação do sub-agente
- [ ] Fonte Inter + Cabinet Grotesk (consistente com dashboard)
- [ ] Contato via WhatsApp funcional
- [ ] Build Next.js sem erros (`npm run build`)

---

## 7. Estratégia de Implementação

### 7.1 Ordem

1. SDD spec ✅ (este documento)
2. Sub-agente de precificação (pesquisa de mercado)
3. Reestruturar layouts (separar homepage do dashboard)
4. Componentes da homepage (1 por 1)
5. Montagem da página `/`
6. Ajustes responsivos e build

### 7.2 Sub-Agente de Precificação

O sub-agente especialista deve:
- Pesquisar preços de mercado para SaaS de automação para rádios
- Analisar concorrentes (serviços similares de pedidos musicais, chatbots)
- Considerar o mercado brasileiro
- Validar ou sugerir ajustes nos valores: integração R$ 1.997, mensalidades R$ 297/397/597
- Entregar relatório com recomendação final

### 7.3 Observações

- Produto white-label: o nome "Assistente Virtual Musical" é genérico, a rádio
  pode nomear como quiser (ex: "LuzIA" para Luz FM)
- A empresa AKAPO é quem fornece a tecnologia
- O link do WhatsApp deve ser configurável (enviar para contato comercial)

### 7.4 Integração na base main

- Landing em `/`; páginas atuais da `main` preservadas em `/painel` e `/insights`
  por um grupo de rotas com `FiltersProvider` próprio.
- Contato por `NEXT_PUBLIC_CONTACT_WHATSAPP`, configurado antes do build. Na
  ausência de número válido, usa `NEXT_PUBLIC_CONTACT_EMAIL` (padrão:
  `contato@akapo.com.br`), sem encaminhar visitantes ao telefone fictício.
- Valores e serviços dos planos preservam a proposta comercial existente.
  Pesquisa de mercado, cobrança e controle de assinaturas não fazem parte desta
  integração. O experimento conversacional permanece em branch separada.
