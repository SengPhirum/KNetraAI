<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Staff / Customer Face Database</h1>
        <p class="page-subtitle">Registered people and their face enrollment status.</p>
      </div>
      <div class="btn-row">
        <button v-if="canManage" class="btn secondary" @click="showImport = !showImport">{{ showImport ? 'Hide Import / Sync' : 'Import / Sync' }}</button>
        <NuxtLink v-if="canOperate" class="btn" to="/persons/new">Add Person</NuxtLink>
      </div>
    </div>

    <div v-if="showImport && canManage" class="card" style="margin-bottom: 1rem;">
      <h2 class="card-title">Import / Sync People</h2>
      <div class="grid-cards" style="grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));">
        <div>
          <h3 class="import-subtitle">1. CSV file import</h3>
          <p class="import-text">
            Upload a CSV with a <code>full_name</code> column. Optional columns:
            <code>person_type</code> (staff/customer), <code>gender</code>, <code>branch</code>, <code>status</code>,
            <code>staff_id</code>, <code>department</code>, <code>position</code>, <code>customer_id</code>,
            <code>customer_type</code>, <code>vip_flag</code>, <code>email</code>, <code>phone</code>,
            <code>notes</code>, <code>consent_confirmed</code>.
          </p>
          <button class="btn sm secondary" style="margin-bottom: 0.75rem;" @click="downloadTemplate">Download CSV template</button>
          <input class="input" type="file" accept=".csv,text/csv" @change="onImportFile" />
          <label class="checkbox-label">
            <input v-model="syncMode" type="checkbox" />
            Sync mode - update existing people matched by Staff ID / Customer ID
          </label>
          <button class="btn" :disabled="!importFile || importing" @click="runImport">{{ importing ? 'Importing...' : 'Import CSV' }}</button>
        </div>

        <div>
          <h3 class="import-subtitle">2. Pull from HR / CRM API</h3>
          <p class="import-text">
            Configure an external API and map its fields to person fields, then pull people on demand.
            Records matching an existing Staff ID / Customer ID are updated instead of duplicated.
          </p>
          <div class="api-form">
            <div class="api-row">
              <select v-model="apiConfig.method" style="max-width: 90px;">
                <option>GET</option>
                <option>POST</option>
              </select>
              <input v-model="apiConfig.url" class="input" placeholder="https://hr.example.com/api/employees" />
            </div>
            <div v-for="(header, index) in apiHeaders" :key="index" class="api-row">
              <input v-model="header.name" class="input" placeholder="Header (e.g. Authorization)" style="max-width: 45%;" />
              <input v-model="header.value" class="input" :placeholder="header.saved ? '******** (saved - blank keeps it)' : 'Value'" />
              <button class="btn sm secondary" type="button" @click="apiHeaders.splice(index, 1)">✕</button>
            </div>
            <button class="btn sm secondary" type="button" @click="apiHeaders.push({ name: '', value: '', saved: false })">+ Add header</button>
            <div v-if="apiConfig.method === 'POST'">
              <label class="label">Request body (JSON)</label>
              <textarea v-model="apiConfig.body" class="input" rows="2" placeholder='{"page_size": 500}'></textarea>
            </div>
            <div class="api-row">
              <div style="flex: 1;">
                <label class="label">Data path</label>
                <input v-model="apiConfig.data_path" class="input" placeholder="e.g. data.items (empty = response root)" />
              </div>
              <div>
                <label class="label">Default type</label>
                <select v-model="apiConfig.default_person_type"><option value="staff">Staff</option><option value="customer">Customer</option></select>
              </div>
              <div>
                <label class="label">Mode</label>
                <select v-model="apiConfig.mode"><option value="upsert">Upsert</option><option value="create">Create only</option></select>
              </div>
            </div>

            <details :open="mappingOpen">
              <summary class="details-title" @click.prevent="mappingOpen = !mappingOpen">Field mapping (API field path → person field)</summary>
              <div class="mapping-grid">
                <template v-for="field in mappableFields" :key="field.key">
                  <label class="label" style="margin: 0; align-self: center;">{{ field.label }}<span v-if="field.required"> *</span></label>
                  <input v-model="apiConfig.mapping[field.key]" class="input" :placeholder="field.placeholder" />
                </template>
              </div>
              <small class="hint">Use dot paths for nested values, e.g. <code>profile.name</code> or <code>contact.email</code>.</small>
            </details>

            <div class="btn-row">
              <button v-if="isAdmin" class="btn sm secondary" :disabled="apiBusy" type="button" @click="saveApiConfig">Save Config</button>
              <button class="btn sm secondary" :disabled="apiBusy || !apiConfig.url" type="button" @click="runApiSync(true)">Test / Preview</button>
              <button class="btn sm" :disabled="apiBusy || !apiConfig.url" type="button" @click="runApiSync(false)">{{ apiBusy ? 'Working...' : 'Sync Now' }}</button>
            </div>
            <p v-if="apiMessage" class="notice" style="margin: 0.25rem 0 0;">{{ apiMessage }}</p>
            <p v-if="apiError" class="error" style="margin: 0.25rem 0 0;">{{ apiError }}</p>
            <div v-if="apiPreview" class="table-wrap" style="margin-top: 0.5rem; max-height: 220px; overflow: auto;">
              <table class="table compact-table">
                <thead><tr><th>Name</th><th>Type</th><th>ID</th><th>Gender</th><th>Branch</th><th>Email</th></tr></thead>
                <tbody>
                  <tr v-for="(item, i) in apiPreview.items" :key="i">
                    <td>{{ item.full_name || '(missing name!)' }}</td>
                    <td>{{ item.person_type }}</td>
                    <td>{{ item.staff_id || item.customer_id || '-' }}</td>
                    <td>{{ item.gender || '-' }}</td>
                    <td>{{ item.branch || '-' }}</td>
                    <td>{{ item.email || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div>
          <h3 class="import-subtitle">3. API push (external systems)</h3>
          <p class="import-text">
            External systems can also push people programmatically to
            <code>POST /persons/import-json</code> with a bearer token:
          </p>
          <pre class="code-block">{
  "mode": "upsert",
  "persons": [
    { "person_type": "staff",
      "full_name": "Jane Doe",
      "staff_id": "EMP-001",
      "branch": "HQ" }
  ]
}</pre>
          <p class="import-text">
            Run it on a schedule to keep this database in sync with your HR or CRM system.
            See the API docs at <code>/docs</code> for the full schema.
          </p>
        </div>
      </div>
      <div v-if="importResult" class="notice" style="margin-top: 1rem;">
        Import finished: {{ importResult.created }} created, {{ importResult.updated }} updated, {{ importResult.skipped }} skipped.
        <ul v-if="importResult.errors?.length" style="margin: 0.5rem 0 0; padding-left: 1.25rem;">
          <li v-for="err in importResult.errors.slice(0, 10)" :key="err.row">Row {{ err.row }}: {{ err.error }}</li>
          <li v-if="importResult.errors.length > 10">... and {{ importResult.errors.length - 10 }} more</li>
        </ul>
      </div>
      <p v-if="importError" class="error">{{ importError }}</p>
    </div>

    <div class="filters-bar">
      <div class="btn-row">
        <button class="btn sm secondary" :class="{ active: filter === '' }" @click="filter = ''; load()">All</button>
        <button class="btn sm secondary" :class="{ active: filter === 'staff' }" @click="filter = 'staff'; load()">Staff</button>
        <button class="btn sm secondary" :class="{ active: filter === 'customer' }" @click="filter = 'customer'; load()">Customers</button>
      </div>
      <select v-model="biometricFilter" @change="load">
        <option value="">Biometric: all</option>
        <option value="registered">Registered</option>
        <option value="pending">Pending</option>
        <option value="na">N/A</option>
      </select>
      <select v-model="statusFilter" @change="load">
        <option value="">Status: all</option>
        <option value="active">Active</option>
        <option value="inactive">Inactive</option>
      </select>
      <input v-model="search" class="input search-input" placeholder="Search name, ID, email, phone..." @keyup.enter="load" />
      <button class="btn sm secondary" @click="load">Search</button>
      <span class="result-count">{{ persons.length }} people</span>
    </div>

    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Name</th><th>Type</th><th>ID</th><th>Gender</th><th>Branch</th><th>Biometric</th><th>Last Seen</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>
          <tr v-if="!persons.length"><td colspan="9" class="empty-row">No people match the current filters.</td></tr>
          <tr v-for="person in persons" :key="person.id">
            <td style="font-weight: 600;">
              {{ person.full_name }}
              <span v-if="person.vip_flag" class="badge warning" style="margin-left: 0.3rem;">VIP</span>
              <span v-if="person.is_dummy" class="badge info" style="margin-left: 0.3rem;" title="Dummy test data from Settings > Demo">DUMMY</span>
            </td>
            <td><span class="badge" :class="person.person_type === 'staff' ? 'info' : 'success'">{{ person.person_type }}</span></td>
            <td>{{ person.staff_id || person.customer_id || '-' }}</td>
            <td style="text-transform: capitalize;">{{ person.gender }}</td>
            <td>{{ person.branch || '-' }}</td>
            <td>
              <span class="badge" :class="biometricClass(person.biometric_status)">{{ biometricLabel(person.biometric_status) }}</span>
              <small v-if="Number(person.image_count)" style="color: var(--text-muted); margin-left: 0.3rem;">{{ person.image_count }} img</small>
            </td>
            <td style="white-space: nowrap; font-size: 0.82rem;">{{ person.last_seen_at ? formatDate(person.last_seen_at) : '-' }}</td>
            <td><span class="badge" :class="person.status === 'active' ? 'success' : ''">{{ person.status }}</span></td>
            <td><NuxtLink class="btn sm secondary" :to="`/persons/${person.id}`">Open</NuxtLink></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const { isAdmin, canManage, canOperate } = useCurrentUser()
const persons = ref<any[]>([])
const filter = ref('')
const biometricFilter = ref('')
const statusFilter = ref('')
const search = ref('')
const showImport = ref(false)
const importFile = ref<File | null>(null)
const syncMode = ref(false)
const importing = ref(false)
const importResult = ref<any>(null)
const importError = ref('')

const mappableFields = [
  { key: 'full_name', label: 'Full name', required: true, placeholder: 'e.g. name or profile.full_name' },
  { key: 'person_type', label: 'Person type', placeholder: 'field with staff/customer' },
  { key: 'staff_id', label: 'Staff ID', placeholder: 'e.g. employee_id' },
  { key: 'customer_id', label: 'Customer ID', placeholder: 'e.g. customer_code' },
  { key: 'gender', label: 'Gender', placeholder: 'e.g. gender (m/f/male/female)' },
  { key: 'branch', label: 'Branch', placeholder: 'e.g. office.name' },
  { key: 'department', label: 'Department', placeholder: 'e.g. department' },
  { key: 'position', label: 'Position', placeholder: 'e.g. job_title' },
  { key: 'customer_type', label: 'Customer type', placeholder: 'e.g. membership.tier' },
  { key: 'vip_flag', label: 'VIP flag', placeholder: 'boolean-ish field' },
  { key: 'email', label: 'Email', placeholder: 'e.g. contact.email' },
  { key: 'phone', label: 'Phone', placeholder: 'e.g. contact.phone' },
  { key: 'status', label: 'Status', placeholder: 'active/inactive field' },
  { key: 'notes', label: 'Notes', placeholder: '' }
]

const apiConfig = reactive<any>({
  url: '',
  method: 'GET',
  body: '',
  data_path: '',
  default_person_type: 'staff',
  mode: 'upsert',
  mapping: Object.fromEntries(mappableFields.map(f => [f.key, '']))
})
const apiHeaders = ref<Array<{ name: string, value: string, saved: boolean }>>([])
const apiBusy = ref(false)
const apiMessage = ref('')
const apiError = ref('')
const apiPreview = ref<any>(null)
const mappingOpen = ref(false)

const formatDate = (value?: string) => value ? new Date(value).toLocaleString() : '-'
const biometricLabel = (status: string) => status === 'registered' ? 'Registered' : status === 'pending' ? 'Pending' : 'N/A'
const biometricClass = (status: string) => status === 'registered' ? 'success' : status === 'pending' ? 'warning' : ''

const load = async () => {
  const params = new URLSearchParams()
  if (filter.value) params.set('person_type', filter.value)
  if (biometricFilter.value) params.set('biometric', biometricFilter.value)
  if (statusFilter.value) params.set('status', statusFilter.value)
  if (search.value.trim()) params.set('q', search.value.trim())
  const qs = params.toString()
  persons.value = await apiFetch(`/persons${qs ? '?' + qs : ''}`)
}

const loadApiConfig = async () => {
  try {
    const config: any = await apiFetch('/persons/api-config')
    Object.assign(apiConfig, {
      url: config.url || '',
      method: config.method || 'GET',
      body: config.body || '',
      data_path: config.data_path || '',
      default_person_type: config.default_person_type || 'staff',
      mode: config.mode || 'upsert',
      mapping: { ...apiConfig.mapping, ...(config.mapping || {}) }
    })
    apiHeaders.value = Object.entries(config.headers || {}).map(([name, value]) => ({
      name,
      value: '',
      saved: value === '********'
    }))
    if (Object.values(config.mapping || {}).some(Boolean)) mappingOpen.value = true
  } catch {
    // Viewer/Operator roles cannot read the config - the panel still works for CSV.
  }
}

const headerDict = () => {
  const headers: Record<string, string> = {}
  for (const header of apiHeaders.value) {
    if (header.name.trim()) headers[header.name.trim()] = header.value
  }
  return headers
}

const saveApiConfig = async () => {
  apiBusy.value = true
  apiError.value = ''
  apiMessage.value = ''
  try {
    await apiFetch('/persons/api-config', {
      method: 'PUT',
      body: { ...apiConfig, headers: headerDict(), mapping: cleanMapping() }
    })
    apiMessage.value = 'API import configuration saved.'
    await loadApiConfig()
  } catch (e: any) {
    apiError.value = e?.data?.detail || e.message
  } finally {
    apiBusy.value = false
  }
}

const cleanMapping = () => Object.fromEntries(Object.entries(apiConfig.mapping).filter(([, v]) => String(v || '').trim()))

const runApiSync = async (preview: boolean) => {
  apiBusy.value = true
  apiError.value = ''
  apiMessage.value = ''
  apiPreview.value = null
  try {
    if (isAdmin.value) {
      // Persist the latest form state first so the sync uses what's on screen.
      await apiFetch('/persons/api-config', {
        method: 'PUT',
        body: { ...apiConfig, headers: headerDict(), mapping: cleanMapping() }
      })
    }
    const result: any = await apiFetch('/persons/api-sync', { method: 'POST', body: { preview } })
    if (preview) {
      apiPreview.value = result
      apiMessage.value = `Preview OK - ${result.total} records found. Showing first ${result.items.length}.`
    } else {
      importResult.value = result
      apiMessage.value = `Sync finished: ${result.created} created, ${result.updated} updated, ${result.skipped} skipped.`
      await load()
    }
  } catch (e: any) {
    apiError.value = e?.data?.detail || e.message
  } finally {
    apiBusy.value = false
  }
}

const onImportFile = (event: Event) => {
  importFile.value = (event.target as HTMLInputElement).files?.[0] || null
  importResult.value = null
  importError.value = ''
}

const runImport = async () => {
  if (!importFile.value) return
  importing.value = true
  importResult.value = null
  importError.value = ''
  try {
    const form = new FormData()
    form.append('file', importFile.value)
    form.append('mode', syncMode.value ? 'upsert' : 'create')
    importResult.value = await apiFetch('/persons/import', { method: 'POST', body: form })
    await load()
  } catch (e: any) {
    importError.value = e?.data?.detail || e.message
  } finally {
    importing.value = false
  }
}

const downloadTemplate = () => {
  const header = 'person_type,full_name,gender,branch,status,staff_id,department,position,customer_id,customer_type,vip_flag,email,phone,notes,consent_confirmed'
  const example = 'staff,Jane Doe,female,HQ,active,EMP-001,Sales,Manager,,,false,jane@example.com,+85512345678,,true'
  const blob = new Blob([`${header}\n${example}\n`], { type: 'text/csv' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = 'persons-import-template.csv'
  link.click()
  URL.revokeObjectURL(link.href)
}

onMounted(() => {
  load()
  loadApiConfig()
})
</script>

<style scoped>
.import-subtitle {
  font-size: 0.9rem;
  font-weight: 700;
  margin: 0 0 0.5rem;
}

.import-text {
  font-size: 0.85rem;
  color: #334155;
  margin: 0 0 0.75rem;
}

.code-block {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 0.5rem;
  padding: 0.75rem;
  font-size: 0.75rem;
  overflow-x: auto;
  margin: 0 0 0.75rem;
}

.filters-bar {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.filters-bar select {
  max-width: 170px;
}

.search-input {
  max-width: 260px;
}

.result-count {
  font-size: 0.82rem;
  color: var(--text-muted);
  margin-left: auto;
}

.api-form {
  display: grid;
  gap: 0.6rem;
}

.api-row {
  display: flex;
  gap: 0.4rem;
  align-items: end;
}

.mapping-grid {
  display: grid;
  grid-template-columns: minmax(110px, auto) 1fr;
  gap: 0.4rem 0.6rem;
  margin: 0.6rem 0 0.4rem;
}

.details-title {
  cursor: pointer;
  font-weight: 700;
  font-size: 0.85rem;
  padding: 0.3rem 0;
}
</style>
