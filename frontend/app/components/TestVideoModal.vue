<template>
  <div v-if="show" class="picker-overlay" role="dialog" aria-modal="true" @click.self="$emit('close')">
    <div class="picker-dialog">
      <div class="picker-header">
        <div>
          <h2 class="picker-title">Test Videos</h2>
          <p class="picker-meta">
            Play a video file as a looping test camera - no real CCTV needed. Bundled clips match the dummy
            staff/customers from Settings &gt; Demo, so recognition and greetings can be tested end to end.
          </p>
        </div>
        <div class="btn-row">
          <button class="btn sm secondary" type="button" :disabled="loading" @click="loadAll">
            {{ loading ? 'Reloading...' : 'Reload' }}
          </button>
          <button class="btn sm secondary" type="button" @click="$emit('close')">Close</button>
        </div>
      </div>

      <div class="picker-body">
        <p v-if="error" class="error">{{ error }}</p>

        <div class="upload-row">
          <input ref="fileInput" type="file" accept="video/mp4,video/x-m4v,video/quicktime,video/x-msvideo,video/x-matroska,video/webm,.mp4,.m4v,.mov,.avi,.mkv,.webm" style="display: none;" @change="onFileChosen" />
          <button class="btn sm" type="button" :disabled="uploading" @click="fileInput?.click()">
            {{ uploading ? `Uploading... ${uploadNote}` : '⬆ Upload your own test video' }}
          </button>
          <small style="color: var(--text-muted);">mp4 / mov / avi / mkv / webm, up to 300 MB. It will loop like a live feed.</small>
        </div>

        <p v-if="!loading && !videos.length" class="picker-empty">No test videos available yet. Upload one above.</p>

        <div class="picker-grid">
          <article v-for="video in videos" :key="video.kind + video.file" class="picker-card" :class="{ 'in-view': !!video.camera_id }">
            <div class="picker-thumb">
              <img v-if="thumbnails[video.file]?.url" :src="thumbnails[video.file].url" :alt="`Preview of ${video.label}`" draggable="false" />
              <div v-else class="picker-thumb-placeholder">
                <span>{{ thumbnails[video.file]?.loading ? 'Loading preview...' : 'No preview' }}</span>
              </div>
              <span class="badge picker-status" :class="video.kind === 'bundled' ? 'info' : 'warning'">
                {{ video.kind === 'bundled' ? 'Bundled' : 'Uploaded' }}
              </span>
            </div>
            <div class="picker-info">
              <strong class="truncate" :title="video.label">{{ video.label }}</strong>
              <small v-if="video.description">{{ video.description }}</small>
              <small>
                {{ formatSize(video.size_bytes) }}
                <template v-if="video.attendance_role && video.attendance_role !== 'none'"> - attendance {{ video.attendance_role }} door</template>
              </small>
            </div>
            <div class="picker-actions">
              <template v-if="video.camera_id">
                <span class="badge success">Camera added</span>
                <button
                  v-if="video.camera_status !== 'running'"
                  class="btn sm"
                  type="button"
                  :disabled="busyFile === video.file"
                  @click="addCamera(video)"
                >{{ busyFile === video.file ? 'Starting...' : 'Start' }}</button>
                <span v-else class="badge dot success">Live</span>
              </template>
              <button
                v-else
                class="btn sm"
                type="button"
                :disabled="busyFile === video.file"
                @click="addCamera(video)"
              >{{ busyFile === video.file ? 'Adding...' : '+ Add & Start' }}</button>
              <button
                v-if="video.kind === 'uploaded' && isAdmin"
                class="btn sm danger"
                type="button"
                :disabled="busyFile === video.file"
                title="Delete this uploaded video (removes its test camera too)"
                @click="deleteVideo(video)"
              >Delete</button>
            </div>
          </article>
        </div>

        <p v-if="license" class="license-note">{{ license }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: [], added: [camera: any] }>()

const { apiFetch } = useApi()
const { isAdmin } = useCurrentUser()

const videos = ref<any[]>([])
const license = ref('')
const thumbnails = reactive<Record<string, { url?: string, loading: boolean }>>({})
const loading = ref(false)
const uploading = ref(false)
const uploadNote = ref('')
const busyFile = ref('')
const error = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const formatSize = (bytes: number) => {
  if (!bytes) return ''
  const mb = bytes / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`
}

const loadThumbnail = async (video: any) => {
  const state = thumbnails[video.file] || (thumbnails[video.file] = { loading: false })
  if (state.url) return
  state.loading = true
  try {
    const result: any = await apiFetch(`/testing/videos/${video.kind}/${encodeURIComponent(video.file)}/thumbnail`)
    if (result?.thumbnail) state.url = result.thumbnail
  } catch {
    // Missing preview is cosmetic only.
  } finally {
    state.loading = false
  }
}

const loadAll = async () => {
  loading.value = true
  error.value = ''
  try {
    const result: any = await apiFetch('/testing/videos')
    videos.value = result.videos || []
    license.value = result.license || ''
    await Promise.all(videos.value.map(video => loadThumbnail(video)))
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Could not load test videos'
  } finally {
    loading.value = false
  }
}

const addCamera = async (video: any) => {
  busyFile.value = video.file
  error.value = ''
  try {
    const result: any = await apiFetch('/testing/videos/camera', {
      method: 'POST',
      body: { kind: video.kind, file: video.file, autostart: true }
    })
    if (result?.camera) emit('added', result.camera)
    await loadAll()
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Could not create the test camera'
  } finally {
    busyFile.value = ''
  }
}

const deleteVideo = async (video: any) => {
  if (!confirm(`Delete uploaded video "${video.file}"? Its test camera and detection history are removed too.`)) return
  busyFile.value = video.file
  error.value = ''
  try {
    await apiFetch(`/testing/videos/${encodeURIComponent(video.file)}`, { method: 'DELETE' })
    delete thumbnails[video.file]
    await loadAll()
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Could not delete the video'
  } finally {
    busyFile.value = ''
  }
}

const onFileChosen = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  uploading.value = true
  uploadNote.value = formatSize(file.size)
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    await apiFetch('/testing/videos/upload', { method: 'POST', body: form })
    await loadAll()
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Upload failed'
  } finally {
    uploading.value = false
    uploadNote.value = ''
  }
}

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
  max-width: 46rem;
}

.picker-body {
  padding: 1rem 1.25rem 1.25rem;
  overflow-y: auto;
}

.upload-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-bottom: 0.9rem;
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
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 0.85rem;
}

.picker-card {
  display: grid;
  gap: 0.5rem;
  padding: 0.6rem;
  border: 1px solid var(--border);
  border-radius: 0.65rem;
  background: var(--surface);
  align-content: start;
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
  gap: 0.15rem;
  font-size: 0.85rem;
}

.picker-info small {
  color: var(--text-muted);
}

.picker-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.license-note {
  margin: 1rem 0 0;
  color: var(--text-muted);
  font-size: 0.75rem;
}
</style>
