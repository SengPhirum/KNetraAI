<template>
  <div>
    <h1 class="page-title">Audit Logs</h1>
    <table class="table">
      <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Metadata</th></tr></thead>
      <tbody>
        <tr v-for="log in logs" :key="log.id">
          <td>{{ new Date(log.created_at).toLocaleString() }}</td>
          <td>{{ log.actor_email || '-' }}</td>
          <td>{{ log.action }}</td>
          <td>{{ log.entity_type }} {{ log.entity_id }}</td>
          <td><code>{{ log.metadata }}</code></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const logs = ref<any[]>([])
onMounted(async () => { logs.value = await apiFetch('/audit-logs') })
</script>
