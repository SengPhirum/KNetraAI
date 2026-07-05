<template>
  <div>
    <NuxtLink to="/persons" class="btn secondary">Back</NuxtLink>
    <h1 class="page-title" style="margin-top: 1rem;">{{ person?.full_name || 'Person Profile' }}</h1>
    <div v-if="person" class="grid-cards">
      <div class="card">
        <h2 style="font-weight: 800; margin-bottom: 0.75rem;">Profile</h2>
        <p><b>Type:</b> {{ person.person_type }}</p>
        <p><b>Gender:</b> {{ person.gender }}</p>
        <p><b>Branch:</b> {{ person.branch || '-' }}</p>
        <p><b>Status:</b> {{ person.status }}</p>
        <p><b>Consent:</b> {{ person.consent_at ? 'Confirmed' : 'Not recorded' }}</p>
      </div>
      <div class="card">
        <h2 style="font-weight: 800; margin-bottom: 0.75rem;">Upload Face Image</h2>
        <input class="input" type="file" accept="image/*" @change="onFile" />
        <button class="btn" style="margin-top: 0.75rem;" @click="upload" :disabled="!file">Upload and Generate Embedding</button>
        <p v-if="message" style="margin-top: 0.5rem;">{{ message }}</p>
      </div>
    </div>

    <section class="card" style="margin-top: 1rem;">
      <h2 style="font-weight: 800; margin-bottom: 0.75rem;">Face Images</h2>
      <div class="grid-cards">
        <div v-for="image in person?.images || []" :key="image.id" class="card">
          <img :src="`${apiBaseUrl}/files/${image.file_path}`" style="width: 100%; height: 180px; object-fit: cover; border-radius: 0.75rem;" />
          <p>Quality: {{ image.quality_score ? Number(image.quality_score).toFixed(2) : '-' }}</p>
          <p style="font-size: 0.8rem; color: #64748b;">{{ image.original_filename }}</p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const { apiFetch, apiBaseUrl } = useApi()
const person = ref<any>(null)
const file = ref<File | null>(null)
const message = ref('')
const load = async () => { person.value = await apiFetch(`/persons/${route.params.id}`) }
const onFile = (event: Event) => { file.value = (event.target as HTMLInputElement).files?.[0] || null }
const upload = async () => {
  if (!file.value) return
  const form = new FormData()
  form.append('file', file.value)
  message.value = 'Uploading...'
  const result: any = await apiFetch(`/persons/${route.params.id}/images`, { method: 'POST', body: form })
  message.value = result.embedding_status === 'created' ? 'Embedding created' : `Image saved but embedding failed: ${result.embedding_error}`
  file.value = null
  await load()
}
onMounted(load)
</script>
