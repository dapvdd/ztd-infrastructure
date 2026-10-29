<script setup>
import { ref } from 'vue'
import { fetchDashboardSummary } from '@/api/dashboardApi'
const state = ref('Not checked')
const checked = ref(null)
const busy = ref(false)
async function check() {
  busy.value = true
  try {
    await fetchDashboardSummary()
    state.value = 'Device summary API responded successfully'
    checked.value = new Date().toLocaleString()
  } catch (error) {
    state.value = `API check failed: ${error.message}`
  } finally { busy.value = false }
}
</script>
<template>
  <section class="control-page">
    <p class="eyebrow">Operations / Infrastructure</p><h2>Infrastructure Health</h2>
    <p>API reachability is not proof that its dependencies are healthy.</p>
    <article class="control-card" aria-live="polite">
      <h3>Dashboard API</h3><p>{{ state }}</p>
      <p>Last successful check: {{ checked || 'Not available' }}</p>
      <button :disabled="busy" @click="check">{{ busy ? 'Checking…' : 'Check API reachability' }}</button>
    </article>
    <div class="control-grid">
      <article v-for="service in ['Nginx', 'FastAPI process', 'PostgreSQL', 'Mosquitto MQTT', 'Host resources']" :key="service" class="control-card">
        <h3>{{ service }}</h3><strong>Not monitored</strong>
        <p>No supported service-level health contract is integrated. Resource usage, connectivity, and recovery cannot be inferred from device counts.</p>
      </article>
    </div>
  </section>
</template>
