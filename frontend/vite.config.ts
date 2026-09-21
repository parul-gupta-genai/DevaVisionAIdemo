import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
import basicSsl from '@vitejs/plugin-basic-ssl'

const ignoreCodes = new Set(['ECONNRESET', 'EPIPE', 'ECONNREFUSED', 'ECANCELED', 'ECONNABORTED']);

const handleProxyError = (err: any) => {
  if (err && ignoreCodes.has(err.code)) {
    return;
  }
  console.error('Vite Proxy Error:', err);
};

export default defineConfig({
  plugins: [
    basicSsl(),
    tailwindcss(),
    react()
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    allowedHosts: true,
    port: 3000,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true, configure: (proxy) => proxy.on('error', handleProxyError) },
      '/auth': { target: 'http://localhost:8000', changeOrigin: true, configure: (proxy) => proxy.on('error', handleProxyError) },
      '/users': { target: 'http://localhost:8000', changeOrigin: true, configure: (proxy) => proxy.on('error', handleProxyError) },
      '/roles': { target: 'http://localhost:8000', changeOrigin: true, configure: (proxy) => proxy.on('error', handleProxyError) },
      '/events': { target: 'http://localhost:8000', changeOrigin: true, configure: (proxy) => proxy.on('error', handleProxyError) },
      '/analytics': { target: 'http://localhost:8000', changeOrigin: true, configure: (proxy) => proxy.on('error', handleProxyError) },
      '/snapshots': { target: 'http://localhost:8000', changeOrigin: true, configure: (proxy) => proxy.on('error', handleProxyError) },
      '/video': { target: 'http://localhost:8000', changeOrigin: true, configure: (proxy) => proxy.on('error', handleProxyError) },
      '/kill-stream': { target: 'http://localhost:8000', changeOrigin: true, configure: (proxy) => proxy.on('error', handleProxyError) },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        configure: (proxy) => {
          proxy.on('error', handleProxyError);
          proxy.on('proxyReqWs', (_proxyReq, _req, socket) => {
            socket.on('error', handleProxyError);
          });
        }
      },
      '/webrtc-stream': {
        target: 'http://localhost:8189',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/webrtc-stream/, ''),
        configure: (proxy) => proxy.on('error', handleProxyError)
      },
      '^/raw_.*': {
        target: 'http://localhost:8189',
        changeOrigin: true,
        configure: (proxy) => proxy.on('error', handleProxyError)
      },
      '^/.*\\/whep$': {
        target: 'http://localhost:8189',
        changeOrigin: true,
        configure: (proxy) => proxy.on('error', handleProxyError)
      }
    }
  }
})
