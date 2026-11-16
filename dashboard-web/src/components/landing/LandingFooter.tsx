import Link from 'next/link'
import { contactEmail, salesContact } from '@/lib/sales-contact'

export default function LandingFooter() {
  return (
    <footer className="border-t border-border bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
          <div>
            <Link href="/" className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-white font-heading font-bold text-sm">
                A
              </div>
              <span className="font-heading font-bold text-content-primary text-lg">AKAPO</span>
            </Link>
            <p className="mt-4 text-sm text-content-secondary leading-relaxed max-w-xs">
              Assistente virtual musical white-label para rádios FM. Tecnologia que aproxima
              sua rádio dos ouvintes.
            </p>
          </div>

          <div>
            <h4 className="font-heading font-bold text-sm text-content-primary uppercase tracking-wider">
              Produto
            </h4>
            <ul className="mt-4 space-y-3">
              {[
                { label: 'Como funciona', href: '#como-funciona' },
                { label: 'Benefícios', href: '#beneficios' },
                { label: 'Preços', href: '#precos' },
                { label: 'Área do Cliente', href: '/painel' },
              ].map((item) => (
                <li key={item.label}>
                  <Link
                    href={item.href}
                    className="text-sm text-content-secondary hover:text-content-primary transition-colors"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h4 className="font-heading font-bold text-sm text-content-primary uppercase tracking-wider">
              Contato
            </h4>
            <ul className="mt-4 space-y-3">
              {salesContact.isWhatsApp && <li>
                <Link
                  href={salesContact.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-content-secondary hover:text-content-primary transition-colors"
                >
                  WhatsApp
                </Link>
              </li>}
              <li>
                <a
                  href={`mailto:${contactEmail}`}
                  className="text-sm text-content-secondary hover:text-content-primary transition-colors"
                >
                  {contactEmail}
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-border">
          <p className="text-sm text-content-secondary text-center">
            &copy; {new Date().getFullYear()} AKAPO. Todos os direitos reservados.
          </p>
        </div>
      </div>
    </footer>
  )
}
