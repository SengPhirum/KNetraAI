// Voice greeting engine for the Live Monitoring page.
//
// Playback path depends on the configured audio output:
//  - A specific output device selected (per-browser, localStorage): fetch WAV
//    speech from the backend /tts endpoint and play it through an <audio>
//    element routed with setSinkId(). This is the only way browsers allow
//    choosing an output device - the Web Speech API always uses the default.
//  - Default device (or /tts unavailable): browser speechSynthesis with the
//    configured voice/rate/volume.
//
// Server-side presence tracking already suppresses repeat events while a person
// stays in a camera zone; the repeat window here is a second client-side guard
// so reconnects/refreshes don't re-announce someone.

const OUTPUT_DEVICE_KEY = 'voice.output_device_id'
const OUTPUT_DEVICE_LABEL_KEY = 'voice.output_device_label'
const MUTED_KEY = 'voice.muted_on_this_device'

export interface VoiceSettings {
  enabled: boolean
  greetKnown: boolean
  greetUnknown: boolean
  repeatSeconds: number
  rate: number
  volume: number
  voiceName: string
}

const parseBool = (value: string | undefined, fallback: boolean) =>
  value === undefined ? fallback : ['1', 'true', 'yes'].includes(value.toLowerCase())
const parseNum = (value: string | undefined, fallback: number) => {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

export const voiceSettingsFromList = (settings: Array<{ key: string, value: string }>): VoiceSettings => {
  const get = (key: string) => settings.find(s => s.key === key)?.value
  return {
    enabled: parseBool(get('voice.enabled'), false),
    greetKnown: parseBool(get('voice.greet_known'), true),
    greetUnknown: parseBool(get('voice.greet_unknown'), true),
    repeatSeconds: parseNum(get('voice.repeat_seconds'), 60),
    rate: parseNum(get('voice.rate'), 1.0),
    volume: parseNum(get('voice.volume'), 1.0),
    voiceName: get('voice.voice_name') || ''
  }
}

export const useVoiceGreeter = () => {
  const { apiFetch } = useApi()
  const lastSpokenAt = new Map<string, number>()
  let serverTtsBroken = false

  const outputDeviceId = ref(import.meta.client ? localStorage.getItem(OUTPUT_DEVICE_KEY) || '' : '')
  const outputDeviceLabel = ref(import.meta.client ? localStorage.getItem(OUTPUT_DEVICE_LABEL_KEY) || '' : '')
  const mutedOnThisDevice = ref(import.meta.client ? localStorage.getItem(MUTED_KEY) === 'true' : false)

  const setOutputDevice = (deviceId: string, label: string) => {
    outputDeviceId.value = deviceId
    outputDeviceLabel.value = label
    if (!import.meta.client) return
    if (deviceId) {
      localStorage.setItem(OUTPUT_DEVICE_KEY, deviceId)
      localStorage.setItem(OUTPUT_DEVICE_LABEL_KEY, label)
    } else {
      localStorage.removeItem(OUTPUT_DEVICE_KEY)
      localStorage.removeItem(OUTPUT_DEVICE_LABEL_KEY)
    }
  }

  const setMuted = (muted: boolean) => {
    mutedOnThisDevice.value = muted
    if (import.meta.client) localStorage.setItem(MUTED_KEY, String(muted))
  }

  const sinkRoutingSupported = () =>
    import.meta.client && typeof (document.createElement('audio') as any).setSinkId === 'function'

  const listOutputDevices = async (): Promise<Array<{ deviceId: string, label: string }>> => {
    if (!import.meta.client || !navigator.mediaDevices?.enumerateDevices) return []
    let devices = await navigator.mediaDevices.enumerateDevices()
    // Labels are hidden until any media permission is granted once.
    if (devices.some(d => d.kind === 'audiooutput' && !d.label)) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        stream.getTracks().forEach(t => t.stop())
        devices = await navigator.mediaDevices.enumerateDevices()
      } catch {
        // Permission denied - device IDs still work, labels stay generic.
      }
    }
    return devices
      .filter(d => d.kind === 'audiooutput')
      .map(d => ({ deviceId: d.deviceId, label: d.label || `Audio output (${d.deviceId.slice(0, 6)}...)` }))
  }

  const speakWithBrowser = (text: string, settings: VoiceSettings) => {
    if (!import.meta.client || !('speechSynthesis' in window)) return
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = Math.min(2, Math.max(0.5, settings.rate))
    utterance.volume = Math.min(1, Math.max(0, settings.volume))
    if (settings.voiceName) {
      const voice = window.speechSynthesis.getVoices().find(v => v.name === settings.voiceName)
      if (voice) utterance.voice = voice
    }
    window.speechSynthesis.speak(utterance)
  }

  const speakViaServer = async (text: string, settings: VoiceSettings, deviceId: string): Promise<boolean> => {
    try {
      const blob = await apiFetch<Blob>(`/tts?text=${encodeURIComponent(text)}&rate=${settings.rate}&volume=${settings.volume}`, {
        responseType: 'blob'
      })
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.volume = Math.min(1, Math.max(0, settings.volume))
      try {
        await (audio as any).setSinkId(deviceId)
      } catch {
        // Device unplugged / permission issue - fall through to default output.
      }
      await audio.play()
      audio.addEventListener('ended', () => URL.revokeObjectURL(url), { once: true })
      return true
    } catch (e: any) {
      // 503 = no TTS engine on the server; remember and stop retrying.
      if ((e?.statusCode || e?.response?.status) === 503) serverTtsBroken = true
      return false
    }
  }

  /** Speak text now, regardless of throttling (used by the settings Test button). */
  const speakNow = async (text: string, settings: VoiceSettings) => {
    if (!import.meta.client) return
    if (outputDeviceId.value && sinkRoutingSupported() && !serverTtsBroken) {
      if (await speakViaServer(text, settings, outputDeviceId.value)) return
    }
    speakWithBrowser(text, settings)
  }

  /**
   * Speak a greeting for a detection event, throttled per person/zone key.
   * Returns true when audio was actually triggered.
   */
  const speakGreeting = async (event: any, settings: VoiceSettings): Promise<boolean> => {
    if (!import.meta.client || !settings.enabled || mutedOnThisDevice.value) return false
    const known = Boolean(event?.person_id)
    if (known && !settings.greetKnown) return false
    if (!known && !settings.greetUnknown) return false
    const text = String(event?.greeting || '').trim()
    if (!text) return false

    const key = known ? `person:${event.person_id}` : `zone:${event.camera_id || 'any'}:${event.gender_estimate || 'unknown'}`
    const now = Date.now()
    const last = lastSpokenAt.get(key) || 0
    if (now - last < settings.repeatSeconds * 1000) return false
    lastSpokenAt.set(key, now)

    await speakNow(text, settings)
    return true
  }

  return {
    outputDeviceId,
    outputDeviceLabel,
    mutedOnThisDevice,
    setOutputDevice,
    setMuted,
    listOutputDevices,
    sinkRoutingSupported,
    speakNow,
    speakGreeting
  }
}
