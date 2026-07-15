import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Brand — cyan/sky-blue primary
        brand: {
          50: '#E0F9FF',
          100: '#B3F0FF',
          200: '#80E6FF',
          300: '#4DD9FF',
          400: '#1ACBFF',
          500: '#00BFFF',
          600: '#009ACC',
          700: '#007399',
          800: '#004D66',
          900: '#002633',
          950: '#001219',
        },
        accent: {
          400: '#38BDF8',
          500: '#0EA5E9',
          600: '#0284C7',
        },
        // Bespoke neutral scale, theme-aware via CSS variables
        surface: {
          base: 'var(--color-bg-base)',
          surface: 'var(--color-bg-surface)',
          elevated: 'var(--color-bg-elevated)',
          overlay: 'var(--color-bg-overlay)',
        },
        border: {
          subtle: 'var(--color-border-subtle)',
          strong: 'var(--color-border-strong)',
        },
        ink: {
          primary: 'var(--color-text-primary)',
          secondary: 'var(--color-text-secondary)',
          muted: 'var(--color-text-muted)',
        },
        success: '#22C55E',
        warning: '#F59E0B',
        danger: {
          DEFAULT: '#EF4444',
          500: '#EF4444',
          600: '#DC2626',
          700: '#B91C1C',
          800: '#991B1B',
        },
        info: '#7DD3FC',
        // TODO: remove `primary` alias — migration to `brand` is complete.
        primary: {
          50: '#E0F9FF',
          100: '#B3F0FF',
          200: '#80E6FF',
          300: '#4DD9FF',
          400: '#1ACBFF',
          500: '#00BFFF',
          600: '#009ACC',
          700: '#007399',
          800: '#004D66',
          900: '#002633',
          950: '#001219',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1.5' }],
        sm: ['0.875rem', { lineHeight: '1.5' }],
        base: ['0.9375rem', { lineHeight: '1.6' }],
        lg: ['1.0625rem', { lineHeight: '1.6' }],
        xl: ['1.25rem', { lineHeight: '1.4' }],
        '2xl': ['1.5rem', { lineHeight: '1.3' }],
        '3xl': ['1.875rem', { lineHeight: '1.25' }],
        '4xl': ['2.375rem', { lineHeight: '1.15' }],
        '5xl': ['3rem', { lineHeight: '1.1' }],
      },
      borderRadius: {
        sm: '6px',
        md: '10px',
        lg: '14px',
        xl: '20px',
      },
      boxShadow: {
        'elevation-1': '0 1px 2px 0 rgb(0 0 0 / 0.35), inset 0 0 0 1px rgb(255 255 255 / 0.04)',
        'elevation-2': '0 4px 12px 0 rgb(0 0 0 / 0.4), inset 0 0 0 1px rgb(255 255 255 / 0.05)',
        'elevation-3': '0 12px 32px 0 rgb(0 0 0 / 0.45), inset 0 0 0 1px rgb(255 255 255 / 0.06)',
      },
      keyframes: {
        'fade-slide-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-slide-up': 'fade-slide-up 200ms ease-out',
      },
    },
  },
  plugins: [require('@tailwindcss/forms')],
};

export default config;
