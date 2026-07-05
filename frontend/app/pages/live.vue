<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Live Camera Monitoring</h1>
        <p class="page-subtitle">Browsers cannot display RTSP directly. This MVP shows camera worker status and live detection events. Add HLS/WebRTC transcoding later for true browser playback.</p>
      </div>
    </div>
    <div class="grid-cards">
      <div v-if="!cameras.length" class="card" style="text-align: center; color: var(--text-muted);">
        No cameras configured yet. Add one in <NuxtLink to="/cameras">Camera Management</NuxtLink>.
      </div>
      <div v-for="camera in cameras" :key="camera.id" class="card">
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;">
          <h2 class="card-title" style="margin: 0;">{{ camera.name }}</h2>
          <span class="badge dot" :class="statusClass(camera.status)">{{ camera.status }}</span>
        </div>
        <p style="color: var(--text-muted); font-size: 0.85rem; margin: 0.35rem 0 0;">{{ camera.branch || '-' }} / {{ camera.location || '-' }}</p>
        <div class="preview">RTSP Preview Placeholder</div>
        <div class="btn-row" style="margin-top: 0.85rem;">
          <button class="btn sm" @click="start(camera.id)">Start AI</button>
          <button class="btn sm secondary" @click="stop(camera.id)">Stop AI</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const cameras = ref<any[]>([])
const load = async () => { cameras.value = await apiFetch('/cameras') }
const start = async (id: string) => { await apiFetch(`/cameras/${id}/start`, { method: 'POST' }); await load() }
const stop = async (id: string) => { await apiFetch(`/cameras/${id}/stop`, { method: 'POST' }); await load() }
const statusClass = (status: string) => status === 'running' ? 'success' : status === 'error' ? 'danger' : ''
onMounted(load)
</script>

<style scoped>
.preview {
  height: 160px;
  background: linear-gradient(135deg, #0f172a, #1e293b);
  color: #64748b;
  border-radius: 0.6rem;
  display: grid;
  place-items: center;
  margin-top: 0.85rem;
  font-size: 0.85rem;
}
</style>
