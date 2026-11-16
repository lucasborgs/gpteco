import Link from 'next/link'
import { salesContact } from '@/lib/sales-contact'

const PLANS = [
  {
    name: 'Basic',
    subtitle: 'Automação inteligente',
    price: '297',
    integration: 'R$ 1.997',
    popular: false,
    features: [
      'Automação de pedidos via WhatsApp',
      'Curadoria por repertório da rádio',
      'Cooldown entre pedidos',
      'Bloqueio de conteúdo inapropriado',
      'Confirmação automática ao ouvinte',
      'Suporte técnico',
    ],
  },
  {
    name: 'Pro',
    subtitle: 'Automação + Marketing',
    price: '397',
    integration: 'R$ 1.997',
    popular: true,
    features: [
      'Tudo do Basic',
      'Dashboard com dados em tempo real',
      'Gráficos de audiência e horários',
      'Identificação de ouvintes frequentes',
      'Exportação de relatórios',
      'Suporte prioritário',
    ],
  },
  {
    name: 'Pro Max',
    subtitle: 'Automação + Marketing + Conteúdo',
    price: '597',
    integration: 'R$ 1.997',
    popular: false,
    features: [
      'Tudo do Pro',
      'Curadoria de notícias diárias',
      'Benchmark mensal de mercado',
      'Relatório executivo mensal',
      'Gerente de sucesso dedicado',
      'Onboarding personalizado',
    ],
  },
]

export default function PricingSection() {
  return (
    <section id="precos" className="py-20 sm:py-28 bg-gray-50">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-heading font-bold text-2xl sm:text-3xl text-content-primary">
            Planos
          </h2>
          <p className="mt-4 text-content-secondary text-lg">
            Escolha o plano ideal para sua rádio. Todos incluem integração e suporte.
          </p>
        </div>

        <div className="mt-16 grid grid-cols-1 gap-8 lg:grid-cols-3">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`relative rounded-2xl border bg-white p-8 flex flex-col ${
                plan.popular
                  ? 'border-primary shadow-lg ring-1 ring-primary'
                  : 'border-border'
              }`}
            >
              {plan.popular && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 inline-flex items-center px-4 py-1 rounded-full bg-primary text-white text-xs font-semibold uppercase tracking-wider">
                  Mais popular
                </span>
              )}

              <div>
                <h3 className="font-heading font-bold text-xl text-content-primary">
                  {plan.name}
                </h3>
                <p className="mt-1 text-sm text-content-secondary">{plan.subtitle}</p>

                <div className="mt-6 flex items-baseline gap-1">
                  <span className="font-heading font-extrabold text-4xl text-content-primary">
                    R$ {plan.price}
                  </span>
                  <span className="text-content-secondary text-sm">/mês</span>
                </div>
                <p className="mt-1 text-xs text-content-secondary">
                  Integração: {plan.integration}
                </p>
              </div>

              <ul className="mt-8 space-y-4 flex-1">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-3 text-sm">
                    <svg
                      className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2.5}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                    </svg>
                    <span className="text-content-secondary">{feature}</span>
                  </li>
                ))}
              </ul>

              <Link
                href={salesContact.href}
                target="_blank"
                rel="noopener noreferrer"
                className={`mt-8 inline-flex items-center justify-center px-6 py-3 text-sm font-semibold rounded-lg transition-colors ${
                  plan.popular
                    ? 'bg-primary text-white hover:bg-primary-hover shadow-sm'
                    : 'border border-border text-content-secondary hover:bg-gray-50 hover:text-content-primary'
                }`}
              >
                Falar com comercial
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
