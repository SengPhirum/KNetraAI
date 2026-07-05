<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Audit Logs</h1>
        <p class="page-subtitle">Chronological record of user and system actions.</p>
      </div>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Metadata</th></tr></thead>
        <tbody>
          <tr v-if="!logs.length"><td colspan="5" class="empty-row">No audit log entries yet.</td></tr>
          <tr v-for="log in logs" :key="log.id">
            <td style="white-space: nowrap;">{{ new Date(log.created_at).toLocaleString() }}</td>
            <td>{{ log.actor_email || '-' }}</td>
            <td><span class="badge">{{ log.action }}</span></td>
            <td>{{ log.entity_type }} {{ log.entity_id }}</td>
            <td style="max-width: 420px;"><code>{{ log.metadata }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const logs = ref<any[]>([])
onMounted(async () => { logs.value = await apiFetch('/audit-logs') })
</script>
