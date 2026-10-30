/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'IBM Plex Mono', 'monospace'],
        sans: ['IBM Plex Sans', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      colors: {
        paper: {
          canvas: '#F3F0E6',
          panel: '#FAF8F3',
          border: '#D5D0C3',
          text: '#1C2026',
          muted: '#6C7480',
        },
        carbon: {
          canvas: '#0B0E14',
          panel: '#11161F',
          border: '#1E2633',
          text: '#E5E9F0',
          muted: '#7E8B9B',
        }
      }
    },
  },
  plugins: [],
}
