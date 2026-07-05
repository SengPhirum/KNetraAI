<template>
  <div>
    <h1 class="page-title">Camera Management</h1>
    <div class="card" style="margin-bottom: 1rem;">
      <h2 style="font-weight: 800; margin-bottom: 0.75rem;">Add Camera</h2>
      <form class="form-grid" @submit.prevent="createCamera">
        <div><label class="label">Name</label><input v-model="form.name" class="input" required /></div>
        <div><label class="label">Branch</label><input v-model="form.branch" class="input" /></div>
        <div><label class="label">Location</label><input v-model="form.location" class="input" /></div>
        <div style="grid-column: 1 / -1;"><label class="label">RTSP URL</label><input v-model="form.rtsp_url" class="input" placeholder="rtsp://user:pass@ip:554/stream" required /></div>
        <button class="btn" type="submit">Add Camera</button>
      </form>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <table class="table">
      <thead><tr><th>Name</th><th>Branch</th><th>Location</th><th>Status</th><th>RTSP</th><th>Actions</th></tr></thead>
      <tbody>
        <tr v-for="camera in cameras" :key="camera.id">
          <td>{{ camera.name }}</td>
          <td>{{ camera.branch || '-' }}</td>
          <td>{{ camera.location || '-' }}</td>
          <td><span class="badge">{{ camera.status }}</span></td>
          <td style="max-width: 380px; overflow: hidden; text-overflow: ellipsis;">{{ camera.rtsp_url }}</td>
          <td style="display: flex; gap: 0.4rem;">
            <button class="btn" @click="start(camera.id)">Start</button>
            <button class="btn secondary" @click="stop(camera.id)">Stop</button>
            <button class="btn danger" @click="remove(camera.id)">Delete</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const cameras = ref<any[]>([])
const error = ref('')
const form = reactive({ name: '', branch: '', location: '', rtsp_url: '' })

const load = async () => { cameras.value = await apiFetch('/cameras') }
const createCamera = async () => {
  error.value = ''
  try {
    await apiFetch('/cameras', { method: 'POST', body: form })
    Object.assign(form, { name: '', branch: '', location: '', rtsp_url: '' })
    await load()
  } catch (e: any) { error.value = e?.data?.detail || e.message }
}
const start = async (id: string) => { await apiFetch(`/cameras/${id}/start`, { method: 'POST' }); await load() }
const stop = async (id: string) => { await apiFetch(`/cameras/${id}/stop`, { method: 'POST' }); await load() }
const remove = async (id: string) => { if (confirm('Delete camera?')) { await apiFetch(`/cameras/${id}`, { method: 'DELETE' }); await load() } }
onMounted(load)
</script>
