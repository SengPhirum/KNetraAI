<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Live Camera Monitoring</h1>
        <p class="page-subtitle">Real-time camera feeds, AI face overlays, and live walk-in events.</p>
      </div>
      <div class="btn-row">
        <button
          v-if="voiceSettings.enabled"
          class="btn secondary"
          type="button"
          :title="voiceGreeter.mutedOnThisDevice.value ? 'Voice greeting muted on this device' : 'Voice greeting active on this device'"
          @click="voiceGreeter.setMuted(!voiceGreeter.mutedOnThisDevice.value)"
        >
          {{ voiceGreeter.mutedOnThisDevice.value ? '🔇 Voice Off' : '🔊 Voice On' }}
        </button>
        <button class="btn secondary" type="button" @click="load">Refresh</button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="card" style="margin-bottom: 1rem;">
      <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.85rem;">
        <h2 class="card-title" style="margin: 0;">Live View</h2>
        <div class="btn-row" v-if="!focusedCamera">
          <button v-for="opt in layoutOptions" :key="opt" class="btn sm secondary" :class="{ active: layout === opt }" @click="setLayout(opt)">{{ opt }}-up</button>
          <button class="btn sm" type="button" @click="showPicker = true">+ Add Camera</button>
        </div>
      </div>

      <div v-if="!cameras.length" style="text-align: center; color: var(--text-muted); padding: 2rem 1rem;">
        No cameras configured yet. Add one in <NuxtLink to="/cameras">Camera Management</NuxtLink>.
      </div>

      <template v-else>
        <div v-if="!visibleCameras.length" style="text-align: center; color: var(--text-muted); padding: 2rem 1rem;">
          <p style="margin: 0 0 0.75rem;">All channels are removed from view.</p>
          <button class="btn" type="button" @click="showPicker = true">+ Add Camera</button>
        </div>

        <div v-else-if="focusedCamera">
          <div class="btn-row" style="margin-bottom: 0.6rem;">
            <button class="btn sm secondary" type="button" @click="focusedCameraId = null">&larr; Back to grid</button>
            <strong style="align-self: center; margin-left: 0.4rem;">{{ focusedCamera.name }}</strong>
            <span class="badge dot" :class="statusClass(focusedCamera.status)">{{ focusedCamera.status }}</span>
            <span class="badge dot" :class="focusedCamera.ai_enabled ? 'success' : ''">{{ focusedCamera.ai_enabled ? 'AI on' : 'AI off' }}</span>
          </div>
          <div class="stream-box focused">
            <LiveStreamTile
              :camera="focusedCamera"
              :src="streamSrc(focusedCamera)"
              :fallback-image="snapshotUrl(latestEvent(focusedCamera.id))"
              :fallback-text="focusedCamera.status === 'running' ? 'Waiting for video...' : 'Live worker is offline'"
            />
          </div>
          <div class="btn-row" style="margin-top: 0.85rem;">
            <button v-if="canStart(focusedCamera)" class="btn sm" :disabled="isBusy" @click="startLive(focusedCamera)">Start Live</button>
            <button v-if="canStopWorker(focusedCamera)" class="btn sm secondary" :disabled="isBusy" @click="stopLive(focusedCamera)">Stop Live</button>
            <template v-if="canOperate">
              <button class="btn sm" :disabled="!canEnableAi(focusedCamera)" @click="enableAi(focusedCamera)">Enable AI</button>
              <button class="btn sm secondary" :disabled="!canDisableAi(focusedCamera)" @click="disableAi(focusedCamera)">Disable AI</button>
            </template>
            <button class="btn sm danger" :disabled="isBusy" @click="removeFromView(focusedCamera)">✕ Remove from view</button>
          </div>
        </div>

        <template v-else>
          <div class="live-grid" :style="gridStyle">
            <div
              v-for="camera in pagedCameras"
              :key="camera.id"
              class="grid-tile"
              :class="{ dragging: draggingId === camera.id, 'drop-target': dragOverId === camera.id && draggingId && draggingId !== camera.id }"
              draggable="true"
              @dragstart="onDragStart(camera, $event)"
              @dragover.prevent="dragOverId = camera.id"
              @dragleave="dragOverId === camera.id && (dragOverId = null)"
              @drop.prevent="onDropTile(camera)"
              @dragend="onDragEnd"
            >
              <div class="tile-header">
                <span class="drag-handle" title="Drag to rearrange">⠿</span>
                <strong class="truncate" :title="camera.name">{{ camera.name }}</strong>
                <div class="btn-row tile-badges">
                  <span class="badge dot" :class="statusClass(camera.status)">{{ camera.status }}</span>
                  <span class="badge dot" :class="camera.ai_enabled ? 'success' : ''">{{ camera.ai_enabled ? 'AI on' : 'AI off' }}</span>
                  <button
                    class="tile-remove"
                    type="button"
                    title="Remove this channel from live view (stops its worker)"
                    @click="removeFromView(camera)"
                  >✕</button>
                </div>
              </div>
              <div class="stream-box" @dblclick="focusedCameraId = camera.id">
                <LiveStreamTile
                  :camera="camera"
                  :src="streamSrc(camera)"
                  :fallback-image="snapshotUrl(latestEvent(camera.id))"
                  :fallback-text="camera.status === 'running' ? 'Waiting for video...' : 'Live worker is offline'"
                />
              </div>
              <div class="btn-row" style="margin-top: 0.5rem;">
                <button v-if="canStart(camera)" class="btn sm" :disabled="isBusy" @click="startLive(camera)">Start Live</button>
                <button v-if="canStopWorker(camera)" class="btn sm secondary" :disabled="isBusy" @click="stopLive(camera)">Stop Live</button>
                <template v-if="canOperate">
                  <button class="btn sm" :disabled="!canEnableAi(camera)" @click="enableAi(camera)">Enable AI</button>
                  <button class="btn sm secondary" :disabled="!canDisableAi(camera)" @click="disableAi(camera)">Disable AI</button>
                </template>
                <button class="btn sm secondary" @click="focusedCameraId = camera.id">Focus</button>
              </div>
            </div>
          </div>
          <div v-if="totalPages > 1" class="btn-row" style="justify-content: center; margin-top: 0.85rem;">
            <button
              class="btn sm secondary"
              :class="{ 'page-drop': draggingId && safePage > 0 }"
              :disabled="safePage === 0 && !draggingId"
              @click="page = safePage - 1"
              @dragover.prevent="onPageDragOver(-1)"
              @dragleave="onPageDragLeave"
              @drop.prevent="onDropPage(-1)"
            >Prev</button>
            <span style="align-self: center; font-size: 0.85rem; color: var(--text-muted);">
              Page {{ safePage + 1 }} / {{ totalPages }}
              <template v-if="draggingId"> - drop on Prev/Next to move between pages</template>
            </span>
            <button
              class="btn sm secondary"
              :class="{ 'page-drop': draggingId && safePage < totalPages - 1 }"
              :disabled="safePage >= totalPages - 1 && !draggingId"
              @click="page = safePage + 1"
              @dragover.prevent="onPageDragOver(1)"
              @dragleave="onPageDragLeave"
              @drop.prevent="onDropPage(1)"
            >Next</button>
          </div>
        </template>
      </template>
    </div>

    <section class="card" style="margin-top: 1rem;">
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
        <h2 class="card-title" style="margin: 0;">Live Detection Events</h2>
        <button v-if="isAdmin && events.length" class="btn sm danger" type="button" :disabled="clearing" @click="clearEvents">
          {{ clearing ? 'Clearing...' : 'Clear Events' }}
        </button>
      </div>
      <div class="table-wrap" style="box-shadow: none;">
        <table class="table">
          <thead><tr><th>Snapshot</th><th>Time</th><th>Camera</th><th>Person</th><th>Type</th><th>Greeting</th><th>Confidence</th></tr></thead>
          <tbody>
            <tr v-if="!events.length"><td colspan="7" class="empty-row">No detection events yet. Enable AI and keep a face in view of a live camera.</td></tr>
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
    <CameraPickerModal
      :show="showPicker"
      :in-view-ids="visibleCameraIds"
      @close="showPicker = false"
      @add="addToView"
      @remove="hideFromView"
    />
  </div>
</template>

<script setup lang="ts">
const { apiFetch, apiBaseUrl, token } = useApi()
const { isAdmin, canOperate } = useCurrentUser()
const voiceGreeter = useVoiceGreeter()

const cameras = ref<any[]>([])
const events = ref<any[]>([])
const selectedEvent = ref<any | null>(null)
const error = ref('')
const clearing = ref(false)
let source: EventSource | null = null
let refreshTimer: ReturnType<typeof setInterval> | null = null

const layoutOptions = [1, 4, 6, 9]
const layoutCols: Record<number, number> = { 1: 1, 4: 2, 6: 3, 9: 3 }
const layout = ref(4)
const page = ref(0)
const focusedCameraId = ref<string | null>(null)

const HIDDEN_KEY = 'live.hidden_camera_ids'
const ORDER_KEY = 'live.camera_order'
const hiddenIds = ref<string[]>(import.meta.client ? JSON.parse(localStorage.getItem(HIDDEN_KEY) || '[]') : [])
const persistHidden = () => { if (import.meta.client) localStorage.setItem(HIDDEN_KEY, JSON.stringify(hiddenIds.value)) }
const cameraOrder = ref<string[]>(import.meta.client ? JSON.parse(localStorage.getItem(ORDER_KEY) || '[]') : [])
const persistOrder = () => { if (import.meta.client) localStorage.setItem(ORDER_KEY, JSON.stringify(cameraOrder.value)) }

const showPicker = ref(false)

const voiceSettings = ref<ReturnType<typeof voiceSettingsFromList>>({
  enabled: false, greetKnown: true, greetUnknown: true, repeatSeconds: 60, rate: 1, volume: 1, voiceName: ''
})

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

const loadVoiceSettings = async () => {
  try {
    voiceSettings.value = voiceSettingsFromList(await apiFetch('/settings'))
  } catch {
    // Voice greeting stays off if settings can't be read.
  }
}

// Cameras in the user's saved arrangement first, then any new/unordered ones.
const orderedCameras = computed(() => {
  const position = new Map(cameraOrder.value.map((id, index) => [id, index]))
  return [...cameras.value].sort((a, b) => {
    const pa = position.has(a.id) ? position.get(a.id)! : Number.MAX_SAFE_INTEGER
    const pb = position.has(b.id) ? position.get(b.id)! : Number.MAX_SAFE_INTEGER
    return pa - pb
  })
})

const visibleCameras = computed(() => orderedCameras.value.filter(c => !hiddenIds.value.includes(c.id)))
const visibleCameraIds = computed(() => visibleCameras.value.map(c => c.id))

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

const totalPages = computed(() => Math.max(1, Math.ceil(visibleCameras.value.length / layout.value)))
const safePage = computed(() => Math.min(page.value, totalPages.value - 1))
const pagedCameras = computed(() => {
  const start = safePage.value * layout.value
  return visibleCameras.value.slice(start, start + layout.value)
})
const gridStyle = computed(() => ({ gridTemplateColumns: `repeat(${layoutCols[layout.value] || 2}, 1fr)` }))
const focusedCamera = computed(() => visibleCameras.value.find(c => c.id === focusedCameraId.value) || null)
const runningStatuses = new Set(['starting', 'connecting', 'running', 'reconnecting'])

const setLayout = (opt: number) => {
  layout.value = opt
  page.value = 0
}

const formatDate = (value?: string) => value ? new Date(value).toLocaleString() : '-'
const confidence = (event?: any) => event?.confidence ? Number(event.confidence).toFixed(3) : '-'
const typeClass = (type: string) => type === 'staff' ? 'info' : type === 'customer' ? 'success' : 'warning'

const isBusy = ref(false)
const canStart = (camera: any) => canOperate.value && Boolean(camera?.enabled) && !runningStatuses.has(camera.status)
const canStopWorker = (camera: any) => canOperate.value && runningStatuses.has(camera?.status)
const canEnableAi = (camera: any) => Boolean(camera?.enabled) && runningStatuses.has(camera.status) && !camera.ai_enabled && !isBusy.value
const canDisableAi = (camera: any) => Boolean(camera?.ai_enabled) && !isBusy.value

const callCamera = async (path: string, body?: any) => {
  error.value = ''
  isBusy.value = true
  try {
    await apiFetch(path, { method: 'POST', ...(body !== undefined ? { body } : {}) })
    await load()
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Camera action failed'
  } finally {
    isBusy.value = false
  }
}

const startLive = (camera: any) => callCamera(`/cameras/${camera.id}/start`)
const stopLive = (camera: any) => callCamera(`/cameras/${camera.id}/stop`)
const enableAi = (camera: any) => callCamera(`/cameras/${camera.id}/ai`, { enabled: true })
const disableAi = (camera: any) => callCamera(`/cameras/${camera.id}/ai`, { enabled: false })

const removeFromView = async (camera: any) => {
  const stopIt = canOperate.value && runningStatuses.has(camera.status)
  const message = stopIt
    ? `Remove "${camera.name}" from live view and stop its running worker?`
    : `Remove "${camera.name}" from live view on this device?`
  if (!confirm(message)) return
  if (focusedCameraId.value === camera.id) focusedCameraId.value = null
  hiddenIds.value = [...hiddenIds.value, camera.id]
  persistHidden()
  if (stopIt) await callCamera(`/cameras/${camera.id}/stop`)
}

// Modal "Add to view": unhide the channel; if its worker is stopped, the tile
// shows offline with a Start Live button (starting stays an explicit action).
const addToView = (camera: any) => {
  hiddenIds.value = hiddenIds.value.filter(id => id !== camera.id)
  persistHidden()
}

// Modal "Remove": composing the view only - hides the tile without touching the
// worker (the tile's ✕ is the action that also stops it).
const hideFromView = (camera: any) => {
  if (!hiddenIds.value.includes(camera.id)) {
    hiddenIds.value = [...hiddenIds.value, camera.id]
    persistHidden()
  }
  if (focusedCameraId.value === camera.id) focusedCameraId.value = null
}

// ---------------- Drag & drop tile arrangement ----------------
const draggingId = ref<string | null>(null)
const dragOverId = ref<string | null>(null)
let pageFlipTimer: ReturnType<typeof setTimeout> | null = null

const onDragStart = (camera: any, event: DragEvent) => {
  draggingId.value = camera.id
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', camera.id)
  }
}

const onDragEnd = () => {
  draggingId.value = null
  dragOverId.value = null
  if (pageFlipTimer) { clearTimeout(pageFlipTimer); pageFlipTimer = null }
}

/** Insert the dragged camera at `insertAt` within the visible list (computed
 *  after removing it), then persist visible order + hidden ids as the new order. */
const reorderVisible = (insertAt: number) => {
  if (!draggingId.value) return
  const ids = visibleCameraIds.value.filter(id => id !== draggingId.value)
  ids.splice(Math.max(0, Math.min(insertAt, ids.length)), 0, draggingId.value)
  cameraOrder.value = [...ids, ...hiddenIds.value]
  persistOrder()
}

const onDropTile = (target: any) => {
  if (!draggingId.value || draggingId.value === target.id) { onDragEnd(); return }
  const ids = visibleCameraIds.value.filter(id => id !== draggingId.value)
  reorderVisible(ids.indexOf(target.id))
  onDragEnd()
}

// Hovering Prev/Next for a moment while dragging flips the page so the tile
// can be dropped precisely on the other page.
const onPageDragOver = (direction: number) => {
  if (!draggingId.value || pageFlipTimer) return
  pageFlipTimer = setTimeout(() => {
    pageFlipTimer = null
    const target = safePage.value + direction
    if (target >= 0 && target < totalPages.value) page.value = target
  }, 600)
}

const onPageDragLeave = () => {
  if (pageFlipTimer) { clearTimeout(pageFlipTimer); pageFlipTimer = null }
}

// Dropping directly on Prev/Next moves the camera to the start of that page.
const onDropPage = (direction: number) => {
  if (!draggingId.value) return
  const targetPage = Math.max(0, Math.min(safePage.value + direction, totalPages.value - 1))
  reorderVisible(targetPage * layout.value)
  page.value = targetPage
  onDragEnd()
}

const clearEvents = async () => {
  if (!confirm('Delete ALL detection events and snapshots from the server? This cannot be undone.')) return
  clearing.value = true
  error.value = ''
  try {
    await apiFetch('/detection-events/clear', { method: 'POST', body: {} })
    events.value = []
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Could not clear events'
  } finally {
    clearing.value = false
  }
}

const statusClass = (status: string) => {
  if (status === 'running') return 'success'
  if (status === 'connecting' || status === 'starting' || status === 'reconnecting') return 'warning'
  if (status === 'error') return 'danger'
  return ''
}

const addEvent = (event: any) => {
  events.value = [event, ...events.value.filter(item => item.id !== event.id)].slice(0, 30)
  voiceGreeter.speakGreeting(event, voiceSettings.value).catch(() => {})
}

onMounted(async () => {
  await load()
  await loadVoiceSettings()
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

.tile-badges {
  flex-wrap: nowrap;
  justify-content: flex-end;
  align-items: center;
}

.tile-remove {
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.9rem;
  font-weight: 700;
  line-height: 1;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 0.35rem;
  cursor: pointer;
}

.tile-remove:hover {
  background: var(--danger-soft);
  color: var(--danger);
}

.drag-handle {
  cursor: grab;
  color: var(--text-muted);
  font-size: 0.95rem;
  line-height: 1;
  user-select: none;
  flex-shrink: 0;
}

.grid-tile.dragging {
  opacity: 0.45;
}

.grid-tile.drop-target .stream-box {
  outline: 3px solid var(--primary);
  outline-offset: 2px;
}

.page-drop {
  outline: 2px dashed var(--primary);
  outline-offset: 2px;
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
