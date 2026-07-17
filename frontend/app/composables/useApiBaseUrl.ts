// All API/SSE/stream/file traffic goes through this same-origin path, which
// server/api/[...path].ts proxies to the backend server-side. The browser never
// talks to the backend's own origin/port directly.
export const useApiBaseUrl = () => '/api'
