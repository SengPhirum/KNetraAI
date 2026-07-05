<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Staff / Customer Face Database</h1>
        <p class="page-subtitle">Registered people and their face enrollment status.</p>
      </div>
      <div class="btn-row">
        <button class="btn secondary" @click="showImport = !showImport">{{ showImport ? 'Hide Import / Sync' : 'Import / Sync' }}</button>
        <NuxtLink class="btn" to="/persons/new">Add Person</NuxtLink>
      </div>
    </div>

    <div v-if="showImport" class="card" style="margin-bottom: 1rem;">
      <h2 class="card-title">Import / Sync People</h2>
      <div class="grid-cards" style="grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));">
        <div>
          <h3 class="import-subtitle">1. CSV file import</h3>
          <p class="import-text">
            Upload a CSV with a <code>full_name</code> column. Optional columns:
            <code>person_type</code> (staff/customer), <code>gender</code>, <code>branch</code>, <code>status</code>,
            <code>staff_id</code>, <code>department</code>, <code>position</code>, <code>customer_id</code>,
            <code>customer_type</code>, <code>vip_flag</code>, <code>notes</code>, <code>consent_confirmed</code>.
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
          <h3 class="import-subtitle">2. API sync (HR / CRM integration)</h3>
          <p class="import-text">
            External systems can push people programmatically to
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
            With <code>"mode": "upsert"</code>, records matching an existing Staff ID / Customer ID are updated
            instead of duplicated - run it on a schedule to keep this database in sync with your HR or CRM system.
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

    <div class="btn-row" style="margin-bottom: 1rem;">
      <button class="btn sm secondary" :class="{ active: filter === '' }" @click="filter = ''; load()">All</button>
      <button class="btn sm secondary" :class="{ active: filter === 'staff' }" @click="filter = 'staff'; load()">Staff</button>
      <button class="btn sm secondary" :class="{ active: filter === 'customer' }" @click="filter = 'customer'; load()">Customers</button>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Name</th><th>Type</th><th>Gender</th><th>Branch</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>
          <tr v-if="!persons.length"><td colspan="6" class="empty-row">No people registered yet.</td></tr>
          <tr v-for="person in persons" :key="person.id">
            <td style="font-weight: 600;">{{ person.full_name }}</td>
            <td><span class="badge" :class="person.person_type === 'staff' ? 'info' : 'success'">{{ person.person_type }}</span></td>
            <td style="text-transform: capitalize;">{{ person.gender }}</td>
            <td>{{ person.branch || '-' }}</td>
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
const persons = ref<any[]>([])
const filter = ref('')
const showImport = ref(false)
const importFile = ref<File | null>(null)
const syncMode = ref(false)
const importing = ref(false)
const importResult = ref<any>(null)
const importError = ref('')

const load = async () => {
  const qs = filter.value ? `?person_type=${filter.value}` : ''
  persons.value = await apiFetch(`/persons${qs}`)
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
  const header = 'person_type,full_name,gender,branch,status,staff_id,department,position,customer_id,customer_type,vip_flag,notes,consent_confirmed'
  const example = 'staff,Jane Doe,female,HQ,active,EMP-001,Sales,Manager,,,false,,true'
  const blob = new Blob([`${header}\n${example}\n`], { type: 'text/csv' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = 'persons-import-template.csv'
  link.click()
  URL.revokeObjectURL(link.href)
}

onMounted(load)
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
</style>
