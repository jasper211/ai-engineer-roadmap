/** @type {import('tailwindcss').Config} */
// 主题token从app_v2（VNW自己的前端）搬运，保持视觉一致性——这是两个前端
// 之间唯一共享的东西，路由/数据层/组件逻辑完全独立，不是同一个app。
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
        'bg-surface': '#EEF1F7',
        'bg-overlay': '#E4E8F1',
        'border-default': '#DCE1EB',
        'border-hover': '#B8C1D3',
        'accent-primary': '#5B5BD6',
        'accent-primary-light': '#4F46C7',
        'accent-primary-dark': '#4338A8',
        'accent-secondary': '#087F8C',
        'accent-success': '#16815D',
        'accent-warning': '#B77900',
        'accent-danger': '#C2414B',
        'accent-info': '#2563B8',
        'text-primary': '#182033',
        'text-secondary': '#526078',
        'text-muted': '#7A879D',
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
    },
  },
  plugins: [],
}
