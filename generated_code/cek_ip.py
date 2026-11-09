#!/usr/bin/env python3
"""
cek_ip.py

Script sederhana untuk menampilkan:
1. Alamat IP publik (menggunakan layanan https://api.ipify.org)
2. Alamat IP lokal (interface jaringan yang aktif)

Cara pakai:
    $ python3 cek_ip.py
"""

import socket
import sys

try:
    import requests
except ImportError:
    sys.exit("Modul 'requests' belum terinstall. Pasang dulu dengan: pip install requests")


def get_public_ip() -> str:
    """Mengambil IP publik dengan memanggil layanan api.ipify.org."""
    try:
        response = requests.get("https://api.ipify.org?format=text", timeout=5)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as e:
        return f"Gagal mengambil IP publik: {e}"


def get_local_ip() -> str:
    """Mencoba mendapatkan IP lokal dengan membuka socket ke internet."""
    try:
        # Membuat socket UDP ke alamat publik (tidak mengirim paket)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError as e:
        return f"Gagal mendapatkan IP lokal: {e}"


def main():
    print("=== Informasi IP ===")
    print(f"IP Publik : {get_public_ip()}")
    print(f"IP Lokal  : {get_local_ip()}")


if __name__ == "__main__":
    main()
