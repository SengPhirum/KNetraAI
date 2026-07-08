<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Live Camera Monitoring</h1>
        <p class="page-subtitle">Real-time camera feeds, worker status, and live walk-in events.</p>
      </div>
      <button class="btn secondary" type="button" @click="load">Refresh</button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="card" style="margin-bottom: 1rem;">
      <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.85rem;">
        <h2 class="card-title" style="margin: 0;">Live View</h2>
        <div class="btn-row" v-if="!focusedCamera">
          <button v-for="opt in layoutOptions" :key="opt" class="btn sm secondary" :class="{ active: layout === opt }" @click="setLayout(opt)">{{ opt }}-up</button>
        </div>
      </div>

      <div v-if="!cameras.length" style="text-align: center; color: var(--text-muted); padding: 2rem 1rem;">
        No cameras configured yet. Add one in <NuxtLink to="/cameras">Camera Management</NuxtLink>.
      </div>

      <template v-else>
        <div v-if="focusedCamera">
          <div class="btn-row" style="margin-bottom: 0.6rem;">
            <button class="btn sm secondary" type="button" @click="focusedCameraId = null">&larr; Back to grid</button>
            <strong style="align-self: center; margin-left: 0.4rem;">{{ focusedCamera.name }}</strong>
            <span class="badge dot" :class="statusClass(focusedCamera.status)">{{ focusedCamera.status }}</span>
          </div>
          <div class="stream-box focused">
            <LiveStreamTile
              :camera="focusedCamera"
              :src="streamSrc(focusedCamera)"
              :fallback-image="snapshotUrl(latestEvent(focusedCamera.id))"
              :fallback-text="focusedCamera.status === 'running' ? 'Waiting for video...' : 'Camera worker is stopped - click Start to view the live feed'"
            />
          </div>
          <div class="btn-row" style="margin-top: 0.85rem;">
            <button class="btn sm" @click="start(focusedCamera.id)">Start AI</button>
            <button class="btn sm secondary" @click="stop(focusedCamera.id)">Stop AI</button>
          </div>
        </div>

        <template v-else>
          <div class="live-grid" :style="gridStyle">
            <div v-for="camera in pagedCameras" :key="camera.id" class="grid-tile">
              <div class="tile-header">
                <strong class="truncate" :title="camera.name">{{ camera.name }}</strong>
                <span class="badge dot" :class="statusClass(camera.status)">{{ camera.status }}</span>
              </div>
              <div class="stream-box" @dblclick="focusedCameraId = camera.id">
                <LiveStreamTile
                  :camera="camera"
                  :src="streamSrc(camera)"
                  :fallback-image="snapshotUrl(latestEvent(camera.id))"
                  :fallback-text="camera.status === 'running' ? 'Waiting for video...' : 'Camera worker is stopped'"
                />
              </div>
              <div class="btn-row" style="margin-top: 0.5rem;">
                <button class="btn sm" @click="start(camera.id)">Start</button>
                <button class="btn sm secondary" @click="stop(camera.id)">Stop</button>
                <button class="btn sm secondary" @click="focusedCameraId = camera.id">Focus</button>
              </div>
            </div>
          </div>
          <div v-if="totalPages > 1" class="btn-row" style="justify-content: center; margin-top: 0.85rem;">
            <button class="btn sm secondary" :disabled="safePage === 0" @click="page = safePage - 1">Prev</button>
            <span style="align-self: center; font-size: 0.85rem; color: var(--text-muted);">Page {{ safePage + 1 }} / {{ totalPages }}</span>
            <button class="btn sm secondary" :disabled="safePage >= totalPages - 1" @click="page = safePage + 1">Next</button>
          </div>
        </template>
      </template>
    </div>

    <section class="card" style="margin-top: 1rem;">
      <h2 class="card-title">Live Detection Events</h2>
      <div class="table-wrap" style="box-shadow: none;">
        <table class="table">
          <thead><tr><th>Snapshot</th><th>Time</th><th>Camera</th><th>Person</th><th>Type</th><th>Greeting</th><th>Confidence</th></tr></thead>
          <tbody>
            <tr v-if="!events.length"><td colspan="7" class="empty-row">No detection events yet. Keep a face in view of a running camera.</td></tr>
            <tr v-for="event in events" :key="event.id">
              <td>
                <button v-if="event.snapshot_path" class="snapshot-thumb" type="button" @click="selectedEvent = event">
                  <img :src="`${apiBaseUrl}/files/${event.snapshot_path}`" class="thumb" />
                </button>
                <span v-else>-</span>
              </td>
              <td style="white-space: nowrap;">{{ formatDate(event.detected_at) }}</td>
              <td>{{ event.camera_name || '-' }}</td>
              <td>{{ event.person_name || 'Unknown' }}</td>
              <td><span class="badge" :class="typeClass(event.person_type)">{{ event.person_type }}</span></td>
              <td class="truncate" :title="event.greeting">{{ event.greeting }}</td>
              <td>{{ confidence(event) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <SnapshotModal :event="selectedEvent" :api-base-url="apiBaseUrl" @close="selectedEvent = null" />
  </div>
</template>

<script setup lang="ts">
const { apiFetch, apiBaseUrl, token } = useApi()
const cameras = ref<any[]>([])
const events = ref<any[]>([])
const selectedEvent = ref<any | null>(null)
const error = ref('')
let source: EventSource | null = null
let refreshTimer: ReturnType<typeof setInterval> | null = null

const layoutOptions = [1, 4, 6, 9]
const layoutCols: Record<number, number> = { 1: 1, 4: 2, 6: 3, 9: 3 }
const layout = ref(4)
const page = ref(0)
const focusedCameraId = ref<string | null>(null)

const load = async () => {
  error.value = ''
  try {
    const [cameraRows, eventRows] = await Promise.all([
      apiFetch<any[]>('/cameras'),
      apiFetch<any[]>('/detection-events?limit=30&has_snapshot=true')
    ])
    cameras.value = cameraRows
    events.value = eventRows
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Could not load live monitoring data'
  }
}

const latestByCamera = computed(() => {
  const byCamera = new Map<string, any>()
  for (const event of events.value) {
    if (event.camera_id && !byCamera.has(event.camera_id)) byCamera.set(event.camera_id, event)
  }
  return byCamera
})

const latestEvent = (cameraId: string) => latestByCamera.value.get(cameraId)
const snapshotUrl = (event?: any) => (event?.snapshot_path ? `${apiBaseUrl}/files/${event.snapshot_path}` : null)
const streamSrc = (camera: any) => {
  if (!camera || camera.status !== 'running' || !token.value) return null
  return `${apiBaseUrl}/cameras/${camera.id}/stream?token=${encodeURIComponent(token.value)}`
}

const totalPages = computed(() => Math.max(1, Math.ceil(cameras.value.length / layout.value)))
const safePage = computed(() => Math.min(page.value, totalPages.value - 1))
const pagedCameras = computed(() => {
  const start = safePage.value * layout.value
  return cameras.value.slice(start, start + layout.value)
})
const gridStyle = computed(() => ({ gridTemplateColumns: `repeat(${layoutCols[layout.value] || 2}, 1fr)` }))
const focusedCamera = computed(() => cameras.value.find(c => c.id === focusedCameraId.value) || null)

const setLayout = (opt: number) => {
  layout.value = opt
  page.value = 0
}

const formatDate = (value?: string) => value ? new Date(value).toLocaleString() : '-'
const confidence = (event?: any) => event?.confidence ? Number(event.confidence).toFixed(3) : '-'
const typeClass = (type: string) => type === 'staff' ? 'info' : type === 'customer' ? 'success' : 'warning'

const start = async (id: string) => {
  error.value = ''
  try {
    await apiFetch(`/cameras/${id}/start`, { method: 'POST' })
    await load()
  } catch (e: any) { error.value = e?.data?.detail || e?.message || 'Could not start camera' }
}

const stop = async (id: string) => {
  error.value = ''
  try {
    await apiFetch(`/cameras/${id}/stop`, { method: 'POST' })
    await load()
  } catch (e: any) { error.value = e?.data?.detail || e?.message || 'Could not stop camera' }
}

const statusClass = (status: string) => {
  if (status === 'running') return 'success'
  if (status === 'connecting' || status === 'starting' || status === 'reconnecting') return 'warning'
  if (status === 'error') return 'danger'
  return ''
}

const addEvent = (event: any) => {
  events.value = [event, ...events.value.filter(item => item.id !== event.id)].slice(0, 30)
}

onMounted(async () => {
  await load()
  refreshTimer = setInterval(load, 10000)
  if (token.value) {
    source = new EventSource(`${apiBaseUrl}/events/stream?token=${encodeURIComponent(token.value)}`)
    source.addEventListener('detection', (message: MessageEvent) => addEvent(JSON.parse(message.data)))
  }
})

onBeforeUnmount(() => {
  source?.close()
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.live-grid {
  display: grid;
  gap: 0.85rem;
}

.grid-tile {
  display: grid;
  align-content: start;
}

.tile-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.4rem;
  font-size: 0.85rem;
}

.stream-box {
  width: 100%;
  aspect-ratio: 16 / 9;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  overflow: hidden;
  background: #020617;
}

.stream-box.focused {
  max-height: 70vh;
}

.snapshot-thumb {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: zoom-in;
  display: block;
}
</style>
