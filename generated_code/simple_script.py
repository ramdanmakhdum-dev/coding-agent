#!/usr/bin/env python3
"""
simple_script.py

Sebuah contoh skrip command‑line yang:
1. Menyapa pengguna dengan nama yang diberikan lewat argumen `--name`.
2. Menghitung penjumlahan dua bilangan bulat yang diberikan lewat argumen
   `--a` dan `--b`.

Contoh penggunaan:
    $ python simple_script.py --name "Budi" --a 5 --b 7
    Halo, Budi!
    Hasil penjumlahan 5 + 7 = 12
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


def parse_arguments() -> argparse.Namespace:
    """Parse dan kembalikan argumen command‑line."""
    parser = argparse.ArgumentParser(
        description="Sapa pengguna dan hitung penjumlahan dua bilangan."
    )
    parser.add_argument(
        "--name",
        type=str,
        default="Pengguna",
        help="Nama yang akan disapa (default: Pengguna).",
    )
    parser.add_argument(
        "--a",
        type=int,
        default=0,
        help="Bilangan pertama (default: 0).",
    )
    parser.add_argument(
        "--b",
        type=int,
        default=0,
        help="Bilangan kedua (default: 0).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point utama."""
    try:
        args = parse_arguments()
    except Exception as exc:  # pragma: no cover
        # Jika argparse gagal (misalnya nilai non‑integer), tampilkan pesan bersahabat.
        sys.stderr.write(f"Error parsing arguments: {exc}\n")
        sys.exit(1)

    # 1️⃣ Menyapa pengguna
    print(f"Halo, {args.name}!")

    # 2️⃣ Menghitung penjumlahan
    total: int = args.a + args.b
    print(f"Hasil penjumlahan {args.a} + {args.b} = {total}")


if __name__ == "__main__":
    main()
