import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During development, requests to /api are forwarded to the FastAPI backend
// so the frontend and backend feel like one origin (no CORS headaches).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
