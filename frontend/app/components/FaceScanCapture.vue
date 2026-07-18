<template>
  <div>
    <div v-if="!active" class="scan-intro">
      <p class="scan-text">
        Scan the full face with this device's camera. Keep the face inside the oval,
        look straight at the camera, and make sure the face is well lit and not cut off.
      </p>
      <button class="btn" type="button" @click="start">Start Camera Scan</button>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <div v-else>
      <div class="scan-stage">
        <video ref="videoRef" autoplay playsinline muted class="scan-video"></video>
        <div class="scan-overlay">
          <div class="scan-oval" :class="{ flash: flashing }"></div>
        </div>
        <div v-if="instruction" class="scan-instruction">{{ instruction }}</div>
      </div>

      <div class="btn-row" style="margin-top: 0.75rem; flex-wrap: wrap;">
        <select v-if="cameras.length > 1" v-model="selectedCameraId" style="max-width: 220px;" @change="restart">
          <option v-for="cam in cameras" :key="cam.deviceId" :value="cam.deviceId">{{ cam.label }}</option>
        </select>
        <button class="btn" type="button" :disabled="busy" @click="captureOne">Capture Photo</button>
        <button class="btn secondary" type="button" :disabled="busy" @click="guidedScan">
          {{ busy ? scanProgress : 'Auto Scan (3 poses)' }}
        </button>
        <button class="btn secondary" type="button" @click="stop">Stop Camera</button>
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <div v-if="captures.length" class="captures">
        <div v-for="(capture, index) in captures" :key="index" class="capture-item">
          <img :src="capture.dataUrl" alt="capture" />
          <span class="badge" :class="capture.status === 'ok' ? 'success' : capture.status === 'uploading' ? 'info' : 'danger'">
            {{ capture.status === 'ok' ? `Enrolled ${capture.quality != null ? '(q ' + capture.quality.toFixed(2) + ')' : ''}` : capture.status === 'uploading' ? 'Uploading...' : 'Failed' }}
          </span>
          <small v-if="capture.error" class="capture-error" :title="capture.error">{{ capture.error }}</small>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ personId: string }>()
const emit = defineEmits<{ uploaded: [] }>()

const { apiFetch } = useApi()

const videoRef = ref<HTMLVideoElement | null>(null)
const active = ref(false)
const busy = ref(false)
const flashing = ref(false)
const error = ref('')
const instruction = ref('')
const scanProgress = ref('Scanning...')
const cameras = ref<Array<{ deviceId: string, label: string }>>([])
const selectedCameraId = ref('')
const captures = ref<Array<{ dataUrl: string, status: 'uploading' | 'ok' | 'failed', quality?: number | null, error?: string }>>([])

let stream: MediaStream | null = null

const start = async () => {
  error.value = ''
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: selectedCameraId.value
        ? { deviceId: { exact: selectedCameraId.value }, width: { ideal: 1280 }, height: { ideal: 720 } }
        : { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false
    })
    active.value = true
    await nextTick()
    if (videoRef.value) videoRef.value.srcObject = stream
    const devices = await navigator.mediaDevices.enumerateDevices()
    cameras.value = devices
      .filter(d => d.kind === 'videoinput')
      .map(d => ({ deviceId: d.deviceId, label: d.label || 'Camera' }))
    if (!selectedCameraId.value && stream) {
      selectedCameraId.value = stream.getVideoTracks()[0]?.getSettings().deviceId || ''
    }
  } catch (e: any) {
    error.value = e?.name === 'NotAllowedError'
      ? 'Camera access was denied. Allow camera permission for this site and try again.'
      : (e?.message || 'Could not open the camera')
  }
}

const stop = () => {
  stream?.getTracks().forEach(t => t.stop())
  stream = null
  active.value = false
  instruction.value = ''
}

const restart = async () => {
  stop()
  await start()
}

const grabFrame = (): Promise<Blob | null> => new Promise((resolve) => {
  const video = videoRef.value
  if (!video || !video.videoWidth) return resolve(null)
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  canvas.getContext('2d')!.drawImage(video, 0, 0)
  canvas.toBlob(blob => resolve(blob), 'image/jpeg', 0.92)
})

const uploadCapture = async (blob: Blob, label: string) => {
  const dataUrl = URL.createObjectURL(blob)
  const item = reactive({ dataUrl, status: 'uploading' as 'uploading' | 'ok' | 'failed', quality: null as number | null, error: '' })
  captures.value = [item, ...captures.value].slice(0, 12)
  try {
    const form = new FormData()
    form.append('file', new File([blob], `scan_${label}_${Date.now()}.jpg`, { type: 'image/jpeg' }))
    const result: any = await apiFetch(`/persons/${props.personId}/images`, { method: 'POST', body: form })
    if (result.embedding_status === 'created') {
      item.status = 'ok'
      item.quality = result.quality_score != null ? Number(result.quality_score) : null
    } else {
      item.status = 'failed'
      item.error = result.embedding_error || 'No face found'
    }
  } catch (e: any) {
    item.status = 'failed'
    item.error = e?.data?.detail || e.message
  }
  emit('uploaded')
}

const flash = () => {
  flashing.value = true
  setTimeout(() => { flashing.value = false }, 250)
}

const captureOne = async () => {
  error.value = ''
  const blob = await grabFrame()
  if (!blob) { error.value = 'No video frame available yet'; return }
  flash()
  await uploadCapture(blob, 'manual')
}

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

const guidedScan = async () => {
  if (busy.value) return
  busy.value = true
  error.value = ''
  const poses = [
    { label: 'center', text: 'Look straight at the camera' },
    { label: 'left', text: 'Turn the head slightly LEFT' },
    { label: 'right', text: 'Turn the head slightly RIGHT' }
  ]
  try {
    for (const [index, pose] of poses.entries()) {
      for (let countdown = 3; countdown >= 1; countdown--) {
        instruction.value = `${pose.text} - ${countdown}`
        scanProgress.value = `Pose ${index + 1}/3...`
        await sleep(800)
      }
      instruction.value = pose.text
      const blob = await grabFrame()
      if (blob) {
        flash()
        await uploadCapture(blob, pose.label)
      }
    }
    instruction.value = 'Scan complete'
    setTimeout(() => { if (instruction.value === 'Scan complete') instruction.value = '' }, 2500)
  } finally {
    busy.value = false
  }
}

onBeforeUnmount(stop)
</script>

<style scoped>
.scan-intro {
  display: grid;
  gap: 0.75rem;
  justify-items: start;
}

.scan-text {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin: 0;
}

.scan-stage {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  background: #020617;
  border-radius: 0.6rem;
  overflow: hidden;
}

.scan-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1);
}

.scan-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
}

.scan-oval {
  width: 46%;
  height: 76%;
  border: 3px dashed rgba(255, 255, 255, 0.75);
  border-radius: 50%;
  box-shadow: 0 0 0 2000px rgba(2, 6, 23, 0.35);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.scan-oval.flash {
  border-color: #22c55e;
  box-shadow: 0 0 0 2000px rgba(34, 197, 94, 0.25);
}

.scan-instruction {
  position: absolute;
  bottom: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(15, 23, 42, 0.85);
  color: white;
  font-size: 0.9rem;
  font-weight: 600;
  padding: 0.4rem 0.9rem;
  border-radius: 999px;
  white-space: nowrap;
}

.captures {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin-top: 0.85rem;
}

.capture-item {
  display: grid;
  gap: 0.3rem;
  justify-items: center;
  width: 92px;
}

.capture-item img {
  width: 92px;
  height: 92px;
  object-fit: cover;
  border-radius: 0.5rem;
  border: 1px solid var(--border);
  transform: scaleX(-1);
}

.capture-error {
  font-size: 0.68rem;
  color: var(--danger);
  max-width: 92px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
