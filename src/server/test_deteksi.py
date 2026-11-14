
from pathlib import Path

import cv2
import yaml

from deteksi import MesinDeteksi
from logika import MesinLogika


# Lokasi root repository
ROOT = Path(__file__).resolve().parents[2]

# Baca konfigurasi
with open(ROOT / "src/server/config.yaml", encoding="utf-8") as file:
    config = yaml.safe_load(file)

# Lokasi satu frame training
gambar_path = (
    ROOT
    / "data/frame-blur/lorong-lt9-ubm-tower_2026-10-30_03_dada-20261111T155025Z-1-001"
    / "lorong-lt9-ubm-tower_2026-10-30_03_dada"
    / "lorong-lt9-ubm-tower_2026-10-30_03_dada_t0000000.jpg"
)

# Baca gambar
gambar = cv2.imread(str(gambar_path))

if gambar is None:
    raise FileNotFoundError(f"Gambar tidak ditemukan: {gambar_path}")

print("=" * 50)
print("JALANKU - TEST INFERENCE")
print("=" * 50)
print("Gambar:", gambar_path.name)
print("Resolusi:", gambar.shape[1], "x", gambar.shape[0])

# Inisialisasi model
mesin = MesinDeteksi(config)

# Jalankan inference
hasil = mesin.prediksi(gambar)

print("\n--- HASIL DETEKSI KOTAK ---")

for objek in hasil["objek"]:
    print(objek)

print("\n--- HASIL SEGMENTASI ---")

if hasil["mask_seg"] is not None:
    print("Jumlah mask:", len(hasil["mask_seg"]))
    print("Bentuk mask:", hasil["mask_seg"].shape)
    print("Kelas segmentasi:", hasil["nama_kelas_seg"])
    print("ID kelas setiap mask:", hasil["kelas_seg"])
    print("Jumlah ID kelas:", len(hasil["kelas_seg"]))
else:
    print("Tidak ada mask segmentasi yang dihasilkan.")

print("\n--- PERFORMA ---")
print("Waktu inference:", hasil["waktu_ms"], "ms")

print("\nTEST SELESAI")

# Uji integrasi mesin logika
mesin_logika = MesinLogika(config)
hasil_navigasi = mesin_logika.proses(hasil)

print('\n--- HASIL ANALISIS JALANKU ---')
print(hasil_navigasi)
