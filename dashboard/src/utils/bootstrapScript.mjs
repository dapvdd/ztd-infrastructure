// Generator for the Raspberry Pi bootstrap script downloaded from the
// dashboard.
//
// Security rules enforced here:
//   * No credential is ever embedded. The WPA-PSK passphrase, the 802.1X
//     identity and the 802.1X password are asked for in the terminal when the
//     script runs, with hidden input for passwords.
//   * Only non-secret configuration (SSID, EAP method, certificate paths, ...)
//     is written into the file, and it is passed to the Pi as a base64 encoded
//     KEY=value block that is sourced by the remote script.
//   * Every value that reaches a shell is single quoted, and every runtime
//     value is expanded inside double quotes so that special characters
//     cannot break the command.

import {
  buildEnterpriseNmcliProperties,
  buildPersonalNmcliProperties,
  eapUsesPassword,
  isEnterpriseWifi,
  normalizeEapMethod,
  normalizePhase2Auth,
} from './bootstrapWifi.mjs'

const SUBNET_MASK_PREFIXES = {
  '255.255.255.0': '24',
  '255.255.255.128': '25',
  '255.255.255.192': '26',
  '255.255.255.224': '27',
  '255.255.255.240': '28',
  '255.255.255.248': '29',
  '255.255.255.252': '30',
}

// NetworkManager property -> variable of the generated config block.
const CONFIG_VAR_BY_PROPERTY = {
  '802-1x.eap': 'WIFI_EAP_METHOD',
  '802-1x.ca-cert': 'WIFI_CA_CERT',
  '802-1x.client-cert': 'WIFI_CLIENT_CERT',
  '802-1x.private-key': 'WIFI_CLIENT_KEY',
  '802-1x.phase2-auth': 'WIFI_PHASE2_AUTH',
}

export const shellQuote = (value) => `'${String(value ?? '').replaceAll("'", "'\\''")}'`

export function normalizeSubnetPrefix(subnet) {
  const value = String(subnet ?? '').trim()
  return SUBNET_MASK_PREFIXES[value] || value
}

export function buildInstallScriptUrl(repositoryUrl) {
  const repository = String(repositoryUrl ?? '').trim().replace(/\.git$/, '')
  const slug = repository.replace('https://github.com/', '')
  return `https://raw.githubusercontent.com/${slug}/main/scripts/install-agent.sh`
}

export function buildWifiProfileName(connectionType, wifiType) {
  if (connectionType !== 'Wi-Fi') return 'ZTD-Wired'
  return isEnterpriseWifi(wifiType) ? 'ZTD-Enterprise' : 'ZTD-WiFi'
}

/**
 * Network section of the remote script (step 4/5).
 * Exported so it can be asserted in tests without building the whole file.
 */
export function buildNetworkLines({
  connectionType = 'Wi-Fi',
  wifiType = 'Personal',
  eapMethod = '',
  caCert = '',
  clientCert = '',
  clientKey = '',
  phase2Auth = '',
} = {}) {
  if (connectionType !== 'Wi-Fi') {
    // Wired: no Wi-Fi configuration at all.
    return [
      'WIRED_DEVICE=$(nmcli -t -f DEVICE,TYPE device status | awk -F: \'$2=="ethernet" && $1!="--" {print $1; exit}\')',
      'if [[ -z "$WIRED_DEVICE" ]]; then echo "No Ethernet device found." >&2; exit 1; fi',
      'if ! nmcli connection show "$WIFI_PROFILE" >/dev/null 2>&1; then',
      '  nmcli connection add type ethernet ifname "$WIRED_DEVICE" con-name "$WIFI_PROFILE"',
      'fi',
    ]
  }

  const lines = [
    '# Detect the Wi-Fi interface; nmcli reports it, wlan0 is the fallback.',
    'WIFI_DEVICE=$(nmcli -t -f DEVICE,TYPE device status | awk -F: \'$2=="wifi" && $1!="--" {print $1; exit}\')',
    'if [[ -z "$WIFI_DEVICE" ]]; then',
    '  if [[ -e /sys/class/net/wlan0 ]]; then WIFI_DEVICE=wlan0; else echo "No Wi-Fi device found." >&2; exit 1; fi',
    'fi',
    'if nmcli connection show "$WIFI_PROFILE" >/dev/null 2>&1; then',
    '  nmcli connection modify "$WIFI_PROFILE" wifi.ssid "$WIFI_SSID"',
    'else',
    '  nmcli connection add type wifi ifname "$WIFI_DEVICE" con-name "$WIFI_PROFILE" ssid "$WIFI_SSID"',
    'fi',
  ]

  if (!isEnterpriseWifi(wifiType)) {
    // Personal network: WPA-PSK. The passphrase is read with hidden input.
    const properties = buildPersonalNmcliProperties()
    const propertyArgs = properties.map((property) => `${property.name} ${shellQuote(property.value)}`)
    lines.push(
      '# WPA-PSK passphrase: asked here, never stored in this file.',
      'IFS= read -r -s -p "Wi-Fi password (WPA-PSK) for $WIFI_SSID: " WIFI_PASSWORD </dev/tty; echo',
      'if [[ -z "$WIFI_PASSWORD" ]]; then echo "Wi-Fi password is required." >&2; exit 1; fi',
      'if (( ${#WIFI_PASSWORD} < 8 || ${#WIFI_PASSWORD} > 63 )); then echo "WPA passphrase must be 8-63 characters." >&2; exit 1; fi',
      `nmcli connection modify "$WIFI_PROFILE" ${propertyArgs.join(' ')} wifi-sec.psk "$WIFI_PASSWORD" || { echo "Failed to apply the WPA-PSK settings." >&2; exit 1; }`,
      'unset WIFI_PASSWORD',
    )
    return lines
  }

  // Enterprise network: 802.1X / EAP.
  const properties = buildEnterpriseNmcliProperties({
    eapMethod,
    caCert,
    clientCert,
    clientKey,
    phase2Auth,
  })
  const propertyArgs = properties.map((property) => {
    if (property.source === 'config') {
      const variable = CONFIG_VAR_BY_PROPERTY[property.name]
      if (!variable) {
        throw new Error(`Unsupported NetworkManager property: ${property.name}`)
      }
      return `${property.name} "$${variable}"`
    }
    return `${property.name} ${shellQuote(property.value)}`
  })

  lines.push(
    '# 802.1X / EAP. The identity and the password are asked for here, they are',
    '# never written into this file. The EAP method, CA certificate, client',
    '# certificate and phase 2 authentication come from the bootstrap form.',
    'IFS= read -r -p "Wi-Fi username (802.1X identity) for $WIFI_SSID: " WIFI_USERNAME </dev/tty',
    'if [[ -z "$WIFI_USERNAME" ]]; then echo "Wi-Fi username is required for Enterprise networks." >&2; exit 1; fi',
    `EAP_ARGS=(${propertyArgs.join(' ')} 802-1x.identity "$WIFI_USERNAME")`,
  )

  if (eapUsesPassword(eapMethod)) {
    lines.push(
      'IFS= read -r -s -p "Wi-Fi password for $WIFI_USERNAME: " WIFI_PASSWORD </dev/tty; echo',
      'if [[ -z "$WIFI_PASSWORD" ]]; then echo "Wi-Fi password is required." >&2; exit 1; fi',
      'EAP_ARGS+=(802-1x.password "$WIFI_PASSWORD")',
    )
  } else {
    lines.push(
      '# EAP-TLS authenticates with a client certificate and key instead of a password.',
      'for EAP_FILE in "$WIFI_CLIENT_CERT" "$WIFI_CLIENT_KEY"; do',
      '  if [[ ! -r "$EAP_FILE" ]]; then echo "EAP-TLS file is not readable on the Pi: $EAP_FILE" >&2; exit 1; fi',
      'done',
    )
  }

  if (String(caCert ?? '').trim()) {
    lines.push(
      'if [[ ! -r "$WIFI_CA_CERT" ]]; then echo "CA certificate is not readable on the Pi: $WIFI_CA_CERT" >&2; exit 1; fi',
    )
  }

  lines.push(
    'nmcli connection modify "$WIFI_PROFILE" "${EAP_ARGS[@]}" || { echo "Failed to apply the 802.1X/EAP settings." >&2; exit 1; }',
    'unset WIFI_PASSWORD WIFI_USERNAME',
    '# Optional: when the RADIUS server requires an outer identity, apply it manually:',
    '#   nmcli connection modify "$WIFI_PROFILE" 802-1x.anonymous-identity "<outer-identity>"',
  )

  return lines
}

/**
 * Build the full bootstrap script.
 * Returns the script text that the dashboard offers as a download.
 */
export function generateBootstrapScript({
  deviceName = '',
  piHost = '',
  piUsername = '',
  connectionType = 'Wi-Fi',
  wifiType = 'Personal',
  wifiSsid = '',
  eapMethod = '',
  caCert = '',
  clientCert = '',
  clientKey = '',
  phase2Auth = '',
  ipMode = 'DHCP',
  localIp = '',
  gateway = '',
  subnet = '',
  dns = '',
  mqttHost = '',
  roomId = '',
  repositoryUrl = '',
} = {}) {
  const name = String(deviceName).trim()
  const ssid = String(wifiSsid).trim()
  const isWifi = connectionType === 'Wi-Fi'
  const enterprise = isWifi && isEnterpriseWifi(wifiType)
  const wifiProfile = buildWifiProfileName(connectionType, wifiType)

  const configLines = [
    `DEVICE_NAME=${shellQuote(name)}`,
    `CONNECTION_TYPE=${shellQuote(String(connectionType).toUpperCase())}`,
    `WIFI_TYPE=${shellQuote(String(wifiType).toUpperCase())}`,
    `WIFI_PROFILE=${shellQuote(wifiProfile)}`,
    `WIFI_SSID=${shellQuote(ssid)}`,
    // WIFI_USERNAME is deliberately absent: the 802.1X identity is a
    // credential and is asked for in the terminal, never embedded here.
    ...(enterprise
      ? [
        `WIFI_EAP_METHOD=${shellQuote(normalizeEapMethod(eapMethod).toLowerCase())}`,
        `WIFI_CA_CERT=${shellQuote(String(caCert).trim())}`,
        `WIFI_CLIENT_CERT=${shellQuote(String(clientCert).trim())}`,
        `WIFI_CLIENT_KEY=${shellQuote(String(clientKey).trim())}`,
        `WIFI_PHASE2_AUTH=${shellQuote(normalizePhase2Auth(phase2Auth))}`,
      ]
      : []),
    `IP_MODE=${shellQuote(String(ipMode).toUpperCase())}`,
    `LOCAL_IP=${shellQuote(String(localIp).trim())}`,
    `GATEWAY=${shellQuote(String(gateway).trim())}`,
    `SUBNET=${shellQuote(normalizeSubnetPrefix(subnet))}`,
    `DNS=${shellQuote(String(dns).trim())}`,
    `MQTT_HOST=${shellQuote(String(mqttHost).trim())}`,
    `ROOM_ID=${shellQuote(String(roomId).trim())}`,
    `REPO_URL=${shellQuote(String(repositoryUrl).trim())}`,
  ]
  const configArguments = configLines.map((line) => `  ${shellQuote(line)} \\`)

  const lines = [
    '#!/usr/bin/env bash',
    'set -euo pipefail',
    '',
    `SSH_TARGET=${shellQuote(`${String(piUsername).trim()}@${String(piHost).trim()}`)}`,
    'if ! command -v ssh >/dev/null 2>&1 || ! command -v base64 >/dev/null 2>&1; then',
    '  echo "This laptop needs ssh and base64 installed." >&2',
    '  exit 1',
    'fi',
    'if [[ ! -r /dev/tty ]]; then',
    '  echo "Run this script from a terminal so SSH and bootstrap can prompt for passwords." >&2',
    '  exit 1',
    'fi',
    '',
    'CONFIG_B64=$(printf \'%s\\n\' \\',
    ...configArguments,
    '  | base64 | tr -d \'\\n\')',
    '',
    'echo "Connecting to $SSH_TARGET. SSH and sudo may prompt for the Pi password."',
    'ssh -tt "$SSH_TARGET" "sudo bash -s -- \'$CONFIG_B64\'" <<\'REMOTE_SCRIPT\'',
    'set -euo pipefail',
    'CONFIG_B64=$1',
    'source <(printf \'%s\' "$CONFIG_B64" | base64 --decode)',
    '',
    'echo "[1/5] Preparing Raspberry Pi..."',
    'hostnamectl set-hostname "$DEVICE_NAME"',
    'systemctl enable --now ssh',
    '',
    'if ! command -v nmcli >/dev/null 2>&1; then',
    '  echo "NetworkManager (nmcli) is required. Install/enable it before running this script." >&2',
    '  exit 1',
    'fi',
    '# 802.1X properties used below are available in NetworkManager 1.x',
    '# (Debian 11 ships 1.30, Debian 12 ships 1.42).',
    'echo "NetworkManager: $(nmcli --version 2>/dev/null | head -n1)"',
    'if ! command -v curl >/dev/null 2>&1; then',
    '  apt-get update',
    '  apt-get install -y curl',
    'fi',
    '',
    'echo "[2/5] Installing and connecting Tailscale..."',
    'if ! command -v tailscale >/dev/null 2>&1; then',
    '  curl -fsSL https://tailscale.com/install.sh | sh',
    'fi',
    'IFS= read -r -s -p "Tailscale auth key: " TAILSCALE_AUTH_KEY </dev/tty; echo',
    'if [[ -z "$TAILSCALE_AUTH_KEY" ]]; then echo "Tailscale auth key is required." >&2; exit 1; fi',
    'tailscale up --auth-key="$TAILSCALE_AUTH_KEY" --hostname="$DEVICE_NAME"',
    'unset TAILSCALE_AUTH_KEY',
    '',
    'echo "[3/5] Installing ZTD edge agent..."',
    'export MQTT_HOST ROOM_ID REPO_URL',
    `curl -fsSL ${shellQuote(buildInstallScriptUrl(repositoryUrl))} | bash`,
    '',
    'echo "[4/5] Configuring network..."',
  ]

  lines.push(...buildNetworkLines({
    connectionType,
    wifiType,
    eapMethod,
    caCert,
    clientCert,
    clientKey,
    phase2Auth,
  }))

  lines.push('nmcli connection modify "$WIFI_PROFILE" connection.autoconnect yes')

  if (String(ipMode).toUpperCase() === 'STATIC') {
    lines.push(
      'nmcli connection modify "$WIFI_PROFILE" ipv4.method manual ipv4.addresses "$LOCAL_IP/$SUBNET" ipv4.gateway "$GATEWAY" ipv4.dns "$DNS"',
    )
  } else {
    lines.push(
      'nmcli connection modify "$WIFI_PROFILE" ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""',
    )
  }

  lines.push(
    'echo "[5/5] Applying network profile..."',
    'systemd-run --on-active=5s --collect nmcli connection up "$WIFI_PROFILE"',
    'echo "Network reconfiguration scheduled. The SSH session may disconnect as the Pi reconnects."',
    'echo "Device: $DEVICE_NAME"',
    'echo "Tailscale IP: $(tailscale ip -4)"',
    'echo "The device should appear in the ZTD dashboard after MQTT registration."',
    'REMOTE_SCRIPT',
    '',
  )

  return lines.join('\n')
}
