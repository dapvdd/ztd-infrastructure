import test from 'node:test'
import assert from 'node:assert/strict'

import {
  normalizeUnit,
  summarizeTelemetry,
  toCelsius,
  toFiniteNumber,
} from '../src/utils/telemetry.mjs'

const close = (actual, expected, epsilon = 1e-9) => {
  assert.ok(Math.abs(actual - expected) < epsilon, `${actual} != ${expected}`)
}

test('normalizeUnit accepts explicit tokens only', () => {
  const cases = {
    C: 'C',
    c: 'C',
    celsius: 'C',
    '\u00b0C': 'C',
    ' F ': 'F',
    fahrenheit: 'F',
    '\u00b0F': 'F',
  }
  for (const [raw, expected] of Object.entries(cases)) {
    assert.equal(normalizeUnit(raw), expected, `unit ${raw}`)
  }
})

test('normalizeUnit never guesses an unknown or missing unit', () => {
  for (const raw of [null, undefined, '', 'K', 'kelvin', 'rankine', 5, true]) {
    assert.equal(normalizeUnit(raw), null, `unit ${raw}`)
  }
})

test('toFiniteNumber rejects null, booleans and non-finite input', () => {
  assert.equal(toFiniteNumber('42.5'), 42.5)
  assert.equal(toFiniteNumber(42), 42)
  assert.equal(toFiniteNumber(null), null)
  assert.equal(toFiniteNumber(''), null)
  assert.equal(toFiniteNumber(true), null)
  assert.equal(toFiniteNumber('abc'), null)
  assert.equal(toFiniteNumber(Number.NaN), null)
  assert.equal(toFiniteNumber(Number.POSITIVE_INFINITY), null)
})

test('toCelsius converts only when a unit is known', () => {
  close(toCelsius(42.5, 'C'), 42.5)
  close(toCelsius(108.5, 'F'), 42.5)
  assert.equal(toCelsius(42.5, null), null)
  assert.equal(toCelsius(null, 'C'), null)
})

test('empty window has no average', () => {
  const summary = summarizeTelemetry([])
  assert.equal(summary.mode, 'empty')
  assert.equal(summary.average, null)
  assert.deepEqual(summary.counts, {
    total: 0, valued: 0, reported: 0, legacy: 0, celsius: 0, fahrenheit: 0,
  })
})

test('reported Celsius window averages in Celsius', () => {
  const summary = summarizeTelemetry([
    { timestamp: 't1', cpu_temp: 41.5, unit: 'C', schema_version: 2 },
    { timestamp: 't2', cpu_temp: 43.5, unit: 'C', schema_version: 2 },
  ])
  assert.equal(summary.mode, 'celsius')
  close(summary.average, 42.5)
  assert.equal(summary.legacyExcluded, 0)
  assert.deepEqual(summary.reportedUnits, ['C'])
})

test('reported Fahrenheit window is converted for display and average', () => {
  const summary = summarizeTelemetry([
    { timestamp: 't1', cpu_temp: 104.0, unit: 'F' },
    { timestamp: 't2', cpu_temp: 113.0, unit: 'F' },
  ])
  assert.equal(summary.mode, 'fahrenheit')
  close(summary.average, 42.5)
  close(summary.points[0].celsius, 40)
  close(summary.points[1].celsius, 45)
})

test('legacy window stays unlabeled and out of the official average', () => {
  const summary = summarizeTelemetry([
    { timestamp: 't1', cpu_temp: 43.82 },
    { timestamp: 't2', cpu_temp: 107.4 },
  ])
  assert.equal(summary.mode, 'legacy')
  assert.equal(summary.average, null)
  assert.equal(summary.legacyExcluded, 2)
  assert.deepEqual(summary.points.map((point) => point.unit), [null, null])
  assert.deepEqual(summary.points.map((point) => point.celsius), [null, null])
})

test('legacy samples never dilute a reported Celsius average', () => {
  const summary = summarizeTelemetry([
    { cpu_temp: 41.0, unit: 'C' },
    { cpu_temp: 43.0, unit: 'C' },
    { cpu_temp: 107.6 },
  ])
  assert.equal(summary.mode, 'mixed')
  close(summary.average, 42.0)
  assert.equal(summary.legacyExcluded, 1)
  assert.equal(summary.mixedUnits, false)
  assert.deepEqual(summary.reportedUnits, ['C'])
})

test('unknown units are treated as unlabeled, not as Celsius', () => {
  const summary = summarizeTelemetry([
    { cpu_temp: 300, unit: 'K', schema_version: 2 },
    { cpu_temp: 42.0, unit: 'C' },
  ])
  assert.equal(summary.mode, 'mixed')
  close(summary.average, 42.0)
  assert.equal(summary.legacyExcluded, 1)
})

test('mixed Celsius and Fahrenheit is never averaged across units', () => {
  const summary = summarizeTelemetry([
    { cpu_temp: 42.0, unit: 'C' },
    { cpu_temp: 107.6, unit: 'F' },
  ])
  assert.equal(summary.mode, 'mixed')
  assert.equal(summary.average, null)
  assert.equal(summary.mixedUnits, true)
  assert.deepEqual(summary.reportedUnits, ['C', 'F'])
})

test('null and invalid values do not break the window', () => {
  const summary = summarizeTelemetry([
    { cpu_temp: null, unit: 'C' },
    { cpu_temp: 'abc', unit: 'C' },
    { cpu_temp: Number.NaN, unit: 'C' },
    { cpu_temp: '42.3', unit: 'C' },
  ])
  assert.equal(summary.mode, 'celsius')
  assert.equal(summary.counts.total, 4)
  assert.equal(summary.counts.valued, 1)
  close(summary.average, 42.3)
})

test('all-null window reports empty, not zero', () => {
  const summary = summarizeTelemetry([
    { cpu_temp: null, unit: 'C' },
    { cpu_temp: null, unit: 'C' },
  ])
  assert.equal(summary.mode, 'empty')
  assert.equal(summary.average, null)
  assert.equal(summary.counts.valued, 0)
})

test('v1 backend samples are legacy and keep their timestamp/room metadata', () => {
  const summary = summarizeTelemetry([{ timestamp: '2026-10-01T06:15:13Z', cpu_temp: 43.82 }])
  assert.equal(summary.mode, 'legacy')
  assert.equal(summary.points[0].timestamp, '2026-10-01T06:15:13Z')
  assert.equal(summary.points[0].roomId, null)
})
