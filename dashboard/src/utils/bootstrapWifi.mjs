// Wi-Fi validation and 802.1X/EAP parameter helpers for the Raspberry Pi
// bootstrap form.
//
// Two network profiles are supported:
//
//   * Personal  -> WPA-PSK. The passphrase is only ever asked for in the
//                  terminal when the generated script runs.
//   * Enterprise -> 802.1X/EAP. The EAP method, CA certificate, client
//                  certificate and phase 2 authentication are explicit form
//                  inputs: the dashboard does not guess them, because the
//                  campus network requirements are not known here.
//
// Nothing in this module returns or stores a secret. The 802.1X identity and
// the password are prompted for at runtime, so they are never part of the
// downloaded bootstrap file.

export const WIFI_TYPE_PERSONAL = 'Personal'
export const WIFI_TYPE_ENTERPRISE = 'Enterprise'

// nmcli expects the EAP outer method in lower case.
export const EAP_METHODS = ['TTLS', 'PEAP', 'TLS']
export const PHASE2_AUTH_METHODS = ['', 'mschapv2', 'pap', 'gtc']

export const MAX_SSID_LENGTH = 32
export const MAX_IDENTITY_LENGTH = 253
export const MAX_PASSWORD_LENGTH = 256

const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/

const hasControlCharacters = (value) => CONTROL_CHARACTERS.test(String(value ?? ''))

export const isEnterpriseWifi = (wifiType) => wifiType === WIFI_TYPE_ENTERPRISE

export const isPersonalWifi = (wifiType) => !isEnterpriseWifi(wifiType)

export const eapRequiresClientCertificate = (eapMethod) =>
  String(eapMethod ?? '').trim().toUpperCase() === 'TLS'

export const eapUsesPassword = (eapMethod) => !eapRequiresClientCertificate(eapMethod)

export const normalizeEapMethod = (eapMethod) =>
  String(eapMethod ?? '').trim().toUpperCase()

export const normalizePhase2Auth = (phase2Auth) =>
  String(phase2Auth ?? '').trim().toLowerCase()

export function validateWifiSsid(value) {
  const ssid = String(value ?? '').trim()
  if (!ssid) return 'Wi-Fi SSID wajib diisi.'
  if (ssid.length > MAX_SSID_LENGTH) {
    return `Wi-Fi SSID maksimal ${MAX_SSID_LENGTH} karakter (batas standar 802.11).`
  }
  if (hasControlCharacters(ssid)) {
    return 'Wi-Fi SSID tidak boleh memuat karakter kontrol.'
  }
  return ''
}

export function validateEnterpriseUsername(value) {
  const username = String(value ?? '').trim()
  if (!username) return 'Wi-Fi username wajib diisi untuk jaringan Enterprise.'
  if (username.length > MAX_IDENTITY_LENGTH) {
    return `Wi-Fi username maksimal ${MAX_IDENTITY_LENGTH} karakter.`
  }
  if (hasControlCharacters(username)) {
    return 'Wi-Fi username tidak boleh memuat karakter kontrol.'
  }
  return ''
}

export function validateEnterprisePassword(value) {
  const password = String(value ?? '')
  if (!password.trim()) return 'Wi-Fi password wajib diisi untuk jaringan Enterprise.'
  if (password.length > MAX_PASSWORD_LENGTH) {
    return `Wi-Fi password maksimal ${MAX_PASSWORD_LENGTH} karakter.`
  }
  if (hasControlCharacters(password)) {
    return 'Wi-Fi password tidak boleh memuat karakter kontrol atau baris baru.'
  }
  return ''
}

export function validateWpaPassphrase(value) {
  const password = String(value ?? '')
  if (!password) return 'Wi-Fi password wajib diisi untuk jaringan Personal.'
  if (password.length < 8 || password.length > 63) {
    return 'Passphrase WPA harus 8–63 karakter.'
  }
  if (hasControlCharacters(password)) {
    return 'Wi-Fi password tidak boleh memuat karakter kontrol atau baris baru.'
  }
  return ''
}

export function validateCertPath(value, label, { required = false } = {}) {
  const path = String(value ?? '').trim()
  if (!path) return required ? `${label} wajib diisi.` : ''
  if (!path.startsWith('/')) {
    return `${label} harus berupa path absolut di Raspberry Pi (contoh /etc/ssl/certs/campus-ca.pem).`
  }
  if (hasControlCharacters(path)) {
    return `${label} tidak boleh memuat karakter kontrol.`
  }
  return ''
}

export function validateEapMethod(value) {
  const method = normalizeEapMethod(value)
  if (!method) {
    return 'Pilih metode EAP (TTLS, PEAP, atau TLS) sesuai requirement jaringan Enterprise.'
  }
  if (!EAP_METHODS.includes(method)) {
    return 'Metode EAP harus TTLS, PEAP, atau TLS.'
  }
  return ''
}

export function validatePhase2Auth(value) {
  const phase2 = normalizePhase2Auth(value)
  if (!PHASE2_AUTH_METHODS.includes(phase2)) {
    return 'Phase 2 authentication harus mschapv2, pap, gtc, atau dikosongkan.'
  }
  return ''
}

/**
 * Validate the Wi-Fi part of the bootstrap form.
 * Returns an empty string when the form is valid, otherwise a message.
 */
export function validateWifiForm({
  wifiType,
  ssid,
  username,
  password,
  eapMethod,
  caCert,
  clientCert,
  clientKey,
  phase2Auth,
} = {}) {
  const ssidError = validateWifiSsid(ssid)
  if (ssidError) return ssidError

  if (isPersonalWifi(wifiType)) {
    // Personal uses WPA-PSK, so the passphrase follows the WPA length rules.
    return validateWpaPassphrase(password)
  }

  const usernameError = validateEnterpriseUsername(username)
  if (usernameError) return usernameError

  const passwordError = validateEnterprisePassword(password)
  if (passwordError) return passwordError

  const methodError = validateEapMethod(eapMethod)
  if (methodError) return methodError

  const method = normalizeEapMethod(eapMethod)

  const caCertError = validateCertPath(caCert, 'CA certificate')
  if (caCertError) return caCertError

  const clientCertError = validateCertPath(clientCert, 'Client certificate', {
    required: eapRequiresClientCertificate(method),
  })
  if (clientCertError) return clientCertError

  const clientKeyError = validateCertPath(clientKey, 'Client private key', {
    required: eapRequiresClientCertificate(method),
  })
  if (clientKeyError) return clientKeyError

  const phase2Error = validatePhase2Auth(phase2Auth)
  if (phase2Error) return phase2Error

  return ''
}

/**
 * Which Wi-Fi fields the bootstrap form shows.
 *
 * The component renders from this state, so the visibility rules stay
 * testable without a browser:
 *   Personal   -> SSID + WPA passphrase
 *   Enterprise -> SSID + 802.1X identity + password + EAP method, while the
 *                 remaining 802.1X parameters sit behind a collapsible
 *                 "Advanced Settings" section
 *   Wired      -> no Wi-Fi field at all
 */
export function getWifiFormState({
  connectionType = 'Wi-Fi',
  wifiType = 'Personal',
  eapMethod = '',
  advancedOpen = false,
} = {}) {
  const isWifi = connectionType === 'Wi-Fi'
  const enterprise = isWifi && isEnterpriseWifi(wifiType)
  const tls = enterprise && eapRequiresClientCertificate(eapMethod)
  const advanced = enterprise && Boolean(advancedOpen)

  return {
    isWifi,
    isEnterprise: enterprise,
    showSsid: isWifi,
    showPassword: isWifi,
    showUsername: enterprise,
    showEapMethod: enterprise,
    showAdvancedSection: enterprise,
    advancedOpen: advanced,
    showCaCert: advanced,
    showClientCert: advanced,
    showClientKey: advanced,
    showPhase2Auth: advanced && !tls,
    requiresClientCertificate: tls,
  }
}

/**
 * NetworkManager properties for a WPA2-Enterprise (802.1X) profile.
 *
 * `source` tells the script generator where the value comes from:
 *   literal -> a constant that is safe to embed (never a secret)
 *   config  -> a non-secret variable of the generated bootstrap config block
 *
 * The identity and the password are intentionally NOT part of this list: they
 * are read from the terminal at runtime and must never be embedded in the
 * downloaded script.
 */
export function buildEnterpriseNmcliProperties({
  eapMethod,
  caCert,
  clientCert,
  clientKey,
  phase2Auth,
} = {}) {
  const method = normalizeEapMethod(eapMethod).toLowerCase()
  const properties = [
    { name: 'wifi-sec.key-mgmt', value: 'wpa-eap', source: 'literal' },
    { name: '802-1x.eap', value: method, source: 'config' },
  ]

  const ca = String(caCert ?? '').trim()
  if (ca) properties.push({ name: '802-1x.ca-cert', value: ca, source: 'config' })

  const cert = String(clientCert ?? '').trim()
  if (cert) properties.push({ name: '802-1x.client-cert', value: cert, source: 'config' })

  const key = String(clientKey ?? '').trim()
  if (key) properties.push({ name: '802-1x.private-key', value: key, source: 'config' })

  const phase2 = normalizePhase2Auth(phase2Auth)
  if (phase2 && method !== 'tls') {
    properties.push({ name: '802-1x.phase2-auth', value: phase2, source: 'config' })
  }

  return properties
}

/** NetworkManager properties for a personal (WPA-PSK) profile. */
export function buildPersonalNmcliProperties() {
  return [
    { name: 'wifi-sec.key-mgmt', value: 'wpa-psk', source: 'literal' },
  ]
}
