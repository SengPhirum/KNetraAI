<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Camera Management</h1>
        <p class="page-subtitle">Connect RTSP cameras or NVR channels and control the AI workers.</p>
      </div>
      <button class="btn secondary" type="button" @click="showHelp = !showHelp">{{ showHelp ? 'Hide Camera Setup Help' : 'Camera Setup Help' }}</button>
    </div>

    <CameraDiscoveryPanel @added="load" />

    <div class="card" style="margin-bottom: 1rem;">
      <h2 class="card-title">{{ editingId ? 'Edit Camera' : 'Add Camera Manually' }}</h2>
      <form class="form-grid" @submit.prevent="saveCamera">
        <div><label class="label">Name</label><input v-model="form.name" class="input" required /></div>
        <div><label class="label">Branch</label><input v-model="form.branch" class="input" /></div>
        <div><label class="label">Location</label><input v-model="form.location" class="input" /></div>
        <div class="full-row">
          <label class="label">RTSP URL</label>
          <input v-model="form.rtsp_url" class="input" placeholder="rtsp://user:pass@ip:554/stream" required />
          <small class="hint">Not sure about the URL? Open Camera Setup Help for brand templates (Hikvision, EZVIZ, Dahua, ...), or use Discover Cameras above to pick a channel instead.</small>
        </div>
        <div class="btn-row">
          <button class="btn" type="submit">{{ editingId ? 'Save Camera' : 'Add Camera' }}</button>
          <button class="btn secondary" type="button" :disabled="testing" @click="testConnection">{{ testing ? 'Testing...' : 'Test Connection' }}</button>
          <button v-if="editingId" class="btn secondary" type="button" @click="resetForm">Cancel</button>
        </div>
      </form>
      <p v-if="testResult?.ok" class="notice">Connected - {{ testResult.width }}x{{ testResult.height }}</p>
      <p v-if="testResult && !testResult.ok" class="error">{{ testResult.error }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <div v-if="showHelp" class="card" style="margin-bottom: 1rem;">
      <h2 class="card-title">Camera Setup Help</h2>
      <p style="margin: 0 0 0.85rem; color: #334155; font-size: 0.9rem;">
        Every RTSP URL follows <code>rtsp://username:password@camera-ip:554/stream-path</code>.
        Use your camera's local login (not the cloud app account). If the password contains special
        characters, URL-encode them (<code>@</code> → <code>%40</code>, <code>#</code> → <code>%23</code>).
        Test the URL in VLC (Media → Open Network Stream) before adding it here.
      </p>

      <div class="table-wrap" style="box-shadow: none; margin-bottom: 0.85rem;">
        <table class="table">
          <thead><tr><th>Brand</th><th>Main stream URL template</th><th></th></tr></thead>
          <tbody>
            <tr v-for="tpl in rtspTemplates" :key="tpl.brand">
              <td style="white-space: nowrap;">{{ tpl.brand }}</td>
              <td><code>{{ tpl.url }}</code></td>
              <td><button class="btn sm secondary" type="button" @click="useTemplate(tpl.url)">Use</button></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div style="display: grid; gap: 0.5rem; color: #334155; font-size: 0.9rem;">
        <details>
          <summary style="cursor: pointer; font-weight: 700;">Hikvision - step by step</summary>
          <ol style="margin: 0.5rem 0 0; padding-left: 1.25rem; line-height: 1.6;">
            <li>Find the camera IP with the SADP tool or your router's client list; activate the camera if it is new.</li>
            <li>In the camera web page, confirm RTSP is enabled (Configuration → Network → Advanced → Integration Protocol) and port is 554.</li>
            <li>Set RTSP Authentication to digest/basic (Configuration → System → Security → Authentication).</li>
            <li>Channel code = channel + stream: main stream of camera 1 is <code>101</code>, sub stream <code>102</code>. On an NVR, camera 2 main stream is <code>201</code>.</li>
          </ol>
        </details>
        <details>
          <summary style="cursor: pointer; font-weight: 700;">EZVIZ - step by step</summary>
          <ol style="margin: 0.5rem 0 0; padding-left: 1.25rem; line-height: 1.6;">
            <li>Username is <code>admin</code>; the password is the 6-character <strong>verification code</strong> printed on the camera sticker (not your EZVIZ app password).</li>
            <li>Enable RTSP/local service via the EZVIZ Studio PC app (Device Settings → Advanced → Local Service) - some newer models ship with it off.</li>
            <li>Turn off Image Encryption in the EZVIZ app (Settings → Privacy), otherwise the stream is scrambled.</li>
            <li>Some cloud-only models have no RTSP; if VLC cannot connect, check your model or pull the stream through an NVR instead.</li>
          </ol>
        </details>
        <details>
          <summary style="cursor: pointer; font-weight: 700;">Other / unknown brand (ONVIF)</summary>
          <ol style="margin: 0.5rem 0 0; padding-left: 1.25rem; line-height: 1.6;">
            <li>Run ONVIF Device Manager (free, Windows) on the same network - it discovers most IP cameras and shows the exact RTSP URI under Live video.</li>
            <li>Or look up your model in the iSpy camera connection database (ispyconnect.com/cameras).</li>
            <li>TP-Link Tapo: create a separate Camera Account in the Tapo app first (Settings → Advanced → Camera Account).</li>
          </ol>
        </details>
        <p style="margin: 0;">Full brand guides and troubleshooting: see <strong>docs/user-manual-and-configuration.md</strong>, section 6.</p>
      </div>
    </div>

    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Name</th><th>Branch</th><th>Location</th><th>Source</th><th>Status</th><th>RTSP</th><th>Actions</th></tr></thead>
        <tbody>
          <tr v-if="!cameras.length"><td colspan="7" class="empty-row">No cameras yet. Add your first camera above.</td></tr>
          <tr v-for="camera in cameras" :key="camera.id">
            <td style="font-weight: 600;">{{ camera.name }}</td>
            <td>{{ camera.branch || '-' }}</td>
            <td>{{ camera.location || '-' }}</td>
            <td><span class="badge" :class="camera.source === 'onvif' ? 'info' : ''">{{ camera.source === 'onvif' ? 'ONVIF' : 'Manual' }}</span></td>
            <td><span class="badge dot" :class="statusClass(camera.status)">{{ camera.status }}</span></td>
            <td class="truncate" :title="camera.rtsp_url">{{ camera.rtsp_url }}</td>
            <td>
              <div class="btn-row">
                <button class="btn sm secondary" @click="edit(camera)">Edit</button>
                <button class="btn sm" @click="start(camera.id)">Start</button>
                <button class="btn sm secondary" @click="stop(camera.id)">Stop</button>
                <button class="btn sm danger" @click="remove(camera.id)">Delete</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const cameras = ref<any[]>([])
const error = ref('')
const showHelp = ref(false)
const form = reactive({ name: '', branch: '', location: '', rtsp_url: '' })
const editingId = ref<string | null>(null)
const testing = ref(false)
const testResult = ref<{ ok: boolean; width?: number; height?: number; error?: string } | null>(null)

const rtspTemplates = [
  { brand: 'Hikvision / HiLook / Annke', url: 'rtsp://user:pass@CAMERA_IP:554/Streaming/Channels/101' },
  { brand: 'EZVIZ', url: 'rtsp://admin:VERIFY_CODE@CAMERA_IP:554/h264/ch1/main/av_stream' },
  { brand: 'Dahua / Imou / Amcrest', url: 'rtsp://user:pass@CAMERA_IP:554/cam/realmonitor?channel=1&subtype=0' },
  { brand: 'TP-Link Tapo / VIGI', url: 'rtsp://user:pass@CAMERA_IP:554/stream1' },
  { brand: 'Reolink', url: 'rtsp://user:pass@CAMERA_IP:554/h264Preview_01_main' },
  { brand: 'Uniview (UNV)', url: 'rtsp://user:pass@CAMERA_IP:554/unicast/c1/s0/live' },
  { brand: 'Axis', url: 'rtsp://user:pass@CAMERA_IP:554/axis-media/media.amp' }
]

const useTemplate = (url: string) => {
  form.rtsp_url = url
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const resetForm = () => {
  editingId.value = null
  testResult.value = null
  Object.assign(form, { name: '', branch: '', location: '', rtsp_url: '' })
}

const edit = (camera: any) => {
  error.value = ''
  testResult.value = null
  editingId.value = camera.id
  Object.assign(form, {
    name: camera.name || '',
    branch: camera.branch || '',
    location: camera.location || '',
    rtsp_url: camera.rtsp_url || ''
  })
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const statusClass = (status: string) => {
  if (status === 'running') return 'success'
  if (status === 'connecting' || status === 'starting' || status === 'reconnecting') return 'warning'
  if (status === 'error') return 'danger'
  return ''
}

const testConnection = async () => {
  if (!form.rtsp_url) { error.value = 'Enter an RTSP URL first.'; return }
  testing.value = true
  testResult.value = null
  error.value = ''
  try {
    testResult.value = await apiFetch('/cameras/test-stream', { method: 'POST', body: { rtsp_url: form.rtsp_url } })
  } catch (e: any) {
    testResult.value = { ok: false, error: e?.data?.detail || e.message }
  } finally {
    testing.value = false
  }
}

const load = async () => { cameras.value = await apiFetch('/cameras') }
const saveCamera = async () => {
  error.value = ''
  try {
    if (editingId.value) {
      await apiFetch(`/cameras/${editingId.value}`, { method: 'PUT', body: form })
    } else {
      await apiFetch('/cameras', { method: 'POST', body: form })
    }
    resetForm()
    await load()
  } catch (e: any) { error.value = e?.data?.detail || e.message }
}
const start = async (id: string) => {
  error.value = ''
  try {
    await apiFetch(`/cameras/${id}/start`, { method: 'POST' })
    await load()
  } catch (e: any) { error.value = e?.data?.detail || e.message }
}
const stop = async (id: string) => {
  error.value = ''
  try {
    await apiFetch(`/cameras/${id}/stop`, { method: 'POST' })
    await load()
  } catch (e: any) { error.value = e?.data?.detail || e.message }
}
const remove = async (id: string) => {
  if (!confirm('Delete camera?')) return
  error.value = ''
  try {
    await apiFetch(`/cameras/${id}`, { method: 'DELETE' })
    if (editingId.value === id) resetForm()
    await load()
  } catch (e: any) { error.value = e?.data?.detail || e.message }
}
onMounted(load)
</script>
