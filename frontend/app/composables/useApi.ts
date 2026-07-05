export const useApi = () => {
  const config = useRuntimeConfig()
  const token = useState<string | null>('auth-token', () => {
    if (process.client) return localStorage.getItem('token')
    return null
  })

  const setToken = (value: string | null) => {
    token.value = value
    if (process.client) {
      if (value) localStorage.setItem('token', value)
      else localStorage.removeItem('token')
    }
  }

  const apiFetch = async <T = any>(path: string, options: any = {}): Promise<T> => {
    const headers: Record<string, string> = { ...(options.headers || {}) }
    if (token.value) headers.Authorization = `Bearer ${token.value}`
    return await $fetch<T>(path, {
      baseURL: config.public.apiBaseUrl as string,
      ...options,
      headers
    })
  }

  const logout = () => {
    setToken(null)
    return navigateTo('/login')
  }

  return { apiFetch, token, setToken, logout, apiBaseUrl: config.public.apiBaseUrl as string }
}
