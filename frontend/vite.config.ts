import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The FastAPI backend serves /api and /static. In dev we proxy both so the
// frontend can use same-origin relative URLs in every environment.
const BACKEND = process.env.VITE_BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/static': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
