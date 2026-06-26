/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#F6F4ED',
        card: '#FFFEFB',
        ink: {
          DEFAULT: '#16201C',
          soft: '#4A564F',
          faint: '#7C867F',
        },
        line: {
          DEFAULT: '#DCD8CC',
          soft: '#E8E4D9',
        },
        jade: {
          DEFAULT: '#0F6E56',
          soft: '#E1F1EA',
          dark: '#0d5e49',
        },
        gold: {
          DEFAULT: '#B8801A',
          soft: '#F6ECD6',
        },
        gain: '#0F6E56',
        loss: {
          DEFAULT: '#A8401F',
          soft: '#F6E3DA',
        },
        info: {
          DEFAULT: '#2F4858',
          soft: '#E2E9EE',
        },
        rose: {
          DEFAULT: '#925B6A',
          soft: '#F2E4E8',
        },
        plum: {
          DEFAULT: '#5A3D6B',
          soft: '#EDE4F2',
        },
        neutral: '#4A564F',
        ac: {
          stock: '#0F6E56',
          crypto: '#5A3D6B',
          tbill: '#2F4858',
          commodity: '#B8801A',
          fund: '#3E7C8C',
        },
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'display-xl': ['48px', { lineHeight: '1.05', fontWeight: '600' }],
        'display-l': ['34px', { lineHeight: '1.1', fontWeight: '600' }],
        heading: ['24px', { lineHeight: '1.2', fontWeight: '600' }],
        subheading: ['19px', { lineHeight: '1.3', fontWeight: '500' }],
        body: ['16px', { lineHeight: '1.6', fontWeight: '400' }],
        'body-sm': ['14px', { lineHeight: '1.5', fontWeight: '400' }],
        caption: ['12px', { lineHeight: '1.4', fontWeight: '500' }],
        eyebrow: ['11px', { lineHeight: '1.4', fontWeight: '600', letterSpacing: '0.18em' }],
        'data-l': ['32px', { lineHeight: '1.1', fontWeight: '500' }],
        data: ['16px', { lineHeight: '1.3', fontWeight: '500' }],
      },
      borderRadius: {
        sm: '6px',
        DEFAULT: '10px',
        lg: '14px',
        xl: '20px',
      },
      boxShadow: {
        sm: '0 1px 2px rgba(22,32,28,.05)',
        DEFAULT: '0 4px 16px rgba(22,32,28,.08)',
        lg: '0 12px 32px rgba(22,32,28,.12)',
        glow: '0 0 20px rgba(15,110,86,.15)',
      },
      keyframes: {
        'dot-pulse': {
          '0%, 100%': { opacity: '0.3' },
          '50%': { opacity: '1' },
        },
        'tool-spin': {
          to: { transform: 'rotate(360deg)' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'skeleton-shimmer': {
          '0%': { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' },
        },
        'count-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'collapse-out': {
          '0%': { opacity: '1', maxHeight: '200px' },
          '100%': { opacity: '0', maxHeight: '0', paddingTop: '0', paddingBottom: '0', marginTop: '0', marginBottom: '0' },
        },
        'ticker-scroll': {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(-50%)' },
        },
      },
      animation: {
        'dot-pulse': 'dot-pulse 1s ease infinite',
        'dot-pulse-2': 'dot-pulse 1s ease 0.2s infinite',
        'dot-pulse-3': 'dot-pulse 1s ease 0.4s infinite',
        'tool-spin': 'tool-spin 1s linear infinite',
        'slide-up': 'slide-up 200ms cubic-bezier(0.23,1,0.32,1) both',
        'skeleton-shimmer': 'skeleton-shimmer 1.5s ease-in-out infinite',
        'count-up': 'count-up 400ms ease-out',
        'fade-in': 'fade-in 200ms ease-out',
        'scale-in': 'scale-in 150ms cubic-bezier(0.23,1,0.32,1)',
        'collapse-out': 'collapse-out 300ms ease-out forwards',
      },
    },
  },
  plugins: [],
}
