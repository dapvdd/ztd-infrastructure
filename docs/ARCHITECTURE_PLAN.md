# 📋 Rencana Arsitektur & Implementasi: Sistem Provisioning ZTD

> **Konteks Proyek**: Sistem ini berfokus pada **Domain Provisioning (Inisialisasi & Setup Perangkat Edge)**. Proses operasional lanjutan (monitoring runtime, visualisasi data IoT) diserahkan ke **Tim Monitoring**.
> 
> **Pembaruan Fitur Keamanan**: Sistem menggunakan **Autentikasi Berbasis Header** (HTTP Basic Auth untuk Raspberry Pi, dan `X-MAC-Address` / `X-Device-Name` untuk Node ESP/IoT), serta menerapkan **Fitur Approval Ganda (Dual Approval)** langsung pada **Dashboard Provisioning** baik untuk Raspberry Pi maupun Node ESP sebelum perangkat dinyatakan aktif sepenuhnya.

---

## 1. Ringkasan & Batasan Lingkup Kerja (*Scope Boundary*)

Sistem dibagi menjadi dua domain terpisah dengan kepemilikan tim yang berbeda:

* **Tim Provisioning (Lingkup Kita)**:
  * **VPS Provisioning (Hosting Backend & Dashboard)**:
    * **Dashboard Provisioning (Web UI)**: Antarmuka web yang disajikan oleh VPS Provisioning untuk teknisi melakukan registrasi perangkat, penentuan konfigurasi paten, serta **Approval untuk Raspberry Pi dan Node ESP**.
    * **Backend Provisioning (REST API)**: Layanan API di VPS Provisioning untuk mengelola katalog modul, manifest *desired state*, validasi header kredensial, dan antrean approval.
  * **Edge Gateway (Backend Raspi)**: Layanan latar belakang (*daemon*) pada Raspberry Pi yang mengurus inisialisasi broker MQTT lokal, penarikan modul dari GitHub, pembentukan file `.env`, autentikasi dengan kredensial User/Password ke VPS Provisioning, serta kontak pertama ke VPS Monitoring.
  * **Titik Akhir (*Handoff*)**: Perangkat Raspi dan ESP telah di-approve di Dashboard Provisioning, file `.env` terisi alamat VPS Monitoring, dan Raspi berhasil mengirimkan sinyal siap ke VPS Monitoring.
* **Tim Monitoring (Lingkup Tim Lain)**:
  * **VPS Monitoring**: Backend penerima telemetri runtime via HTTP Request.
  * **Dashboard Monitoring**: Antarmuka visualisasi telemetri dan metrik perangkat.

---

## 2. Diagram Arsitektur Sistem Terpadu

```mermaid
flowchart TD
    subgraph SetupTeknisi["1. Setup Lapangan (Teknisi)"]
        Laptop["Laptop Teknisi (Web Browser)"]
    end

    subgraph VPSProvisioningHost["2. VPS Provisioning (Domain Tim Kita)"]
        direction TB
        NginxWeb["Web Server / Nginx Gateway"]
        DashProv["Dashboard Provisioning<br/><b>Fitur:</b> Form, Raspi Approval & ESP Approval"]
        APIProv["Backend Provisioning (REST API)<br/><b>Auth:</b> Header Parser & Basic Auth Validator"]
        DBProv[("Database Registry & Approvals")]
        
        NginxWeb -->|"Serve Static UI"| DashProv
        NginxWeb -->|"Reverse Proxy /api"| APIProv
        APIProv <--> DBProv
    end

    subgraph GitCloud["3. Cloud Code Repository"]
        GitRepo[("GitHub / Git Repo Modul")]
    end

    subgraph RaspiEdge["4. Edge Gateway (Raspberry Pi)"]
        RaspiBackend["Backend Raspi (Daemon Service)<br/><i>Auth: Basic Auth User/Pass</i>"]
        RaspiEnv[".env (Konfigurasi Paten)"]
        LocalMQTT["Broker MQTT Lokal (Mosquitto)"]
        
        RaspiBackend -->|"Membaca & Menulis"| RaspiEnv
        LocalMQTT -->|"Internal Pub/Sub Data Sensor"| RaspiBackend
    end

    subgraph SensorNodes["Node Sensor Lapangan (IoT)"]
        ESP1["ESP Node #1<br/><i>Header: X-MAC-Address, X-Device-Name</i>"]
        ESP2["ESP Node #2<br/><i>Header: X-MAC-Address, X-Device-Name</i>"]
        ESP1 -->|"MQTT Pub / HTTP Register"| LocalMQTT
        ESP2 -->|"MQTT Pub / HTTP Register"| LocalMQTT
    end

    subgraph MonitoringDomain["5. Domain Monitoring (Tim Lain)"]
        VPSMon["VPS Monitoring (HTTP API)"]
        DashMon["Dashboard Monitoring (UI Telemetry)"]
        VPSMon <--> DashMon
    end

    %% Hubungan Jaringan
    Laptop -->|"Akses Web UI & Approval (HTTP/S)"| NginxWeb
    Laptop -.->|"Koneksi Lokal Setup Jaringan (LAN/Hotspot)"| RaspiBackend
    RaspiBackend <-->|"HTTP Request (Basic Auth)"| APIProv
    GitRepo -->|"Git Clone / Pull Modul Aplikasi"| RaspiBackend
    RaspiBackend -->|"HTTP POST: First Contact (Pairing) & Data Forwarding"| VPSMon
```

---

## 3. Diagram Alur Kerja (*Sequence Diagram dengan Dual Approval*)

```mermaid
sequenceDiagram
    autonumber
    actor Teknisi as Teknisi Lapangan
    participant UI as Dashboard Provisioning
    participant API as VPS Provisioning API
    participant Raspi as Backend Raspi
    participant Git as GitHub Repo
    participant ESP as Node Sensor ESP
    participant VPSMon as VPS Monitoring

    Note over Teknisi, UI: FASE 1: Registrasi Awal & Bootstrap
    Teknisi->>UI: Input Form Perangkat (ID, Modul, IP Mon)
    UI->>API: POST /api/v1/devices/provision
    API-->>UI: Generate Username & Password Raspi
    UI-->>Teknisi: Download bootstrap-pi.sh

    Note over Raspi, API: FASE 2: Provisioning Raspi & Approval
    Raspi->>API: GET /api/v1/provision/manifest (Header: Basic Auth)
    API-->>Raspi: Manifest (Modul, Config Paten)
    Raspi->>Git: git clone / pull modul aplikasi
    Raspi->>Raspi: Generate .env & Aktifkan Systemd Daemon
    Raspi->>API: POST /api/v1/provision/ack (Header: Basic Auth)
    API->>UI: Tampilkan di Dashboard: "Raspi Menunggu Approval"
    Teknisi->>UI: Klik "Approve Raspi"
    UI->>API: POST /api/v1/devices/{device_id}/approve

    Note over ESP, UI: FASE 3: Onboarding ESP & Approval IoT
    ESP->>API: POST /api/v1/iot/register (Header: X-MAC-Address & X-Device-Name)
    API->>UI: Tampilkan di Dashboard: "ESP Menunggu Approval"
    Teknisi->>UI: Verifikasi MAC & Klik "Approve ESP"
    UI->>API: POST /api/v1/iot/{mac_address}/approve

    Note over Raspi, VPSMon: FASE 4: Handoff ke Tim Monitoring & Operasional
    Raspi->>VPSMon: POST /api/v1/devices/pair (Handshake awal)
    loop Operasional Runtime
        ESP->>Raspi: Kirim data sensor via MQTT lokal
        Raspi->>VPSMon: Forward data sensor via HTTP POST /telemetry
    end
```

---

## 4. Analisis Peran Komponen di Raspberry Pi

### Mengapa Raspberry Pi Membutuhkan `backend` dan `.env`?

1. **Provisioning Engine & Automation**:
   * Raspi memerlukan *backend agent* untuk menerima konfigurasi jaringan awal dari teknisi, berkomunikasi dengan VPS Provisioning menggunakan kredensial User/Password, menjalankan perintah `git clone`, serta mengonfigurasi *systemd daemon*.
2. **Konfigurasi Paten Berbasis `.env`**:
   * File `.env` menjadi *Single Source of Truth* di tingkat lokal perangkat setelah fase provisioning selesai. Di dalamnya tersimpan parameter permanen seperti `DEVICE_ID`, `MONITORING_VPS_URL`, kredensial `PROVISIONING_PASSWORD`, dan kredensial autentikasi lainnya.
3. **Data Forwarder (MQTT Lokal ➔ HTTP Cloud)**:
   * Broker MQTT lokal (Mosquitto) dipasang di Raspi untuk menerima data berkecepatan tinggi dan hemat daya dari node ESP yang telah terverifikasi.
   * Backend Raspi bertindak sebagai jembatan (*bridge*): men-*subscribe* topik MQTT lokal, memvalidasi payload, lalu meneruskannya (*forwarding*) ke VPS Monitoring via **HTTP Request**.

---

## 5. Rencana File Unit Systemd Daemon (`iot-agent.service`)

```ini
[Unit]
Description=ZTD Edge Gateway Agent & Telemetry Forwarder
After=network-online.target mosquitto.service
Wants=network-online.target mosquitto.service

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/ztd/agent
EnvironmentFile=-/opt/ztd/agent/.env
ExecStart=/opt/ztd/agent/venv/bin/python /opt/ztd/agent/agent.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
