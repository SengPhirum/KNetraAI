<template>
  <div>
    <h1 class="page-title">Live Camera Monitoring</h1>
    <p style="color: #64748b; margin-bottom: 1rem;">Browsers cannot display RTSP directly. This MVP shows camera worker status and live detection events. Add HLS/WebRTC transcoding later for true browser playback.</p>
    <div class="grid-cards">
      <div v-for="camera in cameras" :key="camera.id" class="card">
        <h2 style="font-weight: 800;">{{ camera.name }}</h2>
        <p>{{ camera.branch || '-' }} / {{ camera.location || '-' }}</p>
        <p><span class="badge">{{ camera.status }}</span></p>
        <div style="height: 160px; background: #0f172a; color: white; border-radius: 0.75rem; display: grid; place-items: center; margin-top: 0.75rem;">RTSP Preview Placeholder</div>
        <div style="display: flex; gap: 0.4rem; margin-top: 0.75rem;">
          <button class="btn" @click="start(camera.id)">Start AI</button>
          <button class="btn secondary" @click="stop(camera.id)">Stop AI</button>
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
onMounted(load)
</script>
