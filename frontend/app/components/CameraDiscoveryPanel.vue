<template>
  <div class="card" style="margin-bottom: 1rem;">
    <h2 class="card-title">Discover Cameras (ONVIF)</h2>
    <p style="margin: 0 0 0.85rem; color: #334155; font-size: 0.9rem;">
      Connect to a camera or NVR and pick channels from a list instead of typing RTSP URLs. Works with most
      Hikvision, Dahua, Uniview, Axis, Reolink, and other ONVIF-compliant devices/NVRs.
    </p>

    <div class="btn-row" style="margin-bottom: 0.85rem;">
      <button class="btn secondary" type="button" :disabled="scanning" @click="scanNetwork">
        {{ scanning ? 'Scanning...' : 'Scan Network' }}
      </button>
      <span class="hint" style="align-self: center;">Auto-scan is best-effort - if it finds nothing, enter the IP directly below.</span>
    </div>
    <p v-if="scanNotice" class="notice" style="margin-bottom: 0.85rem;">{{ scanNotice }}</p>

    <div v-if="scanResults.length" class="table-wrap" style="box-shadow: none; margin-bottom: 0.85rem;">
      <table class="table">
        <thead><tr><th>Address</th><th>Hint</th><th></th></tr></thead>
        <tbody>
          <tr v-for="device in scanResults" :key="`${device.host}:${device.port}`">
            <td>{{ device.host }}:{{ device.port }}</td>
            <td>{{ device.hint || '-' }}</td>
            <td><button class="btn sm secondary" type="button" @click="useDevice(device)">Use</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <form class="form-grid" @submit.prevent="fetchChannels">
      <div><label class="label">Camera / NVR IP</label><input v-model="connectForm.host" class="input" placeholder="192.168.1.100" required /></div>
      <div><label class="label">Port</label><input v-model.number="connectForm.port" type="number" class="input" placeholder="80" /></div>
      <div><label class="label">Username</label><input v-model="connectForm.username" class="input" placeholder="admin" /></div>
      <div><label class="label">Password</label><input v-model="connectForm.password" type="password" class="input" /></div>
      <div class="btn-row">
        <button class="btn" type="submit" :disabled="probing">{{ probing ? 'Connecting...' : 'Fetch Channels' }}</button>
      </div>
    </form>
    <p v-if="probeError" class="error">{{ probeError }}</p>

    <div v-if="channelRows.length" style="margin-top: 1rem;">
      <p style="margin: 0 0 0.6rem; font-size: 0.9rem; color: #334155;">
        <strong>{{ probeResult?.manufacturer || 'Device' }} {{ probeResult?.model || '' }}</strong>
        - select the channel(s) to add:
      </p>
      <div class="form-grid" style="margin-bottom: 0.6rem;">
        <div><label class="label">Branch (applied to all selected)</label><input v-model="sharedBranch" class="input" /></div>
        <div><label class="label">Location (applied to all selected)</label><input v-model="sharedLocation" class="input" /></div>
      </div>
      <div class="table-wrap" style="box-shadow: none;">
        <table class="table">
          <thead><tr><th></th><th>Name</th><th>Resolution</th><th>Codec</th><th>Status</th><th></th></tr></thead>
          <tbody>
            <tr v-for="row in channelRows" :key="row.profile_token || row.name">
              <td><input type="checkbox" v-model="row.selected" :disabled="!row.rtsp_url" /></td>
              <td><input v-model="row.name" class="input" style="min-width: 180px;" /></td>
              <td>{{ row.resolution || '-' }}</td>
              <td>{{ row.encoding || '-' }}</td>
              <td>
                <span v-if="row.error" class="badge danger">{{ row.error }}</span>
                <span v-else-if="row.testResult?.ok" class="badge success">OK {{ row.testResult.width }}x{{ row.testResult.height }}</span>
                <span v-else-if="row.testResult && !row.testResult.ok" class="badge danger">{{ row.testResult.error }}</span>
                <span v-else class="badge">Not tested</span>
              </td>
              <td>
                <button class="btn sm secondary" type="button" :disabled="!row.rtsp_url || row.testing" @click="testChannel(row)">
                  {{ row.testing ? 'Testing...' : 'Test' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="btn-row" style="margin-top: 0.85rem;">
        <button class="btn" type="button" :disabled="adding" @click="addSelected">
          {{ adding ? 'Adding...' : 'Add Selected Channels' }}
        </button>
      </div>
      <p v-if="addError" class="error">{{ addError }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const emit = defineEmits<{ added: [] }>()

const scanning = ref(false)
const scanResults = ref<any[]>([])
const scanNotice = ref('')

const connectForm = reactive({ host: '', port: 80, username: '', password: '' })
const probing = ref(false)
const probeError = ref('')
const probeResult = ref<any | null>(null)
const channelRows = ref<any[]>([])

const sharedBranch = ref('')
const sharedLocation = ref('')
const adding = ref(false)
const addError = ref('')

const scanNetwork = async () => {
  scanning.value = true
  scanNotice.value = ''
  scanResults.value = []
  try {
    const res = await apiFetch<{ devices: any[] }>('/cameras/discover', { method: 'POST', body: { timeout_seconds: 4 } })
    scanResults.value = res.devices || []
    if (!scanResults.value.length) {
      scanNotice.value = 'No devices auto-discovered. This is common when the AI service runs in a container without LAN broadcast access - enter the camera/NVR IP directly below.'
    }
  } catch (e: any) {
    scanNotice.value = e?.data?.detail || e?.message || 'Scan failed - enter the camera/NVR IP directly below.'
  } finally {
    scanning.value = false
  }
}

const useDevice = (device: any) => {
  connectForm.host = device.host
  connectForm.port = device.port || 80
}

const fetchChannels = async () => {
  probing.value = true
  probeError.value = ''
  probeResult.value = null
  channelRows.value = []
  try {
    const res = await apiFetch<any>('/cameras/probe', {
      method: 'POST',
      body: {
        host: connectForm.host,
        port: connectForm.port || 80,
        username: connectForm.username,
        password: connectForm.password
      }
    })
    probeResult.value = res
    channelRows.value = (res.channels || []).map((ch: any, i: number) => ({
      selected: !ch.error && !!ch.rtsp_url,
      name: `${res.model || res.manufacturer || connectForm.host} - ${ch.name || 'Channel ' + (i + 1)}`,
      profile_token: ch.profile_token,
      resolution: ch.resolution,
      encoding: ch.encoding,
      rtsp_url: ch.rtsp_url,
      error: ch.error,
      testResult: null as any,
      testing: false
    }))
  } catch (e: any) {
    probeError.value = e?.data?.detail || e?.message || 'Could not connect to that IP with the given credentials.'
  } finally {
    probing.value = false
  }
}

const testChannel = async (row: any) => {
  row.testing = true
  try {
    row.testResult = await apiFetch('/cameras/test-stream', { method: 'POST', body: { rtsp_url: row.rtsp_url } })
  } catch (e: any) {
    row.testResult = { ok: false, error: e?.data?.detail || e?.message || 'Test failed' }
  } finally {
    row.testing = false
  }
}

const addSelected = async () => {
  const rows = channelRows.value.filter(row => row.selected && row.rtsp_url)
  if (!rows.length) {
    addError.value = 'Select at least one channel with a valid stream URL.'
    return
  }
  adding.value = true
  addError.value = ''
  try {
    for (const row of rows) {
      await apiFetch('/cameras', {
        method: 'POST',
        body: {
          name: row.name,
          branch: sharedBranch.value || undefined,
          location: sharedLocation.value || undefined,
          rtsp_url: row.rtsp_url,
          enabled: true,
          source: 'onvif',
          onvif_host: connectForm.host,
          onvif_profile_token: row.profile_token
        }
      })
    }
    channelRows.value = []
    probeResult.value = null
    emit('added')
  } catch (e: any) {
    addError.value = e?.data?.detail || e?.message || 'Could not add the selected cameras.'
  } finally {
    adding.value = false
  }
}
</script>
