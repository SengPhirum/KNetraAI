<template>
  <div>
    <h1 class="page-title">Detection History</h1>
    <table class="table">
      <thead><tr><th>Time</th><th>Snapshot</th><th>Camera</th><th>Person</th><th>Type</th><th>Greeting</th><th>Gender</th><th>Confidence</th></tr></thead>
      <tbody>
        <tr v-for="event in events" :key="event.id">
          <td>{{ formatDate(event.detected_at) }}</td>
          <td><img v-if="event.snapshot_path" :src="`${apiBaseUrl}/files/${event.snapshot_path}`" style="width: 72px; height: 48px; object-fit: cover; border-radius: 0.35rem;" /></td>
          <td>{{ event.camera_name || '-' }}</td>
          <td>{{ event.person_name || 'Unknown' }}</td>
          <td><span class="badge">{{ event.person_type }}</span></td>
          <td>{{ event.greeting }}</td>
          <td>{{ event.gender_estimate || '-' }}</td>
          <td>{{ event.confidence ? Number(event.confidence).toFixed(3) : '-' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
const { apiFetch, apiBaseUrl } = useApi()
const events = ref<any[]>([])
const formatDate = (value: string) => value ? new Date(value).toLocaleString() : '-'
onMounted(async () => { events.value = await apiFetch('/detection-events?limit=100') })
</script>
