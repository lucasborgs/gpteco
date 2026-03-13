import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#1DB954',
        'primary-hover': '#1ED760',
        'app-bg': '#F9FAFB',
        surface: '#FFFFFF',
        'content-primary': '#111827',
        'content-secondary': '#6B7280',
        border: '#E5E7EB',
      },
      boxShadow: {
        card: '0 1px 3px 0 rgb(0 0 0 / 0.08), 0 1px 2px -1px rgb(0 0 0 / 0.06)',
      },
      fontFamily: {
        heading: ['Cabinet Grotesk', 'sans-serif'],
        data: ['Fragment Mono', 'monospace'],
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

export default config
