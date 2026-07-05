export interface Appearance {
  app_name: string
  logo_url: string
  primary_color: string
  secondary_color: string
}

export const APPEARANCE_DEFAULTS: Appearance = {
  app_name: 'KNetraAI',
  logo_url: '',
  primary_color: '#1E90FF',
  secondary_color: '#0f172a'
}

export const useAppearance = () => {
  const config = useRuntimeConfig()
  const appearance = useState<Appearance>('appearance', () => ({ ...APPEARANCE_DEFAULTS }))

  const logoSrc = computed(() =>
    appearance.value.logo_url
      ? `${config.public.apiBaseUrl}/files/${appearance.value.logo_url}`
      : '/logo.svg'
  )

  const applyTheme = () => {
    if (!import.meta.client) return
    const root = document.documentElement
    root.style.setProperty('--primary', appearance.value.primary_color || APPEARANCE_DEFAULTS.primary_color)
    root.style.setProperty('--secondary', appearance.value.secondary_color || APPEARANCE_DEFAULTS.secondary_color)
  }

  const refresh = async () => {
    try {
      const data = await $fetch<Appearance>('/public/appearance', { baseURL: config.public.apiBaseUrl as string })
      appearance.value = { ...APPEARANCE_DEFAULTS, ...data }
    } catch {
      /* backend unreachable - keep defaults */
    }
    applyTheme()
  }

  return { appearance, logoSrc, refresh, applyTheme }
}
