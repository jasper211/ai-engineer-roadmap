/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-base': '#0B0E17',
        'bg-elevated': '#131825',
        'bg-surface': '#1B2132',
        'bg-overlay': '#242B40',
        'border-default': '#2A324A',
        'border-hover': '#3D4770',
        'accent-primary': '#6366F1',
        'accent-primary-light': '#818CF8',
        'accent-primary-dark': '#4F46E5',
        'accent-secondary': '#22D3EE',
        'accent-success': '#34D399',
        'accent-warning': '#FBBF24',
        'accent-danger': '#F87171',
        'accent-info': '#60A5FA',
        'text-primary': '#F1F5F9',
        'text-secondary': '#94A3B8',
        'text-muted': '#64748B',
      },
      fontFamily: {
        heading: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      borderRadius: {
        'radius-sm': '6px',
        'radius-md': '10px',
        'radius-lg': '16px',
        'radius-xl': '20px',
      },
      boxShadow: {
        panel: '0 18px 55px rgba(0,0,0,.22)',
        glow: '0 0 30px rgba(99,102,241,.28)',
      },
    },
  },
  plugins: [],
}
