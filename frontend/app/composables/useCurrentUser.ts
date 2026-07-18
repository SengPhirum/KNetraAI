// Current user info decoded from the JWT access token (no extra API call).
// The backend enforces all permissions server-side; this only drives UI
// visibility (e.g. hiding admin-only buttons from non-admins).
export const useCurrentUser = () => {
  const { token } = useApi()

  const payload = computed<Record<string, any> | null>(() => {
    if (!import.meta.client || !token.value) return null
    const part = token.value.split('.')[1]
    if (!part) return null
    try {
      const normalized = part.replace(/-/g, '+').replace(/_/g, '/')
      const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
      return JSON.parse(window.atob(padded))
    } catch {
      return null
    }
  })

  const role = computed<string>(() => payload.value?.role || '')
  const email = computed<string>(() => payload.value?.email || '')
  const isAdmin = computed(() => role.value === 'Admin')
  const canManage = computed(() => ['Admin', 'Manager'].includes(role.value))
  const canOperate = computed(() => ['Admin', 'Manager', 'Operator'].includes(role.value))

  return { role, email, isAdmin, canManage, canOperate }
}
