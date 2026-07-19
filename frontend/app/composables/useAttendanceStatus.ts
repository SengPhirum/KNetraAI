// Cached attendance-mode flag driving nav visibility and per-page features.
// Refreshed on login/page load and after saving the Attendance settings tab.
export const useAttendanceStatus = () => {
  const state = useState<{ enabled: boolean, voice_alerts: boolean, loaded: boolean }>(
    'attendance-status',
    () => ({ enabled: false, voice_alerts: true, loaded: false })
  )

  const refresh = async () => {
    const { apiFetch, token } = useApi()
    if (!token.value) return
    try {
      const status = await apiFetch<{ enabled: boolean, voice_alerts: boolean }>('/attendance/status')
      state.value = { ...status, loaded: true }
    } catch {
      state.value = { enabled: false, voice_alerts: true, loaded: true }
    }
  }

  const ensureLoaded = () => {
    if (!state.value.loaded) refresh()
  }

  return {
    attendanceEnabled: computed(() => state.value.enabled),
    attendanceVoiceAlerts: computed(() => state.value.voice_alerts),
    refresh,
    ensureLoaded
  }
}
