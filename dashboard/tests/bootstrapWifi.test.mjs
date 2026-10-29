import test from 'node:test'
import assert from 'node:assert/strict'

import {
  EAP_METHODS,
  buildEnterpriseNmcliProperties,
  buildPersonalNmcliProperties,
  eapRequiresClientCertificate,
  eapUsesPassword,
  getWifiFormState,
  isEnterpriseWifi,
  isPersonalWifi,
  validateCertPath,
  validateEnterprisePassword,
  validateEnterpriseUsername,
  validateWifiForm,
  validateWifiSsid,
  validateWpaPassphrase,
} from '../src/utils/bootstrapWifi.mjs'

const enterpriseForm = (overrides = {}) => ({
  wifiType: 'Enterprise',
  ssid: 'CampusWiFi',
  username: 'student-01',
  password: 'correct horse battery',
  eapMethod: 'PEAP',
  caCert: '/etc/ssl/certs/campus-ca.pem',
  clientCert: '',
  clientKey: '',
  phase2Auth: 'mschapv2',
  ...overrides,
})

test('SSID is validated against the 802.11 limit', () => {
  assert.equal(validateWifiSsid(''), 'Wi-Fi SSID wajib diisi.')
  assert.equal(validateWifiSsid('   '), 'Wi-Fi SSID wajib diisi.')
  assert.match(validateWifiSsid('a'.repeat(33)), /maksimal 32 karakter/)
  assert.match(validateWifiSsid('bad\u0007ssid'), /karakter kontrol/)
  assert.equal(validateWifiSsid('CampusWiFi'), '')
  assert.equal(validateWifiSsid('a'.repeat(32)), '')
})

test('Enterprise username is required and must be printable', () => {
  assert.match(validateEnterpriseUsername(''), /wajib diisi/)
  assert.match(validateEnterpriseUsername('a'.repeat(254)), /maksimal 253 karakter/)
  assert.match(validateEnterpriseUsername('user\nname'), /karakter kontrol/)
  assert.equal(validateEnterpriseUsername('student-01'), '')
})

test('Enterprise password is required and must not contain control characters', () => {
  assert.match(validateEnterprisePassword(''), /wajib diisi/)
  assert.match(validateEnterprisePassword('   '), /wajib diisi/)
  assert.match(validateEnterprisePassword('pass\nword'), /karakter kontrol/)
  assert.match(validateEnterprisePassword('a'.repeat(257)), /maksimal 256 karakter/)
  assert.equal(validateEnterprisePassword('S3cret!pass'), '')
})

test('certificate paths must be absolute on the Pi', () => {
  assert.equal(validateCertPath('', 'CA certificate'), '')
  assert.match(validateCertPath('etc/certs/ca.pem', 'CA certificate'), /path absolut/)
  assert.equal(validateCertPath('/etc/ssl/certs/ca.pem', 'CA certificate'), '')
  assert.match(validateCertPath('', 'Client certificate', { required: true }), /wajib diisi/)
})

test('Personal networks need an SSID and a WPA passphrase', () => {
  assert.equal(isPersonalWifi('Personal'), true)
  assert.equal(isEnterpriseWifi('Enterprise'), true)
  assert.match(
    validateWifiForm({ wifiType: 'Personal', ssid: 'HomeWiFi' }),
    /password wajib diisi/,
  )
  assert.match(
    validateWifiForm({ wifiType: 'Personal', ssid: 'HomeWiFi', password: 'short' }),
    /8–63 karakter/,
  )
  assert.equal(
    validateWifiForm({ wifiType: 'Personal', ssid: 'HomeWiFi', password: 'HomeWiFiSecret' }),
    '',
  )
  assert.match(
    validateWifiForm({ wifiType: 'Personal', ssid: '' }),
    /SSID wajib diisi/,
  )
})

test('the WPA passphrase follows the WPA length rules and rejects control characters', () => {
  assert.match(validateWpaPassphrase(''), /wajib diisi/)
  assert.match(validateWpaPassphrase('1234567'), /8–63 karakter/)
  assert.match(validateWpaPassphrase('a'.repeat(64)), /8–63 karakter/)
  assert.match(validateWpaPassphrase('pass\nword'), /karakter kontrol/)
  assert.equal(validateWpaPassphrase('12345678'), '')
  assert.equal(validateWpaPassphrase('a'.repeat(63)), '')
})

test('Enterprise networks require username, password and an explicit EAP method', () => {
  assert.match(
    validateWifiForm(enterpriseForm({ username: '' })),
    /username wajib diisi/,
  )
  assert.match(
    validateWifiForm(enterpriseForm({ password: '' })),
    /password wajib diisi/,
  )
  assert.match(
    validateWifiForm(enterpriseForm({ eapMethod: '' })),
    /metode EAP/,
  )
  assert.equal(validateWifiForm(enterpriseForm()), '')
})

test('EAP-TLS requires a client certificate and key, and uses no password', () => {
  assert.equal(eapRequiresClientCertificate('TLS'), true)
  assert.equal(eapRequiresClientCertificate('tls'), true)
  assert.equal(eapRequiresClientCertificate('PEAP'), false)
  assert.equal(eapUsesPassword('PEAP'), true)
  assert.equal(eapUsesPassword('TLS'), false)

  assert.match(
    validateWifiForm(enterpriseForm({ eapMethod: 'TLS', clientCert: '', clientKey: '' })),
    /Client certificate wajib diisi/,
  )
  assert.equal(
    validateWifiForm(enterpriseForm({
      eapMethod: 'TLS',
      clientCert: '/etc/ssl/certs/client.pem',
      clientKey: '/etc/ssl/private/client.key',
      phase2Auth: 'mschapv2',
    })),
    '',
  )
})

test('phase 2 authentication is optional but must be a known method', () => {
  assert.equal(validateWifiForm(enterpriseForm({ phase2Auth: '' })), '')
  assert.match(
    validateWifiForm(enterpriseForm({ phase2Auth: 'ntlm' })),
    /Phase 2 authentication/,
  )
})

test('EAP methods offered by the form are the explicit NetworkManager outer methods', () => {
  assert.deepEqual(EAP_METHODS, ['TTLS', 'PEAP', 'TLS'])
})

test('Enterprise nmcli properties never carry the identity or the password', () => {
  const properties = buildEnterpriseNmcliProperties({
    eapMethod: 'PEAP',
    caCert: '/etc/ssl/certs/campus-ca.pem',
    clientCert: '',
    clientKey: '',
    phase2Auth: 'mschapv2',
  })
  const names = properties.map((property) => property.name)
  assert.deepEqual(names, [
    'wifi-sec.key-mgmt',
    '802-1x.eap',
    '802-1x.ca-cert',
    '802-1x.phase2-auth',
  ])
  assert.equal(properties[0].value, 'wpa-eap')
  assert.equal(properties[1].value, 'peap')
  assert.equal(
    properties.some((property) => property.name === '802-1x.identity'
      || property.name === '802-1x.password'
      || property.name === '802-1x.anonymous-identity'),
    false,
  )
})

test('EAP-TLS adds the client certificate and key and drops phase 2', () => {
  const properties = buildEnterpriseNmcliProperties({
    eapMethod: 'TLS',
    caCert: '',
    clientCert: '/etc/ssl/certs/client.pem',
    clientKey: '/etc/ssl/private/client.key',
    phase2Auth: 'mschapv2',
  })
  const names = properties.map((property) => property.name)
  assert.deepEqual(names, [
    'wifi-sec.key-mgmt',
    '802-1x.eap',
    '802-1x.client-cert',
    '802-1x.private-key',
  ])
  assert.equal(properties[1].value, 'tls')
})

test('personal nmcli properties are WPA-PSK only', () => {
  assert.deepEqual(buildPersonalNmcliProperties(), [
    { name: 'wifi-sec.key-mgmt', value: 'wpa-psk', source: 'literal' },
  ])
})

test('Personal shows only the SSID and the WPA passphrase', () => {
  const state = getWifiFormState({ connectionType: 'Wi-Fi', wifiType: 'Personal' })
  assert.equal(state.showSsid, true)
  assert.equal(state.showPassword, true)
  assert.equal(state.showUsername, false)
  assert.equal(state.showEapMethod, false)
  assert.equal(state.showAdvancedSection, false)
  assert.equal(state.advancedOpen, false)
})

test('Enterprise shows the credentials and the EAP choice, advanced settings stay closed', () => {
  const state = getWifiFormState({ connectionType: 'Wi-Fi', wifiType: 'Enterprise' })
  assert.equal(state.showSsid, true)
  assert.equal(state.showUsername, true)
  assert.equal(state.showPassword, true)
  assert.equal(state.showEapMethod, true)
  assert.equal(state.showAdvancedSection, true)
  assert.equal(state.advancedOpen, false)
  assert.equal(state.showCaCert, false)
  assert.equal(state.showClientCert, false)
  assert.equal(state.showClientKey, false)
  assert.equal(state.showPhase2Auth, false)
  assert.equal(state.requiresClientCertificate, false)
})

test('Advanced Settings can be opened and closed', () => {
  const closed = getWifiFormState({
    connectionType: 'Wi-Fi', wifiType: 'Enterprise', eapMethod: 'PEAP', advancedOpen: false,
  })
  assert.equal(closed.advancedOpen, false)
  assert.equal(closed.showCaCert, false)
  assert.equal(closed.showClientCert, false)
  assert.equal(closed.showClientKey, false)

  const open = getWifiFormState({
    connectionType: 'Wi-Fi', wifiType: 'Enterprise', eapMethod: 'PEAP', advancedOpen: true,
  })
  assert.equal(open.advancedOpen, true)
  assert.equal(open.showCaCert, true)
  assert.equal(open.showClientCert, true)
  assert.equal(open.showClientKey, true)
  assert.equal(open.showPhase2Auth, true)
})

test('EAP-TLS asks for a client certificate and drops phase 2', () => {
  const tls = getWifiFormState({
    connectionType: 'Wi-Fi', wifiType: 'Enterprise', eapMethod: 'TLS', advancedOpen: true,
  })
  assert.equal(tls.requiresClientCertificate, true)
  assert.equal(tls.showClientCert, true)
  assert.equal(tls.showClientKey, true)
  assert.equal(tls.showPhase2Auth, false)
  assert.equal(tls.showCaCert, true)
})

test('Wired shows no Wi-Fi field at all', () => {
  const state = getWifiFormState({
    connectionType: 'Wired', wifiType: 'Enterprise', eapMethod: 'PEAP', advancedOpen: true,
  })
  assert.equal(state.isWifi, false)
  assert.equal(state.isEnterprise, false)
  assert.equal(state.showSsid, false)
  assert.equal(state.showPassword, false)
  assert.equal(state.showUsername, false)
  assert.equal(state.showEapMethod, false)
  assert.equal(state.showAdvancedSection, false)
  assert.equal(state.advancedOpen, false)
  assert.equal(state.requiresClientCertificate, false)
})
