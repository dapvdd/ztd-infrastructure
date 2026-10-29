// Status is computed by the backend from last_seen (15 s window) and returned by
// /api/v1/devices. The dashboard must only render that value: any local ageing
// would be a second source of truth and could contradict the summary cards.
const KNOWN = new Set(['ONLINE', 'OFFLINE'])

export function normalizeStatus(rawStatus) {
  const status = String(rawStatus ?? '').trim().toUpperCase()
  return KNOWN.has(status) ? status : 'UNKNOWN'
}
