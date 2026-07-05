<template>
  <div class="card stat-card">
    <div class="stat-label">{{ label }}</div>
    <div class="stat-value">{{ value ?? 0 }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ label: string, value: number | string | null | undefined }>()
</script>

<style scoped>
.stat-card {
  border-top: 3px solid var(--primary);
}

.stat-label {
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.stat-value {
  font-size: 1.9rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin-top: 0.3rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
