<template>
  <div v-if="show" class="picker-overlay" role="dialog" aria-modal="true" @click.self="$emit('close')">
    <div class="picker-dialog">
      <div class="picker-header">
        <div>
          <h2 class="picker-title">Add Cameras to Live View</h2>
          <p class="picker-meta">All active camera channels. Thumbnails come from the live worker when running.</p>
        </div>
        <div class="btn-row">
          <button class="btn sm secondary" type="button" :disabled="loading" @click="loadAll">
            {{ loading ? 'Reloading...' : 'Reload' }}
          </button>
          <button
            v-if="addableCameras.length"
            class="btn sm"
            type="button"
            @click="addableCameras.forEach(camera => $emit('add', camera))"
          >Add All ({{ addableCameras.length }})</button>
          <button class="btn sm secondary" type="button" @click="$emit('close')">Close</button>
        </div>
      </div>

      <div class="picker-body">
        <input
          v-if="cameras.length > 6"
          v-model="search"
          class="input"
          placeholder="Search camera name, branch, location..."
          style="margin-bottom: 0.85rem;"
        />
        <p v-if="error" class="error">{{ error }}</p>
        <p v-if="!loading && !filteredCameras.length" class="picker-empty">
          {{ cameras.length ? 'No cameras match the search.' : 'No active camera channels. Enable or add cameras in Camera Management.' }}
        </p>

        <div class="picker-grid">
          <article v-for="camera in filteredCameras" :key="camera.id" class="picker-card" :class="{ 'in-view': isInView(camera.id) }">
            <div class="picker-thumb">
              <img v-if="thumbnails[camera.id]?.url" :src="thumbnails[camera.id].url" :alt="`Preview of ${camera.name}`" draggable="false" />
              <div v-else class="picker-thumb-placeholder">
                <span>{{ thumbnails[camera.id]?.loading ? 'Loading...' : (thumbnails[camera.id]?.error || 'No live preview') }}</span>
                <button
                  v-if="!thumbnails[camera.id]?.loading && camera.status !== 'running'"
                  class="btn sm secondary"
                  type="button"
                  @click="loadThumbnail(camera, true)"
                >Load preview</button>
              </div>
              <span class="badge dot picker-status" :class="statusClass(camera.status)">{{ camera.status === 'running' ? 'Live' : camera.status || 'stopped' }}</span>
            </div>
            <div class="picker-info">
              <strong class="truncate" :title="camera.name">{{ camera.name }}</strong>
              <small class="truncate">{{ [camera.branch, camera.location].filter(Boolean).join(' - ') || 'No site set' }}</small>
            </div>
            <button
              v-if="!isInView(camera.id)"
              class="btn sm"
              type="button"
              @click="$emit('add', camera)"
            >+ Add to view</button>
            <div v-else class="picker-inview-row">
              <span class="badge success">In view</span>
              <button class="btn sm secondary" type="button" @click="$emit('remove', camera)">Remove</button>
            </div>
          </article>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  show: boolean
  inViewIds: string[]
}>()
defineEmits<{ close: [], add: [camera: any], remove: [camera: any] }>()

const { apiFetch } = useApi()
const cameras = ref<any[]>([])
const thumbnails = reactive<Record<string, { url?: string, loading: boolean, error?: string }>>({})
const loading = ref(false)
const error = ref('')
const search = ref('')

const isInView = (id: string) => props.inViewIds.includes(id)
const addableCameras = computed(() => filteredCameras.value.filter(camera => !isInView(camera.id)))

const filteredCameras = computed(() => {
  const term = search.value.trim().toLowerCase()
  if (!term) return cameras.value
  return cameras.value.filter(camera =>
    [camera.name, camera.branch, camera.location].some(value => String(value || '').toLowerCase().includes(term))
  )
})

const statusClass = (status: string) => {
  if (status === 'running') return 'success'
  if (['connecting', 'starting', 'reconnecting'].includes(status)) return 'warning'
  if (status === 'error') return 'danger'
  return ''
}

const loadThumbnail = async (camera: any, probe = false) => {
  const state = thumbnails[camera.id] || (thumbnails[camera.id] = { loading: false })
  state.loading = true
  state.error = undefined
  try {
    const result: any = await apiFetch(`/cameras/${camera.id}/snapshot${probe ? '?probe=true' : ''}`)
    if (result.ok && result.thumbnail) state.url = result.thumbnail
    else if (!result.ok) state.error = probe ? (result.error || 'No preview') : 'No live preview'
  } catch (e: any) {
    state.error = e?.data?.detail || e.message || 'Preview failed'
  } finally {
    state.loading = false
  }
}

const loadAll = async () => {
  loading.value = true
  error.value = ''
  try {
    const rows = await apiFetch<any[]>('/cameras')
    cameras.value = rows.filter(camera => camera.enabled)
    for (const id of Object.keys(thumbnails)) delete thumbnails[id]
    // Cheap path only by default: live workers re-serve their latest frame. Probing
    // every stopped channel would open one RTSP connection per camera on the NVR,
    // so stopped ones get a manual "Load preview" button instead.
    await Promise.all(
      cameras.value.filter(camera => camera.status === 'running').map(camera => loadThumbnail(camera))
    )
  } catch (e: any) {
    error.value = e?.data?.detail || e.message || 'Could not load cameras'
  } finally {
    loading.value = false
  }
}

// Fresh reload every time the popup opens.
watch(() => props.show, (open) => { if (open) loadAll() })
</script>

<style scoped>
.picker-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 1rem;
  background: rgba(15, 23, 42, 0.72);
}

.picker-dialog {
  width: min(1180px, 100%);
  max-height: min(900px, calc(100vh - 2rem));
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-radius: 0.75rem;
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.36);
}

.picker-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border);
}

.picker-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
}

.picker-meta {
  margin: 0.2rem 0 0;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.picker-body {
  padding: 1rem 1.25rem 1.25rem;
  overflow-y: auto;
}

.picker-empty {
  color: var(--text-muted);
  font-size: 0.9rem;
  text-align: center;
  padding: 2rem 1rem;
  margin: 0;
}

.picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 0.85rem;
}

.picker-card {
  display: grid;
  gap: 0.5rem;
  padding: 0.6rem;
  border: 1px solid var(--border);
  border-radius: 0.65rem;
  background: var(--surface);
}

.picker-card.in-view {
  border-color: color-mix(in srgb, var(--success, #16a34a) 45%, var(--border));
}

.picker-thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 0.5rem;
  overflow: hidden;
  background: #020617;
}

.picker-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.picker-thumb-placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 0.5rem;
  color: #94a3b8;
  font-size: 0.8rem;
  text-align: center;
  padding: 0.5rem;
}

.picker-status {
  position: absolute;
  top: 0.45rem;
  left: 0.45rem;
}

.picker-info {
  display: grid;
  gap: 0.1rem;
  font-size: 0.85rem;
}

.picker-info small {
  color: var(--text-muted);
}

.picker-inview-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
</style>
