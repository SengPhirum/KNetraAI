<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ person?.full_name || 'Person Profile' }}</h1>
        <p v-if="person" class="page-subtitle" style="text-transform: capitalize;">{{ person.person_type }} profile and face enrollment.</p>
      </div>
      <div class="btn-row">
        <button v-if="person && !editing" class="btn secondary" type="button" @click="startEdit">Edit Profile</button>
        <button v-if="person && canManage" class="btn danger" type="button" @click="removePerson">Delete</button>
        <NuxtLink to="/persons" class="btn secondary">Back</NuxtLink>
      </div>
    </div>

    <p v-if="pageError" class="error">{{ pageError }}</p>

    <div v-if="person" class="grid-cards">
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem;">
          <h2 class="card-title" style="margin: 0;">Profile</h2>
          <span class="badge" :class="biometricClass(person.biometric_status)">{{ biometricLabel(person.biometric_status) }}</span>
        </div>

        <dl v-if="!editing" class="profile-list">
          <div><dt>Type</dt><dd style="text-transform: capitalize;">{{ person.person_type }}</dd></div>
          <div><dt>Gender</dt><dd style="text-transform: capitalize;">{{ person.gender }}</dd></div>
          <div><dt>Branch</dt><dd>{{ person.branch || '-' }}</dd></div>
          <template v-if="person.person_type === 'staff'">
            <div><dt>Staff ID</dt><dd>{{ person.staff_id || '-' }}</dd></div>
            <div><dt>Department</dt><dd>{{ person.department || '-' }}</dd></div>
            <div><dt>Position</dt><dd>{{ person.position || '-' }}</dd></div>
          </template>
          <template v-else>
            <div><dt>Customer ID</dt><dd>{{ person.customer_id || '-' }}</dd></div>
            <div><dt>Customer Type</dt><dd>{{ person.customer_type || '-' }}</dd></div>
            <div><dt>VIP</dt><dd>{{ person.vip_flag ? 'Yes' : 'No' }}</dd></div>
          </template>
          <div><dt>Email</dt><dd>{{ person.email || '-' }}</dd></div>
          <div><dt>Phone</dt><dd>{{ person.phone || '-' }}</dd></div>
          <div><dt>Status</dt><dd><span class="badge" :class="person.status === 'active' ? 'success' : ''">{{ person.status }}</span></dd></div>
          <div><dt>Consent</dt><dd><span class="badge" :class="person.consent_at ? 'success' : 'warning'">{{ person.consent_at ? 'Confirmed' : 'Not recorded' }}</span></dd></div>
          <div><dt>Face images</dt><dd>{{ person.image_count || 0 }} ({{ person.embedding_count || 0 }} embeddings)</dd></div>
          <div v-if="person.last_seen_at"><dt>Last seen</dt><dd>{{ formatDate(person.last_seen_at) }}</dd></div>
          <div v-if="person.notes" class="notes-row"><dt>Notes</dt><dd style="text-align: left;">{{ person.notes }}</dd></div>
        </dl>

        <form v-else class="form-grid" @submit.prevent="saveEdit">
          <div class="full-row"><label class="label">Full Name</label><input v-model="editForm.full_name" class="input" required /></div>
          <div>
            <label class="label">Gender</label>
            <select v-model="editForm.gender"><option value="unknown">Unknown</option><option value="male">Male</option><option value="female">Female</option></select>
          </div>
          <div><label class="label">Branch</label><input v-model="editForm.branch" class="input" /></div>
          <template v-if="person.person_type === 'staff'">
            <div><label class="label">Staff ID</label><input v-model="editForm.staff_id" class="input" /></div>
            <div><label class="label">Department</label><input v-model="editForm.department" class="input" /></div>
            <div><label class="label">Position</label><input v-model="editForm.position" class="input" /></div>
          </template>
          <template v-else>
            <div><label class="label">Customer ID</label><input v-model="editForm.customer_id" class="input" /></div>
            <div><label class="label">Customer Type</label><input v-model="editForm.customer_type" class="input" /></div>
          </template>
          <div><label class="label">Email</label><input v-model="editForm.email" class="input" type="email" /></div>
          <div><label class="label">Phone</label><input v-model="editForm.phone" class="input" /></div>
          <div>
            <label class="label">Status</label>
            <select v-model="editForm.status"><option value="active">Active</option><option value="inactive">Inactive</option></select>
          </div>
          <div class="full-row"><label class="label">Notes</label><textarea v-model="editForm.notes" class="input"></textarea></div>
          <div class="full-row">
            <label v-if="person.person_type === 'customer'" class="checkbox-label"><input v-model="editForm.vip_flag" type="checkbox" /> VIP Customer</label>
            <label class="checkbox-label"><input v-model="editForm.consent_confirmed" type="checkbox" /> Consent confirmed for biometric registration</label>
          </div>
          <div class="full-row btn-row">
            <button class="btn" type="submit" :disabled="savingEdit">{{ savingEdit ? 'Saving...' : 'Save Changes' }}</button>
            <button class="btn secondary" type="button" @click="editing = false">Cancel</button>
          </div>
          <p v-if="editError" class="error full-row">{{ editError }}</p>
        </form>
      </div>

      <div class="card">
        <h2 class="card-title">Face Enrollment</h2>
        <div class="tabs-mini">
          <button class="tab-mini" :class="{ active: enrollTab === 'scan' }" type="button" @click="enrollTab = 'scan'">Camera Scan</button>
          <button class="tab-mini" :class="{ active: enrollTab === 'upload' }" type="button" @click="enrollTab = 'upload'">Upload Photo</button>
        </div>

        <div v-show="enrollTab === 'scan'">
          <FaceScanCapture :person-id="String(route.params.id)" @uploaded="load" />
        </div>

        <div v-show="enrollTab === 'upload'">
          <input class="input" type="file" accept="image/*" @change="onFile" />
          <small class="hint">Use 3-5 clear, front-facing photos per person for best recognition.</small>
          <button class="btn" style="margin-top: 0.85rem;" @click="upload" :disabled="!file || uploading">{{ uploading ? 'Uploading...' : 'Upload and Generate Embedding' }}</button>
          <p v-if="message" class="notice" style="margin-top: 0.75rem;">{{ message }}</p>
        </div>
      </div>
    </div>

    <section class="card" style="margin-top: 1.25rem;">
      <h2 class="card-title">Face Images</h2>
      <p v-if="!(person?.images || []).length" style="color: var(--text-muted); font-size: 0.9rem; margin: 0;">No face images enrolled yet.</p>
      <div class="grid-cards">
        <div v-for="image in person?.images || []" :key="image.id" class="card" style="padding: 0.75rem;">
          <img :src="`${apiBaseUrl}/files/${image.file_path}`" style="width: 100%; height: 180px; object-fit: cover; border-radius: 0.5rem;" />
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.6rem; gap: 0.4rem;">
            <span class="badge" :class="Number(image.embedding_count) > 0 ? 'success' : 'warning'">
              {{ Number(image.embedding_count) > 0 ? 'Embedded' : 'No embedding' }}
            </span>
            <span style="font-size: 0.8rem; color: var(--text-muted);">Quality: {{ image.quality_score ? Number(image.quality_score).toFixed(2) : '-' }}</span>
          </div>
          <p class="truncate" style="max-width: 100%; font-size: 0.78rem; color: var(--text-muted); margin: 0.35rem 0 0.5rem;" :title="image.original_filename">{{ image.original_filename }}</p>
          <button class="btn sm danger" type="button" @click="removeImage(image)">Delete Image</button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const { apiFetch, apiBaseUrl } = useApi()
const { canManage } = useCurrentUser()

const person = ref<any>(null)
const file = ref<File | null>(null)
const message = ref('')
const pageError = ref('')
const uploading = ref(false)
const editing = ref(false)
const savingEdit = ref(false)
const editError = ref('')
const editForm = reactive<any>({})
const enrollTab = ref<'scan' | 'upload'>('scan')

const load = async () => {
  try {
    person.value = await apiFetch(`/persons/${route.params.id}`)
  } catch (e: any) {
    pageError.value = e?.data?.detail || e.message
  }
}

const formatDate = (value?: string) => value ? new Date(value).toLocaleString() : '-'
const biometricLabel = (status: string) => status === 'registered' ? 'Biometric Registered' : status === 'pending' ? 'Biometric Pending' : 'Biometric N/A'
const biometricClass = (status: string) => status === 'registered' ? 'success' : status === 'pending' ? 'warning' : ''

const startEdit = () => {
  Object.assign(editForm, {
    full_name: person.value.full_name,
    gender: person.value.gender,
    branch: person.value.branch || '',
    status: person.value.status,
    staff_id: person.value.staff_id || '',
    department: person.value.department || '',
    position: person.value.position || '',
    customer_id: person.value.customer_id || '',
    customer_type: person.value.customer_type || '',
    vip_flag: Boolean(person.value.vip_flag),
    email: person.value.email || '',
    phone: person.value.phone || '',
    notes: person.value.notes || '',
    consent_confirmed: Boolean(person.value.consent_at)
  })
  editError.value = ''
  editing.value = true
}

const saveEdit = async () => {
  savingEdit.value = true
  editError.value = ''
  try {
    const payload: any = { ...editForm }
    for (const key of ['branch', 'staff_id', 'department', 'position', 'customer_id', 'customer_type', 'email', 'phone', 'notes']) {
      if (payload[key] === '') payload[key] = null
    }
    await apiFetch(`/persons/${route.params.id}`, { method: 'PUT', body: payload })
    editing.value = false
    await load()
  } catch (e: any) {
    editError.value = e?.data?.detail || e.message
  } finally {
    savingEdit.value = false
  }
}

const removePerson = async () => {
  if (!confirm(`Delete ${person.value.full_name} and all their face data? This cannot be undone.`)) return
  try {
    await apiFetch(`/persons/${route.params.id}`, { method: 'DELETE' })
    await navigateTo('/persons')
  } catch (e: any) {
    pageError.value = e?.data?.detail || e.message
  }
}

const removeImage = async (image: any) => {
  if (!confirm('Delete this face image and its embedding?')) return
  try {
    await apiFetch(`/persons/${route.params.id}/images/${image.id}`, { method: 'DELETE' })
    await load()
  } catch (e: any) {
    pageError.value = e?.data?.detail || e.message
  }
}

const onFile = (event: Event) => { file.value = (event.target as HTMLInputElement).files?.[0] || null }

const upload = async () => {
  if (!file.value) return
  uploading.value = true
  const form = new FormData()
  form.append('file', file.value)
  message.value = 'Uploading...'
  try {
    const result: any = await apiFetch(`/persons/${route.params.id}/images`, { method: 'POST', body: form })
    message.value = result.embedding_status === 'created' ? 'Embedding created' : `Image saved but embedding failed: ${result.embedding_error}`
  } catch (e: any) {
    message.value = e?.data?.detail || e.message
  } finally {
    uploading.value = false
  }
  file.value = null
  await load()
}

onMounted(async () => {
  await load()
  if (route.query.scan === '1') enrollTab.value = 'scan'
})
</script>

<style scoped>
.profile-list {
  margin: 0;
  display: grid;
  gap: 0.55rem;
}

.profile-list > div {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  font-size: 0.9rem;
}

.profile-list dt {
  color: var(--text-muted);
  font-weight: 600;
}

.profile-list dd {
  margin: 0;
  text-align: right;
}

.notes-row {
  flex-direction: column;
  align-items: flex-start !important;
  gap: 0.25rem !important;
}

.tabs-mini {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
}

.tab-mini {
  border: 1px solid var(--border);
  background: transparent;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-muted);
  padding: 0.4rem 0.85rem;
  border-radius: 999px;
  cursor: pointer;
}

.tab-mini.active {
  color: white;
  background: var(--primary);
  border-color: var(--primary);
}
</style>
