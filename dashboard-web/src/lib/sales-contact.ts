const phone = (process.env.NEXT_PUBLIC_CONTACT_WHATSAPP || '').replace(/\D/g, '')
const hasWhatsApp = /^[1-9]\d{9,14}$/.test(phone)
const message = 'Olá! Quero saber mais sobre o assistente virtual AKAPO'

export const contactEmail = process.env.NEXT_PUBLIC_CONTACT_EMAIL?.trim() || 'contato@akapo.com.br'

export const salesContact = {
  href: hasWhatsApp
    ? `https://wa.me/${phone}?text=${encodeURIComponent(message)}`
    : `mailto:${contactEmail}?subject=${encodeURIComponent('Assistente virtual AKAPO')}`,
  label: hasWhatsApp ? 'Fale no WhatsApp' : 'Fale por email',
  description: hasWhatsApp ? 'Chama a gente no WhatsApp.' : 'Escreva para a nossa equipe.',
  isWhatsApp: hasWhatsApp,
}
