export const useApiBaseUrl = () => {
  const config = useRuntimeConfig()
  const explicit = config.public.apiBaseUrl as string
  if (explicit) return explicit
  if (import.meta.client) {
    return `${window.location.protocol}//${window.location.hostname}:${config.public.apiPort}`
  }
  return `http://localhost:${config.public.apiPort}`
}
