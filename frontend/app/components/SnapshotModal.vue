<template>
  <div v-if="event" class="snapshot-overlay" role="dialog" aria-modal="true" @click.self="$emit('close')">
    <div class="snapshot-dialog">
      <div class="snapshot-header">
        <div>
          <h2 class="snapshot-title">{{ event.camera_name || 'Camera snapshot' }}</h2>
          <p class="snapshot-meta">{{ formatDate(event.detected_at) }} · {{ event.person_name || 'Unknown' }}</p>
        </div>
        <button class="btn sm secondary" type="button" @click="$emit('close')">Close</button>
      </div>
      <img v-if="event.snapshot_path" :src="`${apiBaseUrl}/files/${event.snapshot_path}`" class="snapshot-image" />
      <div class="snapshot-details">
        <span class="badge" :class="typeClass(event.person_type)">{{ event.person_type || 'unknown' }}</span>
        <span>{{ event.greeting || '-' }}</span>
        <span v-if="event.confidence">Confidence {{ Number(event.confidence).toFixed(3) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ event: any | null; apiBaseUrl: string }>()
defineEmits<{ close: [] }>()

const formatDate = (value: string) => value ? new Date(value).toLocaleString() : '-'
const typeClass = (type: string) => type === 'staff' ? 'info' : type === 'customer' ? 'success' : 'warning'
</script>

<style scoped>
.snapshot-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 1rem;
  background: rgba(15, 23, 42, 0.72);
}

.snapshot-dialog {
  width: min(960px, 100%);
  max-height: min(860px, calc(100vh - 2rem));
  overflow: auto;
  background: var(--surface);
  border-radius: 0.75rem;
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.36);
}

.snapshot-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem;
  border-bottom: 1px solid var(--border);
}

.snapshot-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 800;
}

.snapshot-meta {
  margin: 0.2rem 0 0;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.snapshot-image {
  width: 100%;
  max-height: 70vh;
  object-fit: contain;
  display: block;
  background: #020617;
}

.snapshot-details {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  padding: 1rem;
  color: #334155;
  font-size: 0.9rem;
}
</style>
