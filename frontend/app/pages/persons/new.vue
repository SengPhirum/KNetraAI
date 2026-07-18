<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Add Person</h1>
        <p class="page-subtitle">Register a staff member or customer, then enroll their face.</p>
      </div>
      <NuxtLink class="btn secondary" to="/persons">Back</NuxtLink>
    </div>

    <div class="type-switch">
      <button
        type="button"
        class="type-card"
        :class="{ active: form.person_type === 'staff' }"
        @click="setType('staff')"
      >
        <span class="type-title">Staff</span>
        <span class="type-desc">Employee with staff ID, department, and position</span>
      </button>
      <button
        type="button"
        class="type-card"
        :class="{ active: form.person_type === 'customer' }"
        @click="setType('customer')"
      >
        <span class="type-title">Customer</span>
        <span class="type-desc">Visitor / client with customer ID, membership tier, VIP flag</span>
      </button>
    </div>

    <div class="card">
      <h2 class="card-title">{{ form.person_type === 'staff' ? 'Staff Details' : 'Customer Details' }}</h2>
      <form class="form-grid" @submit.prevent="save(false)">
        <div><label class="label">Full Name *</label><input v-model="form.full_name" class="input" required /></div>
        <div>
          <label class="label">Gender</label>
          <select v-model="form.gender"><option value="unknown">Unknown</option><option value="male">Male</option><option value="female">Female</option></select>
        </div>
        <div><label class="label">Branch</label><input v-model="form.branch" class="input" placeholder="HQ" /></div>
        <div>
          <label class="label">Status</label>
          <select v-model="form.status"><option value="active">Active</option><option value="inactive">Inactive</option></select>
        </div>

        <!-- Staff-only fields -->
        <template v-if="form.person_type === 'staff'">
          <div><label class="label">Staff ID</label><input v-model="form.staff_id" class="input" placeholder="EMP-001" /></div>
          <div><label class="label">Department</label><input v-model="form.department" class="input" placeholder="Sales" /></div>
          <div><label class="label">Position</label><input v-model="form.position" class="input" placeholder="Manager" /></div>
        </template>

        <!-- Customer-only fields -->
        <template v-else>
          <div><label class="label">Customer ID</label><input v-model="form.customer_id" class="input" placeholder="CUST-001" /></div>
          <div>
            <label class="label">Customer Type</label>
            <select v-model="customerTypeChoice">
              <option value="">Not set</option>
              <option>Regular</option>
              <option>Member</option>
              <option>VIP</option>
              <option>Partner</option>
              <option value="__custom__">Custom...</option>
            </select>
          </div>
          <div v-if="customerTypeChoice === '__custom__'">
            <label class="label">Custom Customer Type</label>
            <input v-model="customCustomerType" class="input" placeholder="e.g. Wholesale" />
          </div>
        </template>

        <div><label class="label">Email</label><input v-model="form.email" class="input" type="email" placeholder="name@example.com" /></div>
        <div><label class="label">Phone</label><input v-model="form.phone" class="input" placeholder="+855 ..." /></div>

        <div class="full-row"><label class="label">Notes</label><textarea v-model="form.notes" class="input"></textarea></div>
        <div class="full-row">
          <label v-if="form.person_type === 'customer'" class="checkbox-label"><input v-model="form.vip_flag" type="checkbox" /> VIP Customer</label>
          <label class="checkbox-label"><input v-model="form.consent_confirmed" type="checkbox" /> Consent confirmed for biometric registration</label>
          <small class="hint">Consent is required before enrolling face images. People without consent stay in "Biometric pending".</small>
        </div>
        <div class="full-row btn-row">
          <button class="btn" type="submit" :disabled="saving">{{ saving ? 'Creating...' : 'Create' }}</button>
          <button class="btn secondary" type="button" :disabled="saving" @click="save(true)">Create &amp; Scan Face</button>
        </div>
      </form>
      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const error = ref('')
const saving = ref(false)
const customerTypeChoice = ref('')
const customCustomerType = ref('')

const form = reactive<any>({
  person_type: 'staff',
  full_name: '',
  gender: 'unknown',
  branch: '',
  status: 'active',
  staff_id: '',
  department: '',
  position: '',
  customer_id: '',
  customer_type: '',
  vip_flag: false,
  email: '',
  phone: '',
  consent_confirmed: false,
  notes: ''
})

const setType = (type: 'staff' | 'customer') => {
  form.person_type = type
}

const save = async (openScan: boolean) => {
  error.value = ''
  saving.value = true
  try {
    const payload = { ...form }
    if (form.person_type === 'customer') {
      payload.customer_type = customerTypeChoice.value === '__custom__' ? customCustomerType.value : customerTypeChoice.value
      payload.staff_id = null
      payload.department = null
      payload.position = null
    } else {
      payload.customer_id = null
      payload.customer_type = null
      payload.vip_flag = false
    }
    for (const key of ['branch', 'staff_id', 'department', 'position', 'customer_id', 'customer_type', 'email', 'phone', 'notes']) {
      if (payload[key] === '') payload[key] = null
    }
    const person: any = await apiFetch('/persons', { method: 'POST', body: payload })
    await navigateTo(`/persons/${person.id}${openScan ? '?scan=1' : ''}`)
  } catch (e: any) {
    error.value = e?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.type-switch {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.type-card {
  display: grid;
  gap: 0.25rem;
  text-align: left;
  padding: 0.9rem 1rem;
  border: 2px solid var(--border);
  border-radius: 0.7rem;
  background: var(--card, white);
  cursor: pointer;
  font: inherit;
  transition: border-color 0.15s, background 0.15s;
}

.type-card:hover {
  border-color: var(--primary);
}

.type-card.active {
  border-color: var(--primary);
  background: var(--primary-soft, rgba(30, 144, 255, 0.08));
}

.type-title {
  font-weight: 800;
  font-size: 0.95rem;
}

.type-desc {
  font-size: 0.8rem;
  color: var(--text-muted);
}
</style>
