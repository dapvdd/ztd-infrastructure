<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  fetchAvailableModules,
  fetchDevices,
  fetchDeviceLogs,
  syncDeviceConfig,
} from '@/api/dashboardApi'

// Starts empty on purpose: the catalog comes from the backend. When /api/v1/modules fails
// the operator sees the real error and can still type a module folder name manually.
const moduleCatalog = ref([])
const modulesLoading = ref(false)
const modulesError = ref('')
const moduleNameInput = ref('')
const devices = ref([])
const route = useRoute()
const selectedDeviceId = ref(typeof route.query.device === 'string' ? route.query.device : '')
const enabledModules = ref([])
const deploymentLogs = ref([])
const loading = ref(false)
const stateLoading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const hasLoadedModuleState = ref(false)

const selectedDevice = computed(() => devices.value.find((device) => device.id === selectedDeviceId.value))
const busy = computed(() => loading.value || stateLoading.value || modulesLoading.value || saving.value)
const refreshLabel = computed(() => {
  if (modulesLoading.value) return 'Memuat katalog…'
  if (loading.value) return 'Memuat perangkat…'
  if (stateLoading.value) return 'Memuat status…'
  return 'Refresh data'
})

const formatTime = (value) => {
  if (!value) return 'N/A'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'N/A'
  return date.toLocaleString('id-ID', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
// Event history, newest first, with row id as a deterministic tie-breaker (the endpoint
// sorts by created_at only, so same-second events could otherwise swap order).
const sortedLogs = computed(() => [...deploymentLogs.value].sort((a, b) => {
  const byTime = new Date(b.created_at) - new Date(a.created_at)
  if (byTime) return byTime
  return (b.id ?? 0) - (a.id ?? 0)
}))

// Newest event per module = that module's current status. Kept separate from sortedLogs,
// which remains the full event history rendered in the history panel.
const latestStatusByModule = computed(() => {
  const statuses = new Map()
  for (const log of sortedLogs.value) {
    if (log?.stage && !statuses.has(log.stage)) {
      statuses.set(log.stage, log.status)
    }
  }
  return statuses
})

const moduleStatus = (moduleName) => latestStatusByModule.value.get(moduleName) || 'unknown'

const statusClass = (status) => {
  const value = status?.toLowerCase()
  if (value === 'success') return 'success'
  if (value === 'failed') return 'danger'
  if (value === 'installing' || value === 'pending') return 'warning'
  if (value === 'removed') return 'neutral'
  return 'unknown'
}

// Token of the newest in-flight state request. The old code cleared the spinner only when
// the device id still matched, so a superseded request (or a reset to no device) could leave
// the page on "Loading…" with the refresh button disabled forever.
let stateToken = 0

const loadDeviceState = async (deviceId) => {
  const token = ++stateToken

  if (!deviceId) {
    deploymentLogs.value = []
    enabledModules.value = []
    hasLoadedModuleState.value = false
    stateLoading.value = false
    return
  }

  stateLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  hasLoadedModuleState.value = false

  try {
    const logs = await fetchDeviceLogs(deviceId)
    if (token !== stateToken || selectedDeviceId.value !== deviceId) return

    if (!Array.isArray(logs)) throw new Error('Unexpected deployment history response.')
    deploymentLogs.value = logs
    const latestByModule = new Map()
    for (const log of sortedLogs.value) {
      if (log?.stage && !latestByModule.has(log.stage)) {
        latestByModule.set(log.stage, log.status?.toLowerCase())
      }
    }

    enabledModules.value = [...latestByModule.entries()]
      .filter(([, status]) => status === 'success' || status === 'installing')
      .map(([moduleName]) => moduleName)
    hasLoadedModuleState.value = true
  } catch (error) {
    if (token === stateToken && selectedDeviceId.value === deviceId) {
      deploymentLogs.value = []
      enabledModules.value = []
      errorMessage.value = `Could not load module state: ${error.message}. Try again.`
    }
  } finally {
    if (token === stateToken) stateLoading.value = false
  }
}

const refreshAll = () => {
  loadModuleCatalog()
  loadDevices()
}

const loadDevices = async () => {
  loading.value = true
  errorMessage.value = ''

  try {
    const list = await fetchDevices()
    if (!Array.isArray(list)) throw new Error('Unexpected device list response.')
    devices.value = list
    if (!devices.value.some((device) => device.id === selectedDeviceId.value)) {
      if (route.query.device) {
        errorMessage.value = 'Requested device not found. Select a device explicitly to continue.'
        selectedDeviceId.value = ''
      } else selectedDeviceId.value = ''
    }
    if (selectedDeviceId.value) await loadDeviceState(selectedDeviceId.value)
  } catch (error) {
    errorMessage.value = `Could not load devices: ${error.message}`
  } finally {
    loading.value = false
  }
}

const loadModuleCatalog = async () => {
  modulesLoading.value = true
  modulesError.value = ''
  try {
    const remoteModules = await fetchAvailableModules()
    // No local seed: if the backend returns nothing, the catalog really is empty.
    if (!Array.isArray(remoteModules) || remoteModules.some(module => typeof module?.name !== 'string')) throw new Error('Unexpected module catalog response.')
    moduleCatalog.value = [...remoteModules].sort((a, b) => a.name.localeCompare(b.name))
  } catch (error) {
    moduleCatalog.value = []
    modulesError.value = `Repository catalog unavailable: ${error.message}. You can still add a module by its folder name below.`
  } finally {
    modulesLoading.value = false
  }
}

const addModuleByName = () => {
  const name = moduleNameInput.value.trim()
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$/.test(name)) {
    modulesError.value = 'Module name must start with a letter or number and contain only letters, numbers, underscores, or hyphens.'
    return
  }

  if (!moduleCatalog.value.some((module) => module.name === name)) {
    // Version is unknown for a manually typed module; the UI shows N/A instead of inventing one.
    moduleCatalog.value = [...moduleCatalog.value, { name }]
      .sort((a, b) => a.name.localeCompare(b.name))
  }
  if (!enabledModules.value.includes(name)) {
    enabledModules.value = [...enabledModules.value, name]
  }
  moduleNameInput.value = ''
  modulesError.value = ''
}

const deployModuleState = async () => {
  if (busy.value || !selectedDevice.value || !hasLoadedModuleState.value) return

  if (
    enabledModules.value.length === 0
    && !window.confirm('No modules are selected. The agent will remove all modules it currently manages. Continue?')
  ) {
    return
  }

  saving.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await syncDeviceConfig(
      selectedDevice.value.id,
      enabledModules.value,
      selectedDevice.value.room_id,
    )
    successMessage.value = 'Configuration request accepted. Deployment is not yet confirmed. Check Deployment History for the agent-reported result.'
  } catch (error) {
    errorMessage.value = `Could not deploy module settings: ${error.message}`
  } finally {
    saving.value = false
  }
}

watch(selectedDeviceId, (deviceId) => loadDeviceState(deviceId))

onMounted(() => {
  loadDevices()
  loadModuleCatalog()
})
</script>

<template>
  <div class="modules-page">
    <header class="page-header">
      <div>
        <p class="kicker">Edge runtime catalog</p>
        <h2>Modules</h2>
        <p class="subtitle">Tambahkan modul ke repository, lalu pilih unit IoT dan deploy modul yang dibutuhkan.</p>
      </div>
      <button
        class="refresh-button"
        type="button"
        :disabled="busy"
        :aria-busy="busy"
        @click="refreshAll"
      >
        {{ refreshLabel }}
      </button>
    </header>

    <div v-if="errorMessage" class="message error-message" role="alert">
      <span>{{ errorMessage }}</span>
      <button
        v-if="selectedDeviceId"
        class="secondary-button inline-retry"
        type="button"
        :disabled="stateLoading"
        @click="loadDeviceState(selectedDeviceId)"
      >
        Coba lagi
      </button>
      <button
        v-else
        class="secondary-button inline-retry"
        type="button"
        :disabled="loading"
        @click="refreshAll"
      >
        {{ loading ? 'Mencoba…' : 'Coba lagi' }}
      </button>
    </div>
    <p v-if="successMessage" class="message success-message" role="status">{{ successMessage }}</p>

    <section class="guide-panel">
      <div class="panel-heading">
        <div>
          <p class="kicker">Developer guide</p>
          <h3>Menambahkan modul baru</h3>
          <p>Modul muncul setelah foldernya tersedia di branch <code>main</code> repository agent. Jika katalog GitHub tidak dapat dibaca server, masukkan nama folder modul secara manual pada bagian konfigurasi.</p>
        </div>
      </div>

      <ol class="guide-steps">
        <li>
          <strong>Buat folder modul</strong>
          <pre><code>mkdir -p modules/nama_modul</code></pre>
        </li>
        <li>
          <strong>Buat <code>module.py</code> dan <code>requirements.txt</code></strong>
          <p>Modul membaca konfigurasi dari <code>/opt/iot-agent/device.json</code> dan mengirim data ke topik MQTT sesuai room perangkat.</p>
          <pre><code>modules/nama_modul/
├── module.py
└── requirements.txt</code></pre>
        </li>
        <li>
          <strong>Commit dan push ke GitHub</strong>
          <pre><code>git add modules/nama_modul
git commit -m "feat: tambah modul nama_modul"
git push origin main</code></pre>
        </li>
        <li>
          <strong>Pilih Raspberry Pi dan deploy</strong>
          <p>Refresh katalog, pilih unit tujuan, centang modul, lalu deploy. Agent akan mengambil modul dari repository dan melaporkan statusnya.</p>
        </li>
      </ol>
    </section>

    <section class="module-panel">
      <div class="panel-heading">
        <div>
          <h3>Konfigurasi modul perangkat</h3>
          <p>Desired state dikirim melalui MQTT retained. Agent harus sudah terhubung agar dapat menerapkan konfigurasi.</p>
        </div>
        <label class="device-select">
          <span>Unit IoT tujuan</span>
          <select v-model="selectedDeviceId" :disabled="loading || saving || devices.length === 0">
            <option value="" disabled>Pilih unit IoT</option>
            <option v-for="device in devices" :key="device.id" :value="device.id">
              {{ device.hostname || device.id }} — {{ device.id }}
            </option>
          </select>
        </label>
      </div>

      <div v-if="modulesError" class="message error-message" role="alert">
        <span>{{ modulesError }}</span>
        <button class="secondary-button inline-retry" type="button" :disabled="modulesLoading" @click="loadModuleCatalog">
          {{ modulesLoading ? 'Memuat…' : 'Coba lagi katalog' }}
        </button>
      </div>

      <div v-if="loading && !devices.length" class="empty-state">
        Memuat daftar perangkat…
      </div>
      <div v-else-if="!devices.length && errorMessage" class="empty-state">
        Daftar perangkat gagal dimuat. Gunakan tombol “Coba lagi” di atas.
      </div>
      <div v-else-if="!devices.length" class="empty-state">
        Belum ada perangkat terdaftar. Bootstrap dan daftarkan unit IoT terlebih dahulu.
      </div>

      <template v-else>
        <p v-if="selectedDevice && !hasLoadedModuleState && stateLoading" class="empty-state">
          Membaca status modul dari riwayat deployment… (permintaan berhenti otomatis setelah 15 detik)
        </p>
        <p v-else-if="selectedDevice && !hasLoadedModuleState && !stateLoading" class="empty-state">
          Status modul belum bisa dibaca. Gunakan tombol “Refresh data” atau “Coba lagi”.
        </p>
        <template v-else>
          <form class="add-module-form" @submit.prevent="addModuleByName">
            <label for="module-name">Nama folder modul di repository agent</label>
            <div>
              <input id="module-name" v-model="moduleNameInput" type="text" placeholder="contoh: kamera" autocomplete="off" />
              <button class="secondary-button" type="submit" :disabled="!hasLoadedModuleState || busy">Tambah modul</button>
            </div>
            <small>Masukkan nama folder yang sama persis di bawah <code>modules/</code> setelah di-push ke GitHub.</small>
          </form>

          <div class="status-legend">
            <strong>Status terkini per modul</strong>
            <span>Dihitung dari event terbaru tiap modul · bukan riwayat</span>
          </div>

          <div v-if="modulesLoading" class="empty-state">
            Memuat katalog modul…
          </div>
          <div v-else-if="moduleCatalog.length" class="module-grid">
            <article v-for="module in moduleCatalog" :key="module.name" class="module-card">
              <div class="module-card-head">
                <div>
                  <span class="module-mark">M</span>
                  <div>
                    <h4>{{ module.name }}</h4>
                    <code>{{ module.name }}</code>
                  </div>
                </div>
                <span class="status-badge" :class="statusClass(moduleStatus(module.name))">
                  {{ moduleStatus(module.name) }}
                </span>
              </div>
              <p>Modul ini akan diambil dari katalog repository agent dan dijalankan sebagai systemd service terpisah.</p>
              <dl>
                <div><dt>Version</dt><dd>{{ module.version || 'N/A' }}</dd></div>
                <div><dt>Source</dt><dd>modules/{{ module.name }}/</dd></div>
                <div><dt>Runtime</dt><dd>Isolated Python venv</dd></div>
              </dl>
              <label class="toggle-row">
                <input
                  v-model="enabledModules"
                  type="checkbox"
                  :value="module.name"
                  :disabled="!selectedDevice || !hasLoadedModuleState || busy"
                />
                <span>{{ enabledModules.includes(module.name) ? 'Dipilih untuk deployment' : 'Tidak dipilih' }}</span>
              </label>
            </article>
          </div>
          <p v-else class="empty-state">
            {{ modulesError
              ? 'Katalog tidak tersedia. Tambahkan nama modul secara manual di atas atau coba lagi.'
              : 'Katalog modul kosong. Tambahkan nama folder setelah modul di-push ke repository.' }}
          </p>

          <div class="actions">
            <span v-if="selectedDevice">
              Tujuan: <strong>{{ selectedDevice.hostname || selectedDevice.id }}</strong>
            </span>
            <button
              class="secondary-button"
              type="button"
              :disabled="!selectedDevice || busy"
              @click="loadDeviceState(selectedDevice.id)"
            >
              {{ stateLoading ? 'Memuat status…' : 'Refresh status modul' }}
            </button>
            <button
              class="refresh-button"
              type="button"
              :disabled="!selectedDevice || !hasLoadedModuleState || busy"
              :aria-busy="saving"
              @click="deployModuleState"
            >
              {{ saving ? 'Mengirim…' : 'Deploy modul terpilih' }}
            </button>
          </div>
        </template>
      </template>
    </section>

    <section class="history-panel">
      <div class="panel-heading">
        <div>
          <h3>Riwayat event deployment</h3>
          <p>
            Setiap baris adalah satu event yang dilaporkan agent, terbaru lebih dulu — bukan status
            akhir modul. Status terkini per modul dihitung dari event terbaru tiap modul pada kartu
            di atas.
          </p>
        </div>
      </div>
      <p v-if="deploymentLogs.length" class="meta-note">
        Menampilkan {{ Math.min(sortedLogs.length, 8) }} dari {{ sortedLogs.length }} event terbaru.
      </p>
      <div v-if="deploymentLogs.length" class="history-list">
        <article v-for="log in sortedLogs.slice(0, 8)" :key="log.id" class="history-row">
          <span class="status-badge" :class="statusClass(log.status)">{{ log.status }}</span>
          <strong>{{ log.stage }}</strong>
          <span class="history-output">{{ log.log_output || 'No details reported' }}</span>
          <time>{{ formatTime(log.created_at) }}</time>
        </article>
      </div>
      <p v-else class="empty-state">Belum ada laporan modul untuk perangkat ini.</p>
    </section>
  </div>
</template>

<style scoped>
.modules-page {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 22px;
}

.page-header,
.panel-heading,
.module-card-head,
.module-card-head > div,
.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.kicker {
  margin: 0 0 8px;
  color: #7dd3fc;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h2,
h3,
h4,
p {
  margin-top: 0;
}

h2 {
  margin-bottom: 6px;
  color: #f8fafc;
  font-size: clamp(1.9rem, 3vw, 2.5rem);
}

h3,
h4 {
  margin-bottom: 5px;
  color: #f8fafc;
}

.subtitle,
.panel-heading p {
  margin-bottom: 0;
  color: #94a3b8;
}

.refresh-button {
  border: 0;
  border-radius: 10px;
  padding: 11px 16px;
  color: white;
  background: linear-gradient(135deg, #38bdf8, #8b5cf6);
  font-weight: 700;
  cursor: pointer;
}

.refresh-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.message {
  margin: 0;
  padding: 12px 14px;
  border-radius: 10px;
}

.error-message {
  color: #fecaca;
  background: rgba(239, 68, 68, 0.12);
}

.success-message {
  color: #a7f3d0;
  background: rgba(34, 197, 94, 0.12);
}

.guide-panel,
.module-panel,
.history-panel {
  min-width: 0;
  padding: 20px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.72);
}

.guide-panel {
  padding: 20px;
  border: 1px solid rgba(56, 189, 248, 0.2);
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.72);
}

.guide-steps {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin: 20px 0 0;
  padding-left: 22px;
}

.guide-steps li {
  min-width: 0;
  padding-left: 4px;
  color: #7dd3fc;
}

.guide-steps li > strong {
  color: #e2e8f0;
}

.guide-steps p {
  margin: 8px 0;
  color: #a5b4c7;
  font-size: 0.82rem;
}

.guide-steps pre {
  overflow-x: auto;
  margin: 9px 0 0;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 9px;
  padding: 11px;
  color: #bae6fd;
  background: rgba(2, 6, 23, 0.55);
  font-size: 0.76rem;
}

.guide-steps code,
.panel-heading code,
.add-module-form code {
  color: #7dd3fc;
}

.add-module-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 20px;
  color: #cbd5e1;
  font-size: 0.82rem;
}

.add-module-form > div {
  display: flex;
  gap: 10px;
}

.add-module-form input {
  flex: 1;
  min-width: 0;
  min-height: 42px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  padding: 9px 12px;
  color: #f8fafc;
  background: #111b2e;
}

.add-module-form small {
  color: #94a3b8;
}

.secondary-button {
  border: 1px solid rgba(56, 189, 248, 0.25);
  border-radius: 10px;
  padding: 9px 14px;
  color: #bae6fd;
  background: rgba(56, 189, 248, 0.1);
  font-weight: 700;
  cursor: pointer;
}

.secondary-button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.guide-panel {
  padding: 20px;
  border-color: rgba(56, 189, 248, 0.2);
}

.guide-steps {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin: 20px 0 0;
  padding-left: 22px;
}

.guide-steps li {
  min-width: 0;
  padding-left: 4px;
  color: #7dd3fc;
}

.guide-steps li > strong {
  color: #e2e8f0;
}

.guide-steps p {
  margin: 8px 0;
  color: #a5b4c7;
  font-size: 0.82rem;
}

.guide-steps pre {
  overflow-x: auto;
  margin: 9px 0 0;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 9px;
  padding: 11px;
  color: #bae6fd;
  background: rgba(2, 6, 23, 0.55);
  font-size: 0.76rem;
}

.guide-steps code,
.panel-heading code {
  color: #7dd3fc;
}

.device-select {
  display: flex;
  flex: 0 1 360px;
  flex-direction: column;
  gap: 7px;
  color: #cbd5e1;
  font-size: 0.8rem;
}

.device-select select {
  min-height: 42px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  padding: 9px 12px;
  color: #f8fafc;
  background: #111b2e;
}

.status-legend {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin: 20px 0 0;
}

.status-legend strong {
  color: #e2e8f0;
  font-size: 0.82rem;
}

.status-legend span {
  color: #94a3b8;
  font-size: 0.72rem;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 22px;
}

.module-card {
  min-width: 0;
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 16px;
  background: rgba(2, 6, 23, 0.3);
}

.module-card-head {
  align-items: flex-start;
}

.module-card-head > div {
  justify-content: flex-start;
}

.module-card-head h4 {
  margin: 0 0 3px;
}

.module-card-head code {
  color: #7dd3fc;
  font-size: 0.75rem;
}

.module-mark {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 13px;
  color: white;
  background: linear-gradient(135deg, #0ea5e9, #8b5cf6);
  font-weight: 800;
}

.module-card > p {
  min-height: 48px;
  margin: 16px 0;
  color: #a5b4c7;
  font-size: 0.88rem;
}

.module-card dl {
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin: 0;
}

.module-card dl > div {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 10px;
  font-size: 0.76rem;
}

.module-card dt {
  color: #94a3b8;
}

.module-card dd {
  overflow-wrap: anywhere;
  margin: 0;
  color: #dbeafe;
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 18px;
  color: #e2e8f0;
  font-size: 0.82rem;
}

.toggle-row input {
  accent-color: #38bdf8;
}

.message {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.inline-retry {
  padding: 6px 10px;
  font-size: 0.75rem;
  white-space: nowrap;
}

.meta-note {
  margin: 0;
  color: #94a3b8;
  font-size: 0.75rem;
}

.history-list {
  max-height: 360px;
  overflow-y: auto;
  padding-right: 6px;
}

.history-output {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.75rem;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 5px 9px;
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  line-height: 1.2;
  text-transform: uppercase;
  white-space: nowrap;
}

.status-badge::before {
  content: '';
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: currentColor;
}

.status-badge.success { color: #6ee7b7; background: rgba(34, 197, 94, 0.13); border-color: rgba(34, 197, 94, 0.3); }
.status-badge.danger { color: #fca5a5; background: rgba(239, 68, 68, 0.13); border-color: rgba(239, 68, 68, 0.3); }
.status-badge.warning { color: #fcd34d; background: rgba(251, 191, 36, 0.13); border-color: rgba(251, 191, 36, 0.3); }
.status-badge.neutral { color: #cbd5e1; background: rgba(148, 163, 184, 0.13); border-color: rgba(148, 163, 184, 0.22); }
.status-badge.unknown { color: #fcd34d; background: rgba(251, 191, 36, 0.08); border: 1px dashed rgba(251, 191, 36, 0.4); }

.actions {
  justify-content: flex-end;
  margin-top: 18px;
  color: #94a3b8;
  font-size: 0.82rem;
}

.empty-state {
  padding: 30px 12px;
  color: #94a3b8;
  text-align: center;
}

.history-list {
  margin-top: 18px;
}

.history-row {
  display: grid;
  grid-template-columns: auto 120px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  color: #cbd5e1;
  font-size: 0.8rem;
}

.history-row span:nth-of-type(2) {
  overflow-wrap: anywhere;
}

.history-row time {
  color: #94a3b8;
}

@media (max-width: 800px) {
  .page-header,
  .panel-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .device-select {
    flex-basis: auto;
    width: 100%;
  }

  .page-header .refresh-button {
    width: 100%;
  }

  .status-legend {
    align-items: flex-start;
    flex-direction: column;
    gap: 3px;
  }

  .module-grid {
    grid-template-columns: 1fr;
  }

  .guide-steps {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 520px) {
  .add-module-form > div {
    align-items: stretch;
    flex-direction: column;
  }
}

@media (max-width: 560px) {
  .history-row {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .history-row > span:nth-of-type(2),
  .history-row time {
    grid-column: 2;
  }

  .actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
