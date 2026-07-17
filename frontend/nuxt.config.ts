export default defineNuxtConfig({
  modules: ['@nuxt/ui'],
  css: ['~/assets/css/main.css'],
  ssr: false,
  app: {
    head: {
      title: 'KNetraAI',
      meta: [
        { name: 'description', content: 'KNetraAI - Walk-in Greeting AI for CCTV/IP cameras' },
        { name: 'theme-color', content: '#1E90FF' }
      ],
      link: [
        { rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' },
        { rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' },
        { rel: 'apple-touch-icon', sizes: '180x180', href: '/apple-touch-icon.png' },
        { rel: 'manifest', href: '/manifest.webmanifest' }
      ]
    }
  },
  runtimeConfig: {
    // Server-only: the browser never sees this. server/api/[...path].ts proxies
    // every /api/** request here, so the backend's real address/port never has to
    // be reachable from - or known to - the browser.
    // This default is only a fallback for `nuxt dev` - nuxt.config.ts is evaluated
    // at build time, so it can't read a docker-compose env var that's only set at
    // container start. Nuxt overrides runtimeConfig keys from matching NUXT_<KEY>
    // env vars at server start instead (see docker-compose.yml's NUXT_BACKEND_URL).
    backendUrl: 'http://localhost:8000'
  }
})
