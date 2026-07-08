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

      <div class="table-wrap camera-table responsive-table">
        <table class="table">
          <caption class="sr-only">Configured cameras</caption>
          <thead>
            <tr>
              <th scope="col">Camera</th>
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
              <td colspan="7" class="empty-row">{{ emptyMessage }}</td>
            </tr>
            <tr v-for="camera in visibleCameras" :key="camera.id">
              <th scope="row">
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
                    {{ busyCameraId === camera.id && busyAction === 'start' ? 'Starting...' : 'Start Live' }}
                  </button>
                  <button class="btn sm secondary" type="button" :disabled="!canStopLive(camera)" @click="stop(camera)">
                    {{ busyCameraId === camera.id && busyAction === 'stop' ? 'Stopping...' : 'Stop Live' }}
                  </button>
                  <button class="btn sm danger" type="button" :disabled="busyCameraId === camera.id" @click="remove(camera)">
                    {{ busyCameraId === camera.id && busyAction === 'delete' ? 'Deleting...' : 'Delete' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="camera-card-list">
        <p v-if="!visibleCameras.length" class="empty-row">{{ emptyMessage }}</p>
        <article v-for="camera in visibleCameras" :key="camera.id" class="camera-mobile-card">
          <div class="mobile-card-head">
            <div>
              <h3>{{ camera.name }}</h3>
              <p>{{ [camera.branch, camera.location].filter(Boolean).join(' - ') || 'No site set' }}</p>
            </div>
            <span class="badge dot" :class="statusClass(camera.status)">{{ statusLabel(camera.status) }}</span>
          </div>
          <dl class="detail-grid">
            <div><dt>Source</dt><dd>{{ camera.source === 'onvif' ? 'ONVIF' : 'Manual' }}</dd></div>
            <div><dt>Active</dt><dd>{{ camera.enabled ? 'Active' : 'Disabled' }}</dd></div>
            <div><dt>RTSP</dt><dd class="truncate">{{ maskRtsp(camera.rtsp_url) }}</dd></div>
            <div v-if="camera.last_error"><dt>Error</dt><dd class="danger-text">{{ camera.last_error }}</dd></div>
          </dl>
          <div class="btn-row action-buttons">
            <button class="btn sm secondary" type="button" @click="edit(camera)">Edit</button>
            <button class="btn sm" type="button" :disabled="!canStartLive(camera)" @click="start(camera)">Start Live</button>
            <button class="btn sm secondary" type="button" :disabled="!canStopLive(camera)" @click="stop(camera)">Stop Live</button>
            <button class="btn sm danger" type="button" :disabled="busyCameraId === camera.id" @click="remove(camera)">Delete</button>
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
const busyCameraId = ref<string | null>(null)
const busyAction = ref<'start' | 'stop' | 'delete' | null>(null)

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

const isBusy = (camera: Camera) => busyCameraId.value === camera.id
const canStartLive = (camera: Camera) => camera.enabled && !runningStatuses.has(camera.status) && !isBusy(camera)
const canStopLive = (camera: Camera) => runningStatuses.has(camera.status) && !isBusy(camera)

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

const runCameraAction = async (camera: Camera, action: 'start' | 'stop' | 'delete', task: () => Promise<void>) => {
  error.value = ''
  busyCameraId.value = camera.id
  busyAction.value = action
  try {
    await task()
    await load()
  } catch (e: any) {
    const actionLabel = action === 'start' ? 'start live view' : action === 'stop' ? 'stop live view' : 'delete camera'
    error.value = e?.data?.detail || e.message || `Could not ${actionLabel}.`
  } finally {
    busyCameraId.value = null
    busyAction.value = null
  }
}

const start = async (camera: Camera) => {
  if (!camera.enabled) {
    error.value = 'Enable this camera before starting live view.'
    return
  }
  await runCameraAction(camera, 'start', async () => {
    await apiFetch(`/cameras/${camera.id}/start`, { method: 'POST' })
  })
}

const stop = async (camera: Camera) => {
  await runCameraAction(camera, 'stop', async () => {
    await apiFetch(`/cameras/${camera.id}/stop`, { method: 'POST' })
  })
}

const remove = async (camera: Camera) => {
  if (!confirm(`Delete camera "${camera.name}"?`)) return
  await runCameraAction(camera, 'delete', async () => {
    await apiFetch(`/cameras/${camera.id}`, { method: 'DELETE' })
    if (editingId.value === camera.id) resetForm()
  })
}

onMounted(load)
</script>
