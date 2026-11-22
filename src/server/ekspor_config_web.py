"""Ekspor config.yaml -> src/web/logika-config.json (hanya kunci yang dibaca MesinLogika).

Dipakai oleh logika JavaScript (src/web/logika.js) supaya HP memakai aturan yang sama
dengan server. Tidak ada path model di keluaran.

  venv\\Scripts\\python src\\server\\ekspor_config_web.py            # tulis (menolak menimpa)
  venv\\Scripts\\python src\\server\\ekspor_config_web.py --force    # timpa
  venv\\Scripts\\python src\\server\\ekspor_config_web.py --cetak    # hanya cetak, tanpa menulis
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SUMBER = ROOT / "src" / "server" / "config.yaml"
TUJUAN = ROOT / "src" / "web" / "logika-config.json"

# Setiap config.get(...) / config[...] di src/server/logika.py. Kunci yang tidak ada di
# YAML tidak ditulis, jadi nilai bawaan kode (sama di Python dan JS) yang berlaku.
KUNCI_LOGIKA = [
    "zona_tengah",
    "jarak_y2",
    "bobot_kelas",
    "faktor_posisi",
    "faktor_jarak",
    "ambang_tingkat",
    "stabil",
    "seg_kosong_minimal",
    "seg_tangga_stabil_minimal",
    "jauh_butuh_seg",
    "tahan_dekat_ms",
    "samping_maks_tingkat",
    "samping_masuk_tengah_min",
    "jalur_ambang_terhalang",
    "seg_tangga_min",
    "seg_kendaraan_min",
    "maks_sesi",
]


def config_web(config):
    """Subset config untuk JS, sudah lewat JSON (kunci int YAML jadi string)."""
    subset = {k: config[k] for k in KUNCI_LOGIKA if k in config}
    return json.loads(json.dumps(subset))


def muat_yaml():
    with open(SUMBER, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="timpa logika-config.json kalau sudah ada")
    ap.add_argument("--cetak", action="store_true", help="cetak JSON ke layar, jangan menulis file")
    args = ap.parse_args()

    teks = json.dumps(config_web(muat_yaml()), indent=2, ensure_ascii=False) + "\n"

    if args.cetak:
        sys.stdout.write(teks)
        return 0

    if TUJUAN.exists() and not args.force:
        print(f"Menolak menimpa {TUJUAN} (pakai --force).", file=sys.stderr)
        return 1

    with open(TUJUAN, "w", encoding="utf-8", newline="\n") as f:
        f.write(teks)
    print(f"Ditulis: {TUJUAN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
