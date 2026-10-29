import test from 'node:test'
import assert from 'node:assert/strict'

import {
  formatLoadAverage,
  formatMetricAge,
  formatPercent,
  formatTemperature,
  formatUptime,
  humanizeMetricReason,
  resolveMetric,
} from '../src/utils/deviceMetrics.mjs'

const metrics = {
  available: true,
  stale: false,
  stale_reason: null,
  unavailable: {
    'network.public_ip': 'not_configured',
    'cpu.utilization_percent': 'warming_up',
  },
  network: { local_ip: '10.0.0.5', tailscale_ip: null, public_ip: null },
  cpu: { utilization_percent: null, load_average_1m: 0.42 },
  uptime_seconds: 93784,
  cpu_temperature: { value: 43.82, unit: 'C' },
}

test('uptime formats without inventing a value', () => {
  assert.equal(formatUptime(93784), '1hr 2j 3m')
  assert.equal(formatUptime(0), '0d')
  assert.equal(formatUptime(null), null)
  assert.equal(formatUptime(-1), null)
})

test('percent and load average remain distinct', () => {
  assert.equal(formatPercent(12.34), '12.3%')
  assert.equal(formatPercent(null), null)
  assert.equal(formatLoadAverage(0.42), '0.42')
  assert.equal(formatLoadAverage(12.34), '12.34')
  assert.equal(formatLoadAverage(-1), null)
  assert.doesNotMatch(formatLoadAverage(0.42), /%/)
})

test('temperature needs an explicit valid unit', () => {
  assert.equal(formatTemperature(43.82, 'C'), '43.8 °C')
  assert.equal(formatTemperature(110.88, 'F'), '110.9 °F')
  assert.equal(formatTemperature(43.82, null), null)
  assert.equal(formatTemperature(43.82, 'K'), null)
})

test('metric age is derived from API seconds', () => {
  assert.equal(formatMetricAge(4), 'baru saja')
  assert.equal(formatMetricAge(42), '42 dtk lalu')
  assert.equal(formatMetricAge(240), '4 mnt lalu')
  assert.equal(formatMetricAge(null), null)
})

test('missing values become N/A with the API reason', () => {
  const utilization = resolveMetric(metrics, 'cpu.utilization_percent', metrics.cpu.utilization_percent, formatPercent)
  assert.deepEqual(utilization, { text: 'N/A', reason: 'warming_up', stale: false })

  const publicIp = resolveMetric(metrics, 'network.public_ip', metrics.network.public_ip, String)
  assert.deepEqual(publicIp, { text: 'N/A', reason: 'not_configured', stale: false })
})

test('stale live metrics are N/A and identity values can remain last-known', () => {
  const stale = { ...metrics, stale: true, stale_reason: 'age_exceeds_threshold' }
  const utilization = resolveMetric(stale, 'cpu.utilization_percent', null, formatPercent)
  assert.deepEqual(utilization, { text: 'N/A', reason: 'stale', stale: true })

  const localIp = resolveMetric(stale, 'network.local_ip', '10.0.0.5', String, { allowStale: true })
  assert.deepEqual(localIp, { text: '10.0.0.5', reason: 'stale', stale: true })
})

test('never-reported metrics explain the missing v1 publisher', () => {
  const none = { available: false, stale: true, stale_reason: 'never_reported', unavailable: { metrics: 'never_reported' } }
  const metric = resolveMetric(none, 'cpu.utilization_percent', null, formatPercent)
  assert.equal(metric.text, 'N/A')
  assert.equal(metric.reason, 'never_reported')
  assert.equal(humanizeMetricReason(metric.reason), 'belum ada metrik v1 dari agent')
})

test('unknown reasons are readable, not hidden', () => {
  assert.equal(humanizeMetricReason('some_new_reason'), 'some new reason')
  assert.equal(humanizeMetricReason(null), null)
})
