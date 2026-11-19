#!/usr/bin/env python3
"""
ZTD Module Deployer (Admin CLI Simulation)
Script ini mensimulasikan tombol 'Admin Klik Deploy' pada dashboard.
Admin dapat memilih Raspberry Pi target dan menentukan modul apa yang ingin dipasang.
"""

import sys
import json
import time
import urllib.request
import urllib.error
import argparse

API_BASE = "http://localhost:8000/api/v1"

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

def api_get(endpoint):
    url = f"{API_BASE}{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": "ZTD-Deployer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"{RED}[✗] Gagal menghubungi backend API ({url}): {e}{RESET}")
        return None

def api_post(endpoint, data):
    url = f"{API_BASE}{endpoint}"
    payload_bytes = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload_bytes,
        headers={"Content-Type": "application/json", "User-Agent": "ZTD-Deployer/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"{RED}[✗] HTTP Error {e.code}: {err_msg}{RESET}")
        return None
    except urllib.error.URLError as e:
        print(f"{RED}[✗] Gagal mengirim data ke API ({url}): {e}{RESET}")
        return None

def select_device():
    print(f"\n{BLUE}[1/3] Mengambil daftar perangkat dari backend...{RESET}")
    devices = api_get("/devices")
    if devices is None:
        sys.exit(1)

    if not devices:
        print(f"{YELLOW}[!] Belum ada Raspberry Pi yang terdaftar di database.{RESET}")
        manual_id = input("Masukkan Device ID secara manual (misal: raspi-a1b2c3): ").strip()
        if not manual_id:
            print(f"{RED}[✗] Device ID tidak boleh kosong.{RESET}")
            sys.exit(1)
        return manual_id, "unknown"

    print(f"\n{BOLD}Daftar Raspberry Pi yang Terdeteksi:{RESET}")
    for idx, d in enumerate(devices, 1):
        status_color = GREEN if d.get("status") == "ONLINE" else RED
        last_seen = d.get("last_seen") or "Never"
        print(f"  {BOLD}[{idx}]{RESET} ID: {BOLD}{d['id']}{RESET} | Status: {status_color}{d.get('status')}{RESET} | Room: {d.get('room_id') or '-'} | Last seen: {last_seen[:19]}")

    print(f"  {BOLD}[M]{RESET} Masukkan Device ID lain secara manual")

    while True:
        choice = input(f"\nPilih perangkat (1-{len(devices)} atau M): ").strip()
        if choice.upper() == "M":
            manual_id = input("Masukkan Device ID manual: ").strip()
            if manual_id:
                return manual_id, "unknown"
        elif choice.isdigit() and 1 <= int(choice) <= len(devices):
            selected = devices[int(choice) - 1]
            return selected["id"], selected.get("room_id") or "lab-01"
        print(f"{RED}Pilihan tidak valid.{RESET}")

def watch_deployment(device_id, module_names, timeout=35):
    print(f"\n{BLUE}[3/3] Memantau respon dari Raspberry Pi secara real-time...{RESET}")
    start_time = time.time()
    completed = set()

    while time.time() - start_time < timeout:
        logs = api_get(f"/devices/{device_id}/logs")
        if logs:
            for mod in module_names:
                if mod in completed:
                    continue
                mod_logs = [l for l in logs if l.get("stage") == mod]
                if mod_logs:
                    latest = mod_logs[0]
                    status = latest.get("status")
                    detail = latest.get("log_output", "")

                    if status == "success":
                        print(f"  ✅ {GREEN}{BOLD}SUKSES! Modul '{mod}' berhasil dipasang dan aktif!{RESET}")
                        completed.add(mod)
                    elif status == "failed":
                        print(f"  ❌ {RED}{BOLD}GAGAL! Modul '{mod}' error:{RESET} {detail}")
                        completed.add(mod)
                    elif status == "installing":
                        print(f"  ⏳ {YELLOW}Raspberry Pi sedang mengunduh & memasang modul '{mod}'...{RESET}")

            if len(completed) == len(module_names):
                return True

        time.sleep(2)

    return False

def main():
    parser = argparse.ArgumentParser(description="ZTD Module Deployer (Admin Simulation)")
    parser.add_argument("--device", help="Device ID target (misal: raspi-3f8a1b)")
    parser.add_argument("--module", default="temperature", help="Nama modul (default: temperature)")
    parser.add_argument("--version", default="1.0.0", help="Versi modul (default: 1.0.0)")
    parser.add_argument("--room", help="Nama ruangan / room_id (default: lab-01)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"{BOLD}       ZERO TOUCH DEPLOYMENT — ADMIN DEPLOY CONTROLLER{RESET}")
    print("=" * 60)

    # 1. Tentukan Device Target
    if args.device:
        device_id = args.device
        room_id = args.room or "lab-01"
    else:
        device_id, default_room = select_device()
        room_id = args.room or default_room

    # 2. Tentukan Modul (Bisa Lebih dari Satu)
    if not args.device:
        print(f"\n{BLUE}[2/3] Konfigurasi Modul:{RESET}")
        print("Masukkan modul yang ingin diaktifkan (pisahkan koma untuk lebih dari satu).")
        mod_input = input(f"Daftar modul [{BOLD}temperature, memory{RESET}]: ").strip()
        raw_mods = mod_input if mod_input else "temperature, memory"
        module_names = [m.strip() for m in raw_mods.split(",") if m.strip()]

        modules_list = []
        for mod in module_names:
            ver_input = input(f"Versi untuk '{mod}' [{BOLD}1.0.0{RESET}]: ").strip()
            ver = ver_input if ver_input else "1.0.0"
            modules_list.append({"name": mod, "version": ver, "enabled": True})

        room_input = input(f"Ruangan / Room ID [{BOLD}{room_id}{RESET}]: ").strip()
        if room_input:
            room_id = room_input
    else:
        raw_mods = [m.strip() for m in args.module.split(",") if m.strip()]
        module_names = raw_mods
        modules_list = [{"name": m, "version": args.version, "enabled": True} for m in raw_mods]

    # Susun Payload Desired State Multi-Module
    payload = {
        "room_id": room_id,
        "modules": modules_list
    }
    print(f"\n{BOLD}Mengirim Desired State ke Server:{RESET}")
    print(f"  Target Device : {BOLD}{device_id}{RESET}")
    print(f"  Ruangan       : {room_id}")
    print(f"  Daftar Modul  : {', '.join([m['name'] + ' (v' + m['version'] + ')' for m in modules_list])}")
    confirm = input("\nKirim perintah deploy sekarang? [Y/n]: ").strip().lower()
    if confirm in ("n", "no"):
        print(f"{YELLOW}Deployment dibatalkan.{RESET}")
        return
    # Kirim ke API backend (yang akan mem-publish MQTT retained message)
    res = api_post(f"/devices/{device_id}/config", payload)
    if res is None:
        print(f"{RED}[✗] Gagal melakukan deployment.{RESET}")
        return
    print(f"\n{GREEN}[✓] Perintah Deploy Berhasil Didaftarkan di Broker MQTT (Retained)!{RESET}")
    print(f"    Pesan: {res.get('message')}")
    # 3. Pantau respon live dari Raspberry Pi
    watch_deployment(device_id, module_names)

    print("\n" + "=" * 60)
    print(f"{BOLD}Untuk memeriksa data telemetri suhu yang masuk, jalankan:{RESET}")
    print(f"  curl -s http://localhost:8000/api/v1/devices/{device_id}/telemetry")
    print("=" * 60)

if __name__ == "__main__":
    main()
