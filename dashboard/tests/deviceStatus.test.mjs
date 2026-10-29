import test from 'node:test'
import assert from 'node:assert/strict'

import { normalizeStatus } from '../src/utils/deviceStatus.mjs'

test('backend ONLINE/OFFLINE values are passed through', () => {
  assert.equal(normalizeStatus('ONLINE'), 'ONLINE')
  assert.equal(normalizeStatus('OFFLINE'), 'OFFLINE')
})

test('case and whitespace are normalized without changing the meaning', () => {
  assert.equal(normalizeStatus(' online '), 'ONLINE')
  assert.equal(normalizeStatus('Offline'), 'OFFLINE')
})

test('missing or non-presence values become UNKNOWN, never a guessed status', () => {
  for (const raw of [null, undefined, '', 'PENDING', 'INSTALLING', 'SUCCESS', 1, true]) {
    assert.equal(normalizeStatus(raw), 'UNKNOWN', `status ${raw}`)
  }
})
