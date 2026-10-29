<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { fetchDevice, fetchDeviceMetrics, fetchDeviceTelemetry, fetchDeviceLogs } from '@/api/dashboardApi'
import { resolveMetric, formatPercent, formatTemperature, humanizeMetricReason } from '@/utils/deviceMetrics.mjs'

const route = useRoute()
const device = ref(null)
const loading = ref(false)
const error = ref('')
const notFound = ref(false)
const metrics = ref(null)
const telemetry = ref([])
const logs = ref([])
const errors = ref({})
let generation = 0
const time = (value) => value && !Number.isNaN(Date.parse(value)) ? new Date(value).toLocaleString() : 'Unknown'
const status = computed(() => ['ONLINE', 'OFFLINE'].includes(device.value?.status?.toUpperCase()) ? device.value.status.toUpperCase() : 'UNKNOWN')
const metricCards = computed(() => [
  { label: 'CPU utilization', ...resolveMetric(metrics.value, 'cpu.utilization_percent', metrics.value?.cpu?.utilization_percent, formatPercent) },
  { label: 'CPU temperature', ...resolveMetric(metrics.value, 'cpu_temperature.value', metrics.value?.cpu_temperature?.value, value => formatTemperature(value, metrics.value?.cpu_temperature?.unit)) },
])
async function load() {
  const token = ++generation
  const id = String(route.params.deviceId)
  loading.value = true
  device.value = null
  error.value = ''
  notFound.value = false
  metrics.value = null
  telemetry.value = []
  logs.value = []
  errors.value = {}
  try {
    const result = await fetchDevice(id)
    if (token !== generation) return
    if (!result || result.id !== id) throw new Error('Unexpected device identity in API response.')
    device.value = result
    await Promise.all([
      ['metrics', fetchDeviceMetrics, metrics],
      ['telemetry', fetchDeviceTelemetry, telemetry],
      ['deployment history', fetchDeviceLogs, logs],
    ].map(async ([name, fetcher, target]) => {
      try {
        const value = await fetcher(id)
        if (token !== generation) return
        if (name !== 'metrics' && !Array.isArray(value)) throw new Error('Unexpected API response.')
        target.value = value
      } catch (failure) {
        if (token === generation) errors.value[name] = failure.message
      }
    }))
  } catch (failure) {
    if (token !== generation) return
    notFound.value = failure.status === 404
    error.value = failure.message
  } finally {
    if (token === generation) loading.value = false
  }
}
watch(() => route.params.deviceId, load, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>

<template>
  <section class="control-page device-detail" :aria-busy="loading">
    <RouterLink to="/">Back to fleet</RouterLink>
    <h2>Device 360°</h2>
    <button type="button" :disabled="loading" @click="load">Refresh device</button>
    <p v-if="loading" role="status">Loading device data…</p>
    <article v-if="notFound" class="control-card" role="alert"><h3>Device not found</h3><p>No device matches {{ route.params.deviceId }}.</p></article>
    <p v-else-if="error" role="alert">Could not load device: {{ error }}</p>
    <template v-if="device">
      <article class="control-card">
        <h3>{{ device.hostname || device.id }}</h3>
        <dl><dt>Device ID</dt><dd>{{ device.id }}</dd><dt>Status</dt><dd>{{ status }}</dd><dt>Room</dt><dd>{{ device.room_id || 'Not reported' }}</dd><dt>IP address</dt><dd>{{ device.ip_address || 'Not reported' }}</dd><dt>Registered</dt><dd>{{ time(device.created_at) }}</dd><dt>Last heartbeat</dt><dd>{{ time(device.last_seen) }}</dd></dl>
        <RouterLink :to="{ path: '/modules', query: { device: device.id } }">Configure modules for this device</RouterLink>
      </article>
      <p v-for="(message, section) in errors" :key="section" role="alert">Could not load {{ section }}: {{ message }}. Use Refresh device to retry.</p>
      <div class="control-grid"><article v-for="metric in metricCards" :key="metric.label" class="control-card"><h3>{{ metric.label }}</h3><strong>{{ metric.text }}</strong><p v-if="metric.reason">{{ humanizeMetricReason(metric.reason) }}</p></article></div>
      <article class="control-card"><h3>Installed modules</h3><p>Last successful module states reported by the backend; not a live inventory.</p><ul v-if="device.modules?.length"><li v-for="module in device.modules" :key="module">{{ module }}</li></ul><p v-else>No installed modules reported.</p></article>
      <article class="control-card"><h3>Telemetry history</h3><p>Latest 12 samples. Units are shown only when reported.</p><p v-if="!telemetry.length && !errors.telemetry">{{ loading ? 'Loading telemetry…' : 'No telemetry reported.' }}</p><div class="table-scroll"><table v-if="telemetry.length"><thead><tr><th>Time</th><th>Temperature</th><th>Error</th></tr></thead><tbody><tr v-for="(sample, index) in telemetry" :key="index"><td>{{ time(sample.timestamp) }}</td><td>{{ formatTemperature(sample.cpu_temp, sample.unit) || (sample.cpu_temp == null ? 'N/A' : `${sample.cpu_temp} (unit unknown)`) }}</td><td>{{ sample.error || '—' }}</td></tr></tbody></table></div></article>
      <article class="control-card"><h3>Deployment history</h3><p v-if="!logs.length && !errors['deployment history']">{{ loading ? 'Loading history…' : 'No deployment events reported.' }}</p><div class="table-scroll"><table v-if="logs.length"><thead><tr><th>Time</th><th>Module / stage</th><th>Status</th><th>Details</th></tr></thead><tbody><tr v-for="(log, index) in logs" :key="log.id ?? index"><td>{{ time(log.created_at) }}</td><td>{{ log.stage || 'Unknown' }}</td><td>{{ log.status || 'Unknown' }}</td><td class="details">{{ log.log_output || 'No details reported' }}</td></tr></tbody></table></div></article>
    </template>
  </section>
</template>

<style scoped>
.device-detail { overflow-wrap: anywhere; }
.control-card { margin-top: 1rem; }
dl { display: grid; grid-template-columns: minmax(7rem, 1fr) 2fr; gap: .6rem; }
dd { margin: 0; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; text-align: left; }
th, td { padding: .7rem; border-bottom: 1px solid #64748b55; vertical-align: top; }
.details { white-space: pre-wrap; min-width: 12rem; }
button { padding: .6rem 1rem; cursor: pointer; }
</style>
