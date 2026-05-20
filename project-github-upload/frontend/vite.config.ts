import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  base: "/frontend/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 백엔드 API 프록시: /api 로 시작하는 요청은 FastAPI 서버로 전달
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
