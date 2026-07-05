<template>
  <div>
    <h1 class="page-title">Dashboard</h1>
    <div class="grid-cards">
      <StatCard label="Events Today" :value="stats.events_today" />
      <StatCard label="Staff Today" :value="stats.staff_today" />
      <StatCard label="Customers Today" :value="stats.customer_today" />
      <StatCard label="Unknown Today" :value="stats.unknown_today" />
      <StatCard label="Running Cameras" :value="`${stats.camera_running || 0}/${stats.camera_total || 0}`" />
    </div>

    <section class="card" style="margin-top: 1rem;">
      <h2 style="font-size: 1.15rem; font-weight: 800; margin-bottom: 1rem;">Realtime Walk-in Events</h2>
      <table class="table">
        <thead><tr><th>Time</th><th>Camera</th><th>Person</th><th>Type</th><th>Greeting</th><th>Confidence</th></tr></thead>
        <tbody>
          <tr v-for="event in events" :key="event.id">
            <td>{{ formatDate(event.detected_at) }}</td>
            <td>{{ event.camera_name || '-' }}</td>
            <td>{{ event.person_name || 'Unknown' }}</td>
            <td><span class="badge">{{ event.person_type }}</span></td>
            <td>{{ event.greeting }}</td>
            <td>{{ event.confidence ? Number(event.confidence).toFixed(3) : '-' }}</td>
          </tr>
        </tbody>
      </table>
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
