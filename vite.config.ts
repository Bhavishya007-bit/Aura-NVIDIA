import { defineConfig } from 'vite'
import type { PreviewServer, ViteDevServer } from 'vite'
import react from '@vitejs/plugin-react'

// Expose only the UI's API contracts through this temporary preview.
// Existing local course-based source sharing remains unchanged.
const sharedRoutes: Array<[string, RegExp]> = [
  ['POST', /^\/api\/auth\/(register|login|logout)$/],
  ['GET', /^\/api\/auth\/me$/],
  ['GET', /^\/api\/courses$/],
  ['POST', /^\/api\/courses\/\d+\/sources$/],
  ['POST', /^\/api\/courses\/\d+\/preparation-jobs$/],
  ['GET', /^\/api\/preparation-jobs$/],
  ['GET', /^\/api\/preparation-jobs\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i],
  ['POST', /^\/api\/preparation-jobs\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/retry$/i],
  ['GET', /^\/api\/sources\/\d+$/],
  ['POST', /^\/api\/sources\/\d+\/generate-embeddings$/],
  ['POST', /^\/api\/chat$/],
  ['POST', /^\/api\/study\/tools$/],
  ['GET', /^\/api\/study\/(materials|artifacts|progress)$/],
  ['PATCH', /^\/api\/study\/materials\/\d+\/visibility$/],
  ['POST', /^\/api\/study\/assessments\/[0-9a-f-]{36}\/submit$/],
]
function restrictSharedApi(server: PreviewServer | ViteDevServer) {
  server.middlewares.use((request, response, next) => {
    const hostname = (request.headers.host ?? '').toLowerCase().replace(/:\d+$/, '')
    const tunnelHost = (process.env.__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS ?? '').toLowerCase()
    if (!['localhost', '127.0.0.1', '[::1]', tunnelHost].filter(Boolean).includes(hostname)) {
      response.statusCode = 403
      response.end('This hostname is not allowed for the shared preview.')
      return
    }
    const path = (request.url ?? '').split('?')[0]
    if (!path.startsWith('/api')) return next()
    if (sharedRoutes.some(([method, pattern]) => method === request.method && pattern.test(path))) return next()
    response.statusCode = 403
    response.setHeader('Content-Type', 'application/json')
    response.end(JSON.stringify({ detail: 'This endpoint is not available in the shared preview.' }))
  })
}
const proxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api(?=\/|$)/, ''),
  },
}
export default defineConfig({
  plugins: [react(), { name: 'aura-temporary-share-filter', configureServer: restrictSharedApi, configurePreviewServer: restrictSharedApi }],
  optimizeDeps: { include: ['react', 'react-dom/client'] },
  server: {
    proxy,
    watch: { ignored: ['**/.venv/**', '**/venv/**', '**/backend/uploads/**', '**/aura-update-backups/**'] },
  },
  preview: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
})
