<template>
  <div class="login-screen">
    <div class="card login-card">
      <div class="login-brand">
        <img :src="logoSrc" :alt="appearance.app_name" class="login-mark" />
        <div>
          <div style="font-weight: 800; font-size: 1.1rem; letter-spacing: -0.01em;">{{ appearance.app_name }}</div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">Walk-in Greeting AI</div>
        </div>
      </div>

      <div v-if="methods.ldap?.enabled" class="btn-row" style="margin-bottom: 1rem;">
        <button class="btn sm secondary" :class="{ active: mode === 'password' }" @click="mode = 'password'">Local account</button>
        <button class="btn sm secondary" :class="{ active: mode === 'ldap' }" @click="mode = 'ldap'">LDAP / Active Directory</button>
      </div>

      <form v-if="mode === 'password'" @submit.prevent="login" style="display: grid; gap: 0.85rem;">
        <div>
          <label class="label">Email</label>
          <input v-model="email" class="input" type="email" autocomplete="username" />
        </div>
        <div>
          <label class="label">Password</label>
          <input v-model="password" class="input" type="password" autocomplete="current-password" />
        </div>
        <button class="btn" type="submit" :disabled="loading">{{ loading ? 'Logging in...' : 'Login' }}</button>
      </form>

      <form v-else @submit.prevent="ldapLogin" style="display: grid; gap: 0.85rem;">
        <div>
          <label class="label">Username</label>
          <input v-model="ldapUsername" class="input" autocomplete="username" />
        </div>
        <div>
          <label class="label">Password</label>
          <input v-model="ldapPassword" class="input" type="password" autocomplete="current-password" />
        </div>
        <button class="btn" type="submit" :disabled="loading">{{ loading ? 'Logging in...' : 'Login with LDAP' }}</button>
      </form>

      <template v-if="methods.oidc?.enabled">
        <div class="divider"><span>or</span></div>
        <button class="btn secondary" style="width: 100%;" @click="ssoLogin">Continue with {{ methods.oidc.provider_name || 'SSO' }}</button>
      </template>

      <p v-if="error" class="error">{{ error }}</p>
      <p style="font-size: 0.8rem; color: var(--text-muted); margin: 1rem 0 0;">Default: admin@example.com / admin123</p>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: false })
const route = useRoute()
const { apiFetch, setToken, apiBaseUrl } = useApi()
const { appearance, logoSrc } = useAppearance()
const email = ref('admin@example.com')
const password = ref('admin123')
const ldapUsername = ref('')
const ldapPassword = ref('')
const mode = ref<'password' | 'ldap'>('password')
const loading = ref(false)
const error = ref('')
const methods = ref<any>({ password: true, oidc: { enabled: false }, ldap: { enabled: false } })

const finishLogin = async (result: any) => {
  setToken(result.access_token)
  await navigateTo('/')
}

const login = async () => {
  error.value = ''
  loading.value = true
  try {
    await finishLogin(await apiFetch('/auth/login', { method: 'POST', body: { email: email.value, password: password.value } }))
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Login failed'
  } finally {
    loading.value = false
  }
}

const ldapLogin = async () => {
  error.value = ''
  loading.value = true
  try {
    await finishLogin(await apiFetch('/auth/ldap/login', { method: 'POST', body: { username: ldapUsername.value, password: ldapPassword.value } }))
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'LDAP login failed'
  } finally {
    loading.value = false
  }
}

const ssoLogin = () => {
  window.location.href = `${apiBaseUrl}/auth/oidc/login`
}

onMounted(async () => {
  const ssoToken = route.query.sso_token as string | undefined
  const ssoError = route.query.sso_error as string | undefined
  if (ssoToken) {
    await finishLogin({ access_token: ssoToken })
    return
  }
  if (ssoError) error.value = ssoError
  try {
    methods.value = await apiFetch('/auth/methods')
  } catch {
    /* backend down - keep password form visible */
  }
})
</script>

<style scoped>
.login-screen {
  display: grid;
  place-items: center;
  min-height: 100vh;
  padding: 1rem;
  background: linear-gradient(160deg, #0f172a 0%, #1e293b 55%, #1E90FF 140%);
}

.login-card {
  width: 100%;
  max-width: 400px;
  padding: 1.75rem;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.login-mark {
  width: 2.75rem;
  height: 2.75rem;
}

.divider {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: var(--text-muted);
  font-size: 0.78rem;
  margin: 1rem 0;
}

.divider::before, .divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--border);
}
</style>
