<template>
  <div style="display: flex; min-height: 100vh;">
    <aside v-if="!isLogin" style="width: 260px; background: #0f172a; color: white; padding: 1rem;">
      <h2 style="font-weight: 800; font-size: 1.2rem; margin-bottom: 1rem;">Vision AI System</h2>
      <nav style="display: grid; gap: 0.4rem;">
        <NuxtLink v-for="item in nav" :key="item.to" :to="item.to" class="nav-link">{{ item.label }}</NuxtLink>
      </nav>
      <button class="btn secondary" style="margin-top: 1rem; width: 100%;" @click="logout">Logout</button>
    </aside>
    <main style="flex: 1; padding: 1.5rem; overflow: auto;">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const { logout } = useApi()
const isLogin = computed(() => route.path === '/login')
const nav = [
  { to: '/', label: 'Dashboard' },
  { to: '/live', label: 'Live Monitoring' },
  { to: '/cameras', label: 'Camera Management' },
  { to: '/persons', label: 'Staff/Customer Database' },
  { to: '/detection-history', label: 'Detection History' },
  { to: '/settings', label: 'Settings' },
  { to: '/users', label: 'Users' },
  { to: '/audit-logs', label: 'Audit Logs' }
]
</script>

<style scoped>
.nav-link {
  color: white;
  text-decoration: none;
  padding: 0.65rem 0.75rem;
  border-radius: 0.5rem;
  opacity: 0.9;
}
.nav-link.router-link-active, .nav-link:hover {
  background: rgba(255,255,255,0.12);
  opacity: 1;
}
</style>
