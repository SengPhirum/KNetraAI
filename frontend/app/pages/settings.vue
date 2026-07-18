<template>
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">Settings</h1>
        <p class="page-subtitle">Configure recognition, branding, detection, and sign-in for the whole system.</p>
      </div>
    </div>

    <div class="tabs">
      <button v-for="tab in tabs" :key="tab.id" class="tab" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">
        {{ tab.label }}
      </button>
    </div>

    <!-- ============================ GENERAL ============================ -->
    <div v-show="activeTab === 'general'" class="settings-grid">
      <div class="card">
        <h2 class="card-title">AI Recognition</h2>
        <div class="setting-row">
          <label class="label">Recognition threshold: {{ Number(generalForm.recognition_threshold).toFixed(2) }}</label>
          <input v-model.number="generalForm.recognition_threshold" type="range" min="0.2" max="0.9" step="0.01" class="range-input" />
          <small class="hint">Minimum cosine similarity to accept a face match. Higher = stricter (fewer false matches, more misses).</small>
        </div>
        <div class="setting-row">
          <label class="label">Gender confidence: {{ Number(generalForm.gender_min_confidence).toFixed(2) }}</label>
          <input v-model.number="generalForm.gender_min_confidence" type="range" min="0.3" max="0.95" step="0.01" class="range-input" />
          <small class="hint">Minimum confidence before greeting an unknown person as sir/madam instead of the neutral greeting.</small>
        </div>
        <div class="setting-row">
          <label class="label">Greeting cooldown (seconds)</label>
          <input v-model.number="generalForm.greeting_cooldown_seconds" type="number" min="0" class="input" style="max-width: 140px;" />
          <small class="hint">Minimum time before the same person can trigger a new greeting event.</small>
        </div>
        <div class="setting-row">
          <label class="label">Left-the-zone time (seconds)</label>
          <input v-model.number="generalForm.presence_absence_seconds" type="number" min="5" class="input" style="max-width: 140px;" />
          <small class="hint">
            A person is greeted once per visit. While they stay in front of a camera they are tracked and never
            re-greeted; only after being out of view this long do they count as having left, so a later return
            (past the cooldown) greets them again. Prevents repeated announcements for someone standing in the zone.
          </small>
        </div>
        <button class="btn" :disabled="savingGeneral" @click="saveGeneral">{{ savingGeneral ? 'Saving...' : 'Save Recognition Settings' }}</button>
        <p v-if="generalMessage" class="notice" style="margin-top: 0.75rem;">{{ generalMessage }}</p>
      </div>

      <div class="card">
        <h2 class="card-title">Detection History Storage</h2>
        <p class="section-text">Minimum criteria before a detection is saved to history. Below-criteria faces are still tracked and greeted live, but not stored.</p>
        <div class="setting-row">
          <label class="label">Minimum face capture: {{ Math.round(generalForm.min_face_capture * 100) }}%</label>
          <input v-model.number="generalForm.min_face_capture" type="range" min="0" max="1" step="0.05" class="range-input" />
          <small class="hint">How much of the face must be captured (visibility inside the frame x detection quality). Default 75%.</small>
        </div>
        <label class="checkbox-label">
          <input v-model="generalForm.require_gender_or_person" type="checkbox" />
          Require the person to be recognized OR a gender to be estimated
        </label>
        <small class="hint" style="margin-bottom: 0.85rem;">When on, anonymous faces with no recognition result and no confident gender estimate are not stored.</small>
        <div class="setting-row">
          <label class="label">Auto-delete history after (days)</label>
          <input v-model.number="generalForm.retention_days" type="number" min="0" class="input" style="max-width: 140px;" />
          <small class="hint">Detection events and snapshots older than this are deleted automatically. 0 = keep forever.</small>
        </div>
        <button class="btn" :disabled="savingGeneral" @click="saveGeneral">{{ savingGeneral ? 'Saving...' : 'Save Storage Settings' }}</button>
      </div>

      <div class="card">
        <h2 class="card-title">Voice Greeting (AI Speak)</h2>
        <p class="section-text">
          Speaks greetings aloud ("Hello sir", "Welcome back, ...") on the Live Monitoring page of the device
          playing audio - keep that page open on the machine connected to the speaker.
        </p>
        <label class="checkbox-label"><input v-model="voiceForm.enabled" type="checkbox" /> Enable voice greeting</label>
        <label class="checkbox-label"><input v-model="voiceForm.greet_known" type="checkbox" /> Speak for recognized people</label>
        <label class="checkbox-label"><input v-model="voiceForm.greet_unknown" type="checkbox" /> Speak for unknown people (sir/madam/neutral)</label>
        <div class="setting-row" style="margin-top: 0.5rem;">
          <label class="label">Do not repeat the same greeting within (seconds)</label>
          <input v-model.number="voiceForm.repeat_seconds" type="number" min="5" class="input" style="max-width: 140px;" />
          <small class="hint">Extra per-device guard on top of the zone tracking above, so refreshes/reconnects stay quiet.</small>
        </div>
        <div class="setting-row">
          <label class="label">Audio output device (this device only)</label>
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            <select v-model="selectedOutputId" style="flex: 1; min-width: 180px;">
              <option value="">System default output</option>
              <option v-for="device in outputDevices" :key="device.deviceId" :value="device.deviceId">{{ device.label }}</option>
            </select>
            <button class="btn sm secondary" type="button" @click="refreshOutputDevices">Detect devices</button>
          </div>
          <small class="hint">
            Choose which connected speaker plays the AI voice. Saved per browser/device.
            <template v-if="!sinkSupported">Your browser does not support output routing - the system default is used.</template>
          </small>
        </div>
        <div class="setting-row">
          <label class="label">Voice</label>
          <select v-model="voiceForm.voice_name">
            <option value="">Browser default voice</option>
            <option v-for="voice in browserVoices" :key="voice.name" :value="voice.name">{{ voice.name }} ({{ voice.lang }})</option>
          </select>
          <small class="hint">Used for browser speech. When a specific output device is selected, the server voice is used instead so audio can be routed.</small>
        </div>
        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
          <div class="setting-row" style="flex: 1; min-width: 150px;">
            <label class="label">Rate: {{ Number(voiceForm.rate).toFixed(2) }}</label>
            <input v-model.number="voiceForm.rate" type="range" min="0.5" max="2" step="0.05" class="range-input" />
          </div>
          <div class="setting-row" style="flex: 1; min-width: 150px;">
            <label class="label">Volume: {{ Math.round(voiceForm.volume * 100) }}%</label>
            <input v-model.number="voiceForm.volume" type="range" min="0" max="1" step="0.05" class="range-input" />
          </div>
        </div>
        <div class="btn-row">
          <button class="btn" :disabled="savingVoice" @click="saveVoice">{{ savingVoice ? 'Saving...' : 'Save Voice Settings' }}</button>
          <button class="btn secondary" type="button" @click="testVoice">Test Voice</button>
        </div>
        <p v-if="voiceMessage" class="notice" style="margin-top: 0.75rem;">{{ voiceMessage }}</p>
      </div>

      <div class="card">
        <h2 class="card-title">Greeting Templates</h2>
        <div v-for="template in templates" :key="template.language" style="display: grid; gap: 0.6rem; margin-bottom: 1rem;">
          <div><label class="label">Known</label><input v-model="template.known_template" class="input" /></div>
          <div><label class="label">Male Unknown</label><input v-model="template.male_template" class="input" /></div>
          <div><label class="label">Female Unknown</label><input v-model="template.female_template" class="input" /></div>
          <div><label class="label">Neutral Unknown</label><input v-model="template.neutral_template" class="input" /></div>
          <div><button class="btn secondary" @click="saveTemplate(template)">Save Template</button></div>
        </div>
      </div>

      <div v-if="advancedSettings.length" class="card">
        <h2 class="card-title">Advanced</h2>
        <p class="section-text">Raw settings not covered by the cards above.</p>
        <div v-for="setting in advancedSettings" :key="setting.key" class="setting-row">
          <label class="label">{{ setting.key }}</label>
          <div style="display: flex; gap: 0.5rem;">
            <input v-model="setting.value" class="input" />
            <button class="btn secondary" @click="saveSetting(setting)">Save</button>
          </div>
          <small class="hint">{{ setting.description }}</small>
        </div>
      </div>
    </div>

    <!-- ============================ APPEARANCE ============================ -->
    <div v-show="activeTab === 'appearance'" class="settings-grid">
      <div class="card">
        <h2 class="card-title">Branding</h2>
        <div class="setting-row">
          <label class="label">Application name</label>
          <input v-model="appearanceForm.app_name" class="input" />
        </div>
        <div class="setting-row">
          <label class="label">Primary color</label>
          <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
            <input v-model="appearanceForm.primary_color" type="color" class="color-input" />
            <input v-model="appearanceForm.primary_color" class="input" style="max-width: 130px;" />
            <span class="hint" style="margin: 0;">Buttons and accents (default dodgerblue)</span>
          </div>
        </div>
        <div class="setting-row">
          <label class="label">Secondary color</label>
          <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
            <input v-model="appearanceForm.secondary_color" type="color" class="color-input" />
            <input v-model="appearanceForm.secondary_color" class="input" style="max-width: 130px;" />
            <span class="hint" style="margin: 0;">Sidebar and dark surfaces</span>
          </div>
        </div>
        <div class="setting-row">
          <label class="label">App logo</label>
          <div style="display: flex; gap: 0.75rem; align-items: center;">
            <img :src="logoSrc" alt="logo" style="width: 44px; height: 44px; border-radius: 0.6rem; border: 1px solid var(--border);" />
            <input class="input" type="file" accept=".png,.svg,.jpg,.jpeg,.webp" @change="onLogoFile" />
          </div>
          <small class="hint">PNG, SVG, JPG, or WebP. Square images look best. Leave unchanged to keep the built-in logo.</small>
        </div>
        <div class="btn-row">
          <button class="btn" :disabled="savingAppearance" @click="saveAppearance">{{ savingAppearance ? 'Saving...' : 'Save Appearance' }}</button>
          <button class="btn secondary" @click="resetAppearance">Reset to defaults</button>
        </div>
        <p v-if="appearanceMessage" class="notice" style="margin-top: 0.75rem;">{{ appearanceMessage }}</p>
      </div>
    </div>

    <!-- ============================ DETECTION ============================ -->
    <div v-show="activeTab === 'detection'" class="settings-grid">
      <div class="card">
        <h2 class="card-title">Deep Learning Provider</h2>
        <p class="section-text">
          Active provider:
          <span class="badge" :class="providerInfo.reachable ? (isDeepLearning ? 'success' : 'warning') : 'danger'">
            {{ providerInfo.reachable ? providerInfo.provider : 'AI service unreachable' }}
          </span>
        </p>
        <p class="section-text" v-if="!isDeepLearning">
          The system is running the lightweight OpenCV development provider. It keeps the app runnable without
          large models, but it is <strong>not reliable CCTV face detection</strong>. Use InsightFace for production.
        </p>
        <details>
          <summary class="details-title">Production checklist</summary>
          <ol class="details-list">
            <li>In your <code>.env</code>, set <code>AI_PROVIDER=yolo_cascade</code> (recommended: fast YOLO12 person detection narrows the frame down before the accurate InsightFace stage runs) and <code>ALLOW_PROVIDER_FALLBACK=false</code>.</li>
            <li>Rebuild the AI service so its Docker image includes the exported YOLO model: <code>docker compose up -d --build ai-service</code>.</li>
            <li>The first start downloads the InsightFace model weights (several hundred MB); watch <code>docker logs knetraai-service</code>.</li>
            <li>This card should show a <code>yolo_person_cascade+insightface_...</code> provider. If it instead shows <code>insightface_...</code>, the cascade fell back to plain InsightFace - check the ai-service logs for why the YOLO model wasn't found.</li>
            <li>Have an NVIDIA GPU? Build with <code>docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build ai-service</code> to enable CUDA acceleration.</li>
          </ol>
        </details>
      </div>

      <div class="card">
        <h2 class="card-title">Detection Schedule</h2>
        <p class="section-text">When enabled, detection events are only recorded inside this window (server time). Outside it, camera workers keep running but events and greetings are suppressed.</p>
        <label class="checkbox-label">
          <input v-model="scheduleForm.enabled" type="checkbox" />
          Enable detection schedule
        </label>
        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
          <div>
            <label class="label">Start time</label>
            <input v-model="scheduleForm.start_time" type="time" class="input" />
          </div>
          <div>
            <label class="label">End time</label>
            <input v-model="scheduleForm.end_time" type="time" class="input" />
          </div>
        </div>
        <label class="label" style="margin-top: 0.75rem;">Active days</label>
        <div class="btn-row" style="margin-bottom: 1rem;">
          <button v-for="day in allDays" :key="day" class="btn sm secondary" :class="{ active: scheduleForm.days.includes(day) }" @click="toggleDay(day)">
            {{ day.charAt(0).toUpperCase() + day.slice(1) }}
          </button>
        </div>
        <button class="btn" :disabled="savingSchedule" @click="saveSchedule">{{ savingSchedule ? 'Saving...' : 'Save Schedule' }}</button>
        <p v-if="scheduleMessage" class="notice" style="margin-top: 0.75rem;">{{ scheduleMessage }}</p>
      </div>
    </div>

    <!-- ============================ AUTHENTICATION ============================ -->
    <div v-show="activeTab === 'authentication'" class="settings-grid">
      <!-- Local -->
      <div class="card">
        <div class="auth-card-header">
          <h2 class="card-title" style="margin: 0;">Local Accounts</h2>
          <span class="badge dot" :class="authForm.local.enabled ? 'success' : ''">{{ authForm.local.enabled ? 'Enabled' : 'Disabled' }}</span>
        </div>
        <p class="section-text">Email/password accounts managed on the Users page.</p>
        <label class="checkbox-label">
          <input v-model="authForm.local.enabled" type="checkbox" />
          Enable local password login
        </label>
        <p v-if="!authForm.local.enabled" class="section-text" style="color: var(--warning);">
          At least one other method must be enabled, or saving will be rejected - otherwise everyone is locked out.
        </p>
        <h3 class="subheading">Password rules</h3>
        <div class="setting-row">
          <label class="label">Minimum length</label>
          <input v-model.number="authForm.local.password_min_length" type="number" min="4" max="128" class="input" style="max-width: 120px;" />
        </div>
        <label class="checkbox-label"><input v-model="authForm.local.password_require_uppercase" type="checkbox" /> Require an uppercase letter</label>
        <label class="checkbox-label"><input v-model="authForm.local.password_require_lowercase" type="checkbox" /> Require a lowercase letter</label>
        <label class="checkbox-label"><input v-model="authForm.local.password_require_digit" type="checkbox" /> Require a digit</label>
        <label class="checkbox-label"><input v-model="authForm.local.password_require_special" type="checkbox" /> Require a special character</label>
        <small class="hint" style="margin-bottom: 0.75rem;">Rules apply when creating users or changing passwords; existing passwords are not affected.</small>
        <button class="btn" :disabled="savingAuth" @click="saveAuth('local')">{{ savingAuth === 'local' ? 'Saving...' : 'Save Local Settings' }}</button>
      </div>

      <!-- OIDC -->
      <div class="card">
        <div class="auth-card-header">
          <h2 class="card-title" style="margin: 0;">OIDC Single Sign-On</h2>
          <span class="badge dot" :class="authForm.oidc.enabled ? 'success' : ''">{{ authForm.oidc.enabled ? 'Enabled' : 'Disabled' }}</span>
        </div>
        <p class="section-text">Keycloak, Authentik, or any OpenID Connect provider. Changes apply immediately - no restart needed.</p>
        <label class="checkbox-label">
          <input v-model="authForm.oidc.enabled" type="checkbox" />
          Enable OIDC login
        </label>
        <div class="setting-row">
          <label class="label">Provider name (login button label)</label>
          <input v-model="authForm.oidc.provider_name" class="input" placeholder="Keycloak" />
        </div>
        <div class="setting-row">
          <label class="label">Issuer URL</label>
          <input v-model="authForm.oidc.issuer" class="input" placeholder="https://keycloak.example.com/realms/main" />
        </div>
        <div class="setting-row">
          <label class="label">Client ID</label>
          <input v-model="authForm.oidc.client_id" class="input" placeholder="knetraai" />
        </div>
        <div class="setting-row">
          <label class="label">Client secret</label>
          <input v-model="authForm.oidc.client_secret" type="password" class="input" :placeholder="authForm.oidc.client_secret_set ? '******** (saved - leave blank to keep)' : ''" />
        </div>
        <div class="setting-row">
          <label class="label">Scopes</label>
          <input v-model="authForm.oidc.scopes" class="input" />
        </div>
        <div class="setting-row">
          <label class="label">Default role for new SSO users</label>
          <select v-model="authForm.oidc.default_role"><option>Admin</option><option>Manager</option><option>Operator</option><option>Viewer</option></select>
        </div>
        <label class="checkbox-label">
          <input v-model="authForm.oidc.auto_create_users" type="checkbox" />
          Auto-create users on first SSO login
        </label>
        <p class="section-text">Redirect URI to register at the provider: <code>{{ authForm.oidc.redirect_uri }}</code></p>
        <button class="btn" :disabled="savingAuth" @click="saveAuth('oidc')">{{ savingAuth === 'oidc' ? 'Saving...' : 'Save OIDC Settings' }}</button>

        <details style="margin-top: 1rem;">
          <summary class="details-title">Keycloak - step by step</summary>
          <ol class="details-list">
            <li>Admin console → your realm → <strong>Clients → Create client</strong> (OpenID Connect, ID <code>knetraai</code>).</li>
            <li>Enable <strong>Client authentication</strong> and keep <strong>Standard flow</strong> checked.</li>
            <li>Valid redirect URIs: <code>{{ authForm.oidc.redirect_uri }}</code>; Web origins: your frontend URL.</li>
            <li>Copy the secret from the <strong>Credentials</strong> tab into the form above.</li>
            <li>Issuer URL: <code>https://&lt;keycloak-host&gt;/realms/&lt;realm&gt;</code>. Ensure users have an email set.</li>
          </ol>
        </details>
        <details>
          <summary class="details-title">Authentik - step by step</summary>
          <ol class="details-list">
            <li><strong>Applications → Providers → Create → OAuth2/OpenID Provider</strong> (Confidential) with redirect URI <code>{{ authForm.oidc.redirect_uri }}</code>.</li>
            <li>Create an <strong>Application</strong> with slug <code>knetraai</code> linked to the provider.</li>
            <li>Issuer URL: <code>https://&lt;authentik-host&gt;/application/o/knetraai/</code>.</li>
            <li>Copy the Client ID and Client Secret into the form above.</li>
          </ol>
        </details>
      </div>

      <!-- LDAP -->
      <div class="card">
        <div class="auth-card-header">
          <h2 class="card-title" style="margin: 0;">LDAP / Active Directory</h2>
          <span class="badge dot" :class="authForm.ldap.enabled ? 'success' : ''">{{ authForm.ldap.enabled ? 'Enabled' : 'Disabled' }}</span>
        </div>
        <p class="section-text">Users sign in with their directory credentials and are provisioned on first login.</p>
        <label class="checkbox-label">
          <input v-model="authForm.ldap.enabled" type="checkbox" />
          Enable LDAP login
        </label>
        <div class="setting-row">
          <label class="label">Server URL</label>
          <input v-model="authForm.ldap.server_url" class="input" placeholder="ldaps://ad.example.com:636" />
        </div>
        <div class="setting-row">
          <label class="label">User DN template (direct bind - option A)</label>
          <input v-model="authForm.ldap.user_dn_template" class="input" placeholder="uid={username},ou=users,dc=example,dc=org" />
          <small class="hint">Leave empty to use search + bind below (typical for Active Directory).</small>
        </div>
        <div class="setting-row">
          <label class="label">Bind DN (service account - option B)</label>
          <input v-model="authForm.ldap.bind_dn" class="input" placeholder="cn=svc-knetraai,ou=service,dc=example,dc=org" />
        </div>
        <div class="setting-row">
          <label class="label">Bind password</label>
          <input v-model="authForm.ldap.bind_password" type="password" class="input" :placeholder="authForm.ldap.bind_password_set ? '******** (saved - leave blank to keep)' : ''" />
        </div>
        <div class="setting-row">
          <label class="label">Search base</label>
          <input v-model="authForm.ldap.search_base" class="input" placeholder="ou=users,dc=example,dc=org" />
        </div>
        <div class="setting-row">
          <label class="label">User filter</label>
          <input v-model="authForm.ldap.user_filter" class="input" />
          <small class="hint">The default matches uid, sAMAccountName, or mail. <code>{username}</code> is replaced with the login name.</small>
        </div>
        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
          <div class="setting-row" style="flex: 1; min-width: 140px;">
            <label class="label">Email attribute</label>
            <input v-model="authForm.ldap.email_attribute" class="input" />
          </div>
          <div class="setting-row" style="flex: 1; min-width: 140px;">
            <label class="label">Name attribute</label>
            <input v-model="authForm.ldap.name_attribute" class="input" />
          </div>
        </div>
        <div class="setting-row">
          <label class="label">Default role for new LDAP users</label>
          <select v-model="authForm.ldap.default_role"><option>Admin</option><option>Manager</option><option>Operator</option><option>Viewer</option></select>
        </div>
        <button class="btn" :disabled="savingAuth" @click="saveAuth('ldap')">{{ savingAuth === 'ldap' ? 'Saving...' : 'Save LDAP Settings' }}</button>
      </div>

      <div v-if="authMessage" class="notice" style="grid-column: 1 / -1;">{{ authMessage }}</div>
      <p v-if="authError" class="error" style="grid-column: 1 / -1; margin: 0;">{{ authError }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch, apiBaseUrl } = useApi()
const { logoSrc, refresh: refreshAppearance } = useAppearance()

const tabs = [
  { id: 'general', label: 'General' },
  { id: 'appearance', label: 'Appearance' },
  { id: 'detection', label: 'Detection' },
  { id: 'authentication', label: 'Authentication' }
]
const activeTab = ref('general')

const settings = ref<any[]>([])
const templates = ref<any[]>([])
const providerInfo = ref<any>({ reachable: false, provider: null })

const appearanceForm = reactive({ app_name: 'KNetraAI', primary_color: '#1E90FF', secondary_color: '#0f172a' })
const logoFile = ref<File | null>(null)
const savingAppearance = ref(false)
const appearanceMessage = ref('')

const allDays = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
const scheduleForm = reactive({ enabled: false, start_time: '08:00', end_time: '20:00', days: [...allDays] })
const savingSchedule = ref(false)
const scheduleMessage = ref('')

const authForm = reactive<any>({
  local: { enabled: true, password_min_length: 8, password_require_uppercase: false, password_require_lowercase: false, password_require_digit: false, password_require_special: false },
  oidc: { enabled: false, issuer: '', client_id: '', client_secret: '', client_secret_set: false, scopes: 'openid profile email', provider_name: 'SSO', default_role: 'Viewer', auto_create_users: true, redirect_uri: '' },
  ldap: { enabled: false, server_url: '', user_dn_template: '', bind_dn: '', bind_password: '', bind_password_set: false, search_base: '', user_filter: '(|(uid={username})(sAMAccountName={username})(mail={username}))', email_attribute: 'mail', name_attribute: 'cn', default_role: 'Viewer' }
})
const savingAuth = ref('')
const authMessage = ref('')
const authError = ref('')

const GENERAL_KEYS = [
  'recognition_threshold', 'gender_min_confidence', 'greeting_cooldown_seconds',
  'presence.absence_seconds', 'detection.min_face_capture', 'detection.require_gender_or_person',
  'retention.days', 'person_api.config'
]
const advancedSettings = computed(() =>
  settings.value.filter(s =>
    !s.key.startsWith('appearance.') && !s.key.startsWith('schedule.') && !s.key.startsWith('auth.')
    && !s.key.startsWith('voice.') && !GENERAL_KEYS.includes(s.key)
  )
)

const generalForm = reactive({
  recognition_threshold: 0.45,
  gender_min_confidence: 0.6,
  greeting_cooldown_seconds: 300,
  presence_absence_seconds: 30,
  min_face_capture: 0.75,
  require_gender_or_person: true,
  retention_days: 0
})
const savingGeneral = ref(false)
const generalMessage = ref('')

const voiceForm = reactive({
  enabled: false,
  greet_known: true,
  greet_unknown: true,
  repeat_seconds: 60,
  rate: 1.0,
  volume: 1.0,
  voice_name: ''
})
const savingVoice = ref(false)
const voiceMessage = ref('')

const voiceGreeter = useVoiceGreeter()
const outputDevices = ref<Array<{ deviceId: string, label: string }>>([])
const selectedOutputId = ref(voiceGreeter.outputDeviceId.value)
const browserVoices = ref<SpeechSynthesisVoice[]>([])
const sinkSupported = ref(true)

const isDeepLearning = computed(() =>
  providerInfo.value.reachable && !String(providerInfo.value.provider || '').startsWith('opencv_mock')
)

const settingValue = (key: string, fallback: string) =>
  settings.value.find(s => s.key === key)?.value ?? fallback

const parseBool = (value: string) => ['1', 'true', 'yes'].includes(value.toLowerCase())

const load = async () => {
  settings.value = await apiFetch('/settings')
  templates.value = await apiFetch('/greeting-templates')
  appearanceForm.app_name = settingValue('appearance.app_name', 'KNetraAI')
  appearanceForm.primary_color = settingValue('appearance.primary_color', '#1E90FF')
  appearanceForm.secondary_color = settingValue('appearance.secondary_color', '#0f172a')
  scheduleForm.enabled = parseBool(settingValue('schedule.enabled', 'false'))
  scheduleForm.start_time = settingValue('schedule.start_time', '08:00')
  scheduleForm.end_time = settingValue('schedule.end_time', '20:00')
  scheduleForm.days = settingValue('schedule.days', allDays.join(',')).split(',').map((d: string) => d.trim()).filter(Boolean)

  generalForm.recognition_threshold = Number(settingValue('recognition_threshold', '0.45'))
  generalForm.gender_min_confidence = Number(settingValue('gender_min_confidence', '0.6'))
  generalForm.greeting_cooldown_seconds = Number(settingValue('greeting_cooldown_seconds', '300'))
  generalForm.presence_absence_seconds = Number(settingValue('presence.absence_seconds', '30'))
  generalForm.min_face_capture = Number(settingValue('detection.min_face_capture', '0.75'))
  generalForm.require_gender_or_person = parseBool(settingValue('detection.require_gender_or_person', 'true'))
  generalForm.retention_days = Number(settingValue('retention.days', '0'))

  voiceForm.enabled = parseBool(settingValue('voice.enabled', 'false'))
  voiceForm.greet_known = parseBool(settingValue('voice.greet_known', 'true'))
  voiceForm.greet_unknown = parseBool(settingValue('voice.greet_unknown', 'true'))
  voiceForm.repeat_seconds = Number(settingValue('voice.repeat_seconds', '60'))
  voiceForm.rate = Number(settingValue('voice.rate', '1'))
  voiceForm.volume = Number(settingValue('voice.volume', '1'))
  voiceForm.voice_name = settingValue('voice.voice_name', '')

  providerInfo.value = await apiFetch('/settings/ai-provider').catch(() => ({ reachable: false }))
  const authConfig = await apiFetch('/settings/auth-config').catch(() => null)
  if (authConfig) {
    Object.assign(authForm.local, authConfig.local)
    Object.assign(authForm.oidc, authConfig.oidc)
    Object.assign(authForm.ldap, authConfig.ldap)
  }
}

const putSetting = (key: string, value: string | number | boolean) =>
  apiFetch(`/settings/${key}`, { method: 'PUT', body: { value: String(value) } })

const saveGeneral = async () => {
  savingGeneral.value = true
  generalMessage.value = ''
  try {
    await putSetting('recognition_threshold', generalForm.recognition_threshold)
    await putSetting('gender_min_confidence', generalForm.gender_min_confidence)
    await putSetting('greeting_cooldown_seconds', generalForm.greeting_cooldown_seconds)
    await putSetting('presence.absence_seconds', generalForm.presence_absence_seconds)
    await putSetting('detection.min_face_capture', generalForm.min_face_capture)
    await putSetting('detection.require_gender_or_person', generalForm.require_gender_or_person)
    await putSetting('retention.days', generalForm.retention_days)
    generalMessage.value = 'Saved. Camera workers pick up the new values within ~30 seconds - no restart needed.'
    await load()
  } catch (e: any) {
    generalMessage.value = e?.data?.detail || e.message
  } finally {
    savingGeneral.value = false
  }
}

const saveVoice = async () => {
  savingVoice.value = true
  voiceMessage.value = ''
  try {
    await putSetting('voice.enabled', voiceForm.enabled)
    await putSetting('voice.greet_known', voiceForm.greet_known)
    await putSetting('voice.greet_unknown', voiceForm.greet_unknown)
    await putSetting('voice.repeat_seconds', voiceForm.repeat_seconds)
    await putSetting('voice.rate', voiceForm.rate)
    await putSetting('voice.volume', voiceForm.volume)
    await putSetting('voice.voice_name', voiceForm.voice_name)
    const device = outputDevices.value.find(d => d.deviceId === selectedOutputId.value)
    voiceGreeter.setOutputDevice(selectedOutputId.value, device?.label || '')
    voiceMessage.value = 'Voice settings saved. The Live Monitoring page uses them immediately.'
    await load()
  } catch (e: any) {
    voiceMessage.value = e?.data?.detail || e.message
  } finally {
    savingVoice.value = false
  }
}

const refreshOutputDevices = async () => {
  outputDevices.value = await voiceGreeter.listOutputDevices()
  sinkSupported.value = voiceGreeter.sinkRoutingSupported()
  if (selectedOutputId.value && !outputDevices.value.some(d => d.deviceId === selectedOutputId.value)) {
    // Previously chosen device is gone (unplugged); fall back to default.
    selectedOutputId.value = ''
  }
}

const loadBrowserVoices = () => {
  if (!('speechSynthesis' in window)) return
  browserVoices.value = window.speechSynthesis.getVoices()
  if (!browserVoices.value.length) {
    window.speechSynthesis.addEventListener('voiceschanged', () => {
      browserVoices.value = window.speechSynthesis.getVoices()
    }, { once: true })
  }
}

const testVoice = async () => {
  const device = outputDevices.value.find(d => d.deviceId === selectedOutputId.value)
  voiceGreeter.setOutputDevice(selectedOutputId.value, device?.label || '')
  await voiceGreeter.speakNow('Hello sir, welcome. This is a voice test.', {
    enabled: true,
    greetKnown: true,
    greetUnknown: true,
    repeatSeconds: 0,
    rate: voiceForm.rate,
    volume: voiceForm.volume,
    voiceName: voiceForm.voice_name
  })
}

const saveSetting = async (setting: any) => { await apiFetch(`/settings/${setting.key}`, { method: 'PUT', body: { value: setting.value } }); await load() }
const saveTemplate = async (template: any) => { await apiFetch(`/greeting-templates/${template.language}`, { method: 'PUT', body: template }); await load() }

const onLogoFile = (event: Event) => { logoFile.value = (event.target as HTMLInputElement).files?.[0] || null }

const saveAppearance = async () => {
  savingAppearance.value = true
  appearanceMessage.value = ''
  try {
    await apiFetch('/settings/appearance.app_name', { method: 'PUT', body: { value: appearanceForm.app_name } })
    await apiFetch('/settings/appearance.primary_color', { method: 'PUT', body: { value: appearanceForm.primary_color } })
    await apiFetch('/settings/appearance.secondary_color', { method: 'PUT', body: { value: appearanceForm.secondary_color } })
    if (logoFile.value) {
      const form = new FormData()
      form.append('file', logoFile.value)
      await apiFetch('/settings/appearance/logo', { method: 'POST', body: form })
      logoFile.value = null
    }
    await refreshAppearance()
    await load()
    appearanceMessage.value = 'Appearance saved and applied.'
  } catch (e: any) {
    appearanceMessage.value = e?.data?.detail || e.message
  } finally {
    savingAppearance.value = false
  }
}

const resetAppearance = async () => {
  appearanceForm.app_name = 'KNetraAI'
  appearanceForm.primary_color = '#1E90FF'
  appearanceForm.secondary_color = '#0f172a'
  await apiFetch('/settings/appearance.logo_url', { method: 'PUT', body: { value: '' } })
  await saveAppearance()
}

const toggleDay = (day: string) => {
  scheduleForm.days = scheduleForm.days.includes(day)
    ? scheduleForm.days.filter(d => d !== day)
    : [...scheduleForm.days, day]
}

const saveSchedule = async () => {
  savingSchedule.value = true
  scheduleMessage.value = ''
  try {
    await apiFetch('/settings/schedule.enabled', { method: 'PUT', body: { value: String(scheduleForm.enabled) } })
    await apiFetch('/settings/schedule.start_time', { method: 'PUT', body: { value: scheduleForm.start_time } })
    await apiFetch('/settings/schedule.end_time', { method: 'PUT', body: { value: scheduleForm.end_time } })
    await apiFetch('/settings/schedule.days', { method: 'PUT', body: { value: scheduleForm.days.join(',') } })
    scheduleMessage.value = scheduleForm.enabled
      ? `Detection events limited to ${scheduleForm.start_time}-${scheduleForm.end_time} on ${scheduleForm.days.length} day(s).`
      : 'Schedule disabled - detection runs at all times.'
    await load()
  } catch (e: any) {
    scheduleMessage.value = e?.data?.detail || e.message
  } finally {
    savingSchedule.value = false
  }
}

const saveAuth = async (section: 'local' | 'oidc' | 'ldap') => {
  savingAuth.value = section
  authMessage.value = ''
  authError.value = ''
  try {
    const { client_secret_set, ...oidc } = authForm.oidc
    const { bind_password_set, ...ldap } = authForm.ldap
    const body = section === 'local' ? { local: authForm.local } : section === 'oidc' ? { oidc } : { ldap }
    const result = await apiFetch('/settings/auth-config', { method: 'PUT', body })
    Object.assign(authForm.local, result.local)
    Object.assign(authForm.oidc, result.oidc)
    Object.assign(authForm.ldap, result.ldap)
    authMessage.value = `${section === 'local' ? 'Local account' : section.toUpperCase()} settings saved - they apply immediately, no restart needed.`
  } catch (e: any) {
    authError.value = e?.data?.detail || e.message
  } finally {
    savingAuth.value = ''
  }
}

onMounted(() => {
  load()
  loadBrowserVoices()
  refreshOutputDevices().catch(() => {})
  if (import.meta.client && navigator.mediaDevices?.addEventListener) {
    navigator.mediaDevices.addEventListener('devicechange', () => refreshOutputDevices().catch(() => {}))
  }
})
</script>

<style scoped>
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  border-bottom: 2px solid var(--border);
  margin-bottom: 1.25rem;
}

.tab {
  border: 0;
  background: transparent;
  font: inherit;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-muted);
  padding: 0.6rem 1rem;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: color 0.15s, border-color 0.15s;
}

.tab:hover {
  color: var(--text);
}

.tab.active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 1rem;
  align-items: start;
}

.setting-row {
  margin-bottom: 1rem;
}

.auth-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.subheading {
  font-size: 0.85rem;
  font-weight: 700;
  margin: 1rem 0 0.5rem;
  color: var(--text);
}

.color-input {
  width: 2.6rem;
  height: 2.4rem;
  padding: 0.15rem;
  border: 1px solid #cbd5e1;
  border-radius: 0.5rem;
  background: white;
  cursor: pointer;
}

.range-input {
  width: 100%;
  accent-color: var(--primary);
}

.section-text {
  font-size: 0.875rem;
  color: #334155;
  margin: 0 0 0.75rem;
}

.details-title {
  cursor: pointer;
  font-weight: 700;
  font-size: 0.9rem;
  padding: 0.4rem 0;
}

.details-list {
  margin: 0.5rem 0 0.75rem;
  padding-left: 1.25rem;
  line-height: 1.7;
  font-size: 0.875rem;
  color: #334155;
}

.code-block {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 0.5rem;
  padding: 0.75rem;
  font-size: 0.75rem;
  overflow-x: auto;
  margin: 0.4rem 0;
}
</style>
