<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Users</h1>
        <p class="page-subtitle">Manage system accounts and their roles.</p>
      </div>
    </div>
    <div class="card" style="margin-bottom: 1rem;">
      <h2 class="card-title">Create User</h2>
      <form class="form-grid" @submit.prevent="createUser">
        <div><label class="label">Email</label><input v-model="form.email" class="input" type="email" required /></div>
        <div><label class="label">Full Name</label><input v-model="form.full_name" class="input" required /></div>
        <div><label class="label">Password</label><input v-model="form.password" class="input" type="password" required /></div>
        <div><label class="label">Role</label><select v-model="form.role"><option>Admin</option><option>Manager</option><option>Operator</option><option>Viewer</option></select></div>
        <div><button class="btn" type="submit">Create</button></div>
      </form>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th></tr></thead>
        <tbody>
          <tr v-if="!users.length"><td colspan="4" class="empty-row">No users found.</td></tr>
          <tr v-for="user in users" :key="user.id">
            <td style="font-weight: 600;">{{ user.full_name }}</td>
            <td>{{ user.email }}</td>
            <td><span class="badge info">{{ user.role }}</span></td>
            <td><span class="badge" :class="user.is_active ? 'success' : 'danger'">{{ user.is_active ? 'Active' : 'Disabled' }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const users = ref<any[]>([])
const form = reactive({ email: '', full_name: '', password: '', role: 'Viewer' })
const load = async () => { users.value = await apiFetch('/users') }
const createUser = async () => { await apiFetch('/users', { method: 'POST', body: form }); Object.assign(form, { email: '', full_name: '', password: '', role: 'Viewer' }); await load() }
onMounted(load)
</script>
