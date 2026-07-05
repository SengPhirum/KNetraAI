<template>
  <div>
    <h1 class="page-title">Settings</h1>
    <div class="grid-cards">
      <div class="card">
        <h2 style="font-weight: 800; margin-bottom: 0.75rem;">AI Settings</h2>
        <div v-for="setting in settings" :key="setting.key" style="margin-bottom: 0.75rem;">
          <label class="label">{{ setting.key }}</label>
          <input v-model="setting.value" class="input" />
          <small>{{ setting.description }}</small><br />
          <button class="btn secondary" style="margin-top: 0.4rem;" @click="saveSetting(setting)">Save</button>
        </div>
      </div>
      <div class="card">
        <h2 style="font-weight: 800; margin-bottom: 0.75rem;">Greeting Templates</h2>
        <div v-for="template in templates" :key="template.language" style="display: grid; gap: 0.5rem; margin-bottom: 1rem;">
          <label class="label">Known</label><input v-model="template.known_template" class="input" />
          <label class="label">Male Unknown</label><input v-model="template.male_template" class="input" />
          <label class="label">Female Unknown</label><input v-model="template.female_template" class="input" />
          <label class="label">Neutral Unknown</label><input v-model="template.neutral_template" class="input" />
          <button class="btn secondary" @click="saveTemplate(template)">Save Template</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const settings = ref<any[]>([])
const templates = ref<any[]>([])
const load = async () => {
  settings.value = await apiFetch('/settings')
  templates.value = await apiFetch('/greeting-templates')
}
const saveSetting = async (setting: any) => { await apiFetch(`/settings/${setting.key}`, { method: 'PUT', body: { value: setting.value } }); await load() }
const saveTemplate = async (template: any) => { await apiFetch(`/greeting-templates/${template.language}`, { method: 'PUT', body: template }); await load() }
onMounted(load)
</script>
