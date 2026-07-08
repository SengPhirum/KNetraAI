<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Detection History</h1>
        <p class="page-subtitle">Recent walk-in detection events with snapshots and recognition results.</p>
      </div>
    </div>

    <section class="card filters-card">
      <div class="form-grid">
        <div>
          <label class="label">Camera</label>
          <select v-model="filters.camera_id">
            <option value="">All cameras</option>
            <option v-for="camera in cameras" :key="camera.id" :value="camera.id">{{ camera.name }}</option>
          </select>
        </div>
        <div>
          <label class="label">Type</label>
          <select v-model="filters.person_type">
            <option value="">All types</option>
            <option value="unknown">Unknown</option>
            <option value="staff">Staff</option>
            <option value="customer">Customer</option>
          </select>
        </div>
        <div>
          <label class="label">From</label>
          <input v-model="filters.date_from" class="input" type="date" />
        </div>
        <div>
          <label class="label">To</label>
          <input v-model="filters.date_to" class="input" type="date" />
        </div>
        <div>
          <label class="label">Snapshot</label>
          <select v-model="filters.has_snapshot">
            <option value="">Any</option>
            <option value="true">With snapshot</option>
            <option value="false">Without snapshot</option>
          </select>
        </div>
        <div>
          <label class="label">Search</label>
          <input v-model="filters.q" class="input" placeholder="camera, person, greeting..." @keyup.enter="load" />
        </div>
        <div class="btn-row">
          <button class="btn" type="button" @click="load">Apply</button>
          <button class="btn secondary" type="button" @click="resetFilters">Reset</button>
        </div>
      </div>
    </section>

    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Time</th><th>Snapshot</th><th>Camera</th><th>Person</th><th>Type</th><th>Greeting</th><th>Gender</th><th>Confidence</th></tr></thead>
        <tbody>
          <tr v-if="!events.length"><td colspan="8" class="empty-row">No detection events recorded yet.</td></tr>
          <tr v-for="event in events" :key="event.id">
            <td style="white-space: nowrap;">{{ formatDate(event.detected_at) }}</td>
            <td>
              <button v-if="event.snapshot_path" class="snapshot-thumb" type="button" @click="selectedEvent = event">
                <img :src="`${apiBaseUrl}/files/${event.snapshot_path}`" class="thumb" />
              </button>
              <span v-else>-</span>
            </td>
            <td>{{ event.camera_name || '-' }}</td>
            <td>{{ event.person_name || 'Unknown' }}</td>
            <td><span class="badge" :class="typeClass(event.person_type)">{{ event.person_type }}</span></td>
            <td class="truncate" :title="event.greeting">{{ event.greeting }}</td>
            <td style="text-transform: capitalize;">{{ event.gender_estimate || '-' }}</td>
            <td>{{ event.confidence ? Number(event.confidence).toFixed(3) : '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <SnapshotModal :event="selectedEvent" :api-base-url="apiBaseUrl" @close="selectedEvent = null" />
  </div>
</template>

<script setup lang="ts">
const { apiFetch, apiBaseUrl } = useApi()
const events = ref<any[]>([])
const cameras = ref<any[]>([])
const selectedEvent = ref<any | null>(null)
const filters = reactive({
  camera_id: '',
  person_type: '',
  date_from: '',
  date_to: '',
  has_snapshot: 'true',
  q: '',
  limit: '100'
})

const formatDate = (value: string) => value ? new Date(value).toLocaleString() : '-'
const typeClass = (type: string) => type === 'staff' ? 'info' : type === 'customer' ? 'success' : 'warning'

const query = () => {
  const params = new URLSearchParams({ limit: filters.limit })
  if (filters.camera_id) params.set('camera_id', filters.camera_id)
  if (filters.person_type) params.set('person_type', filters.person_type)
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  if (filters.has_snapshot) params.set('has_snapshot', filters.has_snapshot)
  if (filters.q.trim()) params.set('q', filters.q.trim())
  return params.toString()
}

const load = async () => {
  events.value = await apiFetch(`/detection-events?${query()}`)
}

const resetFilters = async () => {
  Object.assign(filters, {
    camera_id: '',
    person_type: '',
    date_from: '',
    date_to: '',
    has_snapshot: 'true',
    q: '',
    limit: '100'
  })
  await load()
}

onMounted(async () => {
  cameras.value = await apiFetch('/cameras')
  await load()
})
</script>

<style scoped>
.filters-card {
  margin-bottom: 1rem;
}

.snapshot-thumb {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: zoom-in;
  display: block;
}

.snapshot-thumb:focus-visible {
  outline: 3px solid var(--primary-soft);
  border-radius: 0.4rem;
}
</style>
