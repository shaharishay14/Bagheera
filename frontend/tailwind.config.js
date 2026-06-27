/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:             'rgb(var(--bg) / <alpha-value>)',
        surface:        'rgb(var(--surface) / <alpha-value>)',
        'surface-subtle': 'rgb(var(--surface-subtle) / <alpha-value>)',
        border: {
          DEFAULT: 'rgb(var(--border) / <alpha-value>)',
          strong:  'rgb(var(--border-strong) / <alpha-value>)',
        },
        ink: {
          DEFAULT: 'rgb(var(--ink) / <alpha-value>)',
          muted:   'rgb(var(--ink-muted) / <alpha-value>)',
          faint:   'rgb(var(--ink-faint) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--accent) / <alpha-value>)',
          dark:    'rgb(var(--accent-dark) / <alpha-value>)',
          muted:   'rgb(var(--accent-muted) / <alpha-value>)',
          text:    'rgb(var(--accent-text) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['Poppins', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'Consolas', 'monospace'],
      },
      backgroundImage: {
        'grad-accent': 'var(--grad-accent)',
        'grad-brand':  'var(--grad-brand)',
      },
      boxShadow: {
        card:        '0 1px 2px rgba(30,27,22,0.04), 0 4px 16px -8px rgba(30,27,22,0.10)',
        'card-hover':'0 2px 6px rgba(30,27,22,0.06), 0 12px 32px -10px rgba(245,158,66,0.22)',
        modal:       '0 24px 70px -12px rgba(30,27,22,0.28)',
        glow:        'var(--glow-accent)',
        'glow-lg':   'var(--glow-accent-lg)',
      },
      borderRadius: {
        sm:   '0.375rem',
        DEFAULT: '0.5rem',
        md:   '0.625rem',
        lg:   '0.875rem',
        xl:   '1.125rem',
        '2xl':'1.5rem',
        full: '9999px',
      },
      animation: {
        'pulse-slow': 'pulse 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
};
