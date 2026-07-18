<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Audit Logs</h1>
        <p class="page-subtitle">Chronological record of user and system actions.</p>
      </div>
      <button class="btn secondary" type="button" :disabled="exporting" @click="exportCsv">
        {{ exporting ? 'Exporting...' : 'Export CSV (filtered)' }}
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <section class="card" style="margin-bottom: 1rem;">
      <div class="form-grid">
        <div>
          <label class="label">Action</label>
          <select v-model="filters.action">
            <option value="">All actions</option>
            <option v-for="action in actions" :key="action" :value="action">{{ action }}</option>
          </select>
        </div>
        <div>
          <label class="label">Entity type</label>
          <select v-model="filters.entity_type">
            <option value="">All entities</option>
            <option v-for="entity in entityTypes" :key="entity" :value="entity">{{ entity }}</option>
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
          <label class="label">Search</label>
          <input v-model="filters.q" class="input" placeholder="actor, action, entity, metadata..." @keyup.enter="load" />
        </div>
        <div class="btn-row">
          <button class="btn" type="button" @click="load">Apply</button>
          <button class="btn secondary" type="button" @click="resetFilters">Reset</button>
        </div>
      </div>
    </section>

    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Metadata</th></tr></thead>
        <tbody>
          <tr v-if="!logs.length"><td colspan="5" class="empty-row">No audit log entries match the current filters.</td></tr>
          <tr v-for="log in logs" :key="log.id">
            <td style="white-space: nowrap;">{{ new Date(log.created_at).toLocaleString() }}</td>
            <td>{{ log.actor_email || '-' }}</td>
            <td><span class="badge">{{ log.action }}</span></td>
            <td>{{ log.entity_type }} {{ log.entity_id }}</td>
            <td style="max-width: 420px;"><code>{{ log.metadata }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="btn-row" style="justify-content: center; margin-top: 0.85rem;">
      <button class="btn sm secondary" :disabled="offset === 0" @click="page(-1)">Prev</button>
      <span style="align-self: center; font-size: 0.85rem; color: var(--text-muted);">
        {{ offset + 1 }} - {{ offset + logs.length }}
      </span>
      <button class="btn sm secondary" :disabled="logs.length < LIMIT" @click="page(1)">Next</button>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const logs = ref<any[]>([])
const actions = ref<string[]>([])
const error = ref('')
const exporting = ref(false)
const offset = ref(0)
const LIMIT = 100

const filters = reactive({ action: '', entity_type: '', date_from: '', date_to: '', q: '' })
const entityTypes = ['person', 'camera', 'user', 'setting', 'detection_event', 'greeting_template']

const query = () => {
  const params = new URLSearchParams()
  if (filters.action) params.set('action', filters.action)
  if (filters.entity_type) params.set('entity_type', filters.entity_type)
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  if (filters.q.trim()) params.set('q', filters.q.trim())
  return params
}

const load = async (keepOffset = false) => {
  if (!keepOffset) offset.value = 0
  error.value = ''
  try {
    const params = query()
    params.set('limit', String(LIMIT))
    params.set('offset', String(offset.value))
    logs.value = await apiFetch(`/audit-logs?${params.toString()}`)
  } catch (e: any) {
    error.value = e?.data?.detail || e.message
  }
}

const page = async (direction: number) => {
  offset.value = Math.max(0, offset.value + direction * LIMIT)
  await load(true)
}

const resetFilters = async () => {
  Object.assign(filters, { action: '', entity_type: '', date_from: '', date_to: '', q: '' })
  await load()
}

const exportCsv = async () => {
  exporting.value = true
  error.value = ''
  try {
    const blob = await apiFetch<Blob>(`/audit-logs/export?${query().toString()}`, { responseType: 'blob' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (e: any) {
    error.value = e?.data?.detail || e.message
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await load()
  actions.value = await apiFetch('/audit-logs/actions').catch(() => [])
})
</script>
