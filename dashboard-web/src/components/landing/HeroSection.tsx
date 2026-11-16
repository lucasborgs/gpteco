export default function HeroSection() {
  return (
    <section className="relative pt-32 pb-20 sm:pt-40 sm:pb-28 overflow-hidden">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl text-center">
          <h1 className="font-heading font-extrabold text-4xl sm:text-5xl lg:text-6xl text-content-primary leading-[1.1] tracking-tight">
            Transforme o WhatsApp da sua rádio em{' '}
            <span className="text-primary">engajamento</span>
          </h1>
          <p className="mt-6 text-lg sm:text-xl text-content-secondary leading-relaxed max-w-2xl mx-auto">
            Assistente virtual musical que automatiza pedidos, fideliza ouvintes e
            entrega dados em tempo real — tudo com a cara da sua rádio.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              href="#precos"
              className="inline-flex items-center px-8 py-3 text-sm font-semibold rounded-lg bg-primary text-white hover:bg-primary-hover transition-colors shadow-sm"
            >
              Quero para minha rádio
            </a>
            <a
              href="#como-funciona"
              className="inline-flex items-center px-8 py-3 text-sm font-semibold rounded-lg border border-border text-content-secondary hover:bg-gray-50 hover:text-content-primary transition-colors"
            >
              Como funciona
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}
