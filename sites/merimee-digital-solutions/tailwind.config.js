/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#1E3A5F',
        secondary: '#475569',
        accent: '#6366F1',
        background: '#F8FAFC',
        text: '#1E293B',
        surface: '#FFFFFF',
        'on-surface': '#1E293B',
        'primary-container': '#EEF2FF',
      },
      fontFamily: {
        heading: ['Merriweather', 'serif'],
        body: ['Source Sans Pro', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
