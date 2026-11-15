import argparse
import csv
import time
from pathlib import Path

import cv2
import yaml

from deteksi import MesinDeteksi
from logika import MesinLogika


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "src/server/config.yaml"
OUTPUT_DIR = ROOT / "runs/app"


def muat_config():
    with open(CONFIG_PATH, encoding="utf-8") as file:
        config = yaml.safe_load(file)

    config["model_kotak"] = str(ROOT / config["model_kotak"])
    config["model_seg"] = str(ROOT / config["model_seg"])

    return config


def anotasi_gambar(gambar, objek, peringatan, jalur):
    hasil = gambar.copy()
    tinggi, lebar = hasil.shape[:2]

    for item in objek:
        x1, y1, x2, y2 = item["kotak"]

        x1 = int(x1 * lebar)
        y1 = int(y1 * tinggi)
        x2 = int(x2 * lebar)
        y2 = int(y2 * tinggi)

        label = (
            f'{item["kelas"]} '
            f'{item["posisi"]} '
            f'{item["jarak"]}'
        )

        cv2.rectangle(
            hasil,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2,
        )

        cv2.putText(
            hasil,
            label,
            (x1, max(20, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            2,
        )

    pesan = (
        peringatan["pesan"]
        if peringatan
        else "Tidak ada peringatan"
    )

    cv2.putText(
        hasil,
        pesan,
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 0, 255) if peringatan else (0, 255, 0),
        2,
    )

    cv2.putText(
        hasil,
        f'Jalur: {jalur["status"]} '
        f'({jalur["persen_jalan"]:.2%})',
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 0),
        2,
    )

    return hasil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lokasi",
        default=None,
        help="Filter nama lokasi, contoh: lorong",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batasi jumlah frame per lokasi",
    )
    args = parser.parse_args()

    config = muat_config()

    print("[JalanKu] Memuat model...")
    mesin_deteksi = MesinDeteksi(config)
    mesin_logika = MesinLogika(config)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    folder_frame = OUTPUT_DIR / "frames"
    folder_frame.mkdir(parents=True, exist_ok=True)

    manifests = sorted(
        (ROOT / "data/frame-blur").rglob("_manifest.csv")
    )

    if args.lokasi:
        manifests = [
            path for path in manifests
            if args.lokasi.lower() in str(path).lower()
        ]

    if not manifests:
        raise FileNotFoundError("Manifest tidak ditemukan.")

    log_path = OUTPUT_DIR / "log.csv"

    kolom = [
        "lokasi",
        "filename",
        "timestamp_s",
        "persons_blurred",
        "jumlah_objek",
        "kelas_objek",
        "peringatan",
        "kelas_peringatan",
        "posisi_peringatan",
        "jarak_peringatan",
        "tingkat_peringatan",
        "status_jalur",
        "persen_jalan",
        "inference_ms",
        "total_ms",
        "error",
    ]

    total_frame = 0
    berhasil = 0
    gagal = 0

    with open(
        log_path,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(file, fieldnames=kolom)
        writer.writeheader()

        for manifest_path in manifests:
            lokasi = manifest_path.parent.name

            with open(
                manifest_path,
                encoding="utf-8-sig",
            ) as manifest_file:
                frames = list(csv.DictReader(manifest_file))

            frames.sort(
                key=lambda item: float(item["timestamp_s"])
            )

            if args.limit:
                frames = frames[:args.limit]

            sesi_id = lokasi

            print(f"\n===== {lokasi} =====")
            print("Jumlah frame:", len(frames))

            output_lokasi = folder_frame / lokasi
            output_lokasi.mkdir(parents=True, exist_ok=True)

            for nomor, frame in enumerate(frames, start=1):
                total_frame += 1
                gambar_path = manifest_path.parent / frame["filename"]

                awal = time.perf_counter()

                try:
                    gambar = cv2.imread(str(gambar_path))

                    if gambar is None:
                        raise ValueError("Gambar gagal dibaca.")

                    hasil_deteksi = mesin_deteksi.prediksi(gambar)

                    hasil = mesin_logika.proses(
                        hasil_deteksi,
                        sesi_id=sesi_id,
                    )

                    total_ms = round(
                        (time.perf_counter() - awal) * 1000,
                        2,
                    )

                    objek = hasil["objek"]
                    peringatan = hasil["peringatan"]
                    jalur = hasil["jalur"]

                    gambar_anotasi = anotasi_gambar(
                        gambar,
                        objek,
                        peringatan,
                        jalur,
                    )

                    cv2.imwrite(
                        str(output_lokasi / frame["filename"]),
                        gambar_anotasi,
                    )

                    writer.writerow({
                        "lokasi": lokasi,
                        "filename": frame["filename"],
                        "timestamp_s": frame["timestamp_s"],
                        "persons_blurred": frame["persons_blurred"],
                        "jumlah_objek": len(objek),
                        "kelas_objek": ";".join(
                            item["kelas"] for item in objek
                        ),
                        "peringatan": (
                            peringatan["pesan"] if peringatan else ""
                        ),
                        "kelas_peringatan": (
                            peringatan["kelas"] if peringatan else ""
                        ),
                        "posisi_peringatan": (
                            peringatan["posisi"] if peringatan else ""
                        ),
                        "jarak_peringatan": (
                            peringatan["jarak"] if peringatan else ""
                        ),
                        "tingkat_peringatan": (
                            peringatan["tingkat"] if peringatan else ""
                        ),
                        "status_jalur": jalur["status"],
                        "persen_jalan": jalur["persen_jalan"],
                        "inference_ms": hasil_deteksi["waktu_ms"],
                        "total_ms": total_ms,
                        "error": "",
                    })

                    berhasil += 1

                    print(
                        f"[{nomor}/{len(frames)}] "
                        f"{frame['filename']} | "
                        f"Objek: {len(objek)} | "
                        f"Jalur: {jalur['status']} | "
                        f"{total_ms} ms"
                    )

                except Exception as error:
                    gagal += 1

                    writer.writerow({
                        "lokasi": lokasi,
                        "filename": frame["filename"],
                        "timestamp_s": frame["timestamp_s"],
                        "persons_blurred": frame["persons_blurred"],
                        "error": str(error),
                    })

                    print(
                        f"[ERROR] {frame['filename']}: {error}"
                    )

                file.flush()

    print("\n" + "=" * 50)
    print("JALANKU - HASIL PENGUJIAN OFFLINE")
    print("=" * 50)
    print("Total frame:", total_frame)
    print("Berhasil:", berhasil)
    print("Gagal:", gagal)
    print("Log:", log_path)
    print("Anotasi:", folder_frame)


if __name__ == "__main__":
    main()
