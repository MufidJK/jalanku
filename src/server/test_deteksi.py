"""Uji cepat satu gambar tanpa HTTP.

    python src/server/test_deteksi.py <path-gambar.jpg>

Path model diambil dari config.yaml (relatif terhadap root repo).
Jangan dipakai untuk frame lokasi test.
"""
import argparse
import sys
from pathlib import Path

import cv2

from deteksi import MesinDeteksi, muat_config
from logika import MesinLogika


LOKASI_TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gambar", help="Path gambar (JPEG/PNG)")
    args = parser.parse_args()

    gambar_path = Path(args.gambar).resolve()

    if any(nama in str(gambar_path).lower() for nama in LOKASI_TEST):
        sys.exit("Ditolak: gambar dari lokasi test.")

    gambar = cv2.imread(str(gambar_path))

    if gambar is None:
        raise FileNotFoundError(f"Gambar tidak ditemukan: {gambar_path}")

    config = muat_config()

    print("=" * 50)
    print("JALANKU - TEST INFERENCE")
    print("=" * 50)
    print("Gambar:", gambar_path.name)
    print("Resolusi:", gambar.shape[1], "x", gambar.shape[0])

    mesin = MesinDeteksi(config)
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
    else:
        print("Tidak ada mask segmentasi yang dihasilkan.")

    print("\n--- PERFORMA ---")
    print("Waktu inference:", hasil["waktu_ms"], "ms")

    # Dua kali supaya stabilisasi 2 dari 3 frame terpenuhi
    mesin_logika = MesinLogika(config)
    mesin_logika.proses(hasil)
    hasil_navigasi = mesin_logika.proses(hasil)

    print("\n--- HASIL ANALISIS JALANKU ---")
    print(hasil_navigasi)


if __name__ == "__main__":
    main()
