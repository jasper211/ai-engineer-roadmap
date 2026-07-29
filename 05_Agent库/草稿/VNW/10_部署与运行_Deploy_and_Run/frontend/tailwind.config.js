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
        'bg-base': '#F5F7FB',
        'bg-elevated': '#FFFFFF',
        'bg-surface': '#F7F9FC',
        'bg-overlay': '#E9EEF7',
        'border-default': '#D9E1EC',
        'border-hover': '#A9B6CA',
        'accent-primary': '#4F46E5',
        'accent-primary-light': '#4338CA',
        'accent-primary-dark': '#4F46E5',
        'accent-secondary': '#22D3EE',
        'accent-success': '#34D399',
        'accent-warning': '#FBBF24',
        'accent-danger': '#F87171',
        'accent-info': '#60A5FA',
        'text-primary': '#172033',
        'text-secondary': '#4A5870',
        'text-muted': '#718096',
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
        panel: '0 12px 32px rgba(30, 51, 84, .08)',
        glow: '0 8px 22px rgba(79, 70, 229, .20)',
      },
    },
  },
  plugins: [],
}
