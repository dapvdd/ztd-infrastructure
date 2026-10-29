// Relative "last contact" labels for the fleet table and detail panel.
// The timestamp is supplied by the API; this helper never invents presence.
export function formatRelativeAge(value, now = Date.now()) {
  if (value === null || value === undefined || value === '') return null

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null

  const seconds = Math.max(0, Math.floor((now - date.getTime()) / 1000))
  if (seconds < 10) return 'baru saja'
  if (seconds < 60) return `${seconds} dtk lalu`

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} mnt lalu`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} jam lalu`

  return `${Math.floor(hours / 24)} hari lalu`
}
