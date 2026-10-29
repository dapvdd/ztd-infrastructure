import test from 'node:test'
import assert from 'node:assert/strict'

import { formatRelativeAge } from '../src/utils/presenceDisplay.mjs'

const NOW = Date.parse('2026-10-21T11:00:00Z')

test('missing or invalid timestamps have no age label', () => {
  for (const value of [null, undefined, '', 'not-a-date']) {
    assert.equal(formatRelativeAge(value, NOW), null)
  }
})

test('very recent contact is labelled baru saja', () => {
  assert.equal(formatRelativeAge('2026-10-21T10:59:55Z', NOW), 'baru saja')
})

test('seconds are shown below one minute', () => {
  assert.equal(formatRelativeAge('2026-10-21T10:59:50Z', NOW), '10 dtk lalu')
  assert.equal(formatRelativeAge('2026-10-21T10:59:01Z', NOW), '59 dtk lalu')
})

test('minutes and hours are coarse and never negative', () => {
  assert.equal(formatRelativeAge('2026-10-21T10:59:00Z', NOW), '1 mnt lalu')
  assert.equal(formatRelativeAge('2026-10-21T10:00:00Z', NOW), '1 jam lalu')
  assert.equal(formatRelativeAge('2026-10-20T10:00:00Z', NOW), '1 hari lalu')
  assert.equal(formatRelativeAge('2026-10-21T11:00:30Z', NOW), 'baru saja')
})
