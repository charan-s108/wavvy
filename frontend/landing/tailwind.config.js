/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // New design tokens
        'brand-yellow': '#f4f73d',
        // Legacy tokens
        'w-bg':      '#14131d',
        'w-bg-deep': '#10131c',
        'w-card':    '#1b1d2a',
        'w-yellow':  '#f4f73d',
        'w-violet':  '#9543f6',
        'w-blue':    '#1378d1',
        'w-blue-2':  '#523ce5',
        'w-green':   '#1D9E75',
        'w-red':     '#fc535b',
        'w-orange':  '#fabc2d',
        'w-text':    '#ffffff',
        'w-muted':   '#b2b2b4',
        'w-hint':    '#727781',
        'w-lavender':'#d8e7f2',
        'w-border':  'rgba(255,255,255,0.08)',
      },
      fontFamily: {
        'display':   ['Orbikular', 'system-ui', 'sans-serif'],
        'sans':      ['Aeonik', 'system-ui', 'sans-serif'],
        'inter':     ['Inter', 'system-ui', 'sans-serif'],
        // Legacy
        'orbikular': ['Orbikular', 'system-ui', 'sans-serif'],
        'aeonik':    ['Aeonik', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
