<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Detection History</h1>
        <p class="page-subtitle">Recent walk-in detection events with snapshots and recognition results.</p>
      </div>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Time</th><th>Snapshot</th><th>Camera</th><th>Person</th><th>Type</th><th>Greeting</th><th>Gender</th><th>Confidence</th></tr></thead>
        <tbody>
          <tr v-if="!events.length"><td colspan="8" class="empty-row">No detection events recorded yet.</td></tr>
          <tr v-for="event in events" :key="event.id">
            <td style="white-space: nowrap;">{{ formatDate(event.detected_at) }}</td>
            <td><img v-if="event.snapshot_path" :src="`${apiBaseUrl}/files/${event.snapshot_path}`" class="thumb" /></td>
            <td>{{ event.camera_name || '-' }}</td>
            <td>{{ event.person_name || 'Unknown' }}</td>
            <td><span class="badge" :class="typeClass(event.person_type)">{{ event.person_type }}</span></td>
            <td class="truncate" :title="event.greeting">{{ event.greeting }}</td>
            <td style="text-transform: capitalize;">{{ event.gender_estimate || '-' }}</td>
            <td>{{ event.confidence ? Number(event.confidence).toFixed(3) : '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch, apiBaseUrl } = useApi()
const events = ref<any[]>([])
const formatDate = (value: string) => value ? new Date(value).toLocaleString() : '-'
const typeClass = (type: string) => type === 'staff' ? 'info' : type === 'customer' ? 'success' : 'warning'
onMounted(async () => { events.value = await apiFetch('/detection-events?limit=100') })
</script>
