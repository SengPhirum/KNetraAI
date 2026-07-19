<template>
  <div class="shell">
    <aside v-if="!isLogin" class="sidebar">
      <div class="brand">
        <img :src="logoSrc" :alt="appearance.app_name" class="brand-mark" />
        <div>
          <div class="brand-name">{{ appearance.app_name }}</div>
          <div class="brand-sub">Walk-in Greeting AI</div>
        </div>
      </div>
      <nav class="nav">
        <div v-for="group in nav" :key="group.label" class="nav-section">
          <div class="nav-group">{{ group.label }}</div>
          <NuxtLink v-for="item in group.items" :key="item.to" :to="item.to" class="nav-link">{{ item.label }}</NuxtLink>
        </div>
      </nav>
      <div class="sidebar-footer">
        <button class="btn secondary logout" @click="logout">Logout</button>
      </div>
    </aside>
    <main class="content" :class="{ 'content-login': isLogin }">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const { logout } = useApi()
const { appearance, logoSrc } = useAppearance()
const { role } = useCurrentUser()
const { attendanceEnabled, ensureLoaded } = useAttendanceStatus()
const isLogin = computed(() => route.path === '/login')

onMounted(() => { if (!isLogin.value) ensureLoaded() })
watch(isLogin, (login) => { if (!login) ensureLoaded() })

// roles: undefined = every signed-in role may open the page.
// attendance: true = only shown while attendance mode is enabled.
const allNav = [
  {
    label: 'Overview',
    items: [
      { to: '/', label: 'Dashboard' },
      { to: '/live', label: 'Live Monitoring' }
    ]
  },
  {
    label: 'Operations',
    items: [
      { to: '/cameras', label: 'Camera Management', roles: ['Admin', 'Manager', 'Operator'] },
      { to: '/fingerprints', label: 'Fingerprint Management', roles: ['Admin', 'Manager', 'Operator'], attendance: true },
      { to: '/persons', label: 'Staff/Customer Database' },
      { to: '/detection-history', label: 'Detection History' }
    ]
  },
  {
    label: 'Administration',
    items: [
      { to: '/settings', label: 'Settings', roles: ['Admin'] },
      { to: '/users', label: 'Users', roles: ['Admin', 'Manager'] },
      { to: '/audit-logs', label: 'Audit Logs', roles: ['Admin', 'Manager'] }
    ]
  }
]

const nav = computed(() =>
  allNav
    .map(group => ({
      ...group,
      items: group.items.filter((item: any) =>
        (!item.roles || item.roles.includes(role.value)) && (!item.attendance || attendanceEnabled.value)
      )
    }))
    .filter(group => group.items.length)
)
</script>

<style scoped>
.shell {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 260px;
  flex-shrink: 0;
  background: var(--sidebar);
  color: white;
  padding: 1.25rem 1rem;
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0 0.25rem 1.25rem;
}

.brand-mark {
  width: 2.25rem;
  height: 2.25rem;
  flex-shrink: 0;
}

.brand-name {
  font-weight: 800;
  font-size: 0.95rem;
  letter-spacing: 0;
}

.brand-sub {
  font-size: 0.72rem;
  color: #94a3b8;
}

.nav {
  flex: 1;
}

.nav-section {
  display: grid;
  gap: 0.2rem;
}

.nav-group {
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0;
  color: #64748b;
  padding: 0.9rem 0.75rem 0.3rem;
}

.nav-link {
  color: #cbd5e1;
  text-decoration: none;
  padding: 0.55rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  transition: background 0.15s, color 0.15s;
}

.nav-link:hover {
  background: rgba(255, 255, 255, 0.08);
  color: white;
}

.nav-link.router-link-active {
  background: rgba(59, 130, 246, 0.18);
  color: white;
  font-weight: 600;
}

.sidebar-footer {
  padding-top: 1rem;
}

.logout {
  width: 100%;
  background: transparent;
  color: #cbd5e1;
  border-color: #334155;
}

.logout:hover {
  background: rgba(255, 255, 255, 0.08);
  color: white;
}

.content {
  flex: 1;
  min-width: 0;
  padding: 1.75rem;
}

.content > :deep(div) {
  max-width: 1280px;
  margin: 0 auto;
}

.content-login {
  padding: 0;
}

.content-login > :deep(div) {
  max-width: none;
}

@media (max-width: 900px) {
  .shell {
    flex-direction: column;
  }

  .sidebar {
    width: 100%;
    height: auto;
    position: static;
    padding: 1rem;
  }

  .nav, .nav-section {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
  }

  .nav-group {
    display: none;
  }

  .sidebar-footer {
    padding-top: 0.75rem;
  }

  .content {
    padding: 1rem;
  }
}
</style>
