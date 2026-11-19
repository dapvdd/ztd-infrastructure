# 📜 Spesifikasi Kontrak Antarmuka & Standar Penamaan Terpadu (Unified System Contracts)

> **Single Source of Truth**: Dokumen ini adalah acuan resmi semua kontrak data, skema REST API, topik MQTT, variabel `.env`, dan standar penamaan antarkomponen pada Sistem Provisioning ZTD. Semua anggota tim **wajib mematuhi format dan penamaan di bawah ini** agar integrasi berjalan mulus tanpa konflik.

---

## 1. Standar Penamaan Global (*Naming Conventions*)

| Entitas | Format / Aturan | Contoh Valid | Contoh Tidak Valid |
| :--- | :--- | :--- | :--- |
| **Device ID (Raspi)** | `raspi-[a-z0-9-]{3,20}` (lowercase, angka, tanda strip) | `raspi-plant-01`, `raspi-edge-line2` | `Raspi_01` (ada huruf besar & underscore) |
| **Hostname Raspi** | Sama persis dengan `Device ID` | `raspi-plant-01` | `raspberrypi` (default/ambigu) |
| **Node ID (ESP)** | `esp32-[a-z0-9-]{3,20}` atau `esp8266-[a-z0-9-]{3,20}` | `esp32-temp-01`, `esp32-press-a` | `ESP_NODE#1` |
| **MAC Address ESP** | Format 6 heksadesimal terpisah kolon | `24:6F:28:AB:CD:EF` | `246f28abcdef` |
| **Nama Modul** | `[a-z0-9-]{3,30}` | `temperature`, `energy-monitor` | `Temp_Module.py` |
| **Topik MQTT** | `esp/{node_id}/sensors/{sensor_type}` | `esp/esp32-temp-01/sensors/dht22` | `esp\sensors\temp` (salah slash) |
| **Direktori Edge** | Lowercase dengan path absolut di bawah `/opt/ztd/` | `/opt/ztd/agent/`, `/opt/ztd/modules/` | `/home/pi/agent/` (inkonsisten) |

---

## 2. Skema Autentikasi Berbasis Header (*Header-Based Authentication*)

Sistem mengandalkan **HTTP Headers** untuk otentikasi dan identifikasi perangkat pada proses provisioning:

### A. Autentikasi Raspberry Pi (Username & Password)
Raspberry Pi menggunakan standar **HTTP Basic Authentication** (atau header kredensial) saat berkomunikasi dengan VPS Provisioning:
* **Header**: `Authorization: Basic <base64(username:password)>`
* **Contoh Kredensial**:
  * Username: `raspi-plant-01`
  * Password: Dihasilkan saat registrasi form awal dan disimpan dalam `.env` Raspi (`PROVISIONING_API_PASSWORD`).

### B. Autentikasi Node ESP / IoT (Hardware Identifier)
Node ESP tidak menggunakan form login kompleks, melainkan mengidentifikasikan dirinya melalui **Hardware Headers**:
* **Header 1**: `X-MAC-Address: <MAC_ADDRESS_ESP>` (Contoh: `24:6F:28:AB:CD:EF`)
* **Header 2**: `X-Device-Name: <NAMA_PERANGKAT_ESP>` (Contoh: `esp32-temp-01`)
* **Kegunaan**: VPS Provisioning memvalidasi MAC Address ini saat ESP meminta izin *join/register*, lalu menampilkannya di Dashboard Provisioning untuk di-*approve* oleh teknisi.

---

## 3. Katalog Kontrak REST API (VPS Provisioning)

Semua endpoint backend VPS Provisioning menggunakan prefix dasar: `/api/v1`

### [API-01] Katalog Modul: `GET /api/v1/modules`
* **Konsumen**: Dashboard Frontend (mengisi opsi dropdown modul).
* **HTTP Method**: `GET`
* **Response Status**: `200 OK`
* **Response Body (JSON)**:
```json
[
  {
    "name": "temperature",
    "version": "1.0.0",
    "description": "Modul monitoring suhu CPU dan sensor DHT22",
    "git_url": "https://github.com/NICEganteng/modulraspipmld.git"
  },
  {
    "name": "energy-meter",
    "version": "1.0.0",
    "description": "Modul pembacaan sensor arus dan daya PZEM-004T",
    "git_url": "https://github.com/NICEganteng/modulraspipmld.git"
  }
]
```

---

### [API-02] Generator Script Bootstrap: `POST /api/v1/bootstrap/raspberry`
* **Konsumen**: Dashboard Frontend (tombol Download Script Teknisi).
* **HTTP Method**: `POST`
* **Request Body (JSON)**:
```json
{
  "device_name": "raspi-plant-01",
  "connection_type": "Wi-Fi",
  "wifi_type": "Personal",
  "wifi_ssid": "Fabrik-IoT-Mesh",
  "wifi_password": "PasswordAman123!",
  "ip_mode": "DHCP"
}
```
* **Response Status**: `200 OK`
* **Response Type**: `text/plain` (Attachment download: `bootstrap-pi.sh`).

---

### [API-03] Pendaftaran Provisioning: `POST /api/v1/devices/provision`
* **Konsumen**: Dashboard Frontend (saat teknisi menekan tombol *"Submit Provisioning"*).
* **HTTP Method**: `POST`
* **Request Body (JSON)**:
```json
{
  "device_id": "raspi-plant-01",
  "device_name": "Gateway Line Produksi 1",
  "room_id": "room-plant-a",
  "selected_module": "temperature",
  "monitoring_vps_url": "http://103.120.40.15:8000/api/v1",
  "local_mqtt_port": 1883,
  "notes": "Pemasangan batch 1"
}
```
* **Response Status**: `201 Created`
* **Response Body (JSON)**:
```json
{
  "status": "SUCCESS",
  "message": "Device registered and ready for provisioning",
  "device_id": "raspi-plant-01",
  "assigned_username": "raspi-plant-01",
  "assigned_password": "sec_pwd_8899aabbcc",
  "registered_at": "2026-11-04T07:15:00Z"
}
```

---

### [API-04] Pengambilan Manifest: `GET /api/v1/provision/manifest`
* **Konsumen**: Raspberry Pi Agent saat pertama kali menyala dan terhubung ke internet.
* **HTTP Method**: `GET`
* **Headers**: `Authorization: Basic <base64(username:password)>`
* **Query Parameter**: `?device_id=raspi-plant-01`
* **Response Status**: `200 OK`
* **Response Body (JSON)**:
```json
{
  "device_id": "raspi-plant-01",
  "device_name": "Gateway Line Produksi 1",
  "approval_status": "APPROVED",
  "git_module": {
    "repo_url": "https://github.com/NICEganteng/modulraspipmld.git",
    "module_name": "temperature",
    "branch": "main"
  },
  "monitoring_target": {
    "url": "http://103.120.40.15:8000/api/v1",
    "pair_endpoint": "/devices/pair",
    "telemetry_endpoint": "/telemetry",
    "api_key": "sec_paten_token_abc123"
  },
  "edge_settings": {
    "local_mqtt_host": "127.0.0.1",
    "local_mqtt_port": 1883,
    "local_mqtt_topic": "esp/sensors/#",
    "log_level": "INFO",
    "forward_interval_seconds": 10
  }
}
```

---

### [API-05] Laporan Status Akhir: `POST /api/v1/provision/ack`
* **Konsumen**: Raspberry Pi Agent untuk mengonfirmasi ke Cloud bahwa setup lokal telah sukses atau gagal.
* **HTTP Method**: `POST`
* **Headers**: `Authorization: Basic <base64(username:password)>`
* **Request Body (JSON)**:
```json
{
  "device_id": "raspi-plant-01",
  "status": "COMPLETED",
  "module_installed": "temperature",
  "env_generated": true,
  "systemd_active": true,
  "local_ip": "192.168.1.120",
  "error_message": null,
  "timestamp": "2026-11-04T07:16:30Z"
}
```
* **Response Status**: `200 OK`
* **Response Body (JSON)**:
```json
{
  "status": "ACKNOWLEDGED",
  "device_status": "WAITING_APPROVAL"
}
```

---

### [API-06] Approval Raspberry Pi oleh Teknisi: `POST /api/v1/devices/{device_id}/approve`
* **Konsumen**: Dashboard Provisioning (Teknisi menekan tombol *"Approve Raspi"*).
* **HTTP Method**: `POST`
* **Response Status**: `200 OK`
* **Response Body (JSON)**:
```json
{
  "status": "APPROVED",
  "device_id": "raspi-plant-01",
  "approved_at": "2026-11-04T07:17:00Z"
}
```

---

### [API-07] Registrasi Node ESP: `POST /api/v1/iot/register`
* **Konsumen**: Node ESP (atau Raspi yang mem-forward permohonan registrasi ESP).
* **HTTP Method**: `POST`
* **Headers**:
  * `X-MAC-Address: 24:6F:28:AB:CD:EF`
  * `X-Device-Name: esp32-temp-01`
* **Request Body (JSON)**:
```json
{
  "parent_raspi_id": "raspi-plant-01",
  "sensor_types": ["dht22"],
  "ip_address": "192.168.1.155"
}
```
* **Response Status**: `200 OK`
* **Response Body (JSON)**:
```json
{
  "status": "PENDING_APPROVAL",
  "mac_address": "24:6F:28:AB:CD:EF",
  "device_name": "esp32-temp-01",
  "message": "Node ESP terdaftar, menunggu approval di Dashboard Provisioning"
}
```

---

### [API-08] Daftar ESP Pending: `GET /api/v1/iot/pending`
* **Konsumen**: Dashboard Provisioning (menampilkan tabel antrean approval ESP).
* **HTTP Method**: `GET`
* **Response Status**: `200 OK`
* **Response Body (JSON)**:
```json
[
  {
    "mac_address": "24:6F:28:AB:CD:EF",
    "device_name": "esp32-temp-01",
    "parent_raspi_id": "raspi-plant-01",
    "sensor_types": ["dht22"],
    "registered_at": "2026-11-04T07:18:00Z",
    "status": "PENDING"
  }
]
```

---

### [API-09] Approval Node ESP oleh Teknisi: `POST /api/v1/iot/{mac_address}/approve`
* **Konsumen**: Dashboard Provisioning (Teknisi menekan tombol *"Approve ESP"*).
* **HTTP Method**: `POST`
* **Response Status**: `200 OK`
* **Response Body (JSON)**:
```json
{
  "status": "APPROVED",
  "mac_address": "24:6F:28:AB:CD:EF",
  "approved_at": "2026-11-04T07:19:00Z"
}
```

---

## 4. Katalog Kontrak Sensor ESP ➔ Raspberry Pi (MQTT Lokal)

* **Broker**: Mosquitto berjalan lokal di Raspberry Pi (`127.0.0.1:1883`).
* **Format Topik**: `esp/{node_id}/sensors/{sensor_type}`
* **Contoh Topik**: `esp/esp32-temp-01/sensors/dht22`
* **Payload JSON**:
```json
{
  "node_id": "esp32-temp-01",
  "mac_address": "24:6F:28:AB:CD:EF",
  "sensor_type": "dht22",
  "metrics": {
    "temperature": 28.75,
    "humidity": 62.4
  },
  "uptime_seconds": 1420,
  "timestamp": 1730704500
}
```

---

## 5. Kamus Konfigurasi File `.env` di Raspberry Pi

File fisik disimpan di: `/opt/ztd/agent/.env` (Hak akses: `chmod 600`)

```env
# ==========================================
# KONFIGURASI PATEN PERANGKAT EDGE (ZTD)
# ==========================================

# 1. Identitas Perangkat
DEVICE_ID=raspi-plant-01
DEVICE_NAME=Gateway Line Produksi 1
HARDWARE_MODEL=Raspberry Pi 4 Model B

# 2. Kredensial Autentikasi ke VPS Provisioning
PROVISIONING_USERNAME=raspi-plant-01
PROVISIONING_PASSWORD=sec_pwd_8899aabbcc

# 3. Target Monitoring Cloud (Tim Lain)
MONITORING_VPS_URL=http://103.120.40.15:8000/api/v1
MONITORING_PAIR_ENDPOINT=/devices/pair
MONITORING_TELEMETRY_ENDPOINT=/telemetry
DEVICE_API_KEY=sec_paten_token_abc123

# 4. Broker MQTT Lokal (Penerima Data ESP)
LOCAL_MQTT_HOST=127.0.0.1
LOCAL_MQTT_PORT=1883
LOCAL_MQTT_TOPIC=esp/sensors/#

# 5. Modul Aplikasi (Hasil Git Clone)
ACTIVE_MODULE=temperature
MODULE_DIR=/opt/ztd/modules/temperature
MODULE_REPO=https://github.com/NICEganteng/modulraspipmld.git

# 6. Runtime & Daemon
LOG_LEVEL=INFO
FORWARD_INTERVAL_SECONDS=10
```

---

## 6. Katalog Kontrak Handoff (Raspberry Pi ➔ VPS Monitoring Tim Lain)

### [MON-01] Handshake / Registrasi Pairing: `POST {MONITORING_VPS_URL}/devices/pair`
* **Tujuan**: Memicu perangkat agar muncul di Dashboard Monitoring setelah di-approve di Provisioning.
* **HTTP Method**: `POST`
* **Headers**: `Content-Type: application/json`, `X-Device-Token: sec_paten_token_abc123`
* **Request Body (JSON)**:
```json
{
  "device_id": "raspi-plant-01",
  "hostname": "raspi-plant-01",
  "ip_address": "192.168.1.120",
  "active_module": "temperature",
  "status": "PROVISIONED_READY",
  "timestamp": "2026-11-04T07:20:00Z"
}
```

---

### [MON-02] Penerusan Data Telemetri: `POST {MONITORING_VPS_URL}/telemetry`
* **HTTP Method**: `POST`
* **Headers**: `Content-Type: application/json`, `X-Device-Token: sec_paten_token_abc123`
* **Request Body (JSON)**:
```json
{
  "device_id": "raspi-plant-01",
  "node_id": "esp32-temp-01",
  "mac_address": "24:6F:28:AB:CD:EF",
  "sensor_type": "dht22",
  "data": {
    "temperature": 28.75,
    "temp_unit": "C",
    "humidity": 62.4
  },
  "edge_stats": {
    "cpu_temp": 46.2,
    "uptime_seconds": 3600
  },
  "timestamp": 1730704510
}
```
