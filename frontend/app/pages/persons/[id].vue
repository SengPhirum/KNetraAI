<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ person?.full_name || 'Person Profile' }}</h1>
        <p v-if="person" class="page-subtitle" style="text-transform: capitalize;">{{ person.person_type }} profile and face enrollment.</p>
      </div>
      <NuxtLink to="/persons" class="btn secondary">Back</NuxtLink>
    </div>
    <div v-if="person" class="grid-cards">
      <div class="card">
        <h2 class="card-title">Profile</h2>
        <dl class="profile-list">
          <div><dt>Type</dt><dd style="text-transform: capitalize;">{{ person.person_type }}</dd></div>
          <div><dt>Gender</dt><dd style="text-transform: capitalize;">{{ person.gender }}</dd></div>
          <div><dt>Branch</dt><dd>{{ person.branch || '-' }}</dd></div>
          <div><dt>Status</dt><dd><span class="badge" :class="person.status === 'active' ? 'success' : ''">{{ person.status }}</span></dd></div>
          <div><dt>Consent</dt><dd><span class="badge" :class="person.consent_at ? 'success' : 'warning'">{{ person.consent_at ? 'Confirmed' : 'Not recorded' }}</span></dd></div>
        </dl>
      </div>
      <div class="card">
        <h2 class="card-title">Upload Face Image</h2>
        <input class="input" type="file" accept="image/*" @change="onFile" />
        <small class="hint">Use 3-5 clear, front-facing photos per person for best recognition.</small>
        <button class="btn" style="margin-top: 0.85rem;" @click="upload" :disabled="!file">Upload and Generate Embedding</button>
        <p v-if="message" class="notice" style="margin-top: 0.75rem;">{{ message }}</p>
      </div>
    </div>

    <section class="card" style="margin-top: 1.25rem;">
      <h2 class="card-title">Face Images</h2>
      <p v-if="!(person?.images || []).length" style="color: var(--text-muted); font-size: 0.9rem; margin: 0;">No face images enrolled yet.</p>
      <div class="grid-cards">
        <div v-for="image in person?.images || []" :key="image.id" class="card" style="padding: 0.75rem;">
          <img :src="`${apiBaseUrl}/files/${image.file_path}`" style="width: 100%; height: 180px; object-fit: cover; border-radius: 0.5rem;" />
          <p style="margin: 0.6rem 0 0; font-size: 0.85rem;">Quality: {{ image.quality_score ? Number(image.quality_score).toFixed(2) : '-' }}</p>
          <p class="truncate" style="max-width: 100%; font-size: 0.78rem; color: var(--text-muted); margin: 0.2rem 0 0;" :title="image.original_filename">{{ image.original_filename }}</p>
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

<style scoped>
.profile-list {
  margin: 0;
  display: grid;
  gap: 0.55rem;
}

.profile-list > div {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  font-size: 0.9rem;
}

.profile-list dt {
  color: var(--text-muted);
  font-weight: 600;
}

.profile-list dd {
  margin: 0;
  text-align: right;
}
</style>
