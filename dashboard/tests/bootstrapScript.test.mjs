import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildInstallScriptUrl,
  buildNetworkLines,
  buildWifiProfileName,
  generateBootstrapScript,
  normalizeSubnetPrefix,
  shellQuote,
} from '../src/utils/bootstrapScript.mjs'

const baseForm = (overrides = {}) => ({
  deviceName: 'raspi-lab-01',
  piHost: 'ztd.local',
  piUsername: 'pi',
  connectionType: 'Wi-Fi',
  wifiType: 'Personal',
  wifiSsid: 'CampusWiFi',
  eapMethod: '',
  caCert: '',
  clientCert: '',
  clientKey: '',
  phase2Auth: '',
  ipMode: 'DHCP',
  localIp: '',
  gateway: '',
  subnet: '',
  dns: '',
  mqttHost: '100.105.163.126',
  roomId: 'lab-01',
  repositoryUrl: 'https://github.com/NICEganteng/modulraspipmld.git',
  ...overrides,
})

const configBlock = (script) => {
  const lines = script.split('\n')
  const start = lines.findIndex((line) => line.includes("printf '%s\\n'"))
  const end = lines.findIndex((line) => line.includes('| base64'))
  assert.ok(start >= 0 && end > start, 'config block not found')
  return lines.slice(start + 1, end)
}

test('personal networks configure WPA-PSK and ask for the passphrase at runtime', () => {
  const script = generateBootstrapScript(baseForm())
  assert.match(script, /wifi-sec\.key-mgmt 'wpa-psk'/)
  assert.match(script, /wifi-sec\.psk "\$WIFI_PASSWORD"/)
  assert.match(script, /read -r -s -p "Wi-Fi password \(WPA-PSK\)/)
  assert.equal(script.includes('802-1x'), false)
  assert.equal(script.includes('WIFI_EAP_METHOD'), false)
  assert.equal(script.includes('WIFI_USERNAME'), false)
})

test('enterprise networks configure explicit 802.1X/EAP and prompt for the identity', () => {
  const script = generateBootstrapScript(baseForm({
    wifiType: 'Enterprise',
    eapMethod: 'PEAP',
    caCert: '/etc/ssl/certs/campus-ca.pem',
    phase2Auth: 'mschapv2',
  }))
  assert.match(script, /wifi-sec\.key-mgmt 'wpa-eap'/)
  assert.match(script, /802-1x\.eap "\$WIFI_EAP_METHOD"/)
  assert.match(script, /802-1x\.identity "\$WIFI_USERNAME"/)
  assert.match(script, /802-1x\.password "\$WIFI_PASSWORD"/)
  assert.match(script, /802-1x\.ca-cert "\$WIFI_CA_CERT"/)
  assert.match(script, /802-1x\.phase2-auth "\$WIFI_PHASE2_AUTH"/)
  assert.match(script, /read -r -p "Wi-Fi username \(802\.1X identity\)/)
  assert.match(script, /read -r -s -p "Wi-Fi password for \$WIFI_USERNAME/)
  // The outer identity is documented, but never applied automatically.
  assert.equal(/^\s*nmcli .*802-1x\.anonymous-identity/m.test(script), false)
  assert.match(script, /#\s+nmcli connection modify "\$WIFI_PROFILE" 802-1x\.anonymous-identity/)
})

test('EAP-TLS uses a client certificate instead of a password', () => {
  const script = generateBootstrapScript(baseForm({
    wifiType: 'Enterprise',
    eapMethod: 'TLS',
    clientCert: '/etc/ssl/certs/client.pem',
    clientKey: '/etc/ssl/private/client.key',
    phase2Auth: 'mschapv2',
  }))
  assert.match(script, /802-1x\.client-cert "\$WIFI_CLIENT_CERT"/)
  assert.match(script, /802-1x\.private-key "\$WIFI_CLIENT_KEY"/)
  assert.equal(script.includes('802-1x.password'), false)
  assert.equal(script.includes('802-1x.phase2-auth'), false)
  assert.match(script, /EAP-TLS file is not readable on the Pi/)
})

test('no credential is written into the downloaded script', () => {
  const script = generateBootstrapScript(baseForm({
    wifiType: 'Enterprise',
    eapMethod: 'PEAP',
    username: 'student-01',
    password: 'S3cret!pass',
  }))
  const block = configBlock(script).join('\n')
  assert.equal(block.includes('WIFI_USERNAME'), false)
  assert.equal(block.includes('WIFI_PASSWORD'), false)
  assert.equal(block.includes('student-01'), false)
  assert.equal(block.includes('S3cret!pass'), false)
})

test('the personal passphrase is only asked for at runtime, never embedded', () => {
  const script = generateBootstrapScript(baseForm({ password: 'HomeWiFiSecret' }))
  const block = configBlock(script).join('\n')
  assert.equal(block.includes('HomeWiFiSecret'), false)
  assert.equal(block.includes('WIFI_PASSWORD'), false)
  assert.match(script, /read -r -s -p "Wi-Fi password \(WPA-PSK\)/)
  assert.match(script, /wifi-sec\.psk "\$WIFI_PASSWORD"/)
})

test('wired deployments never touch the Wi-Fi configuration', () => {
  const script = generateBootstrapScript(baseForm({ connectionType: 'Wired' }))
  assert.match(script, /nmcli connection add type ethernet/)
  assert.equal(script.includes('type wifi'), false)
  assert.equal(script.includes('wifi-sec'), false)
  assert.equal(script.includes('802-1x'), false)
  assert.equal(script.includes('WIFI_PASSWORD'), false)
  assert.equal(script.includes('Wi-Fi password'), false)
})

test('special characters are shell quoted instead of interpolated raw', () => {
  const ssid = "Lab'; rm -rf / #$(id)`whoami`"
  const script = generateBootstrapScript(baseForm({ wifiSsid: ssid }))
  const block = configBlock(script).join('\n')
  assert.equal(block.includes("WIFI_SSID='Lab'; rm"), false)
  assert.match(block, /WIFI_SSID=/)
  assert.match(block, /'\\''/)
})

test('the runtime prompts keep the credentials inside double quotes', () => {
  const script = generateBootstrapScript(baseForm({ wifiType: 'Enterprise', eapMethod: 'PEAP' }))
  assert.match(script, /nmcli connection modify "\$WIFI_PROFILE" "\$\{EAP_ARGS\[@\]\}"/)
  assert.equal(script.includes('"$WIFI_PASSWORD" "$WIFI_USERNAME"'), false)
  assert.equal(script.includes('$WIFI_PASSWORD $WIFI_USERNAME'), false)
})

test('network section of the wired profile only manages the ethernet device', () => {
  const lines = buildNetworkLines({ connectionType: 'Wired' })
  const text = lines.join('\n')
  assert.match(text, /WIRED_DEVICE=/)
  assert.equal(text.includes('WIFI_DEVICE'), false)
  assert.equal(text.includes('WIFI_PASSWORD'), false)
})

test('subnet masks are converted to a CIDR prefix', () => {
  assert.equal(normalizeSubnetPrefix('255.255.255.0'), '24')
  assert.equal(normalizeSubnetPrefix('255.255.255.252'), '30')
  assert.equal(normalizeSubnetPrefix('24'), '24')
  assert.equal(normalizeSubnetPrefix(' 26 '), '26')
})

test('profile names stay stable per connection type', () => {
  assert.equal(buildWifiProfileName('Wi-Fi', 'Personal'), 'ZTD-WiFi')
  assert.equal(buildWifiProfileName('Wi-Fi', 'Enterprise'), 'ZTD-Enterprise')
  assert.equal(buildWifiProfileName('Wired', 'Personal'), 'ZTD-Wired')
})

test('the install script URL is derived from the agent repository', () => {
  assert.equal(
    buildInstallScriptUrl('https://github.com/NICEganteng/modulraspipmld.git'),
    'https://raw.githubusercontent.com/NICEganteng/modulraspipmld/main/scripts/install-agent.sh',
  )
})

test('shellQuote escapes single quotes the POSIX way', () => {
  assert.equal(shellQuote('simple'), "'simple'")
  assert.equal(shellQuote("it's"), "'it'\\''s'")
})
