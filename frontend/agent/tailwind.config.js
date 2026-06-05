/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        'brand-yellow': '#f4f73d',
        'yellow':       '#f4f73d',
      },
      fontFamily: {
        'display': ['Orbikular', 'system-ui', 'sans-serif'],
        'sans':    ['Aeonik',    'system-ui', 'sans-serif'],
        'inter':   ['Inter',     'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
