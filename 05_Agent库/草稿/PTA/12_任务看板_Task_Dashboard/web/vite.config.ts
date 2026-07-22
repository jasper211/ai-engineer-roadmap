import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev 模式下把 /api 转发给本地 8787 端口的 Python 后端——这是 lib/api.ts 全程
// 只用相对路径 /api/... 的唯一原因：build 之后（生产模式）同一个 Python 进程
// 直接服务这些静态文件 + 处理 /api/*，不再需要这层代理，相对路径天然对。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8787',
    },
  },
})
