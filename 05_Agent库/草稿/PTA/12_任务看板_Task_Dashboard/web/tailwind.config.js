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
    },
  },
  plugins: [],
}
