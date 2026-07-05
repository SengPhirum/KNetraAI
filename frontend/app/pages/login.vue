<template>
  <div style="display: grid; place-items: center; min-height: 90vh;">
    <div class="card" style="width: 100%; max-width: 420px;">
      <h1 class="page-title">Login</h1>
      <form @submit.prevent="login" style="display: grid; gap: 0.75rem;">
        <div>
          <label class="label">Email</label>
          <input v-model="email" class="input" type="email" autocomplete="username" />
        </div>
        <div>
          <label class="label">Password</label>
          <input v-model="password" class="input" type="password" autocomplete="current-password" />
        </div>
        <button class="btn" type="submit" :disabled="loading">{{ loading ? 'Logging in...' : 'Login' }}</button>
        <p v-if="error" class="error">{{ error }}</p>
        <p style="font-size: 0.85rem; color: #64748b;">Default: admin@example.com / admin123</p>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: false })
const { apiFetch, setToken } = useApi()
const email = ref('admin@example.com')
const password = ref('admin123')
const loading = ref(false)
const error = ref('')

const login = async () => {
  error.value = ''
  loading.value = true
  try {
    const result: any = await apiFetch('/auth/login', { method: 'POST', body: { email: email.value, password: password.value } })
    setToken(result.access_token)
    await navigateTo('/')
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>
