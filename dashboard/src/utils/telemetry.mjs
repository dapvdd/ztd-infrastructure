// Temperature telemetry contract helpers.
//
// The unit is a property of the *sample*, reported by the backend. It is never
// inferred from the magnitude of the number: a legacy sample without a unit stays
// unlabeled and is excluded from the official average.
//
// API sample shape (contract v2):
//   { timestamp, cpu_temp, unit: 'C' | 'F' | null,
//     unit_source: 'reported' | 'legacy_unlabeled', schema_version, room_id }
// Older backends return only { timestamp, cpu_temp }, which is treated as legacy.

const UNIT_ALIASES = {
  c: 'C',
  celsius: 'C',
  f: 'F',
  fahrenheit: 'F',
}

export function normalizeUnit(rawUnit) {
  if (rawUnit === null || rawUnit === undefined || typeof rawUnit === 'boolean') return null
  const token = String(rawUnit)
    .trim()
    .toLowerCase()
    .replaceAll('\u00b0', '')
    .replaceAll('degrees', '')
    .replaceAll('degree', '')
    .trim()
  return UNIT_ALIASES[token] ?? null
}

export function toFiniteNumber(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function toCelsius(value, unit) {
  const number = toFiniteNumber(value)
  if (number === null) return null
  if (unit === 'C') return number
  if (unit === 'F') return (number - 32) / 1.8
  return null
}

function normalizeSample(sample) {
  if (!sample || typeof sample !== 'object') return null
  const value = toFiniteNumber(sample.cpu_temp ?? sample.temp ?? sample.value)
  const unit = normalizeUnit(sample.unit)
  return {
    timestamp: sample.timestamp ?? sample.recorded_at ?? null,
    value,
    unit,
    celsius: toCelsius(value, unit),
    schemaVersion: sample.schema_version ?? null,
    roomId: sample.room_id ?? null,
  }
}

/**
 * Summarise a telemetry window without ever mixing units in the average.
 *
 * - `average` is in °C and only exists when every *reported* sample shares one unit.
 * - Unlabeled legacy samples never contribute to `average`.
 * - Mixed C + F windows yield `average: null` (`mixedUnits: true`).
 */
export function summarizeTelemetry(samples) {
  const source = Array.isArray(samples) ? samples : []
  const points = source.map(normalizeSample).filter(Boolean)

  const valued = points.filter((point) => point.value !== null)
  const reported = valued.filter((point) => point.unit !== null)
  const legacy = valued.filter((point) => point.unit === null)

  const units = new Set(reported.map((point) => point.unit))
  const mixedUnits = units.size > 1
  const average = reported.length && !mixedUnits
    ? reported.reduce((sum, point) => sum + point.celsius, 0) / reported.length
    : null

  let mode = 'empty'
  if (valued.length) {
    if (!reported.length) {
      mode = 'legacy'
    } else if (!legacy.length && units.size === 1) {
      mode = units.has('C') ? 'celsius' : 'fahrenheit'
    } else {
      mode = 'mixed'
    }
  }

  return {
    mode,
    points,
    average,
    mixedUnits,
    reportedUnits: [...units].sort(),
    legacyExcluded: legacy.length,
    counts: {
      total: points.length,
      valued: valued.length,
      reported: reported.length,
      legacy: legacy.length,
      celsius: reported.filter((point) => point.unit === 'C').length,
      fahrenheit: reported.filter((point) => point.unit === 'F').length,
    },
  }
}
