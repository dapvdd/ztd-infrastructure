<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import {
  deleteDevice,
  fetchAvailableModules,
  fetchDashboardSummary,
  fetchDevices,
  fetchDeviceLogs,
  fetchDeviceMetrics,
  fetchDeviceTelemetry,
  syncDeviceConfig,
} from '@/api/dashboardApi'
import { summarizeTelemetry } from '@/utils/telemetry.mjs'
import { normalizeStatus } from '@/utils/deviceStatus.mjs'
import { formatRelativeAge } from '@/utils/presenceDisplay.mjs'
import {
  formatLoadAverage,
  formatMetricAge,
  formatPercent,
  formatTemperature,
  formatUptime,
  humanizeMetricReason,
  resolveMetric,
} from '@/utils/deviceMetrics.mjs'

// The backend computes ONLINE/OFFLINE from last_seen with a 15 s window and is the
// single source of truth for presence. The dashboard renders that value as-is and
// never ages devices locally, so the table cannot contradict the summary cards.
const POLL_INTERVAL_MS = 5 * 1000
const ALL_ROOMS = 'all'

const devices = ref([])
// null means "unknown" and is rendered as N/A. It is never replaced with a fake zero.
const summaryStats = ref(null)
const telemetry = ref([])
const deviceMetrics = ref(null)
const deploymentLogs = ref([])
const moduleCatalog = ref([])

const loading = ref(false)
const refreshing = ref(false)
const actionLoading = ref(false)
const moduleSettingsLoading = ref(false)
const metricsLoading = ref(false)

const loadError = ref('')
const actionMessage = ref('')
const actionError = ref('')
const telemetryError = ref('')
const metricsError = ref('')
const moduleCatalogError = ref('')

const activeRoom = ref(ALL_ROOMS)
const searchQuery = ref('')
const route = useRoute()
const selectedDeviceId = ref(route.params.deviceId || '')
const moduleSettingsDirty = ref(false)
const selectedModules = ref([])
const lastLoadedAt = ref(null)

let refreshTimer = null
let refreshInFlight = false
let telemetryToken = 0
let metricsToken = 0

const isFiniteNumber = (value) => value !== null && value !== undefined && value !== ''
  && Number.isFinite(Number(value))

const metricOrNa = (value) => (isFiniteNumber(value) ? Number(value) : 'N/A')
const textOrNa = (value) => (value === null || value === undefined || value === '' ? 'N/A' : String(value))

const normalizeDevice = (item) => ({
  id: item?.id || '',
  hostname: item?.hostname || '',
  room: item?.room_id || item?.room || 'unknown',
  room_id: item?.room_id || item?.room || 'unknown',
  ip: item?.ip_address || item?.ip || null,
  lastSeen: item?.last_seen || item?.lastSeen || null,
  status: normalizeStatus(item?.status),
  // Metrics v1 is a separate endpoint. The inventory API does not provide
  // uptime/CPU values, so this object must not pretend that it does.
  modules: Array.isArray(item?.modules) ? item.modules : [],
  config: item?.config ?? null,
})

const deviceLabel = (device) => device?.hostname || device?.id || 'unknown'
const deviceInitials = (device) => deviceLabel(device).slice(0, 2).toUpperCase()

const hasData = computed(() => devices.value.length > 0)

const roomOptions = computed(() => [
  ALL_ROOMS,
  ...new Set(devices.value.map((device) => device.room_id || device.room).filter(Boolean)),
])

const filteredDevices = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  const roomFiltered = activeRoom.value === ALL_ROOMS
    ? devices.value
    : devices.value.filter((device) => (device.room_id || device.room) === activeRoom.value)

  if (!query) return roomFiltered

  return roomFiltered.filter((device) => {
    const text = `${device.id} ${device.hostname} ${device.room_id || device.room}`.toLowerCase()
    return text.includes(query)
  })
})

const selectedDevice = computed(() => (
  devices.value.find((device) => device.id === selectedDeviceId.value) || null
))

const summaryCards = computed(() => {
  const stats = summaryStats.value
  return [
    { label: 'Total Devices', value: stats ? metricOrNa(stats.total_devices) : 'N/A', detail: 'Perangkat terdaftar', tone: 'cyan' },
    { label: 'Online', value: stats ? metricOrNa(stats.online_devices) : 'N/A', detail: 'Kontak terakhir ≤ 15 detik', tone: 'green' },
    { label: 'Offline', value: stats ? metricOrNa(stats.offline_devices) : 'N/A', detail: 'OFFLINE atau belum ada data', tone: 'red' },
    { label: 'Rooms', value: stats ? metricOrNa(stats.rooms_count) : 'N/A', detail: 'Room dengan perangkat', tone: 'purple' },
  ]
})

// The unit is reported per sample by the API and is never inferred from the value.
// Legacy rows arrive with unit: null -> unlabeled, excluded from the official average.
const telemetrySummary = computed(() => summarizeTelemetry(telemetry.value))

const tempPointLabel = (point, mode) => {
  const at = formatTime(point.timestamp)
  if (point.value === null) return `N/A at ${at}`
  if (mode === 'legacy') return `${point.value} raw (unit unknown, legacy sample) at ${at}`
  if (point.unit === 'F') {
    return `${point.celsius.toFixed(1)} °C (reported ${point.value.toFixed(2)} °F) at ${at}`
  }
  return `${point.value.toFixed(1)} °C (reported) at ${at}`
}

// Only samples with a reported unit share the Celsius axis. An all-legacy window is
// plotted as raw values and labelled as such; mixed windows never plot legacy rows
// next to converted ones.
const tempBars = computed(() => {
  const { mode, points } = telemetrySummary.value
  const plotted = mode === 'legacy'
    ? points.filter((point) => point.value !== null)
    : points.filter((point) => point.celsius !== null)
  if (!plotted.length) return []

  const basis = plotted.map((point) => (mode === 'legacy' ? point.value : point.celsius))
  const min = Math.min(...basis)
  const max = Math.max(...basis)
  const span = max - min || 1

  return plotted.map((point, index) => {
    const value = mode === 'legacy' ? point.value : point.celsius
    const height = 25 + ((value - min) / span) * 75
    return {
      key: `${point.timestamp || 'point'}-${index}`,
      height: Math.max(8, Math.min(100, height)),
      label: tempPointLabel(point, mode),
    }
  })
})

const temperatureHeadline = computed(() => {
  const { average } = telemetrySummary.value
  return average === null ? 'N/A' : `${average.toFixed(1)} °C avg`
})

const temperatureBadge = computed(() => {
  const summary = telemetrySummary.value
  if (summary.mode === 'empty') return 'no numeric samples'
  if (summary.mode === 'legacy') return 'unit unknown · legacy'
  if (summary.mode === 'celsius') return 'reported °C'
  if (summary.mode === 'fahrenheit') return 'converted from reported °F'
  if (summary.mixedUnits) return 'mixed units · no average'
  return `reported ${summary.reportedUnits.join('/')} · legacy excluded`
})

// Device metrics v1 is separate from the legacy temperature stream. Every value
// is resolved against the API's explicit availability/freshness metadata; a
// missing value is never replaced with 0 and load average is never shown as %.
const metricViews = computed(() => {
  const metrics = deviceMetrics.value
  return {
    localIp: resolveMetric(metrics, 'network.local_ip', metrics?.network?.local_ip, String, { allowStale: true }),
    tailscaleIp: resolveMetric(metrics, 'network.tailscale_ip', metrics?.network?.tailscale_ip, String, { allowStale: true }),
    publicIp: resolveMetric(metrics, 'network.public_ip', metrics?.network?.public_ip, String, { allowStale: true }),
    cpuUtilization: resolveMetric(metrics, 'cpu.utilization_percent', metrics?.cpu?.utilization_percent, formatPercent),
    loadAverage: resolveMetric(metrics, 'cpu.load_average_1m', metrics?.cpu?.load_average_1m, formatLoadAverage),
    uptime: resolveMetric(metrics, 'uptime_seconds', metrics?.uptime_seconds, formatUptime),
    temperature: resolveMetric(
      metrics,
      'cpu_temperature.value',
      metrics?.cpu_temperature?.value,
      (value) => formatTemperature(value, metrics?.cpu_temperature?.unit),
    ),
  }
})

const metricsFreshness = computed(() => {
  const metrics = deviceMetrics.value
  if (metricsLoading.value && !metrics) {
    return { tone: 'loading', text: 'Memuat metrik v1…' }
  }
  if (metricsError.value) {
    return { tone: 'error', text: `Metrics API: ${metricsError.value}` }
  }
  if (!metrics) {
    return { tone: 'unknown', text: 'Metrik v1 belum dimuat.' }
  }
  if (!metrics.available) {
    return {
      tone: 'unknown',
      text: humanizeMetricReason(metrics.unavailable?.metrics || metrics.stale_reason) || 'Metrik v1 belum tersedia.',
    }
  }
  if (metrics.stale) {
    return {
      tone: 'stale',
      text: `Metrik stale · ${formatMetricAge(metrics.age_seconds) || 'usia tidak diketahui'} · batas ${metrics.stale_after_seconds} dtk`,
    }
  }
  return {
    tone: 'fresh',
    text: `Metrik segar · ${formatMetricAge(metrics.age_seconds) || 'baru saja'} · diukur ${formatFullTime(metrics.measured_at)}`,
  }
})

const roomOverview = computed(() => {
  const rooms = new Map()
  for (const device of devices.value) {
    const name = device.room_id || device.room || 'unknown'
    const entry = rooms.get(name) || { room: name, total: 0, online: 0 }
    entry.total += 1
    if (device.status === 'ONLINE') entry.online += 1
    rooms.set(name, entry)
  }
  return [...rooms.values()].sort((a, b) => a.room.localeCompare(b.room))
})

const stagesFromLogs = computed(() => {
  const stages = new Set()
  for (const log of deploymentLogs.value) {
    if (log?.stage) stages.add(log.stage)
  }
  return [...stages]
})

// Real module names only: the backend catalog when it is reachable, plus the stages the
// backend actually reported in this device's deployment logs. No hardcoded list.
const availableModules = computed(() => {
  const names = new Set([
    ...moduleCatalog.value.map((module) => module?.name).filter(Boolean),
    ...stagesFromLogs.value,
  ])
  return [...names].sort((a, b) => a.localeCompare(b))
})

const formatTime = (value) => {
  if (!value) return 'N/A'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'N/A'
  return date.toLocaleString('id-ID', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatFullTime = (value) => {
  if (!value) return 'N/A'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'N/A'
  return date.toLocaleString('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  })
}

const statusClass = (status) => {
  const value = String(status || '').toUpperCase()
  const map = {
    ONLINE: 'success',
    OFFLINE: 'danger',
    INSTALLING: 'warning',
    PENDING: 'warning',
    SUCCESS: 'success',
    FAILED: 'danger',
    REMOVED: 'neutral',
    UNKNOWN: 'unknown',
  }
  return map[value] || 'neutral'
}

const clearActionMessages = () => {
  actionMessage.value = ''
  actionError.value = ''
}

const describeError = (error) => error?.message || 'Unknown error'

const loadTelemetryFor = async (deviceId) => {
  const token = ++telemetryToken
  moduleSettingsLoading.value = true
  telemetryError.value = ''

  let telemetryResult
  let logsResult
  try {
    ;[telemetryResult, logsResult] = await Promise.allSettled([
      fetchDeviceTelemetry(deviceId),
      fetchDeviceLogs(deviceId),
    ])
  } finally {
    // The spinner is released for the newest request only, so a superseded call can
    // never leave the module panel stuck on "Reading deployment history…".
    if (token === telemetryToken) moduleSettingsLoading.value = false
  }

  if (token !== telemetryToken || selectedDeviceId.value !== deviceId) return

  if (telemetryResult.status === 'fulfilled' && Array.isArray(telemetryResult.value)) {
    telemetry.value = telemetryResult.value
  } else {
    telemetry.value = []
    telemetryError.value = telemetryResult.status === 'rejected'
      ? `Telemetry unavailable: ${describeError(telemetryResult.reason)}`
      : 'Telemetry unavailable.'
  }

  if (logsResult.status === 'fulfilled' && Array.isArray(logsResult.value)) {
    deploymentLogs.value = logsResult.value
    if (!moduleSettingsDirty.value) applyModuleState(deviceId, logsResult.value)
  } else {
    deploymentLogs.value = []
    if (logsResult.status === 'rejected') {
      actionError.value = `Deployment logs unavailable: ${describeError(logsResult.reason)}`
    }
  }
}

const loadDeviceMetrics = async (deviceId) => {
  const token = ++metricsToken
  metricsLoading.value = true
  metricsError.value = ''

  try {
    const result = await fetchDeviceMetrics(deviceId)
    if (token !== metricsToken || selectedDeviceId.value !== deviceId) return
    if (!result || typeof result !== 'object') {
      throw new Error('Unexpected metrics response shape.')
    }
    deviceMetrics.value = result
  } catch (error) {
    if (token !== metricsToken || selectedDeviceId.value !== deviceId) return
    deviceMetrics.value = null
    metricsError.value = describeError(error)
  } finally {
    if (token === metricsToken) metricsLoading.value = false
  }
}

const loadDashboard = async ({ silent = false } = {}) => {
  if (refreshInFlight) return
  refreshInFlight = true

  if (silent) {
    refreshing.value = true
  } else {
    loading.value = true
    loadError.value = ''
  }

  try {
    const [summaryResult, devicesResult] = await Promise.allSettled([
      fetchDashboardSummary(),
      fetchDevices(),
    ])

    let failure = ''

    if (summaryResult.status === 'fulfilled') {
      summaryStats.value = summaryResult.value
    } else {
      summaryStats.value = null
      failure = `Fleet summary unavailable: ${describeError(summaryResult.reason)}`
    }

    if (devicesResult.status === 'fulfilled' && Array.isArray(devicesResult.value)) {
      const normalized = devicesResult.value.map(normalizeDevice)
      devices.value = normalized
      if (!normalized.some((device) => device.id === selectedDeviceId.value)) {
        selectedDeviceId.value = route.params.deviceId || normalized[0]?.id || ''
        deviceMetrics.value = null
        metricsError.value = ''
      }
      if (!normalized.length) {
        telemetry.value = []
        deviceMetrics.value = null
        metricsError.value = ''
        deploymentLogs.value = []
        selectedModules.value = []
      }
    } else {
      // Keep whatever was already on screen; never swap in fabricated devices.
      const reason = devicesResult.status === 'rejected'
        ? describeError(devicesResult.reason)
        : 'Unexpected response shape.'
      failure = failure ? `${failure} • Device list unavailable: ${reason}` : `Device list unavailable: ${reason}`
    }

    loadError.value = failure
    if (summaryResult.status === 'fulfilled' || devicesResult.status === 'fulfilled') {
      lastLoadedAt.value = new Date()
    }

    if (selectedDeviceId.value) {
      if (silent) {
        // Keep the freshness label honest between explicit refreshes without
        // re-fetching the temperature history or deployment logs every 5 s.
        await loadDeviceMetrics(selectedDeviceId.value)
      } else {
        await Promise.all([
          loadTelemetryFor(selectedDeviceId.value),
          loadDeviceMetrics(selectedDeviceId.value),
        ])
      }
    }
  } finally {
    loading.value = false
    refreshing.value = false
    refreshInFlight = false
  }
}

// Event history vs current state. The logs endpoint returns one row per event, ordered
// by created_at DESC with no tie-breaker, so ties are broken here by row id. The newest
// event per module (not the newest event overall) is what "current state" means.
const sortedLogs = computed(() => [...deploymentLogs.value].sort((a, b) => {
  const byTime = new Date(b.created_at) - new Date(a.created_at)
  if (byTime) return byTime
  return (b.id ?? 0) - (a.id ?? 0)
}))

const latestByModule = computed(() => {
  const events = new Map()
  for (const log of sortedLogs.value) {
    if (log?.stage && !events.has(log.stage)) events.set(log.stage, log)
  }
  return events
})

const currentModuleStates = computed(() => [...latestByModule.value.entries()]
  .map(([name, log]) => ({
    name,
    status: String(log.status || 'unknown').toLowerCase(),
    created_at: log.created_at || null,
  })))

const recentLogs = computed(() => sortedLogs.value.slice(0, 8))
const activityLogs = computed(() => sortedLogs.value.slice(0, 5))

const moduleStateLabel = (module) => {
  const event = latestByModule.value.get(module)
  if (!event) return 'no report in deployment history'
  return `last event: ${String(event.status || 'unknown').toLowerCase()} · ${formatTime(event.created_at)}`
}

const applyModuleState = (deviceId, logs) => {
  if (selectedDeviceId.value !== deviceId) return
  if (moduleSettingsDirty.value) return

  const latestByModule = new Map()
  for (const log of [...logs].sort((a, b) => {
    const byTime = new Date(b.created_at) - new Date(a.created_at)
    return byTime || (b.id ?? 0) - (a.id ?? 0)
  })) {
    if (log?.stage && !latestByModule.has(log.stage)) {
      latestByModule.set(log.stage, String(log.status || '').toLowerCase())
    }
  }

  selectedModules.value = [...latestByModule.entries()]
    .filter(([, status]) => ['success', 'installing'].includes(status))
    .map(([module]) => module)

  // `device.modules` is deliberately NOT overwritten with selectedModules: the inventory
  // endpoint does not report installed modules, and writing the desired state there made
  // the fleet table present intent as fact.
}

const loadModuleCatalog = async () => {
  moduleCatalogError.value = ''
  try {
    const catalog = await fetchAvailableModules()
    moduleCatalog.value = Array.isArray(catalog) ? catalog : []
  } catch (error) {
    moduleCatalog.value = []
    moduleCatalogError.value = `Module catalog unavailable: ${describeError(error)}`
  }
}

const selectDevice = (deviceId) => {
  if (deviceId === selectedDeviceId.value) return
  selectedDeviceId.value = deviceId
  deploymentLogs.value = []
  telemetry.value = []
  deviceMetrics.value = null
  selectedModules.value = []
  moduleSettingsDirty.value = false
  telemetryError.value = ''
  metricsError.value = ''
  clearActionMessages()
  loadTelemetryFor(deviceId)
  loadDeviceMetrics(deviceId)
}

const syncSelectedDevice = async () => {
  const device = selectedDevice.value
  if (!device?.id) return

  clearActionMessages()
  moduleSettingsDirty.value = false

  if (
    selectedModules.value.length === 0
    && !window.confirm('No modules are selected. The agent will remove its managed modules from this device. Continue?')
  ) {
    moduleSettingsDirty.value = true
    return
  }

  actionLoading.value = true
  try {
    const result = await syncDeviceConfig(device.id, selectedModules.value, device.room_id)
    actionMessage.value = result?.message || `Configuration sent to ${deviceLabel(device)}.`
    await Promise.all([
      loadTelemetryFor(device.id),
      loadDeviceMetrics(device.id),
    ])
  } catch (error) {
    actionError.value = `Configuration deployment failed: ${describeError(error)}`
  } finally {
    actionLoading.value = false
  }
}

const loadDeviceLogs = async () => {
  const device = selectedDevice.value
  if (!device?.id) return

  clearActionMessages()
  actionLoading.value = true
  try {
    const logs = await fetchDeviceLogs(device.id)
    deploymentLogs.value = Array.isArray(logs) ? logs : []
    applyModuleState(device.id, deploymentLogs.value)
    actionMessage.value = `Loaded ${deploymentLogs.value.length} log entries for ${deviceLabel(device)}.`
  } catch (error) {
    actionError.value = `Could not load deployment logs: ${describeError(error)}`
  } finally {
    actionLoading.value = false
  }
}

const removeSelectedDevice = async () => {
  const device = selectedDevice.value
  if (!device?.id) return
  if (!window.confirm(`Remove ${deviceLabel(device)} (${device.id}) from inventory?`)) return

  clearActionMessages()
  actionLoading.value = true
  try {
    await deleteDevice(device.id)
    deploymentLogs.value = []
    telemetry.value = []
    deviceMetrics.value = null
    metricsError.value = ''
    actionMessage.value = `${deviceLabel(device)} was removed from inventory.`
    await loadDashboard()
  } catch (error) {
    actionError.value = `Could not remove device: ${describeError(error)}`
  } finally {
    actionLoading.value = false
  }
}

const exportFleetCsv = () => {
  const rows = filteredDevices.value
  if (!rows.length) {
    actionError.value = 'Nothing to export: the current filter returns no devices.'
    return
  }

  const header = ['id', 'hostname', 'room', 'status', 'last_seen']
  const escape = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
  const csv = [
    header.join(','),
    ...rows.map((device) => [
      device.id,
      device.hostname,
      device.room,
      device.status,
      formatTime(device.lastSeen),
    ].map(escape).join(',')),
  ].join('\n')

  try {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `ztd-fleet-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)
    clearActionMessages()
    actionMessage.value = `Exported ${rows.length} device(s) to CSV.`
  } catch (error) {
    actionError.value = `Export failed: ${describeError(error)}`
  }
}

const onRefreshClick = () => loadDashboard()

const startPolling = () => {
  if (refreshTimer) return
  refreshTimer = setInterval(() => {
    // refreshInFlight guarantees at most one request in flight; a slow response
    // skips the next tick instead of stacking requests.
    if (document.hidden || refreshInFlight) return
    loadDashboard({ silent: true })
  }, POLL_INTERVAL_MS)
}

const stopPolling = () => {
  if (!refreshTimer) return
  clearInterval(refreshTimer)
  refreshTimer = null
}

// No polling while the tab is hidden. On return, refresh once and resume.
const handleVisibilityChange = () => {
  if (document.hidden) {
    stopPolling()
    return
  }
  loadDashboard({ silent: true })
  startPolling()
}

onMounted(() => {
  loadModuleCatalog()
  loadDashboard()
  startPolling()
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  telemetryToken += 1
  metricsToken += 1
})
</script>

<template>
  <div class="dashboard-page">
    <header class="topbar">
      <div>
        <p class="kicker">Operations dashboard</p>
        <h2>{{ route.params.deviceId ? 'Device 360°' : 'Operations Overview' }}</h2>
        <p v-if="route.params.deviceId">Requested device: {{ route.params.deviceId }}. {{ selectedDevice ? 'Latest reported state follows.' : 'Device not found or inventory unavailable.' }}</p>
        <RouterLink v-if="selectedDevice" :to="`/devices/${encodeURIComponent(selectedDevice.id)}`">Open Device 360° · {{ selectedDevice.id }}</RouterLink>
        <div class="meta-line">
          <span class="refresh-indicator" :class="{ active: refreshing }" aria-hidden="true"></span>
          <small class="meta-label">
            {{ refreshing ? 'Memperbarui data…' : `Diperbarui ${lastLoadedAt ? formatTime(lastLoadedAt) : '—'}` }}
          </small>
          <span v-if="loadError && lastLoadedAt" class="stale-chip">data mungkin usang</span>
        </div>
      </div>

      <div class="topbar-actions">
        <button class="ghost-button" type="button" :disabled="!filteredDevices.length" @click="exportFleetCsv">
          Export CSV
        </button>
        <button class="primary-button" type="button" :disabled="actionLoading || !selectedDevice" @click="syncSelectedDevice">
          {{ actionLoading ? 'Working…' : 'Deploy Config' }}
        </button>
      </div>
    </header>

    <div v-if="loadError" class="status-banner is-error" role="alert">
      <div class="banner-copy">
        <strong>API dashboard tidak dapat dijangkau sepenuhnya.</strong>
        <span>{{ loadError }}</span>
        <small v-if="lastLoadedAt">
          Data di bawah adalah hasil terakhir {{ formatTime(lastLoadedAt) }} dan bisa sudah usang.
          Status OFFLINE pada perangkat berbeda dari kegagalan API ini.
        </small>
      </div>
      <button class="ghost-button banner-actions" type="button" :disabled="loading" @click="onRefreshClick">
        {{ loading ? 'Mencoba…' : 'Coba lagi' }}
      </button>
    </div>
    <p v-if="actionError" class="status-banner is-error" role="alert">{{ actionError }}</p>
    <p v-if="actionMessage" class="status-banner is-ok" role="status">{{ actionMessage }}</p>

    <section class="summary-grid">
      <article v-for="card in summaryCards" :key="card.label" class="metric-card" :class="card.tone">
        <div class="metric-top">
          <span class="metric-label">{{ card.label }}</span>
          <span class="metric-dot" aria-hidden="true"></span>
        </div>
        <strong>{{ card.value }}</strong>
        <small>{{ card.detail }}</small>
      </article>
    </section>

    <section class="panel controls-panel">
      <div class="panel-header">
        <h3>Fleet Inventory</h3>
      </div>

      <div class="toolbar">
        <label>
          <span>Room</span>
          <select v-model="activeRoom">
            <option v-for="room in roomOptions" :key="room" :value="room">
              {{ room === 'all' ? 'All rooms' : room }}
            </option>
          </select>
        </label>

        <label>
          <span>Search</span>
          <input v-model="searchQuery" type="text" placeholder="Device ID / hostname" />
        </label>
      </div>

      <div v-if="loading && !hasData" class="empty-state">Loading fleet inventory…</div>
      <div v-else-if="!hasData && loadError" class="empty-state">
        Daftar perangkat tidak dapat dimuat karena API bermasalah. Lihat detail di banner atas, lalu coba lagi.
      </div>
      <div v-else-if="!hasData" class="empty-state">
        Belum ada perangkat terdaftar. Unit edge akan muncul di sini setelah melapor ke MQTT.
      </div>
      <div v-else-if="!filteredDevices.length" class="empty-state">
        No devices match the current room filter or search term.
      </div>
      <div v-else class="device-table-wrap">
        <table class="device-table">
          <thead>
            <tr>
              <th>Device</th>
              <th>Room</th>
              <th>Status</th>
              <th>Last Seen</th>
              <th title="Newest deployment event per module, selected device only">Modules (reported)</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="device in filteredDevices"
              :key="device.id || device.hostname"
              :class="{ active: device.id === selectedDeviceId }"
              tabindex="0"
              :aria-current="device.id === selectedDeviceId ? 'true' : undefined"
              @click="selectDevice(device.id)"
              @keydown.enter="selectDevice(device.id)"
              @keydown.space.prevent="selectDevice(device.id)"
            >
              <td>
                <div class="device-cell">
                  <span class="device-avatar">{{ deviceInitials(device) }}</span>
                  <div>
                    <strong>{{ deviceLabel(device) }}</strong>
                    <small>{{ device.id || 'N/A' }}</small>
                  </div>
                </div>
              </td>
              <td>{{ textOrNa(device.room) }}</td>
              <td>
                <span class="status-badge" :class="statusClass(device.status)">{{ device.status }}</span>
              </td>
              <td class="last-seen-cell">
                <strong v-if="device.lastSeen" :title="formatFullTime(device.lastSeen)">
                  {{ formatRelativeAge(device.lastSeen) }}
                </strong>
                <strong v-else class="is-muted">Belum tercatat</strong>
                <small v-if="device.lastSeen">{{ formatTime(device.lastSeen) }}</small>
              </td>
              <td>
                <div v-if="device.id === selectedDeviceId && currentModuleStates.length" class="tag-list">
                  <span
                    v-for="state in currentModuleStates.slice(0, 3)"
                    :key="`${device.id}-${state.name}`"
                    class="tag"
                    :class="`tag-${statusClass(state.status)}`"
                    :title="`${state.status} · ${formatTime(state.created_at)}`"
                  >{{ state.name }}</span>
                </div>
                <span v-else>N/A</span>
              </td>
              <td class="action-cell">
                <button class="table-button" type="button" @click.stop="selectDevice(device.id)">
                  Manage
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="filteredDevices.length" class="scroll-hint">
        Geser tabel ke samping untuk melihat kolom lain.
      </p>
    </section>

    <section class="info-grid">
      <article v-if="selectedDevice" class="panel detail-panel">
        <div class="panel-header">
          <h3>{{ deviceLabel(selectedDevice) }}</h3>
          <span class="status-badge" :class="statusClass(selectedDevice.status)">{{ selectedDevice.status }}</span>
        </div>

        <div class="presence-row">
          <div>
            <span class="meta-label">Terakhir terlihat</span>
            <strong>{{ formatRelativeAge(selectedDevice.lastSeen) || 'Belum tercatat' }}</strong>
            <small v-if="selectedDevice.lastSeen">{{ formatFullTime(selectedDevice.lastSeen) }}</small>
          </div>
          <div>
            <span class="meta-label">Sumber status</span>
            <strong>API backend</strong>
            <small>ONLINE bila kontak ≤ 15 detik</small>
          </div>
          <div>
            <span class="meta-label">Kondisi</span>
            <strong>
              {{ selectedDevice.status === 'ONLINE' ? 'Terhubung' : selectedDevice.status === 'OFFLINE' ? 'Tidak ada kontak' : 'Belum diketahui' }}
            </strong>
            <small>Bukan inferensi dashboard</small>
          </div>
        </div>

        <div class="metrics-freshness" :class="`is-${metricsFreshness.tone}`" role="status">
          <div class="freshness-copy">
            <span class="freshness-dot" aria-hidden="true"></span>
            <strong>{{ metricsFreshness.text }}</strong>
            <small v-if="deviceMetrics?.available && deviceMetrics.measured_at">
              Diukur {{ formatFullTime(deviceMetrics.measured_at) }} · diterima {{ formatFullTime(deviceMetrics.recorded_at) }}
            </small>
            <small v-else>Metrik device v1 · interval 60 dtk · batas stale {{ deviceMetrics?.stale_after_seconds ?? 180 }} dtk</small>
          </div>
          <button
            v-if="metricsError && selectedDevice"
            class="text-button"
            type="button"
            :disabled="metricsLoading"
            @click="loadDeviceMetrics(selectedDevice.id)"
          >
            {{ metricsLoading ? 'Mencoba…' : 'Coba metrik' }}
          </button>
        </div>

        <div class="detail-summary">
          <div>
            <span class="meta-label">Device ID</span>
            <strong>{{ textOrNa(selectedDevice.id) }}</strong>
          </div>
          <div>
            <span class="meta-label">IP lokal</span>
            <strong>{{ metricViews.localIp.text }}</strong>
            <small v-if="metricViews.localIp.reason" class="metric-reason">{{ humanizeMetricReason(metricViews.localIp.reason) }}</small>
          </div>
          <div>
            <span class="meta-label">IP Tailscale</span>
            <strong>{{ metricViews.tailscaleIp.text }}</strong>
            <small v-if="metricViews.tailscaleIp.reason" class="metric-reason">{{ humanizeMetricReason(metricViews.tailscaleIp.reason) }}</small>
          </div>
          <div>
            <span class="meta-label">IP publik</span>
            <strong>{{ metricViews.publicIp.text }}</strong>
            <small v-if="metricViews.publicIp.reason" class="metric-reason">{{ humanizeMetricReason(metricViews.publicIp.reason) }}</small>
          </div>
          <div>
            <span class="meta-label">CPU utilization</span>
            <strong>{{ metricViews.cpuUtilization.text }}</strong>
            <small v-if="metricViews.cpuUtilization.reason" class="metric-reason">{{ humanizeMetricReason(metricViews.cpuUtilization.reason) }}</small>
          </div>
          <div>
            <span class="meta-label">Load avg 1m</span>
            <strong>{{ metricViews.loadAverage.text }}</strong>
            <small v-if="metricViews.loadAverage.reason" class="metric-reason">{{ humanizeMetricReason(metricViews.loadAverage.reason) }}</small>
          </div>
          <div>
            <span class="meta-label">Uptime</span>
            <strong>{{ metricViews.uptime.text }}</strong>
            <small v-if="metricViews.uptime.reason" class="metric-reason">{{ humanizeMetricReason(metricViews.uptime.reason) }}</small>
          </div>
          <div>
            <span class="meta-label">CPU temperature</span>
            <strong>{{ metricViews.temperature.text }}</strong>
            <small v-if="metricViews.temperature.reason" class="metric-reason">{{ humanizeMetricReason(metricViews.temperature.reason) }}</small>
          </div>
        </div>

        <div class="chart-box">
          <div class="chart-header">
            <h4>CPU temperature history</h4>
            <span>
              {{ temperatureHeadline }}
              <span class="unit-badge">{{ temperatureBadge }}</span>
            </span>
          </div>

          <div
            v-if="tempBars.length"
            class="line-chart"
            role="img"
            :aria-label="`Grafik temperatur: ${temperatureHeadline}, ${temperatureBadge}`"
          >
            <span
              v-for="point in tempBars"
              :key="point.key"
              :style="{ height: `${point.height}%` }"
              :title="point.label"
            ></span>
          </div>
          <p v-else class="empty-state">
            {{ telemetryError || 'No telemetry samples reported for this device.' }}
          </p>

          <p v-if="telemetrySummary.mode === 'legacy' && telemetrySummary.counts.valued" class="chart-note">
            {{ telemetrySummary.counts.legacy }} sampel tersimpan tanpa metadata satuan (payload lama).
            Nilai ditampilkan mentah, tidak diberi label °C, dan tidak dihitung ke rata-rata resmi.
          </p>
          <p v-else-if="telemetrySummary.mode === 'fahrenheit'" class="chart-note">
            Sensor melaporkan Fahrenheit; angka °C di atas adalah konversi tampilan dari nilai yang
            dilaporkan, bukan perubahan data tersimpan.
          </p>
          <p v-else-if="telemetrySummary.mode === 'mixed'" class="chart-note">
            <template v-if="telemetrySummary.mixedUnits">
              Sampel memakai satuan berbeda ({{ telemetrySummary.reportedUnits.join(' & ') }});
              rata-rata lintas satuan tidak dihitung.
            </template>
            <template v-else>
              {{ telemetrySummary.legacyExcluded }} sampel legacy tanpa satuan tidak dihitung ke rata-rata.
            </template>
          </p>
        </div>

        <div class="module-controls">
          <div class="module-controls-heading">
            <h4>Module settings</h4>
            <span v-if="moduleSettingsLoading">Reading deployment history…</span>
            <span v-else>Choose what should run on this device</span>
          </div>

          <p v-if="moduleCatalogError" class="module-warning" role="alert">
            <span>{{ moduleCatalogError }}</span>
            <button class="text-button" type="button" @click="loadModuleCatalog">Coba lagi</button>
          </p>

          <template v-if="availableModules.length">
            <label v-for="module in availableModules" :key="module" class="module-option">
              <input
                v-model="selectedModules"
                type="checkbox"
                :value="module"
                :disabled="moduleSettingsLoading || actionLoading"
                @change="moduleSettingsDirty = true"
              />
              <span>{{ module }}</span>
              <small>{{ moduleStateLabel(module) }}</small>
            </label>
          </template>
          <p v-else class="module-warning">
            <span v-if="moduleCatalogError">No modules are known for this device: the backend catalog is unreachable and the device has not reported any module stage yet.</span>
            <span v-else>No modules are known for this device yet: the catalog is empty and the device has not reported any module stage.</span>
          </p>

          <p class="module-warning">
            Changes apply after deployment. Unchecking a module removes it; selecting none removes all managed modules.
          </p>
        </div>

        <div class="module-state">
          <div class="module-state-head">
            <h4>Current module state</h4>
            <span class="meta-label">Newest event per module</span>
          </div>
          <ul v-if="currentModuleStates.length">
            <li v-for="state in currentModuleStates" :key="`state-${state.name}`">
              <span class="status-badge" :class="statusClass(state.status)">{{ state.status }}</span>
              <strong>{{ state.name }}</strong>
              <time>{{ formatTime(state.created_at) }}</time>
            </li>
          </ul>
          <p v-else class="empty-state">No module has reported a deployment event yet.</p>
        </div>

        <div class="quick-actions">
          <button type="button" :disabled="actionLoading || !selectedDevice" @click="syncSelectedDevice">
            {{ actionLoading ? 'Working…' : 'Deploy modules' }}
          </button>
          <button type="button" :disabled="actionLoading || !selectedDevice" @click="loadDeviceLogs">
            Deployment logs
          </button>
          <button class="danger-action" type="button" :disabled="actionLoading || !selectedDevice" @click="removeSelectedDevice">
            Remove device
          </button>
        </div>

        <div v-if="deploymentLogs.length" class="deployment-logs">
          <div class="log-heading">
            <h4>Deployment event history</h4>
            <span class="meta-label">
              Newest first · showing {{ recentLogs.length }} of {{ deploymentLogs.length }}
            </span>
          </div>
          <ul>
            <li v-for="log in recentLogs" :key="log.id">
              <span class="status-badge" :class="statusClass(log.status)">{{ log.status }}</span>
              <strong>{{ log.stage }}</strong>
              <span class="log-output">{{ log.log_output || 'No details' }}</span>
              <time>{{ formatTime(log.created_at) }}</time>
            </li>
          </ul>
          <p class="chart-note">
            Setiap baris adalah satu event, bukan status akhir modul. Status terkini per modul
            dihitung terpisah pada panel “Current module state”.
          </p>
        </div>
      </article>

      <article v-else class="panel detail-panel">
        <div class="panel-header">
          <h3>Device detail</h3>
        </div>
        <p class="empty-state">
          {{ hasData ? 'Select a device from the inventory table to inspect it.' : 'No device data available.' }}
        </p>
      </article>

      <article class="panel">
        <div class="panel-header">
          <h3>Deployment events</h3>
          <span class="meta-label">
            Selected device · latest {{ activityLogs.length }} of {{ deploymentLogs.length }}
          </span>
        </div>

        <ul v-if="activityLogs.length" class="activity-list">
          <li v-for="log in activityLogs" :key="`activity-${log.id}`">
            <div class="activity-dot" :class="statusClass(log.status)"></div>
            <div>
              <strong>{{ log.stage }}</strong>
              <p class="log-output">{{ log.log_output || 'No details reported' }}</p>
            </div>
            <span>{{ formatTime(log.created_at) }}</span>
          </li>
        </ul>
        <p v-else class="empty-state">No deployment activity reported for the selected device.</p>
      </article>
    </section>

    <section class="bottom-grid">
      <article class="panel">
        <div class="panel-header">
          <h3>Room Overview</h3>
          <span class="meta-label">Derived from device inventory</span>
        </div>

        <div v-if="roomOverview.length" class="room-grid">
          <div v-for="room in roomOverview" :key="room.room" class="room-card">
            <div class="room-head">
              <strong>{{ room.room }}</strong>
              <span :class="room.online === room.total ? 'ok' : 'warning'">
                {{ room.online === room.total ? 'All online' : 'Attention' }}
              </span>
            </div>
            <div class="room-meta">
              <span>{{ room.online }}/{{ room.total }} online</span>
              <span>temp N/A</span>
            </div>
          </div>
        </div>
        <p v-else class="empty-state">No rooms reported yet.</p>
      </article>

      <article class="panel">
        <div class="panel-header">
          <h3>MQTT Broker</h3>
        </div>
        <p class="empty-state">
          Broker health is not exposed by the API, so no status is shown here instead of an
          invented one. Device connectivity is reflected by the last-contact status above.
        </p>
      </article>
    </section>
  </div>
</template>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 24px;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 8px;
}

.kicker {
  margin: 0 0 8px;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #7dd3fc;
}

.topbar h2 {
  margin: 0;
  font-size: clamp(1.9rem, 3vw, 2.6rem);
  color: #f8fafc;
}

.topbar-actions {
  display: flex;
  gap: 12px;
}

.meta-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.meta-line .meta-label {
  margin: 0;
}

.refresh-indicator {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #475569;
  transition: background 0.2s ease;
}

.refresh-indicator.active {
  background: #38bdf8;
  box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.12);
  animation: presence-pulse 1.2s ease-in-out infinite;
}

.stale-chip {
  padding: 2px 7px;
  border: 1px solid rgba(251, 191, 36, 0.35);
  border-radius: 999px;
  background: rgba(251, 191, 36, 0.1);
  color: #fcd34d;
  font-size: 0.64rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

@keyframes presence-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.status-banner {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin: 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.2);
  color: #bae6fd;
  font-size: 0.82rem;
  line-height: 1.55;
}

.banner-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.banner-copy strong {
  color: #fecaca;
}

.banner-copy span {
  color: #fecaca;
}

.banner-copy small {
  color: #fca5a5;
  font-size: 0.76rem;
}

button {
  border: none;
  border-radius: 10px;
  padding: 10px 14px;
  font-weight: 700;
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

button:not(:disabled) {
  transition: filter 0.18s ease, transform 0.18s ease;
}

button:not(:disabled):hover {
  filter: brightness(1.08);
}

.primary-button {
  background: linear-gradient(135deg, #38bdf8, #8b5cf6);
  color: white;
}

.ghost-button {
  background: rgba(148, 163, 184, 0.09);
  color: #e2e8f0;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
  gap: 18px;
}

.metric-card {
  --tone: #38bdf8;
  --tone-soft: rgba(56, 189, 248, 0.12);
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 136px;
  padding: 20px 20px 18px 22px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 18px;
  background:
    radial-gradient(circle at 100% 0%, var(--tone-soft), transparent 55%),
    rgba(15, 23, 42, 0.78);
}

.metric-card::after {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--tone);
}

.metric-card.cyan { --tone: #38bdf8; --tone-soft: rgba(56, 189, 248, 0.16); }
.metric-card.green { --tone: #22c55e; --tone-soft: rgba(34, 197, 94, 0.15); }
.metric-card.red { --tone: #ef4444; --tone-soft: rgba(239, 68, 68, 0.14); }
.metric-card.purple { --tone: #a855f7; --tone-soft: rgba(168, 85, 247, 0.15); }

.metric-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.metric-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--tone);
  box-shadow: 0 0 0 4px var(--tone-soft);
}

.metric-card strong {
  color: #f8fafc;
  font-size: clamp(2rem, 3.1vw, 2.7rem);
  font-variant-numeric: tabular-nums;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1;
}

.metric-card small {
  margin-top: auto;
  color: #9fb0c5;
  font-size: 0.76rem;
  line-height: 1.45;
}

.metric-label {
  color: #a5b4c7;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.panel {
  min-width: 0;
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  padding: 20px;
}

.controls-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 18px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 16px;
}

.panel-header h3,
.chart-header h4 {
  margin: 0;
  color: #f8fafc;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.toolbar label {
  flex: 1;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: #cbd5e1;
  font-size: 0.8rem;
}

.toolbar select,
.toolbar input {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.8);
  color: #f8fafc;
  border-radius: 10px;
  padding: 10px 12px;
}

.scroll-hint {
  display: none;
  margin: 10px 0 0;
  color: #94a3b8;
  font-size: 0.72rem;
}

.device-table-wrap {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
  overscroll-behavior-x: contain;
}

.device-table {
  width: 100%;
  border-collapse: collapse;
  color: #e2e8f0;
}

.device-table th,
.device-table td {
  padding: 15px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  text-align: left;
  vertical-align: middle;
}

.device-table th:last-child,
.device-table td:last-child {
  text-align: right;
}

.device-table thead th {
  color: #94a3b8;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.device-table tbody tr {
  cursor: pointer;
  transition: background 0.2s ease;
}

.device-table tbody tr:hover,
.device-table tbody tr.active {
  background: rgba(59, 130, 246, 0.08);
}

.device-table tbody tr.active {
  box-shadow: inset 3px 0 0 #38bdf8;
}

.device-table tbody tr:focus-visible {
  outline: 2px solid #38bdf8;
  outline-offset: -2px;
}

.device-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.device-cell strong,
.device-cell small {
  display: block;
}

.device-cell small {
  margin-top: 2px;
  color: #94a3b8;
}

.last-seen-cell strong,
.last-seen-cell small {
  display: block;
}

.last-seen-cell strong {
  color: #e2e8f0;
  font-size: 0.82rem;
}

.last-seen-cell small {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 0.7rem;
  white-space: nowrap;
}

.last-seen-cell .is-muted {
  color: #64748b;
  font-weight: 600;
}

.device-avatar {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #0ea5e9, #2563eb);
  font-size: 0.72rem;
  font-weight: 700;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 0.7rem;
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

.status-badge.success {
  border-color: rgba(34, 197, 94, 0.3);
  background: rgba(34, 197, 94, 0.13);
  color: #6ee7b7;
}

.status-badge.danger {
  border-color: rgba(239, 68, 68, 0.3);
  background: rgba(239, 68, 68, 0.12);
  color: #fca5a5;
}

.status-badge.warning {
  border-color: rgba(251, 191, 36, 0.3);
  background: rgba(251, 191, 36, 0.13);
  color: #fcd34d;
}

.status-badge.neutral {
  border-color: rgba(148, 163, 184, 0.22);
  background: rgba(148, 163, 184, 0.12);
  color: #cbd5e1;
}

.status-badge.unknown {
  border-color: rgba(251, 191, 36, 0.4);
  border-style: dashed;
  background: rgba(251, 191, 36, 0.08);
  color: #fcd34d;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.12);
  font-size: 0.64rem;
  color: #dbeafe;
}

.table-button {
  background: rgba(56, 189, 248, 0.14);
  color: white;
  padding: 8px 10px;
}

.info-grid,
.bottom-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  min-width: 0;
  gap: 20px;
}

.info-grid > *,
.bottom-grid > * {
  min-width: 0;
}

.presence-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 18px 0 4px;
  padding: 14px;
  border: 1px solid rgba(56, 189, 248, 0.16);
  border-radius: 14px;
  background: rgba(2, 6, 23, 0.28);
}

.presence-row strong,
.presence-row small {
  display: block;
}

.presence-row strong {
  color: #f8fafc;
  font-size: 0.9rem;
}

.presence-row small {
  margin-top: 3px;
  color: #94a3b8;
  font-size: 0.7rem;
}

.detail-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(90px, 1fr));
  gap: 10px;
  margin: 20px 0;
}

.metrics-freshness {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 18px;
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: rgba(2, 6, 23, 0.28);
}

.freshness-copy {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  min-width: 0;
  gap: 8px;
}

.freshness-copy strong {
  color: #e2e8f0;
  font-size: 0.78rem;
}

.freshness-copy small {
  color: #94a3b8;
  font-size: 0.7rem;
  line-height: 1.4;
}

.freshness-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #64748b;
}

.metrics-freshness.is-fresh {
  border-color: rgba(34, 197, 94, 0.28);
  background: rgba(34, 197, 94, 0.06);
}

.metrics-freshness.is-fresh .freshness-dot {
  background: #22c55e;
}

.metrics-freshness.is-stale {
  border-color: rgba(251, 191, 36, 0.35);
  background: rgba(251, 191, 36, 0.07);
}

.metrics-freshness.is-stale .freshness-dot {
  background: #fbbf24;
}

.metrics-freshness.is-error {
  border-color: rgba(248, 113, 113, 0.4);
  background: rgba(127, 29, 29, 0.18);
}

.metrics-freshness.is-error .freshness-dot {
  background: #f87171;
}

.metrics-freshness.is-loading .freshness-dot {
  background: #38bdf8;
  animation: presence-pulse 1.2s ease-in-out infinite;
}

.metric-reason {
  display: block;
  margin-top: 4px;
  color: #fcd34d;
  font-size: 0.66rem;
  line-height: 1.35;
}

.detail-summary strong {
  display: block;
  color: #f8fafc;
  font-size: 0.95rem;
  overflow-wrap: anywhere;
}

.meta-label {
  display: block;
  color: #94a3b8;
  font-size: 0.7rem;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.chart-box {
  background: rgba(2, 6, 23, 0.35);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 16px;
  padding: 16px;
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  color: #cbd5e1;
}

.line-chart {
  display: flex;
  align-items: end;
  gap: 8px;
  height: 120px;
  padding-top: 12px;
}

.line-chart span {
  display: block;
  flex: 1;
  min-width: 12px;
  border-radius: 8px 8px 0 0;
  background: linear-gradient(180deg, #7dd3fc 0%, #8b5cf6 100%);
  box-shadow: 0 8px 18px rgba(125, 211, 252, 0.25);
}

.quick-actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}

.quick-actions button {
  background: rgba(148, 163, 184, 0.08);
  color: #e2e8f0;
  flex: 1;
}

.module-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 14px;
  background: rgba(2, 6, 23, 0.25);
}

.module-controls-heading {
  display: flex;
  flex: 1 1 100%;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.module-controls-heading h4,
.deployment-logs h4 {
  margin: 0;
  color: #f8fafc;
}

.module-controls-heading span {
  color: #94a3b8;
  font-size: 0.75rem;
}

.module-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #dbeafe;
  text-transform: capitalize;
}

.module-option small {
  color: #94a3b8;
  font-size: 0.68rem;
  text-transform: none;
}

.module-option input {
  accent-color: #38bdf8;
}

.module-warning {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  flex: 1 1 100%;
  gap: 8px;
  margin: 0;
  color: #fcd34d;
  font-size: 0.75rem;
}

.text-button {
  padding: 4px 8px;
  border: 1px solid rgba(251, 191, 36, 0.35);
  border-radius: 8px;
  background: rgba(251, 191, 36, 0.1);
  color: #fcd34d;
  font-size: 0.7rem;
  font-weight: 700;
}

.quick-actions .danger-action {
  background: rgba(239, 68, 68, 0.12);
  color: #fca5a5;
}

.deployment-logs {
  margin-top: 18px;
}

.deployment-logs ul {
  display: flex;
  flex-direction: column;
  gap: 10px;
  list-style: none;
  padding: 0;
  margin: 12px 0 0;
}

.deployment-logs li {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  color: #cbd5e1;
  font-size: 0.78rem;
}

.deployment-logs li > span:nth-of-type(2) {
  overflow-wrap: anywhere;
}

.deployment-logs time {
  color: #94a3b8;
}

.activity-list,
.mqtt-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.activity-list li,
.mqtt-list li {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.activity-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.activity-dot.success { background: #22c55e; }
.activity-dot.warning { background: #fbbf24; }
.activity-dot.danger { background: #ef4444; }

.activity-list strong,
.mqtt-list span {
  color: #f8fafc;
}

.activity-list p {
  margin: 4px 0 0;
  color: #a5b4c7;
  font-size: 0.85rem;
}

.activity-list span {
  color: #94a3b8;
  font-size: 0.75rem;
}

/* Readability (small, targeted): wider table, aligned digits, scrollable log panes,
   monospace event text, and labels for the temperature unit. */
.device-table {
  min-width: 860px;
  font-variant-numeric: tabular-nums;
}

.device-table th,
.device-table td {
  font-size: 0.86rem;
  line-height: 1.45;
}

.device-table td:nth-child(4) {
  white-space: nowrap;
}

.tag {
  font-size: 0.7rem;
  border: 1px solid transparent;
}

.tag-success { border-color: rgba(34, 197, 94, 0.35); }
.tag-warning { border-color: rgba(251, 191, 36, 0.35); }
.tag-danger { border-color: rgba(239, 68, 68, 0.35); }

.unit-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.16);
  color: #cbd5e1;
  font-size: 0.66rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.chart-note {
  margin: 12px 0 0;
  color: #94a3b8;
  font-size: 0.74rem;
  line-height: 1.55;
}

.module-state {
  margin-top: 16px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 14px;
  background: rgba(2, 6, 23, 0.25);
}

.module-state-head,
.log-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.module-state-head h4,
.log-heading h4 {
  margin: 0;
  color: #f8fafc;
}

.module-state ul {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}

.module-state li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  font-size: 0.82rem;
}

.module-state time,
.log-heading .meta-label {
  color: #94a3b8;
  white-space: nowrap;
}

.deployment-logs ul {
  max-height: 320px;
  overflow-y: auto;
  padding-right: 6px;
}

.deployment-logs .log-output,
.activity-list .log-output {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.74rem;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.activity-list p.log-output {
  color: #cbd5e1;
}

.activity-list > li > span {
  white-space: nowrap;
}

.room-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(150px, 1fr));
  gap: 12px;
}

.room-card {
  background: rgba(2, 6, 23, 0.32);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 14px;
  padding: 14px;
}

.room-head,
.room-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #e2e8f0;
}

.room-head strong {
  font-size: 1rem;
}

.warn-badge,
.room-head .warning,
.room-head .ok {
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 0.65rem;
  font-weight: 700;
}

.room-head .warning,
.warning {
  background: rgba(251, 191, 36, 0.12);
  color: #fcd34d;
}

.room-head .ok,
.ok {
  background: rgba(34, 197, 94, 0.12);
  color: #6ee7b7;
}

.room-meta {
  margin-top: 12px;
  color: #94a3b8;
  font-size: 0.8rem;
}

.mqtt-list li {
  grid-template-columns: minmax(0, 1fr) auto auto;
}

.mqtt-list small {
  color: #94a3b8;
}

.mqtt-list i {
  font-style: normal;
  background: rgba(56, 189, 248, 0.12);
  color: #7dd3fc;
  border-radius: 999px;
  font-size: 0.72rem;
  padding: 4px 8px;
}

@media (max-width: 1100px) {
  .scroll-hint {
    display: block;
  }

  .summary-grid,
  .info-grid,
  .bottom-grid {
    grid-template-columns: 1fr 1fr;
  }

  .detail-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 780px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .metric-card {
    min-height: 122px;
    padding: 16px 14px 14px 18px;
  }

  .metric-card strong {
    font-size: 2rem;
  }

  .info-grid,
  .bottom-grid,
  .detail-summary,
  .room-grid {
    grid-template-columns: 1fr;
  }

  .topbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .topbar-actions {
    flex-wrap: wrap;
    width: 100%;
  }

  .topbar-actions button {
    flex: 1 1 150px;
  }

  .presence-row {
    grid-template-columns: 1fr;
  }

  .metrics-freshness {
    align-items: flex-start;
    flex-direction: column;
  }

  .banner-copy small {
    font-size: 0.72rem;
  }
}

@media (max-width: 700px) {
  .scroll-hint {
    display: none;
  }

  .device-table {
    min-width: 0;
  }

  .device-table th,
  .device-table td {
    padding: 12px 8px;
    font-size: 0.78rem;
  }

  .device-table th:nth-child(2),
  .device-table td:nth-child(2),
  .device-table th:nth-child(5),
  .device-table td:nth-child(5),
  .device-table th:nth-child(6),
  .device-table td:nth-child(6) {
    display: none;
  }

  .device-table th:nth-child(1) { width: 42%; }
  .device-table th:nth-child(3) { width: 29%; }
  .device-table th:nth-child(4) { width: 29%; }

  .device-avatar {
    width: 28px;
    height: 28px;
    border-radius: 8px;
    font-size: 0.66rem;
  }

  .device-cell {
    gap: 9px;
  }

  .status-badge {
    padding: 4px 7px;
    font-size: 0.62rem;
  }

  .last-seen-cell small {
    font-size: 0.66rem;
  }
}

.status-banner.is-error {
  border-color: rgba(248, 113, 113, 0.45);
  background: rgba(127, 29, 29, 0.28);
  color: #fecaca;
}

.status-banner.is-ok {
  border-color: rgba(52, 211, 153, 0.4);
  background: rgba(6, 78, 59, 0.3);
  color: #a7f3d0;
}

.banner-actions {
  margin-left: 12px;
}

.empty-state {
  padding: 26px 18px;
  text-align: center;
  color: #94a3b8;
  font-size: 0.92rem;
  line-height: 1.5;
}
</style>
