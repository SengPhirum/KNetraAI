import { getRequestURL, proxyRequest } from 'h3'

/**
 * Same-origin reverse proxy for the backend API. The browser only ever talks to
 * this Nuxt server (never the backend's own origin/port directly); the backend's
 * real address is a server-only runtimeConfig value, never sent to the client.
 *
 * `redirect: 'manual'` matters for one path: /auth/oidc/login. The backend answers
 * that with a 302 to the external IdP, and the browser (not this server) needs to
 * follow it so the IdP sees the user's own cookie jar. Without this, Node's fetch
 * would follow the redirect itself and hand back the IdP's page as a 200, breaking
 * SSO. No other proxied route currently issues redirects, so this is safe globally.
 */
export default defineEventHandler((event) => {
  const config = useRuntimeConfig(event)
  const incoming = getRequestURL(event)
  const backendPath = incoming.pathname.replace(/^\/api/, '') + incoming.search
  const target = config.backendUrl.replace(/\/+$/, '') + backendPath
  return proxyRequest(event, target, {
    fetchOptions: { redirect: 'manual' }
  })
})
