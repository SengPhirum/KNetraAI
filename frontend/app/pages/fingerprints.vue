<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Fingerprint Management</h1>
        <p class="page-subtitle">Attendance devices, punch records, and daily scan summary.</p>
      </div>
      <button class="btn secondary" type="button" :disabled="loading" @click="loadDevices">{{ loading ? 'Refreshing...' : 'Refresh' }}</button>
    </div>

    <div v-if="!attendanceEnabled" class="card" style="text-align: center; padding: 2rem 1rem;">
      <p style="margin: 0 0 0.75rem; color: var(--text-muted);">Attendance mode is disabled.</p>
      <NuxtLink v-if="isAdmin" class="btn" to="/settings">Enable it in Settings &rarr; Attendance</NuxtLink>
      <p v-else style="margin: 0; color: var(--text-muted); font-size: 0.85rem;">Ask an administrator to enable it in Settings.</p>
    </div>

    <template v-else>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="notice" class="notice">{{ notice }}</p>

      <!-- ================= Network scan (Manager+) ================= -->
      <section v-if="canManage" class="card" style="margin-bottom: 1rem;">
        <div class="section-heading">
          <div>
            <p class="section-kicker">ZKTeco discovery</p>
            <h2 class="card-title">Scan network for fingerprint devices</h2>
          </div>
        </div>
        <div class="scan-row">
          <div>
            <label class="label">Network base</label>
            <input v-model="scanBase" class="input" placeholder="192.168.1" style="max-width: 160px;" />
          </div>
          <div>
            <label class="label">Port</label>
            <input v-model.number="scanPort" type="number" class="input" style="max-width: 100px;" />
          </div>
          <button class="btn" type="button" :disabled="scanning || !scanBase" @click="scanNetwork">
            {{ scanning ? 'Scanning...' : 'Scan Network' }}
          </button>
        </div>
        <small class="hint">Sweeps .1-.254 for the ZK service port and probes responders for their serial number.</small>
        <div v-if="scanResults.length" class="table-wrap compact-table" style="margin-top: 0.75rem;">
          <table class="table">
            <thead><tr><th>Host</th><th>Device</th><th>Serial</th><th>Users / Records</th><th>Action</th></tr></thead>
            <tbody>
              <tr v-for="found in scanResults" :key="found.host">
                <td><code>{{ found.host }}:{{ found.port }}</code></td>
                <td>{{ found.device_name || (found.ok ? 'ZK device' : '-') }}</td>
                <td>{{ found.serial || (found.error ? found.error : '-') }}</td>
                <td>{{ found.users != null ? `${found.users} / ${found.records}` : '-' }}</td>
                <td><button class="btn sm secondary" type="button" @click="useScanResult(found)">Use</button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="scanNotice" class="notice" style="margin-top: 0.5rem;">{{ scanNotice }}</p>
      </section>

      <!-- ================= Add / edit device (Manager+) ================= -->
      <section v-if="canManage" id="fp-device-form" class="card" style="margin-bottom: 1rem;">
        <div class="section-heading">
          <div>
            <p class="section-kicker">{{ editingId ? 'Edit device' : 'Manual setup' }}</p>
            <h2 class="card-title">{{ editingId ? 'Edit Fingerprint Device' : 'Add Fingerprint Device' }}</h2>
          </div>
          <span v-if="editingId" class="badge info">Editing</span>
        </div>
        <form class="form-grid" style="align-items: start;" @submit.prevent="saveDevice">
          <div><label class="label">Name *</label><input v-model="form.name" class="input" required placeholder="Main entrance FP" /></div>
          <div>
            <label class="label">Connection type</label>
            <select v-model="form.protocol">
              <option value="zk">ZKTeco direct (IP + comm key)</option>
              <option value="adms_push">ZKTeco ADMS push (device sends to this server)</option>
              <option value="biotime">BioTime server API (username / password)</option>
            </select>
          </div>
          <div>
            <label class="label">Records direction</label>
            <select v-model="form.direction">
              <option value="both">Both (staff choose in/out on device)</option>
              <option value="in">Check-in only (entry door)</option>
              <option value="out">Check-out only (exit door)</option>
            </select>
          </div>

          <template v-if="form.protocol === 'zk'">
            <div><label class="label">Device IP *</label><input v-model="form.host" class="input" placeholder="192.168.1.201" /></div>
            <div><label class="label">Port</label><input v-model.number="form.port" type="number" class="input" /></div>
            <div><label class="label">Comm key</label><input v-model="form.comm_key" class="input" placeholder="0" /></div>
            <label class="checkbox-label" style="align-self: end;"><input v-model="form.use_udp" type="checkbox" /> UDP mode (older devices)</label>
          </template>

          <template v-else-if="form.protocol === 'adms_push'">
            <div><label class="label">Device serial number (SN) *</label><input v-model="form.device_serial" class="input" placeholder="e.g. CEXH231234567" /></div>
            <div class="full-row">
              <small class="hint">
                On the device: Comm. &rarr; Cloud Server / ADMS &rarr; set server address to this machine's IP and port
                <code>8010</code> (plain HTTP). Punches then arrive in realtime; nothing is polled. The SN is on the
                device sticker or in its About menu.
              </small>
            </div>
          </template>

          <template v-else>
            <div class="full-row"><label class="label">BioTime server URL *</label><input v-model="form.api_url" class="input" placeholder="http://biotime.example.com:8081" /></div>
            <div><label class="label">Username *</label><input v-model="form.api_username" class="input" autocomplete="off" /></div>
            <div>
              <label class="label">Password</label>
              <input v-model="form.api_password" type="password" class="input" autocomplete="new-password" :placeholder="editingId ? '******** (saved - blank keeps it)' : ''" />
            </div>
            <div class="full-row">
              <small class="hint">Polls the ZKTeco BioTime / ZKBioTime web server's transactions API - covers every terminal already connected to that server.</small>
            </div>
          </template>

          <div><label class="label">Branch</label><input v-model="form.branch" class="input" /></div>
          <div><label class="label">Location</label><input v-model="form.location" class="input" /></div>
          <label class="checkbox-label" style="align-self: end;"><input v-model="form.enabled" type="checkbox" /> Enabled</label>

          <div class="btn-row full-row">
            <button class="btn" type="submit" :disabled="saving">{{ saving ? 'Saving...' : editingId ? 'Save Device' : 'Add Device' }}</button>
            <button v-if="editingId" class="btn secondary" type="button" @click="resetForm">Cancel</button>
          </div>
        </form>
      </section>

      <!-- ================= Device list ================= -->
      <section class="card" style="margin-bottom: 1rem;">
        <h2 class="card-title">Devices</h2>
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th>Device</th><th>Connection</th><th>Direction</th><th>Status</th><th>Last Sync</th><th>Records</th><th>Actions</th></tr></thead>
            <tbody>
              <tr v-if="!devices.length"><td colspan="7" class="empty-row">No fingerprint devices yet.{{ canManage ? ' Add one above or scan the network.' : '' }}</td></tr>
              <tr v-for="device in devices" :key="device.id">
                <td>
                  <div class="primary-cell">{{ device.name }}</div>
                  <div class="muted-cell">{{ [device.branch, device.location].filter(Boolean).join(' - ') || '-' }}</div>
                  <div v-if="device.last_error" class="muted-cell danger-text truncate" style="max-width: 260px;" :title="device.last_error">{{ device.last_error }}</div>
                </td>
                <td>
                  <span class="badge info">{{ protocolLabel(device.protocol) }}</span>
                  <div class="muted-cell">
                    <code v-if="device.protocol === 'zk'">{{ device.host }}:{{ device.port }}</code>
                    <code v-else-if="device.protocol === 'adms_push'">SN {{ device.device_serial || '?' }}</code>
                    <code v-else>{{ device.api_url }}</code>
                  </div>
                </td>
                <td style="text-transform: capitalize;">{{ device.direction }}</td>
                <td>
                  <span class="badge dot" :class="device.status === 'online' ? 'success' : device.status === 'offline' ? 'danger' : ''">{{ device.status }}</span>
                  <span v-if="!device.enabled" class="badge" style="margin-left: 0.25rem;">Disabled</span>
                </td>
                <td style="white-space: nowrap; font-size: 0.82rem;">{{ device.last_sync_at ? formatDate(device.last_sync_at) : '-' }}</td>
                <td>{{ device.record_count }}</td>
                <td>
                  <div class="btn-row" style="flex-wrap: wrap;">
                    <button v-if="canManage" class="btn sm secondary" type="button" :disabled="busyId === device.id" @click="testDevice(device)">Test</button>
                    <button v-if="device.protocol !== 'adms_push'" class="btn sm" type="button" :disabled="busyId === device.id" @click="syncDevice(device)">
                      {{ busyId === device.id ? 'Working...' : 'Sync Now' }}
                    </button>
                    <button v-if="canManage" class="btn sm secondary" type="button" @click="editDevice(device)">Edit</button>
                    <button v-if="isAdmin" class="btn sm danger" type="button" :disabled="busyId === device.id" @click="removeDevice(device)">Delete</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="testResult" class="notice" style="margin-top: 0.75rem;">
          <template v-if="testResult.ok">
            Connected{{ testResult.serial ? ` - SN ${testResult.serial}` : '' }}{{ testResult.firmware ? `, firmware ${testResult.firmware}` : '' }}{{ testResult.users != null ? `, ${testResult.users} users / ${testResult.records} records` : '' }}.
            <template v-if="typeof testResult.clock_drift_seconds === 'number' && Math.abs(testResult.clock_drift_seconds) > 120">
              <strong> Warning: device clock is off by {{ Math.round(testResult.clock_drift_seconds / 60) }} minutes - fix it or attendance times will be wrong.</strong>
            </template>
            <template v-if="testResult.note"> {{ testResult.note }}</template>
          </template>
          <template v-else>Test failed: {{ testResult.error || testResult.note }}</template>
        </div>
      </section>

      <!-- ================= Today's summary ================= -->
      <section class="card" style="margin-bottom: 1rem;">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.6rem;">
          <h2 class="card-title" style="margin: 0;">Daily Attendance Summary</h2>
          <div class="btn-row">
            <input v-model="summaryDate" type="date" class="input" style="max-width: 170px;" @change="loadSummary" />
            <button class="btn sm secondary" type="button" @click="loadSummary">Load</button>
          </div>
        </div>
        <div class="table-wrap">
          <table class="table compact-table">
            <thead><tr><th>Staff</th><th>Branch</th><th>FP / Staff ID</th><th>First In</th><th>Last Out</th><th>Scans</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-if="!summary.staff.length"><td colspan="7" class="empty-row">No active staff registered.</td></tr>
              <tr v-for="row in summary.staff" :key="row.id">
                <td style="font-weight: 600;">{{ row.full_name }}</td>
                <td>{{ row.branch || '-' }}</td>
                <td>{{ row.fp_user_id || row.staff_id || '-' }}</td>
                <td>{{ row.first_in ? formatTime(row.first_in) : '-' }}</td>
                <td>{{ row.last_out ? formatTime(row.last_out) : '-' }}</td>
                <td>{{ row.punch_count }}</td>
                <td>
                  <span v-for="badge in summaryBadges(row)" :key="badge.label" class="badge" :class="badge.cls" style="margin-right: 0.25rem;">{{ badge.label }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ================= Recent punches ================= -->
      <section class="card">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.6rem;">
          <h2 class="card-title" style="margin: 0;">Recent Scans</h2>
          <div class="btn-row" style="flex-wrap: wrap;">
            <select v-model="recordFilters.punch_type" @change="loadRecords">
              <option value="">All types</option>
              <option value="in">Check-in</option>
              <option value="out">Check-out</option>
              <option value="unknown">Unknown</option>
            </select>
            <select v-model="recordFilters.matched" @change="loadRecords">
              <option value="">Matched + unmatched</option>
              <option value="true">Matched to staff</option>
              <option value="false">Unmatched only</option>
            </select>
            <input v-model="recordFilters.q" class="input" placeholder="Search name or FP ID..." style="max-width: 200px;" @keyup.enter="loadRecords" />
            <button class="btn sm secondary" type="button" @click="loadRecords">Apply</button>
          </div>
        </div>
        <div class="table-wrap">
          <table class="table compact-table">
            <thead><tr><th>Time</th><th>Staff</th><th>FP User ID</th><th>Type</th><th>Device</th></tr></thead>
            <tbody>
              <tr v-if="!records.length"><td colspan="5" class="empty-row">No scans recorded yet.</td></tr>
              <tr v-for="record in records" :key="record.id">
                <td style="white-space: nowrap;">{{ formatDate(record.punched_at) }}</td>
                <td>
                  <NuxtLink v-if="record.person_id" :to="`/persons/${record.person_id}`">{{ record.person_name }}</NuxtLink>
                  <span v-else class="badge warning" title="No staff profile has this Fingerprint ID or Staff ID">Unmatched</span>
                </td>
                <td><code>{{ record.device_user_id }}</code></td>
                <td>
                  <span class="badge" :class="record.punch_type === 'in' ? 'success' : record.punch_type === 'out' ? 'info' : ''">{{ record.punch_type }}</span>
                </td>
                <td>{{ record.device_name || 'Pushed' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const { isAdmin, canManage } = useCurrentUser()
const { attendanceEnabled, ensureLoaded } = useAttendanceStatus()

const devices = ref<any[]>([])
const records = ref<any[]>([])
const summary = ref<any>({ staff: [], checkin_deadline: '09:00', checkout_time: '17:00' })
const summaryDate = ref('')
const loading = ref(false)
const saving = ref(false)
const busyId = ref('')
const error = ref('')
const notice = ref('')
const testResult = ref<any>(null)

const scanBase = ref('')
const scanPort = ref(4370)
const scanning = ref(false)
const scanResults = ref<any[]>([])
const scanNotice = ref('')

const editingId = ref<string | null>(null)
const emptyForm = () => ({
  name: '', protocol: 'zk', host: '', port: 4370, comm_key: '0', use_udp: false,
  api_url: '', api_username: '', api_password: '', device_serial: '',
  branch: '', location: '', direction: 'both', enabled: true
})
const form = reactive<any>(emptyForm())

const recordFilters = reactive({ punch_type: '', matched: '', q: '' })

const protocolLabel = (protocol: string) =>
  protocol === 'zk' ? 'ZK direct' : protocol === 'adms_push' ? 'ADMS push' : 'BioTime API'
const formatDate = (value: string) => value ? new Date(value).toLocaleString() : '-'
const formatTime = (value: string) => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-'

const loadDevices = async () => {
  loading.value = true
  error.value = ''
  try {
    devices.value = await apiFetch('/fingerprint-devices')
  } catch (e: any) {
    error.value = e?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

const loadRecords = async () => {
  const params = new URLSearchParams({ limit: '50' })
  if (recordFilters.punch_type) params.set('punch_type', recordFilters.punch_type)
  if (recordFilters.matched) params.set('matched', recordFilters.matched)
  if (recordFilters.q.trim()) params.set('q', recordFilters.q.trim())
  records.value = await apiFetch(`/attendance/records?${params.toString()}`).catch(() => [])
}

const loadSummary = async () => {
  const qs = summaryDate.value ? `?date=${summaryDate.value}` : ''
  summary.value = await apiFetch(`/attendance/summary${qs}`).catch(() => ({ staff: [] }))
  if (!summaryDate.value && summary.value.date) summaryDate.value = summary.value.date
}

const summaryBadges = (row: any) => {
  const badges: Array<{ label: string, cls: string }> = []
  if (!row.first_in && !row.last_out) {
    badges.push({ label: 'No scans', cls: 'warning' })
    return badges
  }
  const deadline = row.shift_start || summary.value.checkin_deadline
  if (row.first_in && deadline) {
    const firstIn = new Date(row.first_in)
    const [h, m] = String(deadline).split(':').map(Number)
    const cutoff = new Date(firstIn); cutoff.setHours(h || 0, m || 0, 0, 0)
    badges.push(firstIn > cutoff ? { label: 'Late', cls: 'danger' } : { label: 'On time', cls: 'success' })
  }
  if (row.first_in && !row.last_out) badges.push({ label: 'No scan-out yet', cls: '' })
  return badges
}

const scanNetwork = async () => {
  scanning.value = true
  scanNotice.value = ''
  scanResults.value = []
  error.value = ''
  try {
    const result: any = await apiFetch('/fingerprint-devices/discover', {
      method: 'POST',
      body: { network_base: scanBase.value.trim(), port: scanPort.value }
    })
    scanResults.value = result.devices || []
    if (!scanResults.value.length) scanNotice.value = 'No devices found on that network. Check the base address or add the device manually.'
  } catch (e: any) {
    error.value = e?.data?.detail || e.message
  } finally {
    scanning.value = false
  }
}

const useScanResult = (found: any) => {
  resetForm()
  form.protocol = 'zk'
  form.host = found.host
  form.port = found.port || 4370
  form.name = found.device_name || `FP ${found.host}`
  form.device_serial = found.serial || ''
  document.getElementById('fp-device-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const resetForm = () => {
  editingId.value = null
  Object.assign(form, emptyForm())
}

const editDevice = (device: any) => {
  editingId.value = device.id
  Object.assign(form, {
    name: device.name, protocol: device.protocol, host: device.host, port: device.port,
    comm_key: device.comm_key, use_udp: device.use_udp, api_url: device.api_url,
    api_username: device.api_username, api_password: '', device_serial: device.device_serial || '',
    branch: device.branch || '', location: device.location || '', direction: device.direction,
    enabled: device.enabled
  })
  document.getElementById('fp-device-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const saveDevice = async () => {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const payload = { ...form, device_serial: form.device_serial || null, branch: form.branch || null, location: form.location || null }
    if (editingId.value) {
      await apiFetch(`/fingerprint-devices/${editingId.value}`, { method: 'PUT', body: payload })
      notice.value = 'Device updated.'
    } else {
      await apiFetch('/fingerprint-devices', { method: 'POST', body: payload })
      notice.value = 'Device added. Use Test to verify the connection.'
    }
    resetForm()
    await loadDevices()
  } catch (e: any) {
    error.value = e?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}

const testDevice = async (device: any) => {
  busyId.value = device.id
  testResult.value = null
  try {
    testResult.value = await apiFetch(`/fingerprint-devices/${device.id}/test`, { method: 'POST' })
    await loadDevices()
  } catch (e: any) {
    testResult.value = { ok: false, error: e?.data?.detail || e.message }
  } finally {
    busyId.value = ''
  }
}

const syncDevice = async (device: any) => {
  busyId.value = device.id
  error.value = ''
  notice.value = ''
  try {
    const result: any = await apiFetch(`/fingerprint-devices/${device.id}/sync`, { method: 'POST' })
    notice.value = result.ok ? `${device.name}: ${result.new_records} new scan(s) pulled.` : `${device.name}: ${result.error}`
    await Promise.all([loadDevices(), loadRecords(), loadSummary()])
  } catch (e: any) {
    error.value = e?.data?.detail || e.message
  } finally {
    busyId.value = ''
  }
}

const removeDevice = async (device: any) => {
  if (!confirm(`Delete fingerprint device "${device.name}"? Its synced records stay in history.`)) return
  busyId.value = device.id
  try {
    await apiFetch(`/fingerprint-devices/${device.id}`, { method: 'DELETE' })
    await loadDevices()
  } catch (e: any) {
    error.value = e?.data?.detail || e.message
  } finally {
    busyId.value = ''
  }
}

let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  ensureLoaded()
  await Promise.all([loadDevices(), loadRecords(), loadSummary()])
  refreshTimer = setInterval(() => { loadRecords(); loadDevices() }, 30000)
})

onBeforeUnmount(() => { if (refreshTimer) clearInterval(refreshTimer) })
</script>

<style scoped>
.scan-row {
  display: flex;
  align-items: end;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin-bottom: 0.35rem;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
</style>
