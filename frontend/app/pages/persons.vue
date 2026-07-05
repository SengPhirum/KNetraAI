<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
      <h1 class="page-title">Staff / Customer Face Database</h1>
      <NuxtLink class="btn" to="/persons/new">Add Person</NuxtLink>
    </div>
    <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem;">
      <button class="btn secondary" @click="filter = ''; load()">All</button>
      <button class="btn secondary" @click="filter = 'staff'; load()">Staff</button>
      <button class="btn secondary" @click="filter = 'customer'; load()">Customers</button>
    </div>
    <table class="table">
      <thead><tr><th>Name</th><th>Type</th><th>Gender</th><th>Branch</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>
        <tr v-for="person in persons" :key="person.id">
          <td>{{ person.full_name }}</td>
          <td><span class="badge">{{ person.person_type }}</span></td>
          <td>{{ person.gender }}</td>
          <td>{{ person.branch || '-' }}</td>
          <td>{{ person.status }}</td>
          <td><NuxtLink class="btn secondary" :to="`/persons/${person.id}`">Open</NuxtLink></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const persons = ref<any[]>([])
const filter = ref('')
const load = async () => {
  const qs = filter.value ? `?person_type=${filter.value}` : ''
  persons.value = await apiFetch(`/persons${qs}`)
}
onMounted(load)
</script>
