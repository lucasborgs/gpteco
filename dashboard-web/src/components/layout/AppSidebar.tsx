'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'

const navLinks = [
  { href: '/geral', label: 'Geral', icon: '♫' },
  { href: '/audiencia', label: 'Audiência', icon: '◉' },
]

export default function AppSidebar() {
  const pathname = usePathname()

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-64 shrink-0 bg-white border-r border-border flex-col h-screen sticky top-0">
        <div className="h-14 flex items-center px-5 border-b border-border">
          <div className="w-8 h-8 rounded-md bg-primary flex items-center justify-center mr-3">
            <span className="text-white font-heading font-bold text-sm">R</span>
          </div>
          <span className="font-heading font-bold text-content-primary text-base">Rádio FM</span>
        </div>
        <nav className="flex flex-col gap-1 p-3 flex-1">
          {navLinks.map((link) => {
            const active = pathname === link.href
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  'flex items-center px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  active
                    ? 'bg-primary/10 text-primary'
                    : 'text-content-secondary hover:bg-gray-100'
                )}
              >
                {link.label}
              </Link>
            )
          })}
        </nav>
      </aside>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-border flex justify-around py-2 px-1">
        {navLinks.map((link) => {
          const active = pathname === link.href
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                'flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg text-xs font-medium transition-colors min-w-[64px]',
                active ? 'text-primary' : 'text-content-secondary'
              )}
            >
              <span className="text-lg">{link.icon}</span>
              {link.label}
            </Link>
          )
        })}
      </nav>
    </>
  )
}
