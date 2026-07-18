<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Users</h1>
        <p class="page-subtitle">{{ isAdmin ? 'Manage system accounts and their roles.' : 'System accounts (read-only view).' }}</p>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="message" class="notice">{{ message }}</p>

    <div v-if="isAdmin" class="card" style="margin-bottom: 1rem;">
      <h2 class="card-title">Create User</h2>
      <form class="form-grid" @submit.prevent="createUser">
        <div><label class="label">Email</label><input v-model="form.email" class="input" type="email" required /></div>
        <div><label class="label">Full Name</label><input v-model="form.full_name" class="input" required /></div>
        <div><label class="label">Password</label><input v-model="form.password" class="input" type="password" required /></div>
        <div><label class="label">Role</label><select v-model="form.role"><option>Admin</option><option>Manager</option><option>Operator</option><option>Viewer</option></select></div>
        <div><button class="btn" type="submit" :disabled="busy">Create</button></div>
      </form>
    </div>

    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Name</th><th>Email</th><th>Role</th><th>Status</th>
            <th v-if="isAdmin">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!users.length"><td :colspan="isAdmin ? 5 : 4" class="empty-row">No users found.</td></tr>
          <tr v-for="account in users" :key="account.id">
            <td style="font-weight: 600;">
              {{ account.full_name }}
              <span v-if="account.email === email" class="badge" style="margin-left: 0.3rem;">You</span>
            </td>
            <td>{{ account.email }}</td>
            <td>
              <select
                v-if="isAdmin && account.email !== email"
                :value="account.role"
                :disabled="busy"
                style="max-width: 130px;"
                @change="changeRole(account, ($event.target as HTMLSelectElement).value)"
              >
                <option>Admin</option><option>Manager</option><option>Operator</option><option>Viewer</option>
              </select>
              <span v-else class="badge info">{{ account.role }}</span>
            </td>
            <td><span class="badge" :class="account.is_active ? 'success' : 'danger'">{{ account.is_active ? 'Active' : 'Disabled' }}</span></td>
            <td v-if="isAdmin">
              <div class="btn-row" style="flex-wrap: nowrap;">
                <button
                  v-if="account.email !== email"
                  class="btn sm secondary"
                  type="button"
                  :disabled="busy"
                  @click="toggleActive(account)"
                >{{ account.is_active ? 'Disable' : 'Enable' }}</button>
                <button class="btn sm secondary" type="button" :disabled="busy" @click="resetPassword(account)">Reset Password</button>
                <button
                  v-if="account.email !== email"
                  class="btn sm danger"
                  type="button"
                  :disabled="busy"
                  @click="removeUser(account)"
                >Delete</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const { isAdmin, email } = useCurrentUser()
const users = ref<any[]>([])
const form = reactive({ email: '', full_name: '', password: '', role: 'Viewer' })
const busy = ref(false)
const error = ref('')
const message = ref('')

const load = async () => {
  try {
    users.value = await apiFetch('/users')
  } catch (e: any) {
    error.value = e?.data?.detail || e.message
  }
}

const run = async (task: () => Promise<void>, successMessage = '') => {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await task()
    if (successMessage) message.value = successMessage
    await load()
  } catch (e: any) {
    error.value = e?.data?.detail || e.message
  } finally {
    busy.value = false
  }
}

const createUser = () => run(async () => {
  await apiFetch('/users', { method: 'POST', body: { ...form } })
  Object.assign(form, { email: '', full_name: '', password: '', role: 'Viewer' })
}, 'User created.')

const changeRole = (account: any, role: string) => run(async () => {
  await apiFetch(`/users/${account.id}`, { method: 'PUT', body: { role } })
}, `${account.full_name} is now ${role}.`)

const toggleActive = (account: any) => run(async () => {
  await apiFetch(`/users/${account.id}`, { method: 'PUT', body: { is_active: !account.is_active } })
}, `${account.full_name} ${account.is_active ? 'disabled' : 'enabled'}.`)

const resetPassword = (account: any) => {
  const password = prompt(`New password for ${account.full_name}:`)
  if (!password) return
  return run(async () => {
    await apiFetch(`/users/${account.id}`, { method: 'PUT', body: { password } })
  }, `Password updated for ${account.full_name}.`)
}

const removeUser = (account: any) => {
  if (!confirm(`Delete user ${account.full_name} (${account.email})? This cannot be undone.`)) return
  return run(async () => {
    await apiFetch(`/users/${account.id}`, { method: 'DELETE' })
  }, 'User deleted.')
}

onMounted(load)
</script>
