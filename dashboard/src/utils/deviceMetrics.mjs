// Formatting and N/A decisions for the device metrics v1 response.
// The API reports values and reasons separately. This module never infers a
// unit, never turns a missing value into 0, and never treats load average as a
// CPU percentage.

const REASON_LABELS = {
  not_reported: 'agent tidak melaporkan field ini',
  never_reported: 'belum ada metrik v1 dari agent',
  invalid_payload: 'payload metrik tidak valid',
  invalid_network: 'payload network tidak valid',
  invalid_cpu: 'payload CPU tidak valid',
  invalid_temperature: 'payload temperatur tidak valid',
  invalid_ip: 'format IP tidak valid',
  not_configured: 'lookup IP publik tidak dikonfigurasi',
  lookup_failed: 'lookup IP publik gagal',
  invalid_response: 'respons lookup IP publik tidak valid',
  unavailable: 'tidak tersedia di perangkat',
  warming_up: 'sampel CPU pertama sedang diambil',
  stat_unavailable: '/proc/stat tidak dapat dibaca',
  invalid_delta: 'penghitung CPU tidak konsisten',
  out_of_range: 'nilai di luar rentang yang masuk akal',
  missing_unit: 'temperatur tidak menyertakan satuan',
  unsupported_unit: 'satuan temperatur tidak didukung',
  sensor_read_failed: 'sensor temperatur tidak dapat dibaca',
  invalid_uptime: 'uptime tidak valid',
  age_exceeds_threshold: 'data metrik sudah melewati batas kesegaran',
  future_timestamp: 'timestamp pengukuran berada di masa depan',
  stale: 'data metrik sudah stale',
}

export function humanizeMetricReason(reason) {
  if (reason === null || reason === undefined || reason === '') return null
  const token = String(reason)
  if (REASON_LABELS[token]) return REASON_LABELS[token]
  return token.replaceAll('_', ' ')
}

export function formatUptime(seconds) {
  if (seconds === null || seconds === undefined || seconds === '') return null
  const total = Number(seconds)
  if (!Number.isFinite(total) || total < 0) return null

  const whole = Math.floor(total)
  const days = Math.floor(whole / 86400)
  const hours = Math.floor((whole % 86400) / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const secs = whole % 60

  if (days > 0) return `${days}hr ${hours}j ${minutes}m`
  if (hours > 0) return `${hours}j ${minutes}m`
  if (minutes > 0) return `${minutes}m ${secs}d`
  return `${secs}d`
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  return `${number.toFixed(digits)}%`
}

export function formatLoadAverage(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  if (!Number.isFinite(number) || number < 0) return null
  return number.toFixed(2)
}

export function formatTemperature(value, unit) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  if (unit !== 'C' && unit !== 'F') return null
  return `${number.toFixed(1)} °${unit}`
}

export function formatMetricAge(seconds) {
  if (seconds === null || seconds === undefined || seconds === '') return null
  const total = Number(seconds)
  if (!Number.isFinite(total) || total < 0) return null

  const whole = Math.floor(total)
  if (whole < 10) return 'baru saja'
  if (whole < 60) return `${whole} dtk lalu`

  const minutes = Math.floor(whole / 60)
  if (minutes < 60) return `${minutes} mnt lalu`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} jam lalu`

  return `${Math.floor(hours / 24)} hari lalu`
}

/**
 * Resolve one metric for display.
 *
 * - `stale` metrics are N/A unless the caller explicitly allows a last-known
 *   identity value (for example an IP address).
 * - Missing values are N/A with the API's reason, never `0` or an inferred unit.
 */
export function resolveMetric(metrics, key, value, formatter, { allowStale = false } = {}) {
  if (!metrics || metrics.available !== true) {
    return {
      text: 'N/A',
      reason: metrics?.unavailable?.[key] || metrics?.stale_reason || 'never_reported',
      stale: true,
    }
  }

  if (metrics.stale && !allowStale) {
    return {
      text: 'N/A',
      reason: 'stale',
      stale: true,
    }
  }

  const formatted = value === null || value === undefined ? null : formatter(value)
  if (formatted === null || formatted === undefined) {
    return {
      text: 'N/A',
      reason: metrics?.unavailable?.[key] || 'not_reported',
      stale: Boolean(metrics.stale),
    }
  }

  return {
    text: formatted,
    reason: metrics.stale ? 'stale' : null,
    stale: Boolean(metrics.stale),
  }
}
