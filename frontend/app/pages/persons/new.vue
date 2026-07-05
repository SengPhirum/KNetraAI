<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Add Person</h1>
        <p class="page-subtitle">Register a staff member or customer before enrolling face images.</p>
      </div>
      <NuxtLink class="btn secondary" to="/persons">Back</NuxtLink>
    </div>
    <div class="card">
      <form class="form-grid" @submit.prevent="save">
        <div><label class="label">Type</label><select v-model="form.person_type"><option value="staff">Staff</option><option value="customer">Customer</option></select></div>
        <div><label class="label">Full Name</label><input v-model="form.full_name" class="input" required /></div>
        <div><label class="label">Gender</label><select v-model="form.gender"><option value="unknown">Unknown</option><option value="male">Male</option><option value="female">Female</option></select></div>
        <div><label class="label">Branch</label><input v-model="form.branch" class="input" /></div>
        <div><label class="label">Staff ID</label><input v-model="form.staff_id" class="input" /></div>
        <div><label class="label">Department</label><input v-model="form.department" class="input" /></div>
        <div><label class="label">Position</label><input v-model="form.position" class="input" /></div>
        <div><label class="label">Customer ID</label><input v-model="form.customer_id" class="input" /></div>
        <div><label class="label">Customer Type</label><input v-model="form.customer_type" class="input" /></div>
        <div class="full-row"><label class="label">Notes</label><textarea v-model="form.notes" class="input"></textarea></div>
        <div class="full-row">
          <label class="checkbox-label"><input v-model="form.vip_flag" type="checkbox" /> VIP Customer</label>
          <label class="checkbox-label"><input v-model="form.consent_confirmed" type="checkbox" /> Consent confirmed for biometric registration</label>
        </div>
        <div><button class="btn" type="submit">Create</button></div>
      </form>
      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const error = ref('')
const form = reactive<any>({ person_type: 'staff', full_name: '', gender: 'unknown', branch: '', staff_id: '', department: '', position: '', customer_id: '', customer_type: '', vip_flag: false, consent_confirmed: false, notes: '' })
const save = async () => {
  error.value = ''
  try {
    const person: any = await apiFetch('/persons', { method: 'POST', body: form })
    await navigateTo(`/persons/${person.id}`)
  } catch (e: any) { error.value = e?.data?.detail || e.message }
}
</script>
