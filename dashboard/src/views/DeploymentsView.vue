<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { fetchDevices, fetchDeviceLogs } from '@/api/dashboardApi'
import { generateBootstrapScript } from '@/utils/bootstrapScript.mjs'
import {
  EAP_METHODS,
  PHASE2_AUTH_METHODS,
  getWifiFormState,
  validateWifiForm,
} from '@/utils/bootstrapWifi.mjs'

const logs = ref([])
const loading = ref(false)
const errorMessage = ref('')
const lastLoadedAt = ref(null)
const commandError = ref(false)
const statusFilter = ref('all')
const searchQuery = ref('')
const deviceName = ref('')
const piHost = ref('ztd.local')
const piUsername = ref('')
const connectionType = ref('Wi-Fi')
const wifiType = ref('Personal')
const wifiSsid = ref('')
const wifiUsername = ref('')
// The password is only used to validate the form in the browser. It is never
// written into the generated bootstrap script and never sent to the API.
const wifiPassword = ref('')
const wifiEapMethod = ref('')
const wifiCaCert = ref('')
const wifiClientCert = ref('')
const wifiClientKey = ref('')
const wifiPhase2Auth = ref('')
const ipMode = ref('DHCP')
const localIp = ref('')
const gateway = ref('')
const subnet = ref('')
const dns = ref('')
const mqttHost = ref('')
const roomId = ref('')
const repositoryUrl = ref('https://github.com/NICEganteng/modulraspipmld.git')
const commandMessage = ref('')
const isWifi = computed(() => connectionType.value === 'Wi-Fi')
const isStaticIp = computed(() => ipMode.value === 'Static')
// The 802.1X parameters live behind a collapsible section so the form stays
// short; it opens by itself when EAP-TLS is selected because that method
// needs a client certificate and a private key.
const showAdvanced = ref(false)
const wifiForm = computed(() => getWifiFormState({
  connectionType: connectionType.value,
  wifiType: wifiType.value,
  eapMethod: wifiEapMethod.value,
  advancedOpen: showAdvanced.value,
}))

watch([() => wifiType.value, () => connectionType.value], () => {
  if (!wifiForm.value.isEnterprise) showAdvanced.value = false
})

watch(() => wifiEapMethod.value, (value) => {
  if (value === 'TLS') showAdvanced.value = true
})

const validIpv4 = (value) => {
  const octets = value.trim().split('.')
  return octets.length === 4 && octets.every((octet) => {
    if (!/^\d{1,3}$/.test(octet)) return false
    const number = Number(octet)
    return number >= 0 && number <= 255
  })
}

const generatedBootstrap = computed(() => generateBootstrapScript({
  deviceName: deviceName.value,
  piHost: piHost.value,
  piUsername: piUsername.value,
  connectionType: connectionType.value,
  wifiType: wifiType.value,
  wifiSsid: wifiSsid.value,
  eapMethod: wifiEapMethod.value,
  caCert: wifiCaCert.value,
  clientCert: wifiClientCert.value,
  clientKey: wifiClientKey.value,
  phase2Auth: wifiPhase2Auth.value,
  ipMode: ipMode.value,
  localIp: localIp.value,
  gateway: gateway.value,
  subnet: subnet.value,
  dns: dns.value,
  mqttHost: mqttHost.value,
  roomId: roomId.value,
  repositoryUrl: repositoryUrl.value,
}))

const visibleLogs = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()

  return logs.value.filter((log) => {
    const matchesStatus = statusFilter.value === 'all'
      || log.status?.toLowerCase() === statusFilter.value
    const matchesQuery = !query
      || `${log.device_id} ${log.hostname} ${log.stage} ${log.log_output}`.toLowerCase().includes(query)

    return matchesStatus && matchesQuery
  })
})

// "Installing" must reflect the newest event per device+module. Counting every historical
// installing row would keep a module counted after its success event arrived.
const currentModuleStates = computed(() => {
  const latest = new Map()
  for (const log of logs.value) {
    const key = `${log.device_id}::${log.stage}`
    const seen = latest.get(key)
    if (!seen) {
      latest.set(key, log)
      continue
    }
    const byTime = new Date(log.created_at) - new Date(seen.created_at)
    if (byTime > 0 || (byTime === 0 && (log.id ?? 0) > (seen.id ?? 0))) {
      latest.set(key, log)
    }
  }
  return [...latest.values()]
})

const summary = computed(() => ({
  // Event counts (history), not current module state.
  total: logs.value.length,
  successful: logs.value.filter((log) => log.status?.toLowerCase() === 'success').length,
  failed: logs.value.filter((log) => log.status?.toLowerCase() === 'failed').length,
  inProgress: currentModuleStates.value
    .filter((log) => ['installing', 'pending'].includes(log.status?.toLowerCase())).length,
}))

const statusClass = (status) => {
  const value = status?.toLowerCase()
  if (value === 'success') return 'success'
  if (value === 'failed') return 'danger'
  if (value === 'installing' || value === 'pending') return 'warning'
  if (value === 'removed') return 'neutral'
  return 'unknown'
}

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

const loadDeployments = async () => {
  loading.value = true
  errorMessage.value = ''

  try {
    const devices = await fetchDevices()
    if (!Array.isArray(devices)) {
      throw new Error('Unexpected device list response.')
    }
    const results = await Promise.allSettled(
      devices.map(async (device) => {
        const deviceLogs = await fetchDeviceLogs(device.id)
        if (!Array.isArray(deviceLogs)) throw new Error('Unexpected deployment history response.')
        return deviceLogs.map((log) => ({
          ...log,
          device_id: device.id,
          hostname: device.hostname || device.id,
        }))
      }),
    )

    const failedRequests = results.filter((result) => result.status === 'rejected').length
    logs.value = results
      .filter((result) => result.status === 'fulfilled')
      .flatMap((result) => result.value)
      .sort((a, b) => {
        const byTime = new Date(b.created_at) - new Date(a.created_at)
        return byTime || (b.id ?? 0) - (a.id ?? 0)
      })

    if (failedRequests > 0) {
      errorMessage.value = `Could not load logs for ${failedRequests} device(s). Other deployment logs are shown.`
    }
    lastLoadedAt.value = new Date()
  } catch (error) {
    errorMessage.value = `Could not load deployments: ${error.message}`
    logs.value = []
  } finally {
    loading.value = false
  }
}

const validateBootstrapForm = () => {
  if (!/^[A-Za-z0-9][A-Za-z0-9.-]{0,62}$/.test(deviceName.value.trim())) {
    return 'Device Name harus 1–63 karakter: huruf, angka, titik, atau tanda hubung.'
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$/.test(piHost.value.trim())) {
    return 'Pi Host / IP harus berupa hostname atau alamat IPv4 tanpa port.'
  }
  if (!/^[A-Za-z_][A-Za-z0-9_.-]{0,31}$/.test(piUsername.value.trim())) {
    return 'Pi Username harus berupa username Linux yang valid.'
  }
  if (!/^[A-Za-z0-9._-]{1,50}$/.test(roomId.value.trim())) {
    return 'Room ID harus berisi huruf, angka, titik, garis bawah, atau tanda hubung.'
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$/.test(mqttHost.value.trim())) {
    return 'MQTT broker address wajib diisi sebagai hostname atau alamat IP tanpa port.'
  }
  if (!/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.git)?$/.test(repositoryUrl.value.trim())) {
    return 'Repository URL harus berbentuk https://github.com/owner/repository.git.'
  }
  if (isWifi.value) {
    const wifiError = validateWifiForm({
      wifiType: wifiType.value,
      ssid: wifiSsid.value,
      username: wifiUsername.value,
      password: wifiPassword.value,
      eapMethod: wifiEapMethod.value,
      caCert: wifiCaCert.value,
      clientCert: wifiClientCert.value,
      clientKey: wifiClientKey.value,
      phase2Auth: wifiPhase2Auth.value,
    })
    if (wifiError) return wifiError
  }
  if (isStaticIp.value) {
    if (![localIp.value, gateway.value, dns.value].every(validIpv4)) {
      return 'Local IP, Gateway, dan DNS harus berupa alamat IPv4 yang valid.'
    }
    const subnetValue = subnet.value.trim()
    const subnetMaskIsValid = validIpv4(subnetValue) && [
      '255.255.255.0',
      '255.255.255.128',
      '255.255.255.192',
      '255.255.255.224',
      '255.255.255.240',
      '255.255.255.248',
      '255.255.255.252',
    ].includes(subnetValue)
    const cidrIsValid = /^\d{1,2}$/.test(subnetValue) && Number(subnetValue) >= 0 && Number(subnetValue) <= 32
    if (!subnetMaskIsValid && !cidrIsValid) {
      return 'Subnet harus CIDR 0–32 atau subnet mask yang didukung (contoh 255.255.255.0).'
    }
  }
  return ''
}

const downloadBootstrapScript = () => {
  commandMessage.value = validateBootstrapForm()
  commandError.value = Boolean(commandMessage.value)
  if (commandMessage.value) {
    return
  }

  try {
    const blob = new Blob([generatedBootstrap.value], { type: 'text/x-shellscript;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `bootstrap-${deviceName.value.trim()}.sh`
    link.click()
    URL.revokeObjectURL(url)
    commandError.value = false
    // The password is only used for validation. Drop it from memory once the
    // (secret free) script has been produced.
    wifiPassword.value = ''
    commandMessage.value = 'Skrip diunduh. Jalankan dari terminal laptop yang satu jaringan dengan Pi: bash <nama-file>.sh. Password SSH, Wi-Fi, dan Tailscale diminta saat proses berlangsung; tidak disimpan dalam skrip.'
  } catch (error) {
    commandError.value = true
    commandMessage.value = `Gagal membuat skrip bootstrap: ${error.message}`
  }
}

onMounted(loadDeployments)
</script>

<template>
  <div class="deployments-page">
    <header class="page-header">
      <div>
        <p class="kicker">Device operations</p>
        <h2>Deployments</h2>
        <p class="subtitle">Module rollout history reported by edge agents.</p>
        <div class="meta-line">
          <span class="refresh-indicator" :class="{ active: loading }" aria-hidden="true"></span>
          <small class="meta-label">
            {{ loading ? 'Memuat riwayat…' : `Diperbarui ${lastLoadedAt ? formatTime(lastLoadedAt) : '—'}` }}
          </small>
        </div>
      </div>
      <button
        class="refresh-button"
        type="button"
        :disabled="loading"
        :aria-busy="loading"
        @click="loadDeployments"
      >
        {{ loading ? 'Memuat…' : 'Refresh logs' }}
      </button>
    </header>

    <div v-if="errorMessage" class="message error-message" role="alert">
      <span>{{ errorMessage }}</span>
      <button
        class="secondary-button inline-retry"
        type="button"
        :disabled="loading"
        @click="loadDeployments"
      >
        {{ loading ? 'Mencoba…' : 'Coba lagi' }}
      </button>
    </div>

    <section class="onboarding-panel">
      <div class="panel-heading">
        <div>
          <h3>Raspberry Pi Bootstrap</h3>
          <p>Isi konfigurasi unit baru. Skrip yang diunduh dijalankan di laptop dan mengonfigurasi Raspberry Pi melalui SSH.</p>
        </div>
      </div>

      <div class="onboarding-fields">
        <label>
          <span>Device Name</span>
          <input v-model="deviceName" type="text" placeholder="raspi-lab-01" autocomplete="off" />
        </label>
        <label>
          <span>Pi Host / IP</span>
          <input v-model="piHost" type="text" placeholder="ztd.local atau 192.168.1.50" autocomplete="off" />
        </label>
        <label>
          <span>Pi Username</span>
          <input v-model="piUsername" type="text" placeholder="pi" autocomplete="username" />
        </label>
        <label>
          <span>Connection Type</span>
          <select v-model="connectionType">
            <option>Wi-Fi</option>
            <option>Wired</option>
          </select>
        </label>

        <template v-if="wifiForm.isWifi">
          <label>
            <span>Wi-Fi Type</span>
            <select v-model="wifiType">
              <option>Personal</option>
              <option>Enterprise</option>
            </select>
          </label>
          <label v-if="wifiForm.showSsid">
            <span>Wi-Fi SSID</span>
            <input v-model="wifiSsid" type="text" autocomplete="off" />
            <small class="field-hint">Maksimal 32 karakter.</small>
          </label>
          <label v-if="wifiForm.showUsername">
            <span>Wi-Fi Username (802.1X identity)</span>
            <input v-model="wifiUsername" type="text" autocomplete="username" />
            <small class="field-hint">Tidak disimpan di skrip; skrip menanyakannya ulang di terminal.</small>
          </label>
          <label v-if="wifiForm.showPassword">
            <span>{{ wifiForm.isEnterprise ? 'Wi-Fi Password' : 'Wi-Fi Password (WPA-PSK)' }}</span>
            <input v-model="wifiPassword" type="password" autocomplete="new-password" />
            <small class="field-hint">
              {{ wifiForm.isEnterprise
                ? 'Hanya untuk validasi form. Tidak ditulis ke skrip dan tidak dikirim ke backend.'
                : 'Passphrase WPA 8–63 karakter. Tidak disimpan di skrip; diminta di terminal.' }}
            </small>
          </label>
          <label v-if="wifiForm.showEapMethod">
            <span>EAP Method</span>
            <select v-model="wifiEapMethod">
              <option value="">Pilih sesuai requirement jaringan</option>
              <option v-for="method in EAP_METHODS" :key="method" :value="method">{{ method }}</option>
            </select>
            <small class="field-hint">TTLS/PEAP memakai password; TLS memakai client certificate dan private key.</small>
          </label>
          <p v-if="wifiForm.requiresClientCertificate" class="certificate-hint">
            EAP-TLS memakai sertifikat: isi Client Certificate Path dan Client Private Key Path di
            Advanced Settings. Kedua file harus sudah ada di Raspberry Pi.
          </p>

          <div v-if="wifiForm.showAdvancedSection" class="advanced-field">
            <button
              type="button"
              class="advanced-toggle"
              :aria-expanded="wifiForm.advancedOpen ? 'true' : 'false'"
              @click="showAdvanced = !showAdvanced"
            >
              <span class="advanced-chevron" :class="{ open: wifiForm.advancedOpen }" aria-hidden="true">▶</span>
              Advanced Settings
            </button>
            <div v-show="wifiForm.advancedOpen" class="advanced-body">
              <label>
                <span>CA Certificate Path</span>
                <input v-model="wifiCaCert" type="text" placeholder="/etc/ssl/certs/campus-ca.pem" autocomplete="off" />
                <small class="field-hint">Path absolut di Raspberry Pi. Kosongkan bila RADIUS memakai CA store sistem.</small>
              </label>
              <label>
                <span>Client Certificate Path{{ wifiForm.requiresClientCertificate ? ' (wajib untuk EAP-TLS)' : ' (opsional)' }}</span>
                <input v-model="wifiClientCert" type="text" placeholder="/etc/ssl/certs/client.pem" autocomplete="off" />
              </label>
              <label>
                <span>Client Private Key Path{{ wifiForm.requiresClientCertificate ? ' (wajib untuk EAP-TLS)' : ' (opsional)' }}</span>
                <input v-model="wifiClientKey" type="text" placeholder="/etc/ssl/private/client.key" autocomplete="off" />
              </label>
              <label v-if="wifiForm.showPhase2Auth">
                <span>Phase 2 Authentication</span>
                <select v-model="wifiPhase2Auth">
                  <option
                    v-for="method in PHASE2_AUTH_METHODS"
                    :key="method || 'default'"
                    :value="method"
                  >{{ method || 'default jaringan' }}</option>
                </select>
                <small class="field-hint">Kosongkan untuk memakai default RADIUS.</small>
              </label>
            </div>
          </div>
        </template>

        <label>
          <span>IP Mode</span>
          <select v-model="ipMode">
            <option>DHCP</option>
            <option>Static</option>
          </select>
        </label>
        <template v-if="isStaticIp">
          <label>
            <span>Local IP</span>
            <input v-model="localIp" type="text" placeholder="192.168.1.50" inputmode="decimal" />
          </label>
          <label>
            <span>Gateway</span>
            <input v-model="gateway" type="text" placeholder="192.168.1.1" inputmode="decimal" />
          </label>
          <label>
            <span>Subnet (CIDR or mask)</span>
            <input v-model="subnet" type="text" placeholder="24 or 255.255.255.0" />
          </label>
          <label>
            <span>DNS</span>
            <input v-model="dns" type="text" placeholder="1.1.1.1" inputmode="decimal" />
          </label>
        </template>

        <label>
          <span>MQTT Broker Host</span>
          <input v-model="mqttHost" type="text" placeholder="100.x.x.x or broker hostname" autocomplete="off" />
        </label>
        <label>
          <span>Room ID</span>
          <input v-model="roomId" type="text" placeholder="lab-01" autocomplete="off" />
        </label>
        <label class="repo-field">
          <span>Agent Repository URL</span>
          <input v-model="repositoryUrl" type="url" />
        </label>
      </div>

      <div class="onboarding-note">
        <strong>Bootstrap berjalan dari laptop melalui SSH</strong>
        <span>Hubungkan laptop dan Pi ke jaringan lokal yang sama, lalu jalankan <code>bash bootstrap-&lt;nama-device&gt;.sh</code> dari terminal. SSH meminta password Pi bila diperlukan; password Wi-Fi, identity 802.1X, dan Tailscale auth key diminta saat bootstrap berjalan.</span>
        <span>Enterprise memakai WPA2-Enterprise (802.1X). Metode EAP, CA certificate, dan — untuk EAP-TLS — client certificate/private key harus sudah tersedia di Pi sesuai requirement jaringan. Outer identity dan phase 2 tidak diasumsikan; cara penerapannya ada di skrip.</span>
        <span>Rahasia tidak disimpan di file unduhan atau dikirim ke backend. Pi memerlukan akses internet untuk mengunduh Tailscale dan agent ZTD.</span>
      </div>

      <div class="onboarding-actions">
        <button class="refresh-button" type="button" @click="downloadBootstrapScript">Start Configuration / Download SSH Script</button>
        <span
          v-if="commandMessage"
          class="command-message"
          :class="{ 'is-error': commandError }"
          :role="commandError ? 'alert' : 'status'"
        >{{ commandMessage }}</span>
      </div>
    </section>

    <section class="summary-grid" aria-label="Deployment summary">
      <article class="summary-card">
        <span>Total events</span>
        <strong>{{ summary.total }}</strong>
        <small>Seluruh riwayat event</small>
      </article>
      <article class="summary-card success-card">
        <span>Success events</span>
        <strong>{{ summary.successful }}</strong>
        <small>Event berhasil</small>
      </article>
      <article class="summary-card warning-card">
        <span>Installing (latest per module)</span>
        <strong>{{ summary.inProgress }}</strong>
        <small>Status terkini, bukan riwayat</small>
      </article>
      <article class="summary-card failed-card">
        <span>Failed events</span>
        <strong>{{ summary.failed }}</strong>
        <small>Event gagal</small>
      </article>
    </section>

    <section class="deployment-panel">
      <div class="panel-heading">
        <div>
          <h3>Deployment history</h3>
          <p>
            Satu baris = satu event dari endpoint log tiap perangkat, terbaru lebih dulu. Status
            akhir per modul dihitung terpisah dari event terbaru tiap modul (lihat kartu
            “Installing (latest per module)”).
          </p>
        </div>
        <span class="result-count">{{ visibleLogs.length }} events</span>
      </div>

      <div class="filters">
        <label>
          <span>Status</span>
          <select v-model="statusFilter">
            <option value="all">All statuses</option>
            <option value="pending">Pending</option>
            <option value="installing">Installing</option>
            <option value="success">Success</option>
            <option value="failed">Failed</option>
            <option value="removed">Removed</option>
          </select>
        </label>
        <label class="search-field">
          <span>Search</span>
          <input v-model="searchQuery" type="search" placeholder="Device, module, details" />
        </label>
      </div>

      <div v-if="loading && logs.length === 0" class="empty-state">Memuat riwayat deployment…</div>
      <div v-else-if="!loading && visibleLogs.length === 0" class="empty-state">
        {{ errorMessage
          ? 'Riwayat deployment tidak dapat dimuat. Gunakan tombol “Coba lagi” di atas.'
          : logs.length
            ? 'Tidak ada event deployment yang cocok dengan filter.'
            : 'Belum ada riwayat deployment.' }}
      </div>
      <div v-else class="table-wrap">
        <table>
          <caption class="sr-only">Riwayat event deployment, terbaru lebih dulu</caption>
          <thead>
            <tr>
              <th scope="col">Device</th>
              <th scope="col">Module / stage</th>
              <th scope="col">Status</th>
              <th scope="col">Details</th>
              <th scope="col">Time</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in visibleLogs" :key="`${log.device_id}-${log.id}`">
              <td>
                <strong>{{ log.hostname }}</strong>
                <small>{{ log.device_id }}</small>
              </td>
              <td>{{ log.stage }}</td>
              <td><span class="status-badge" :class="statusClass(log.status)">{{ log.status }}</span></td>
              <td class="log-details">{{ log.log_output || '—' }}</td>
              <td>{{ formatTime(log.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="visibleLogs.length" class="scroll-hint">
        Geser tabel ke samping untuk melihat kolom detail dan waktu.
      </p>
    </section>
  </div>
</template>

<style scoped>
.deployments-page {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 22px;
}

.page-header,
.panel-heading {
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
p {
  margin-top: 0;
}

h2 {
  margin-bottom: 6px;
  color: #f8fafc;
  font-size: clamp(1.9rem, 3vw, 2.5rem);
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
  cursor: wait;
  opacity: 0.6;
}

.meta-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.meta-line .meta-label {
  color: #94a3b8;
  font-size: 0.7rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.refresh-indicator {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #475569;
}

.refresh-indicator.active {
  background: #38bdf8;
  box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.12);
  animation: refresh-pulse 1.2s ease-in-out infinite;
}

@keyframes refresh-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.message {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin: 0;
  padding: 12px 14px;
  border-radius: 10px;
}

.error-message {
  color: #fecaca;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.24);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.summary-card,
.deployment-panel,
.onboarding-panel {
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.72);
}

.summary-card {
  --tone: #38bdf8;
  --tone-soft: rgba(56, 189, 248, 0.13);
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 122px;
  padding: 18px 18px 16px 20px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 18px;
  background:
    radial-gradient(circle at 100% 0%, var(--tone-soft), transparent 58%),
    rgba(15, 23, 42, 0.72);
}

.summary-card::after {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--tone);
}

.summary-card span {
  color: #a5b4c7;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.summary-card strong {
  color: #f8fafc;
  font-size: clamp(1.9rem, 2.7vw, 2.4rem);
  font-variant-numeric: tabular-nums;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1;
}

.summary-card small {
  margin-top: auto;
  color: #94a3b8;
  font-size: 0.74rem;
}

.success-card { --tone: #22c55e; --tone-soft: rgba(34, 197, 94, 0.13); }
.warning-card { --tone: #fbbf24; --tone-soft: rgba(251, 191, 36, 0.12); }
.failed-card { --tone: #ef4444; --tone-soft: rgba(239, 68, 68, 0.12); }

.deployment-panel {
  padding: 20px;
}

.onboarding-panel {
  padding: 20px;
}

.onboarding-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 20px;
}

.onboarding-fields label {
  display: flex;
  flex-direction: column;
  gap: 7px;
  color: #cbd5e1;
  font-size: 0.8rem;
}

.onboarding-fields .repo-field {
  grid-column: 1 / -1;
}

.onboarding-fields input,
.onboarding-fields select {
  min-height: 42px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  padding: 9px 12px;
  color: #f8fafc;
  background: rgba(15, 23, 42, 0.8);
}

.onboarding-fields .field-hint {
  color: #8fa3b8;
  font-size: 0.7rem;
  line-height: 1.4;
}

.onboarding-fields .advanced-field {
  grid-column: 1 / -1;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(2, 6, 23, 0.28);
}

.advanced-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  padding: 0;
  color: #cbd5e1;
  background: none;
  font-size: 0.8rem;
  font-weight: 700;
  cursor: pointer;
}

.advanced-toggle:hover {
  color: #f8fafc;
}

.advanced-chevron {
  color: #7dd3fc;
  font-size: 0.7rem;
  transition: transform 0.15s ease;
}

.advanced-chevron.open {
  transform: rotate(90deg);
}

.advanced-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 14px;
}

.certificate-hint {
  grid-column: 1 / -1;
  margin: 0;
  padding: 10px 12px;
  border-left: 3px solid #fbbf24;
  border-radius: 8px;
  color: #fde68a;
  background: rgba(251, 191, 36, 0.08);
  font-size: 0.78rem;
  line-height: 1.45;
}

.onboarding-note {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 16px;
  border-left: 3px solid #38bdf8;
  padding: 10px 12px;
  color: #cbd5e1;
  background: rgba(56, 189, 248, 0.08);
  font-size: 0.82rem;
}

.onboarding-note strong {
  color: #f8fafc;
}

.command-preview {
  overflow-x: auto;
  margin: 16px 0 12px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 10px;
  padding: 14px;
  color: #bae6fd;
  background: rgba(2, 6, 23, 0.55);
  font-size: 0.78rem;
}

.onboarding-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.command-message {
  color: #a7f3d0;
  font-size: 0.8rem;
}

.command-message.is-error {
  color: #fca5a5;
}

.inline-retry {
  flex: 0 0 auto;
  padding: 6px 10px;
  border: 0;
  border-radius: 8px;
  background: rgba(148, 163, 184, 0.16);
  color: #e2e8f0;
  font-size: 0.74rem;
  font-weight: 700;
  cursor: pointer;
}

.inline-retry:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.panel-heading h3 {
  margin-bottom: 5px;
  color: #f8fafc;
}

.panel-heading p {
  font-size: 0.84rem;
}

.result-count {
  color: #94a3b8;
  font-size: 0.82rem;
  white-space: nowrap;
}

.filters {
  display: flex;
  gap: 14px;
  margin: 20px 0;
}

.filters label {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 7px;
  color: #cbd5e1;
  font-size: 0.8rem;
}

.filters select,
.filters input {
  min-height: 42px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  padding: 9px 12px;
  color: #f8fafc;
  background: rgba(15, 23, 42, 0.8);
}

.empty-state {
  padding: 40px 16px;
  color: #94a3b8;
  text-align: center;
}

.scroll-hint {
  display: none;
  margin: 10px 0 0;
  color: #94a3b8;
  font-size: 0.72rem;
}

.table-wrap {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 12px;
}

table {
  width: 100%;
  border-collapse: collapse;
  color: #e2e8f0;
}

th,
td {
  padding: 14px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  text-align: left;
  vertical-align: top;
}

th {
  color: #94a3b8;
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

td strong,
td small {
  display: block;
}

td small {
  margin-top: 4px;
  color: #94a3b8;
}

table {
  min-width: 780px;
  font-variant-numeric: tabular-nums;
}

th {
  position: sticky;
  top: 0;
  background: #0d1729;
  z-index: 1;
}

td {
  font-size: 0.85rem;
  line-height: 1.55;
}

.log-details {
  max-width: 520px;
  overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.76rem;
  line-height: 1.6;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 5px 9px;
  font-size: 0.68rem;
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

@media (max-width: 1100px) {
  .scroll-hint {
    display: block;
  }
}

@media (max-width: 760px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .page-header .refresh-button {
    width: 100%;
  }

  .meta-line {
    flex-wrap: wrap;
  }

  .advanced-body {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 520px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .summary-card {
    min-height: 112px;
    padding: 14px 12px 12px 16px;
  }

  .summary-card strong {
    font-size: 1.8rem;
  }

  .summary-card small {
    font-size: 0.68rem;
  }

  .filters {
    flex-direction: column;
  }

  .scroll-hint {
    display: block;
  }

  .panel-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .onboarding-fields {
    grid-template-columns: 1fr;
  }

  .onboarding-fields .repo-field {
    grid-column: auto;
  }
}
</style>
