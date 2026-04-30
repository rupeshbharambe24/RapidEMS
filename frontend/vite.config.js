import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      // Forward all backend calls so the frontend can use relative paths
      '/auth':          { target: 'http://localhost:8000', changeOrigin: true },
      '/emergencies':   { target: 'http://localhost:8000', changeOrigin: true },
      '/ambulances':    { target: 'http://localhost:8000', changeOrigin: true },
      '/hospitals':     { target: 'http://localhost:8000', changeOrigin: true },
      '/dispatches':    { target: 'http://localhost:8000', changeOrigin: true },
      '/ai':            { target: 'http://localhost:8000', changeOrigin: true },
      '/analytics':     { target: 'http://localhost:8000', changeOrigin: true },
      '/health':        { target: 'http://localhost:8000', changeOrigin: true },
      '/admin':         { target: 'http://localhost:8000', changeOrigin: true },
      '/driver':        { target: 'http://localhost:8000', changeOrigin: true },
      '/hospital':      { target: 'http://localhost:8000', changeOrigin: true },
      '/patient':       { target: 'http://localhost:8000', changeOrigin: true },
      '/routing':       { target: 'http://localhost:8000', changeOrigin: true },
      '/notifications': { target: 'http://localhost:8000', changeOrigin: true },
      '/track-api':     { target: 'http://localhost:8000', changeOrigin: true },
      '/copilot':       { target: 'http://localhost:8000', changeOrigin: true },
      '/public-api':    { target: 'http://localhost:8000', changeOrigin: true },
      '/telemetry':     { target: 'http://localhost:8000', changeOrigin: true },
      '/mci':           { target: 'http://localhost:8000', changeOrigin: true },
      '/drones':        { target: 'http://localhost:8000', changeOrigin: true },
      '/insurance':     { target: 'http://localhost:8000', changeOrigin: true },
      '/socket.io':     { target: 'http://localhost:8000', changeOrigin: true, ws: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
