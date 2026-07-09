let sessionExpiryTimer: ReturnType<typeof setTimeout> | null = null

type SessionReason = 'missing' | 'expired' | 'unauthorized' | 'invalid'
type ApiFetchOptions = Record<string, any> & { authRedirect?: boolean }

const PUBLIC_AUTH_PATHS = new Set(['/auth/login', '/auth/ldap/login', '/auth/methods'])
const MAX_TIMEOUT_MS = 2_147_483_647

const pathOnly = (path: string) => path.split('?')[0] || path
const isPublicAuthPath = (path: string, options: ApiFetchOptions) =>
  options.authRedirect === false || PUBLIC_AUTH_PATHS.has(pathOnly(path))

const decodeJwtPayload = (value: string): Record<string, any> | null => {
  if (!import.meta.client) return null
  const payload = value.split('.')[1]
  if (!payload) return null
  try {
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
    return JSON.parse(window.atob(padded))
  } catch {
    return null
  }
}

const tokenExpiresAt = (value: string | null) => {
  if (!value) return null
  const payload = decodeJwtPayload(value)
  return typeof payload?.exp === 'number' ? payload.exp * 1000 : null
}

const safeRedirectPath = (value?: unknown) => {
  const path = Array.isArray(value) ? value[0] : value
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') || path.startsWith('/login')) return '/'
  return path
}

export const useApi = () => {
  const route = useRoute()
  const apiBaseUrl = useApiBaseUrl()
  const token = useState<string | null>('auth-token', () => {
    if (import.meta.client) return localStorage.getItem('token')
    return null
  })

  const setToken = (value: string | null) => {
    token.value = value
    if (!import.meta.client) return
    if (value) localStorage.setItem('token', value)
    else localStorage.removeItem('token')
    scheduleSessionExpiry(value)
  }

  const loginLocation = (reason: SessionReason, returnTo?: string) => {
    const query: Record<string, string> = { reason }
    const redirect = safeRedirectPath(returnTo || route.fullPath)
    if (redirect !== '/') query.redirect = redirect
    return { path: '/login', query }
  }

  const redirectToLogin = async (reason: SessionReason = 'unauthorized', returnTo?: string) => {
    setToken(null)
    if (!import.meta.client) return
    const redirect = safeRedirectPath(returnTo || route.fullPath)
    if (route.path === '/login' && redirect === '/') return
    return await navigateTo(loginLocation(reason, returnTo), { replace: true })
  }

  function scheduleSessionExpiry(value: string | null) {
    if (!import.meta.client) return
    if (sessionExpiryTimer) clearTimeout(sessionExpiryTimer)
    sessionExpiryTimer = null
    const expiresAt = tokenExpiresAt(value)
    if (!expiresAt) return
    const delay = expiresAt - Date.now() + 500
    sessionExpiryTimer = setTimeout(() => {
      if (token.value && Date.now() >= expiresAt) {
        void redirectToLogin('expired')
      }
    }, Math.max(0, Math.min(delay, MAX_TIMEOUT_MS)))
  }

  const sessionStatus = (): { valid: true } | { valid: false, reason: SessionReason } => {
    if (!import.meta.client) return { valid: true }
    const stored = localStorage.getItem('token')
    if (stored !== token.value) token.value = stored
    if (!stored) return { valid: false, reason: 'missing' }
    const expiresAt = tokenExpiresAt(stored)
    if (!expiresAt) return { valid: false, reason: 'invalid' }
    if (Date.now() >= expiresAt - 5000) return { valid: false, reason: 'expired' }
    scheduleSessionExpiry(stored)
    return { valid: true }
  }

  const apiFetch = async <T = any>(path: string, options: ApiFetchOptions = {}): Promise<T> => {
    const publicAuthCall = isPublicAuthPath(path, options)
    if (!publicAuthCall) {
      const status = sessionStatus()
      if (!status.valid) {
        await redirectToLogin(status.reason)
        throw new Error(status.reason === 'expired' ? 'Session expired' : 'Login required')
      }
    }

    const headers: Record<string, string> = { ...(options.headers || {}) }
    if (token.value) headers.Authorization = `Bearer ${token.value}`
    const { authRedirect, ...fetchOptions } = options

    try {
      return await $fetch<T>(path, {
        baseURL: apiBaseUrl,
        ...fetchOptions,
        headers
      })
    } catch (error: any) {
      const statusCode = error?.statusCode || error?.response?.status
      if (statusCode === 401 && !publicAuthCall) {
        const status = sessionStatus()
        await redirectToLogin(status.valid ? 'unauthorized' : status.reason)
      }
      throw error
    }
  }

  const logout = async () => {
    setToken(null)
    if (!import.meta.client || route.path === '/login') return
    return await navigateTo('/login', { replace: true })
  }

  if (import.meta.client && token.value) scheduleSessionExpiry(token.value)

  return {
    apiFetch,
    token,
    setToken,
    logout,
    sessionStatus,
    redirectToLogin,
    safeRedirectPath,
    apiBaseUrl
  }
}
