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
    public: {
      // Leave apiBaseUrl unset to auto-detect from the browser's current host
      // (works for localhost, LAN IP, or any hostname). Set NUXT_PUBLIC_API_BASE_URL
      // to force a specific backend URL instead (e.g. behind a reverse proxy).
      apiBaseUrl: process.env.NUXT_PUBLIC_API_BASE_URL || '',
      apiPort: process.env.NUXT_PUBLIC_API_PORT || '8000'
    }
  }
})
