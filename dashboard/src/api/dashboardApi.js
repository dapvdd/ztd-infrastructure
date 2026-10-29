const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const DEFAULT_TIMEOUT_MS = 15000

class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function apiFetch(path, options = {}) {
  const { timeout = DEFAULT_TIMEOUT_MS, ...rest } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(rest.headers || {}),
      },
      ...rest,
      signal: rest.signal || controller.signal,
    })

    if (!response.ok) {
      const text = await response.text().catch(() => '')
      let detail = text
      try {
        const parsed = JSON.parse(text)
        detail = parsed?.detail || parsed?.message || text
      } catch {
        // keep raw text
      }
      throw new ApiError(
        detail || `Request failed with HTTP ${response.status}`,
        response.status,
        detail,
      )
    }

    if (response.status === 204) {
      return null
    }

    return response.json()
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new ApiError(`Request timed out after ${timeout} ms`, 0, null)
    }
    if (error instanceof ApiError) throw error
    throw new ApiError(error.message || 'Network request failed', 0, null)
  } finally {
    clearTimeout(timer)
  }
}

export async function fetchDashboardSummary() {
  return apiFetch('/api/v1/devices/summary')
}

export async function fetchDevices(roomId = null) {
  const query = roomId ? `?room_id=${encodeURIComponent(roomId)}` : ''
  return apiFetch(`/api/v1/devices${query}`)
}

export async function fetchAvailableModules() {
  return apiFetch('/api/v1/modules')
}

export async function fetchDevice(deviceId) {
  return apiFetch(`/api/v1/devices/${encodeURIComponent(deviceId)}`)
}

export async function fetchDeviceTelemetry(deviceId, limit = 12) {
  return apiFetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/telemetry?limit=${limit}`)
}

export async function fetchDeviceMetrics(deviceId) {
  // Metrics contract v1. The backend owns availability/freshness metadata and
  // returns available:false rather than inventing values when no sample exists.
  return apiFetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/metrics`)
}

export async function fetchDeviceLogs(deviceId) {
  return apiFetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/logs`)
}

export async function deleteDevice(deviceId) {
  return apiFetch(`/api/v1/devices/${encodeURIComponent(deviceId)}`, {
    method: 'DELETE',
  })
}

// `modules` may be a list of names or { name, version } objects. The version is only
// forwarded when the caller actually knows it; the backend defaults to its own value
// otherwise (apps/api/src/schemas.py ModuleItem.version), so no fake version is invented here.
export async function syncDeviceConfig(deviceId, modules, roomId = null) {
  const payload = {
    room_id: roomId,
    modules: modules.map((entry) => {
      const name = typeof entry === 'string' ? entry : entry?.name
      const version = typeof entry === 'string' ? null : entry?.version
      const item = { name, enabled: true }
      if (version) item.version = version
      return item
    }),
  }

  return apiFetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/config`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
