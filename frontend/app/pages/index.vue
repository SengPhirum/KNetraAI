<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Dashboard</h1>
        <p class="page-subtitle">Today's walk-in activity and camera status at a glance.</p>
      </div>
    </div>
    <div class="grid-cards">
      <StatCard label="Events Today" :value="stats.events_today" />
      <StatCard label="Staff Today" :value="stats.staff_today" />
      <StatCard label="Customers Today" :value="stats.customer_today" />
      <StatCard label="Unknown Today" :value="stats.unknown_today" />
      <StatCard label="Running Cameras" :value="`${stats.camera_running || 0}/${stats.camera_total || 0}`" />
    </div>

    <section class="card" style="margin-top: 1.25rem;">
      <h2 class="card-title">Realtime Walk-in Events</h2>
      <div class="table-wrap" style="box-shadow: none;">
        <table class="table">
          <thead><tr><th>Time</th><th>Camera</th><th>Person</th><th>Type</th><th>Greeting</th><th>Confidence</th></tr></thead>
          <tbody>
            <tr v-if="!events.length"><td colspan="6" class="empty-row">No detection events yet. Start a camera to begin monitoring.</td></tr>
            <tr v-for="event in events" :key="event.id">
              <td style="white-space: nowrap;">{{ formatDate(event.detected_at) }}</td>
              <td>{{ event.camera_name || '-' }}</td>
              <td>{{ event.person_name || 'Unknown' }}</td>
              <td><span class="badge" :class="typeClass(event.person_type)">{{ event.person_type }}</span></td>
              <td class="truncate" :title="event.greeting">{{ event.greeting }}</td>
              <td>{{ event.confidence ? Number(event.confidence).toFixed(3) : '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
const { apiFetch, apiBaseUrl, token } = useApi()
const stats = reactive<any>({})
const events = ref<any[]>([])
let source: EventSource | null = null

const load = async () => {
  Object.assign(stats, await apiFetch('/dashboard/stats'))
  events.value = await apiFetch('/detection-events?limit=20')
}

const formatDate = (value: string) => value ? new Date(value).toLocaleString() : '-'
const typeClass = (type: string) => type === 'staff' ? 'info' : type === 'customer' ? 'success' : 'warning'

onMounted(async () => {
  await load()
  if (token.value) {
    source = new EventSource(`${apiBaseUrl}/events/stream?token=${encodeURIComponent(token.value)}`)
    source.addEventListener('detection', (message: MessageEvent) => {
      const event = JSON.parse(message.data)
      events.value.unshift(event)
      events.value = events.value.slice(0, 50)
      load()
    })
  }
})

onBeforeUnmount(() => source?.close())
</script>
