import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During development, requests to /api are forwarded to the FastAPI backend
// so the frontend and backend feel like one origin (no CORS headaches).
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Libraries change rarely; separate chunks stay cached across app releases.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
