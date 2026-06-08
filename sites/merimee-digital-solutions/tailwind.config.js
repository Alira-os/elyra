/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#1E293B',
          50: '#F8FAFC',
          100: '#F1F5F9',
          500: '#475569',
          700: '#1E293B',
          900: '#0F172A',
        },
        secondary: {
          DEFAULT: '#475569',
        },
        accent: {
          DEFAULT: '#6366F1',
          50: '#EEF2FF',
          100: '#E0E7FF',
          500: '#6366F1',
          600: '#4F46E5',
          700: '#4338CA',
        },
        surface: '#F8FAFC',
        'on-surface': '#1E293B',
        'primary-container': '#EEF2FF',
        muted: '#64748B',
        border: '#E2E8F0',
        ink: '#1E293B',
        paper: '#FFFFFF',
      },
      fontFamily: {
        heading: ['Merriweather', 'Georgia', 'serif'],
        body: ['"Source Sans 3"', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        xs: ['12px', { lineHeight: '1.5' }],
        sm: ['14px', { lineHeight: '1.55' }],
        base: ['16px', { lineHeight: '1.65' }],
        lg: ['18px', { lineHeight: '1.6' }],
        xl: ['20px', { lineHeight: '1.55' }],
        '2xl': ['24px', { lineHeight: '1.45' }],
        '3xl': ['30px', { lineHeight: '1.3' }],
        '4xl': ['36px', { lineHeight: '1.2' }],
        '5xl': ['48px', { lineHeight: '1.1' }],
      },
      spacing: {
        'space-xs': '4px',
        'space-sm': '8px',
        'space-md': '16px',
        'space-lg': '24px',
        'space-xl': '32px',
        'space-2xl': '48px',
        'space-3xl': '64px',
      },
      borderRadius: {
        DEFAULT: '0.375rem',
        sm: '0.25rem',
        md: '0.375rem',
        lg: '0.5rem',
      },
      boxShadow: {
        'elev-sm': '0 1px 2px rgba(0,0,0,0.05)',
        'elev-md': '0 4px 6px rgba(0,0,0,0.07)',
        'elev-lg': '0 10px 15px rgba(0,0,0,0.1)',
      },
      transitionDuration: {
        DEFAULT: '200ms',
      },
      transitionTimingFunction: {
        DEFAULT: 'ease-out',
      },
    },
  },
  plugins: [],
};
