# coding_ringan.py
# Script sederhana untuk demonstrasi coding ringan

def greet(name: str = "Dunia") -> None:
    """Cetak salam ke pengguna."""
    print(f"Halo, {name}!")

def tambah(a: int, b: int) -> int:
    """Kembalikan hasil penjumlahan dua bilangan."""
    return a + b

if __name__ == "__main__":
    # Contoh penggunaan fungsi
    greet()                     # Output: Halo, Dunia!
    greet("Teman")              # Output: Halo, Teman!
    
    x, y = 5, 7
    hasil = tambah(x, y)
    print(f"{x} + {y} = {hasil}")  # Output: 5 + 7 = 12
