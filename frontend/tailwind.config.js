/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#fda311',
          50: '#fff8e6',
          100: '#ffedcc',
          200: '#ffdb99',
          300: '#fdc966',
          400: '#fdb733',
          500: '#fda311',
          600: '#e6930f',
          700: '#cc820d',
          800: '#b3720b',
          900: '#996209',
        },
        dark: {
          DEFAULT: '#0b1020',
          50: '#e6e7e9',
          100: '#ccced3',
          200: '#999da7',
          300: '#666c7b',
          400: '#333b4f',
          500: '#0b1020',
          600: '#090e1d',
          700: '#070c1a',
          800: '#050917',
          900: '#030714',
        },
      },
    },
  },
  plugins: [],
}
