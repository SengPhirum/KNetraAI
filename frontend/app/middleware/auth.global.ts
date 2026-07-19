// Minimum role required per route. The backend enforces the real permissions;
// this guard just keeps people out of pages that would be empty/forbidden for
// their role. Roles: Viewer < Operator < Manager < Admin.
const ROUTE_MIN_ROLE: Record<string, string[]> = {
  '/cameras': ['Admin', 'Manager', 'Operator'],
  '/fingerprints': ['Admin', 'Manager', 'Operator'],
  '/settings': ['Admin'],
  '/users': ['Admin', 'Manager'],
  '/audit-logs': ['Admin', 'Manager']
}

export default defineNuxtRouteMiddleware((to) => {
  if (!import.meta.client) return
  if (to.path === '/login') return
  const { sessionStatus, redirectToLogin } = useApi()
  const status = sessionStatus()
  if (!status.valid) return redirectToLogin(status.reason, to.fullPath)

  const required = Object.entries(ROUTE_MIN_ROLE).find(([prefix]) =>
    to.path === prefix || to.path.startsWith(`${prefix}/`)
  )?.[1]
  if (required) {
    const { role } = useCurrentUser()
    if (!required.includes(role.value)) return navigateTo('/', { replace: true })
  }
})
