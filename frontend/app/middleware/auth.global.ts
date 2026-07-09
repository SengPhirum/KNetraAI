export default defineNuxtRouteMiddleware((to) => {
  if (!import.meta.client) return
  if (to.path === '/login') return
  const { sessionStatus, redirectToLogin } = useApi()
  const status = sessionStatus()
  if (!status.valid) return redirectToLogin(status.reason, to.fullPath)
})
