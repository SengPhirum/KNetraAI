<template>
  <section class="card discovery-card">
    <div class="section-heading">
      <div>
        <p class="section-kicker">ONVIF discovery</p>
        <h2 class="card-title">Find active camera channels</h2>
      </div>
      <button class="btn secondary" type="button" :disabled="scanning" @click="scanNetwork">
        {{ scanning ? 'Scanning...' : 'Scan Network' }}
      </button>
    </div>

    <p v-if="scanNotice" class="notice">{{ scanNotice }}</p>

    <div v-if="scanResults.length" class="table-wrap compact-table discovery-results">
      <table class="table">
        <caption class="sr-only">Discovered ONVIF devices</caption>
        <thead>
          <tr>
            <th scope="col">Device</th>
            <th scope="col">Address</th>
            <th scope="col">Hardware</th>
            <th scope="col">Location</th>
            <th scope="col">Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="device in scanResults" :key="`${device.host}:${device.port}`">
            <th scope="row">
              <div class="primary-cell">{{ device.name || device.hint || 'ONVIF device' }}</div>
              <div class="muted-cell">{{ device.types?.join(', ') || 'Network camera/NVR' }}</div>
            </th>
            <td><code>{{ device.host }}:{{ device.port || 80 }}</code></td>
            <td>{{ device.hardware || '-' }}</td>
            <td>{{ device.location || '-' }}</td>
            <td>
              <button class="btn sm secondary" type="button" @click="useDevice(device)">Use</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <form class="form-grid discovery-form" @submit.prevent="fetchChannels">
      <div>
        <label class="label" for="onvif-host">Camera / NVR IP</label>
        <input id="onvif-host" v-model="connectForm.host" class="input" placeholder="192.168.1.100" required />
      </div>
      <div>
        <label class="label" for="onvif-port">Port</label>
        <input id="onvif-port" v-model.number="connectForm.port" type="number" min="1" max="65535" class="input" placeholder="80" />
      </div>
      <div>
        <label class="label" for="onvif-username">Username</label>
        <input id="onvif-username" v-model="connectForm.username" class="input" autocomplete="username" placeholder="admin" />
      </div>
      <div>
        <label class="label" for="onvif-password">Password</label>
        <input id="onvif-password" v-model="connectForm.password" type="password" class="input" autocomplete="current-password" />
      </div>
      <div class="form-actions">
        <button class="btn" type="submit" :disabled="probing || validating">
          {{ probing ? 'Fetching...' : validating ? 'Checking Streams...' : 'Fetch Channels' }}
        </button>
      </div>
    </form>
    <p v-if="probeError" class="error">{{ probeError }}</p>

    <div v-if="probeResult" class="channel-results">
      <div class="channel-summary">
        <div>
          <p class="section-kicker">Fetched device</p>
          <h3>{{ deviceTitle }}</h3>
          <p>
            {{ workingChannelRows.length }} working of {{ channelRows.length }} fetched channels
            <span v-if="hiddenChannelCount">, {{ hiddenChannelCount }} hidden</span>
          </p>
        </div>
        <div class="btn-row channel-tools">
          <button class="btn sm secondary" type="button" :disabled="!workingChannelRows.length" @click="selectAllWorking">Select Working</button>
          <button class="btn sm secondary" type="button" :disabled="!channelRows.length" @click="clearSelection">Clear</button>
          <button class="btn sm secondary" type="button" :class="{ active: showUnavailable }" @click="showUnavailable = !showUnavailable">
            {{ showUnavailable ? 'Working Only' : 'Show Unavailable' }}
          </button>
        </div>
      </div>

      <p v-if="validating" class="notice">Checking streams. Working channels will appear as soon as a frame is readable.</p>
      <p v-else-if="channelRows.length && !workingChannelRows.length" class="error">
        No working streams were found. Show unavailable channels to inspect ONVIF profiles and errors.
      </p>

      <div v-if="workingChannelRows.length" class="form-grid channel-defaults">
        <div>
          <label class="label" for="shared-branch">Branch applied to selected</label>
          <input id="shared-branch" v-model="sharedBranch" class="input" />
        </div>
        <div>
          <label class="label" for="shared-location">Location applied to selected</label>
          <input id="shared-location" v-model="sharedLocation" class="input" />
        </div>
      </div>

      <div v-if="visibleChannelRows.length" class="table-wrap compact-table responsive-table">
        <table class="table">
          <caption class="sr-only">Fetched ONVIF channels</caption>
          <thead>
            <tr>
              <th scope="col">Add</th>
              <th scope="col">Configured Name</th>
              <th scope="col">Stream</th>
              <th scope="col">Profile</th>
              <th scope="col">Video</th>
              <th scope="col">Status</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in visibleChannelRows" :key="rowKey(row)">
              <td>
                <input
                  v-model="row.selected"
                  type="checkbox"
                  :aria-label="`Select ${row.name}`"
                  :disabled="!isWorking(row)"
                />
              </td>
              <th scope="row">
                <input v-model="row.name" class="input dense-input" :disabled="!isWorking(row)" />
                <div class="muted-cell">{{ row.source_name || row.configured_name || '-' }}</div>
              </th>
              <td>
                <span class="badge info">{{ row.stream_label || 'Stream' }}</span>
              </td>
              <td>
                <div>{{ row.profile_name || '-' }}</div>
                <div class="muted-cell">{{ row.profile_token || row.source_token || '-' }}</div>
              </td>
              <td>
                <div>{{ row.resolution || '-' }}</div>
                <div class="muted-cell">{{ row.encoding || '-' }}<span v-if="row.framerate">, {{ row.framerate }} fps</span></div>
              </td>
              <td>
                <span class="badge dot" :class="channelStatusClass(row)">{{ channelStatusText(row) }}</span>
              </td>
              <td>
                <button class="btn sm secondary" type="button" :disabled="!row.rtsp_url || row.testing" @click="testChannel(row)">
                  {{ row.testing ? 'Testing...' : 'Retest' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="visibleChannelRows.length" class="channel-card-list">
        <article v-for="row in visibleChannelRows" :key="rowKey(row)" class="camera-mobile-card">
          <div class="mobile-card-head">
            <label class="checkbox-label">
              <input v-model="row.selected" type="checkbox" :disabled="!isWorking(row)" />
              <span>{{ row.name }}</span>
            </label>
            <span class="badge dot" :class="channelStatusClass(row)">{{ channelStatusText(row) }}</span>
          </div>
          <input v-model="row.name" class="input" :disabled="!isWorking(row)" />
          <dl class="detail-grid">
            <div><dt>Configured</dt><dd>{{ row.source_name || row.configured_name || '-' }}</dd></div>
            <div><dt>Stream</dt><dd>{{ row.stream_label || '-' }}</dd></div>
            <div><dt>Profile</dt><dd>{{ row.profile_name || '-' }}</dd></div>
            <div><dt>Video</dt><dd>{{ row.resolution || '-' }} {{ row.encoding || '' }}</dd></div>
          </dl>
          <button class="btn sm secondary" type="button" :disabled="!row.rtsp_url || row.testing" @click="testChannel(row)">
            {{ row.testing ? 'Testing...' : 'Retest' }}
          </button>
        </article>
      </div>

      <div v-if="workingChannelRows.length" class="action-bar">
        <div class="muted-cell">{{ selectedWorkingCount }} working channel{{ selectedWorkingCount === 1 ? '' : 's' }} selected</div>
        <button class="btn" type="button" :disabled="!canAddSelected" @click="addSelected">
          {{ adding ? 'Adding...' : 'Add Selected Channels' }}
        </button>
      </div>
      <p v-if="addError" class="error">{{ addError }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
type DiscoveryDevice = {
  host: string
  port?: number
  name?: string
  hint?: string
  hardware?: string
  location?: string
  types?: string[]
}

type StreamTestResult = { ok: boolean; width?: number; height?: number; error?: string }

type ChannelRow = {
  selected: boolean
  name: string
  configured_name?: string
  source_name?: string
  profile_name?: string
  encoder_name?: string
  stream_label?: string
  profile_token?: string
  source_token?: string
  resolution?: string
  encoding?: string
  framerate?: number | string
  rtsp_url?: string
  error?: string
  testResult: StreamTestResult | null
  testing: boolean
}

const { apiFetch } = useApi()
const emit = defineEmits<{ added: [] }>()

const scanning = ref(false)
const scanResults = ref<DiscoveryDevice[]>([])
const scanNotice = ref('')

const connectForm = reactive({ host: '', port: 80, username: '', password: '' })
const probing = ref(false)
const validating = ref(false)
const probeError = ref('')
const probeResult = ref<any | null>(null)
const channelRows = ref<ChannelRow[]>([])
const showUnavailable = ref(false)

const sharedBranch = ref('')
const sharedLocation = ref('')
const adding = ref(false)
const addError = ref('')

const deviceTitle = computed(() => {
  if (!probeResult.value) return 'Device'
  return [probeResult.value.manufacturer, probeResult.value.model].filter(Boolean).join(' ') || `${probeResult.value.host}:${probeResult.value.port}`
})

const isWorking = (row: ChannelRow) => Boolean(row.rtsp_url && !row.error && row.testResult?.ok)
const workingChannelRows = computed(() => channelRows.value.filter(isWorking))
const visibleChannelRows = computed(() => showUnavailable.value ? channelRows.value : workingChannelRows.value)
const hiddenChannelCount = computed(() => Math.max(0, channelRows.value.length - workingChannelRows.value.length))
const selectedWorkingCount = computed(() => channelRows.value.filter(row => row.selected && isWorking(row)).length)
const canAddSelected = computed(() => !adding.value && !validating.value && selectedWorkingCount.value > 0)

const rowKey = (row: ChannelRow) => row.profile_token || row.rtsp_url || row.name

const scanNetwork = async () => {
  scanning.value = true
  scanNotice.value = ''
  scanResults.value = []
  try {
    const res = await apiFetch<{ devices: DiscoveryDevice[] }>('/cameras/discover', { method: 'POST', body: { timeout_seconds: 4 } })
    scanResults.value = res.devices || []
    if (!scanResults.value.length) {
      scanNotice.value = 'No ONVIF devices were discovered. Enter the camera or NVR IP directly.'
    }
  } catch (e: any) {
    scanNotice.value = e?.data?.detail || e?.message || 'Scan failed. Enter the camera or NVR IP directly.'
  } finally {
    scanning.value = false
  }
}

const useDevice = (device: DiscoveryDevice) => {
  connectForm.host = device.host
  connectForm.port = device.port || 80
}

const bestChannelName = (ch: any, index: number) => {
  return ch.name || ch.configured_name || ch.source_name || ch.profile_name || `Channel ${index + 1}`
}

const fetchChannels = async () => {
  probing.value = true
  probeError.value = ''
  addError.value = ''
  probeResult.value = null
  channelRows.value = []
  showUnavailable.value = false
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
      selected: false,
      name: bestChannelName(ch, i),
      configured_name: ch.configured_name,
      source_name: ch.source_name,
      profile_name: ch.profile_name,
      encoder_name: ch.encoder_name,
      stream_label: ch.stream_label,
      profile_token: ch.profile_token,
      source_token: ch.source_token,
      resolution: ch.resolution,
      encoding: ch.encoding,
      framerate: ch.framerate,
      rtsp_url: ch.rtsp_url,
      error: ch.error || (!ch.rtsp_url ? 'No RTSP URL returned' : ''),
      testResult: null,
      testing: false
    }))
  } catch (e: any) {
    probeError.value = e?.data?.detail || e?.message || 'Could not connect to that IP with the given credentials.'
  } finally {
    probing.value = false
  }

  if (channelRows.value.some(row => row.rtsp_url && !row.error)) {
    await validateFetchedChannels()
  }
}

const validateFetchedChannels = async () => {
  const rows = channelRows.value.filter(row => row.rtsp_url && !row.error)
  if (!rows.length) return
  validating.value = true
  try {
    let next = 0
    const workerCount = Math.min(3, rows.length)
    const workers = Array.from({ length: workerCount }, async () => {
      while (next < rows.length) {
        const row = rows[next]
        next += 1
        await testChannel(row, true)
      }
    })
    await Promise.all(workers)
    channelRows.value.forEach(row => { row.selected = isWorking(row) })
  } finally {
    validating.value = false
  }
}

const testChannel = async (row: ChannelRow, fromBatch = false) => {
  if (!row.rtsp_url) return
  row.testing = true
  row.testResult = null
  try {
    row.testResult = await apiFetch<StreamTestResult>('/cameras/test-stream', {
      method: 'POST',
      body: { rtsp_url: row.rtsp_url, timeout_ms: fromBatch ? 5000 : 7000 }
    })
    row.selected = Boolean(row.testResult.ok)
  } catch (e: any) {
    row.testResult = { ok: false, error: e?.data?.detail || e?.message || 'Test failed' }
    row.selected = false
  } finally {
    row.testing = false
  }
}

const selectAllWorking = () => {
  channelRows.value.forEach(row => { row.selected = isWorking(row) })
}

const clearSelection = () => {
  channelRows.value.forEach(row => { row.selected = false })
}

const channelStatusClass = (row: ChannelRow) => {
  if (row.testing) return 'warning'
  if (isWorking(row)) return 'success'
  if (row.error || row.testResult?.ok === false) return 'danger'
  return ''
}

const channelStatusText = (row: ChannelRow) => {
  if (row.testing) return 'Testing'
  if (isWorking(row)) return row.testResult?.width && row.testResult?.height ? `Working ${row.testResult.width}x${row.testResult.height}` : 'Working'
  if (row.error) return row.error
  if (row.testResult?.ok === false) return row.testResult.error || 'Unavailable'
  return 'Not tested'
}

const addSelected = async () => {
  const rows = channelRows.value.filter(row => row.selected && isWorking(row))
  if (!rows.length) {
    addError.value = 'Select at least one working channel.'
    return
  }
  adding.value = true
  addError.value = ''
  try {
    for (const row of rows) {
      await apiFetch('/cameras', {
        method: 'POST',
        body: {
          name: row.name.trim() || row.configured_name || row.profile_name || 'Camera channel',
          branch: sharedBranch.value || undefined,
          location: sharedLocation.value || undefined,
          rtsp_url: row.rtsp_url,
          enabled: true,
          ai_enabled: false,
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
