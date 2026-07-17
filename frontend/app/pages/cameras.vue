<template>
  <div class="camera-page">
    <div class="page-header camera-header">
      <div>
        <h1 class="page-title">Camera Management</h1>
        <p class="page-subtitle">Connect RTSP cameras or NVR channels and start or stop live video workers.</p>
      </div>
      <div class="btn-row page-actions">
        <button class="btn secondary" type="button" :disabled="loading" @click="load">
          {{ loading ? 'Refreshing...' : 'Refresh' }}
        </button>
        <button class="btn secondary" type="button" @click="showHelp = !showHelp">
          {{ showHelp ? 'Hide Help' : 'Setup Help' }}
        </button>
      </div>
    </div>

    <div class="camera-stats" aria-label="Camera summary">
      <div class="stat-chip">
        <span>{{ stats.total }}</span>
        <small>Total</small>
      </div>
      <div class="stat-chip">
        <span>{{ stats.enabled }}</span>
        <small>Active</small>
      </div>
      <div class="stat-chip">
        <span>{{ stats.running }}</span>
        <small>Live</small>
      </div>
      <div class="stat-chip danger-soft">
        <span>{{ stats.needsAttention }}</span>
        <small>Needs attention</small>
      </div>
    </div>

    <CameraDiscoveryPanel @added="load" />

    <section id="manual-camera-form" class="card">
      <div class="section-heading">
        <div>
          <p class="section-kicker">Manual setup</p>
          <h2 class="card-title">{{ editingId ? 'Edit Camera' : 'Add Camera Manually' }}</h2>
        </div>
        <span v-if="editingId" class="badge info">Editing</span>
      </div>

      <form class="form-grid camera-form" @submit.prevent="saveCamera">
        <div>
          <label class="label" for="camera-name">Name</label>
          <input id="camera-name" v-model="form.name" class="input" required />
        </div>
        <div>
          <label class="label" for="camera-branch">Branch</label>
          <input id="camera-branch" v-model="form.branch" class="input" />
        </div>
        <div>
          <label class="label" for="camera-location">Location</label>
          <input id="camera-location" v-model="form.location" class="input" />
        </div>
        <label class="checkbox-label active-toggle">
          <input v-model="form.enabled" type="checkbox" />
          <span>Active camera</span>
        </label>
        <div class="full-row">
          <label class="label" for="camera-rtsp">RTSP URL</label>
          <input id="camera-rtsp" v-model="form.rtsp_url" class="input" placeholder="rtsp://user:pass@ip:554/stream" required />
          <small class="hint">Use discovery for ONVIF devices, or paste a brand-specific RTSP URL.</small>
        </div>
        <div class="btn-row full-row">
          <button class="btn" type="submit" :disabled="saving">{{ saving ? 'Saving...' : editingId ? 'Save Camera' : 'Add Camera' }}</button>
          <button class="btn secondary" type="button" :disabled="testing || !form.rtsp_url" @click="testConnection">
            {{ testing ? 'Testing...' : 'Test Connection' }}
          </button>
          <button v-if="editingId" class="btn secondary" type="button" @click="resetForm">Cancel</button>
        </div>
      </form>
      <p v-if="testResult?.ok" class="notice">Connected - {{ testResult.width }}x{{ testResult.height }}</p>
      <p v-if="testResult && !testResult.ok" class="error">{{ testResult.error }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </section>

    <section v-if="showHelp" class="card camera-help">
      <h2 class="card-title">Camera Setup Help</h2>
      <p class="section-text">
        RTSP URLs use <code>rtsp://username:password@camera-ip:554/stream-path</code>. Use the local camera login.
        URL-encode special password characters such as <code>@</code> to <code>%40</code> and <code>#</code> to <code>%23</code>.
      </p>

      <div class="table-wrap compact-table responsive-table">
        <table class="table">
          <caption class="sr-only">RTSP templates by camera brand</caption>
          <thead>
            <tr>
              <th scope="col">Brand</th>
              <th scope="col">Main stream URL template</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="tpl in rtspTemplates" :key="tpl.brand">
              <th scope="row">{{ tpl.brand }}</th>
              <td><code>{{ tpl.url }}</code></td>
              <td><button class="btn sm secondary" type="button" @click="useTemplate(tpl.url)">Use</button></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="help-details">
        <details>
          <summary>Hikvision / HiLook / Annke</summary>
          <ol>
            <li>Confirm RTSP and ONVIF are enabled in the camera or NVR network settings.</li>
            <li>Use channel codes such as <code>101</code> for camera 1 main stream and <code>102</code> for sub stream.</li>
            <li>On an NVR, camera 2 main stream is commonly <code>201</code>.</li>
          </ol>
        </details>
        <details>
          <summary>EZVIZ</summary>
          <ol>
            <li>Use <code>admin</code> plus the camera verification code, not the cloud app password.</li>
            <li>Enable local service in EZVIZ Studio and turn off image encryption when RTSP is needed.</li>
          </ol>
        </details>
        <details>
          <summary>Other ONVIF cameras</summary>
          <ol>
            <li>Use discovery above first; it reads the device profile names and stream URLs when the camera supports ONVIF media services.</li>
            <li>Some devices require a separate ONVIF or integration-protocol account.</li>
          </ol>
        </details>
      </div>
    </section>

    <section class="camera-list-section">
      <div class="list-toolbar">
        <div>
          <p class="section-kicker">Configured cameras</p>
          <h2 class="card-title">Active channels and workers</h2>
        </div>
        <div class="segmented-control" role="group" aria-label="Camera filter">
          <button type="button" :class="{ active: cameraFilter === 'active' }" @click="cameraFilter = 'active'">Active</button>
          <button type="button" :class="{ active: cameraFilter === 'all' }" @click="cameraFilter = 'all'">All</button>
        </div>
      </div>

      <div v-if="selectedIds.size" class="action-bar bulk-action-bar">
        <div class="muted-cell">{{ selectedIds.size }} camera{{ selectedIds.size === 1 ? '' : 's' }} selected</div>
        <div class="btn-row">
          <button class="btn sm" type="button" :disabled="bulkRunning || !selectedStartableCount" @click="bulkStart">
            {{ bulkRunning && bulkActionLabel === 'start' ? 'Starting...' : `Start Selected (${selectedStartableCount})` }}
          </button>
          <button class="btn sm secondary" type="button" :disabled="bulkRunning || !selectedStoppableCount" @click="bulkStop">
            {{ bulkRunning && bulkActionLabel === 'stop' ? 'Stopping...' : `Stop Selected (${selectedStoppableCount})` }}
          </button>
          <button class="btn sm danger" type="button" :disabled="bulkRunning" @click="bulkDelete">
            {{ bulkRunning && bulkActionLabel === 'delete' ? 'Deleting...' : `Delete Selected (${selectedIds.size})` }}
          </button>
          <button class="btn sm secondary" type="button" :disabled="bulkRunning" @click="clearSelection">Clear</button>
        </div>
      </div>
      <p v-if="bulkMessage" class="notice">{{ bulkMessage }}</p>

      <div class="table-wrap camera-table responsive-table">
        <table class="table">
          <caption class="sr-only">Configured cameras</caption>
          <thead>
            <tr>
              <th scope="col" class="checkbox-col">
                <input
                  ref="selectAllRef"
                  type="checkbox"
                  :checked="allVisibleSelected"
                  :disabled="bulkRunning || !visibleCameras.length"
                  aria-label="Select all visible cameras"
                  @change="toggleSelectAll"
                />
              </th>
              <th scope="col">Preview</th>
              <th scope="col" class="camera-name-col">Camera</th>
              <th scope="col">Site</th>
              <th scope="col">Source</th>
              <th scope="col">Active</th>
              <th scope="col">Live</th>
              <th scope="col">RTSP</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!visibleCameras.length">
              <td colspan="9" class="empty-row">{{ emptyMessage }}</td>
            </tr>
            <tr v-for="camera in visibleCameras" :key="camera.id" :class="{ 'row-selected': selectedIds.has(camera.id) }">
              <td>
                <input
                  type="checkbox"
                  :checked="selectedIds.has(camera.id)"
                  :disabled="bulkRunning"
                  :aria-label="`Select ${camera.name}`"
                  @change="toggleSelect(camera.id)"
                />
              </td>
              <td>
                <img v-if="thumbnails[camera.id]?.url" class="thumb" :src="thumbnails[camera.id].url" :alt="`Preview of ${camera.name}`" />
                <div v-else class="thumb thumb-placeholder" :title="thumbnails[camera.id]?.error || ''">
                  {{ thumbnails[camera.id]?.loading ? '...' : 'No preview' }}
                </div>
                <button
                  class="btn sm secondary thumb-refresh"
                  type="button"
                  :disabled="thumbnails[camera.id]?.loading"
                  @click="loadThumbnail(camera, { probe: true })"
                >
                  {{ thumbnails[camera.id]?.loading ? 'Refreshing...' : 'Refresh' }}
                </button>
              </td>
              <th scope="row" class="camera-name-col">
                <div class="primary-cell">{{ camera.name }}</div>
                <div v-if="camera.last_error" class="muted-cell danger-text">{{ camera.last_error }}</div>
              </th>
              <td>
                <div>{{ camera.branch || '-' }}</div>
                <div class="muted-cell">{{ camera.location || '-' }}</div>
              </td>
              <td><span class="badge" :class="camera.source === 'onvif' ? 'info' : ''">{{ camera.source === 'onvif' ? 'ONVIF' : 'Manual' }}</span></td>
              <td><span class="badge dot" :class="camera.enabled ? 'success' : ''">{{ camera.enabled ? 'Active' : 'Disabled' }}</span></td>
              <td><span class="badge dot" :class="statusClass(camera.status)">{{ statusLabel(camera.status) }}</span></td>
              <td class="truncate" :title="camera.rtsp_url">{{ maskRtsp(camera.rtsp_url) }}</td>
              <td>
                <div class="btn-row action-buttons">
                  <button class="btn sm secondary" type="button" @click="edit(camera)">Edit</button>
                  <button class="btn sm" type="button" :disabled="!canStartLive(camera)" @click="start(camera)">
                    {{ busyActions.get(camera.id) === 'start' ? 'Starting...' : 'Start Live' }}
                  </button>
                  <button class="btn sm secondary" type="button" :disabled="!canStopLive(camera)" @click="stop(camera)">
                    {{ busyActions.get(camera.id) === 'stop' ? 'Stopping...' : 'Stop Live' }}
                  </button>
                  <button class="btn sm danger" type="button" :disabled="isBusy(camera)" @click="remove(camera)">
                    {{ busyActions.get(camera.id) === 'delete' ? 'Deleting...' : 'Delete' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="camera-card-list">
        <p v-if="!visibleCameras.length" class="empty-row">{{ emptyMessage }}</p>
        <article v-for="camera in visibleCameras" :key="camera.id" class="camera-mobile-card" :class="{ 'row-selected': selectedIds.has(camera.id) }">
          <div class="mobile-card-head">
            <label class="checkbox-label mobile-select">
              <input
                type="checkbox"
                :checked="selectedIds.has(camera.id)"
                :disabled="bulkRunning"
                :aria-label="`Select ${camera.name}`"
                @change="toggleSelect(camera.id)"
              />
              <div>
                <h3>{{ camera.name }}</h3>
                <p>{{ [camera.branch, camera.location].filter(Boolean).join(' - ') || 'No site set' }}</p>
              </div>
            </label>
            <span class="badge dot" :class="statusClass(camera.status)">{{ statusLabel(camera.status) }}</span>
          </div>
          <div class="mobile-thumb-row">
            <img v-if="thumbnails[camera.id]?.url" class="thumb" :src="thumbnails[camera.id].url" :alt="`Preview of ${camera.name}`" />
            <div v-else class="thumb thumb-placeholder" :title="thumbnails[camera.id]?.error || ''">
              {{ thumbnails[camera.id]?.loading ? '...' : 'No preview' }}
            </div>
            <button
              class="btn sm secondary"
              type="button"
              :disabled="thumbnails[camera.id]?.loading"
              @click="loadThumbnail(camera, { probe: true })"
            >
              {{ thumbnails[camera.id]?.loading ? 'Refreshing...' : 'Refresh' }}
            </button>
          </div>
          <dl class="detail-grid">
            <div><dt>Source</dt><dd>{{ camera.source === 'onvif' ? 'ONVIF' : 'Manual' }}</dd></div>
            <div><dt>Active</dt><dd>{{ camera.enabled ? 'Active' : 'Disabled' }}</dd></div>
            <div><dt>RTSP</dt><dd class="truncate">{{ maskRtsp(camera.rtsp_url) }}</dd></div>
            <div v-if="camera.last_error"><dt>Error</dt><dd class="danger-text">{{ camera.last_error }}</dd></div>
          </dl>
          <div class="btn-row action-buttons">
            <button class="btn sm secondary" type="button" @click="edit(camera)">Edit</button>
            <button class="btn sm" type="button" :disabled="!canStartLive(camera)" @click="start(camera)">
              {{ busyActions.get(camera.id) === 'start' ? 'Starting...' : 'Start Live' }}
            </button>
            <button class="btn sm secondary" type="button" :disabled="!canStopLive(camera)" @click="stop(camera)">
              {{ busyActions.get(camera.id) === 'stop' ? 'Stopping...' : 'Stop Live' }}
            </button>
            <button class="btn sm danger" type="button" :disabled="isBusy(camera)" @click="remove(camera)">
              {{ busyActions.get(camera.id) === 'delete' ? 'Deleting...' : 'Delete' }}
            </button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
type Camera = {
  id: string
  name: string
  branch?: string | null
  location?: string | null
  rtsp_url: string
  enabled: boolean
  ai_enabled: boolean
  worker_running?: boolean
  source?: 'manual' | 'onvif'
  status: string
  last_error?: string | null
}

type ThumbnailState = {
  url?: string
  loading: boolean
  error?: string
}

type BulkAction = 'start' | 'stop' | 'delete'
type SnapshotResponse = { ok: boolean; thumbnail?: string; error?: string; source?: string }

const { apiFetch } = useApi()
const cameras = ref<Camera[]>([])
const error = ref('')
const showHelp = ref(false)
const loading = ref(false)
const saving = ref(false)
const cameraFilter = ref<'active' | 'all'>('active')
const form = reactive({ name: '', branch: '', location: '', rtsp_url: '', enabled: true })
const editingId = ref<string | null>(null)
const testing = ref(false)
const testResult = ref<{ ok: boolean; width?: number; height?: number; error?: string } | null>(null)

const busyActions = reactive(new Map<string, BulkAction>())
const thumbnails = reactive<Record<string, ThumbnailState>>({})
const selectedIds = reactive(new Set<string>())
const selectAllRef = ref<HTMLInputElement | null>(null)
const bulkRunning = ref(false)
const bulkActionLabel = ref<BulkAction | null>(null)
const bulkMessage = ref('')

const rtspTemplates = [
  { brand: 'Hikvision / HiLook / Annke', url: 'rtsp://user:pass@CAMERA_IP:554/Streaming/Channels/101' },
  { brand: 'EZVIZ', url: 'rtsp://admin:VERIFY_CODE@CAMERA_IP:554/h264/ch1/main/av_stream' },
  { brand: 'Dahua / Imou / Amcrest', url: 'rtsp://user:pass@CAMERA_IP:554/cam/realmonitor?channel=1&subtype=0' },
  { brand: 'TP-Link Tapo / VIGI', url: 'rtsp://user:pass@CAMERA_IP:554/stream1' },
  { brand: 'Reolink', url: 'rtsp://user:pass@CAMERA_IP:554/h264Preview_01_main' },
  { brand: 'Uniview (UNV)', url: 'rtsp://user:pass@CAMERA_IP:554/unicast/c1/s0/live' },
  { brand: 'Axis', url: 'rtsp://user:pass@CAMERA_IP:554/axis-media/media.amp' }
]

const runningStatuses = new Set(['starting', 'connecting', 'running', 'reconnecting'])

const visibleCameras = computed(() => {
  if (cameraFilter.value === 'active') return cameras.value.filter(camera => camera.enabled)
  return cameras.value
})

const stats = computed(() => ({
  total: cameras.value.length,
  enabled: cameras.value.filter(camera => camera.enabled).length,
  running: cameras.value.filter(camera => camera.status === 'running').length,
  needsAttention: cameras.value.filter(camera => camera.status === 'error' || camera.last_error).length
}))

const emptyMessage = computed(() => {
  if (!cameras.value.length) return 'No cameras yet. Add your first camera above.'
  return 'No active cameras match this view. Switch to All to see disabled cameras.'
})

const allVisibleSelected = computed(() =>
  visibleCameras.value.length > 0 && visibleCameras.value.every(camera => selectedIds.has(camera.id))
)
const someVisibleSelected = computed(() =>
  visibleCameras.value.some(camera => selectedIds.has(camera.id))
)
const selectedCameras = computed(() => cameras.value.filter(camera => selectedIds.has(camera.id)))
const selectedStartableCount = computed(() => selectedCameras.value.filter(canStartLive).length)
const selectedStoppableCount = computed(() => selectedCameras.value.filter(canStopLive).length)

watchEffect(() => {
  if (selectAllRef.value) {
    selectAllRef.value.indeterminate = someVisibleSelected.value && !allVisibleSelected.value
  }
})

const toggleSelectAll = () => {
  if (allVisibleSelected.value) {
    visibleCameras.value.forEach(camera => selectedIds.delete(camera.id))
  } else {
    visibleCameras.value.forEach(camera => selectedIds.add(camera.id))
  }
}

const toggleSelect = (id: string) => {
  if (selectedIds.has(id)) selectedIds.delete(id)
  else selectedIds.add(id)
}

const clearSelection = () => selectedIds.clear()

const useTemplate = (url: string) => {
  form.rtsp_url = url
  document.getElementById('manual-camera-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const resetForm = () => {
  editingId.value = null
  testResult.value = null
  Object.assign(form, { name: '', branch: '', location: '', rtsp_url: '', enabled: true })
}

const edit = (camera: Camera) => {
  error.value = ''
  testResult.value = null
  editingId.value = camera.id
  Object.assign(form, {
    name: camera.name || '',
    branch: camera.branch || '',
    location: camera.location || '',
    rtsp_url: camera.rtsp_url || '',
    enabled: camera.enabled !== false
  })
  document.getElementById('manual-camera-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const statusClass = (status: string) => {
  if (status === 'running') return 'success'
  if (status === 'connecting' || status === 'starting' || status === 'reconnecting') return 'warning'
  if (status === 'error') return 'danger'
  return ''
}

const statusLabel = (status: string) => {
  if (!status) return 'Offline'
  if (status === 'running') return 'Live'
  return status.replace(/_/g, ' ')
}

const maskRtsp = (url: string) => {
  return url.replace(/(rtsp:\/\/[^:/@]+:)([^@]+)(@)/i, '$1***$3')
}

const isBusy = (camera: Camera) => busyActions.has(camera.id)
function canStartLive(camera: Camera) {
  return camera.enabled && !runningStatuses.has(camera.status) && !isBusy(camera)
}
function canStopLive(camera: Camera) {
  return runningStatuses.has(camera.status) && !isBusy(camera)
}

const loadThumbnail = async (camera: Camera, options: { probe?: boolean } = {}) => {
  const state = thumbnails[camera.id] || (thumbnails[camera.id] = { loading: false })
  state.loading = true
  state.error = undefined
  try {
    const path = `/cameras/${camera.id}/snapshot${options.probe ? '?probe=true' : ''}`
    const result = await apiFetch<SnapshotResponse>(path)
    if (result.ok && result.thumbnail) {
      state.url = result.thumbnail
    } else if (!result.ok) {
      state.error = result.error || 'No preview available'
    }
  } catch (e: any) {
    state.error = e?.data?.detail || e.message || 'Could not load preview.'
  } finally {
    state.loading = false
  }
}

const testConnection = async () => {
  if (!form.rtsp_url) {
    error.value = 'Enter an RTSP URL first.'
    return
  }
  testing.value = true
  testResult.value = null
  error.value = ''
  try {
    testResult.value = await apiFetch('/cameras/test-stream', { method: 'POST', body: { rtsp_url: form.rtsp_url, timeout_ms: 7000 } })
  } catch (e: any) {
    testResult.value = { ok: false, error: e?.data?.detail || e.message || 'Test failed' }
  } finally {
    testing.value = false
  }
}

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    cameras.value = await apiFetch<Camera[]>('/cameras')
    const validIds = new Set(cameras.value.map(camera => camera.id))
    for (const id of Array.from(selectedIds)) {
      if (!validIds.has(id)) selectedIds.delete(id)
    }
    for (const id of Object.keys(thumbnails)) {
      if (!validIds.has(id)) delete thumbnails[id]
    }
    for (const camera of cameras.value) {
      if (!thumbnails[camera.id]) thumbnails[camera.id] = { loading: false }
      // Only auto-refresh cameras already known to be live - fetching a thumbnail for a
      // stopped camera means a real RTSP probe (see loadThumbnail/backend snapshot route),
      // and firing that for every stopped channel on every list load/refresh would hammer
      // the NVR with dozens of simultaneous connections. Stopped cameras get a manual
      // "Refresh" button instead.
      if (camera.status === 'running') loadThumbnail(camera)
    }
  } catch (e: any) {
    error.value = e?.data?.detail || e.message || 'Could not load cameras.'
  } finally {
    loading.value = false
  }
}

const saveCamera = async () => {
  error.value = ''
  saving.value = true
  const payload = {
    name: form.name.trim(),
    branch: form.branch.trim() || undefined,
    location: form.location.trim() || undefined,
    rtsp_url: form.rtsp_url.trim(),
    enabled: form.enabled
  }
  try {
    if (editingId.value) {
      await apiFetch(`/cameras/${editingId.value}`, { method: 'PUT', body: payload })
    } else {
      await apiFetch('/cameras', { method: 'POST', body: payload })
    }
    resetForm()
    await load()
  } catch (e: any) {
    error.value = e?.data?.detail || e.message || 'Could not save camera.'
  } finally {
    saving.value = false
  }
}

const performCameraAction = async (
  camera: Camera,
  action: BulkAction,
  task: () => Promise<void>
): Promise<{ ok: true } | { ok: false; error: string }> => {
  busyActions.set(camera.id, action)
  try {
    await task()
    return { ok: true }
  } catch (e: any) {
    const actionLabel = action === 'start' ? 'start live view' : action === 'stop' ? 'stop live view' : 'delete camera'
    return { ok: false, error: e?.data?.detail || e.message || `Could not ${actionLabel}.` }
  } finally {
    busyActions.delete(camera.id)
  }
}

const start = async (camera: Camera) => {
  if (!camera.enabled) {
    error.value = 'Enable this camera before starting live view.'
    return
  }
  error.value = ''
  const result = await performCameraAction(camera, 'start', async () => {
    await apiFetch(`/cameras/${camera.id}/start`, { method: 'POST' })
  })
  if (!result.ok) error.value = result.error
  await load()
}

const stop = async (camera: Camera) => {
  error.value = ''
  const result = await performCameraAction(camera, 'stop', async () => {
    await apiFetch(`/cameras/${camera.id}/stop`, { method: 'POST' })
  })
  if (!result.ok) error.value = result.error
  await load()
}

const remove = async (camera: Camera) => {
  if (!confirm(`Delete camera "${camera.name}"?`)) return
  error.value = ''
  const result = await performCameraAction(camera, 'delete', async () => {
    await apiFetch(`/cameras/${camera.id}`, { method: 'DELETE' })
    if (editingId.value === camera.id) resetForm()
  })
  if (!result.ok) error.value = result.error
  await load()
}

const runBulk = async (
  label: string,
  actionKey: BulkAction,
  targets: Camera[],
  task: (camera: Camera) => Promise<void>
) => {
  if (!targets.length) return
  bulkRunning.value = true
  bulkActionLabel.value = actionKey
  bulkMessage.value = ''
  error.value = ''
  const results: { camera: Camera; ok: boolean; error?: string }[] = []
  try {
    let next = 0
    const workerCount = Math.min(3, targets.length)
    const workers = Array.from({ length: workerCount }, async () => {
      while (next < targets.length) {
        const camera = targets[next]
        next += 1
        const result = await performCameraAction(camera, actionKey, () => task(camera))
        results.push({ camera, ok: result.ok, error: !result.ok ? result.error : undefined })
      }
    })
    await Promise.all(workers)
  } finally {
    bulkRunning.value = false
    bulkActionLabel.value = null
  }
  await load()
  const failed = results.filter(r => !r.ok)
  bulkMessage.value = failed.length
    ? `${label}: ${results.length - failed.length} of ${results.length} succeeded. Failed: ${failed.map(f => `${f.camera.name} (${f.error})`).join('; ')}`
    : `${label}: ${results.length} of ${results.length} succeeded.`
}

const bulkStart = () => {
  const targets = selectedCameras.value.filter(canStartLive)
  if (!targets.length) {
    error.value = 'None of the selected cameras can be started (already live, disabled, or busy).'
    return
  }
  return runBulk('Start selected', 'start', targets, async (camera) => {
    await apiFetch(`/cameras/${camera.id}/start`, { method: 'POST' })
  })
}

const bulkStop = () => {
  const targets = selectedCameras.value.filter(canStopLive)
  if (!targets.length) {
    error.value = 'None of the selected cameras are currently live.'
    return
  }
  return runBulk('Stop selected', 'stop', targets, async (camera) => {
    await apiFetch(`/cameras/${camera.id}/stop`, { method: 'POST' })
  })
}

const bulkDelete = () => {
  const targets = selectedCameras.value.filter(camera => !isBusy(camera))
  if (!targets.length) return
  if (!confirm(`Delete ${targets.length} selected camera${targets.length === 1 ? '' : 's'}? This cannot be undone.`)) return
  return runBulk('Delete selected', 'delete', targets, async (camera) => {
    await apiFetch(`/cameras/${camera.id}`, { method: 'DELETE' })
    if (editingId.value === camera.id) resetForm()
  })
}

onMounted(load)
</script>
