import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Keep the development fallback aligned with the single formal local API.
// An omitted environment variable must not silently route the workspace to a
// retired prototype port.
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:18765'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': apiProxyTarget,
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts: true,
    proxy: {
      '/api': apiProxyTarget,
    },
  },
})
