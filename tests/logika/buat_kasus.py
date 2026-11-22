"""Buat data uji paritas logika Python vs JavaScript.

Memutar ulang 11.299 frame rekaman PERSIS seperti data/aturan-v1-1/replay.py (satu MesinLogika
per folder, sesi dari index.csv, waktu_s = waktu rekaman) dengan config.yaml SEKARANG, dua kali:
  - keluar     : config.yaml apa adanya (aturan v1.1 hidup)
  - keluar_off : tahan_dekat_ms=0, samping_maks_tingkat=3 (aturan v1.1 mati = v1)
Hasil: data/logika-js/kasus.jsonl.gz  (baris 1 = meta, sisanya satu frame per baris)
       data/logika-js/sintetis.json   (42 kasus sintetis: masukan + keluaran Python)
Menolak menimpa file yang sudah ada.

Jalankan dari root repo:  venv\\Scripts\\python tests\\logika\\buat_kasus.py
"""
import csv
import gzip
import hashlib
import json
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np  # noqa: F401  (dibutuhkan pickle)
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kasus_sintetis as ks  # noqa: E402  (juga menaruh src/server di sys.path)
from ekspor_config_web import config_web  # noqa: E402
from logika import MesinLogika  # noqa: E402

REK = ROOT / "data" / "analisis-rekaman"
KELUAR = ROOT / "data" / "logika-js"
F_KASUS = KELUAR / "kasus.jsonl.gz"
F_SINTETIS = KELUAR / "sintetis.json"
V1_OFF = {"tahan_dekat_ms": 0, "samping_maks_tingkat": 3}  # sama dengan replay.py


def main():
    for f in (F_KASUS, F_SINTETIS):
        if f.exists():
            sys.exit(f"Menolak menimpa {f} (hapus dulu kalau memang mau dibuat ulang).")
    KELUAR.mkdir(parents=True, exist_ok=True)

    # --- 42 kasus sintetis (asersi aslinya dijalankan di sini)
    sint = ks.jalankan_semua()
    gagal = [k for k in sint if not k["lulus_python"]]
    if gagal:
        sys.exit(f"Kasus sintetis gagal di sisi Python: {[k['nomor'] for k in gagal]}")
    with open(F_SINTETIS, "w", encoding="utf-8") as f:
        json.dump(sint, f, ensure_ascii=False)
    print(f"sintetis: {len(sint)} kasus, {sum(len(k['runs']) for k in sint)} mesin -> {F_SINTETIS}")

    # --- 11.299 frame rekaman
    with open(ROOT / "src" / "server" / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config_off = {**config, **V1_OFF}
    sha_config = hashlib.sha256((ROOT / "src" / "server" / "config.yaml").read_bytes()).hexdigest()

    with open(REK / "cache_rekam.pkl", "rb") as f:
        cache = pickle.load(f)
    with open(REK / "index.csv", encoding="utf-8") as f:
        index = list(csv.DictReader(f))
    assert len(cache) == len(index) == 11299, (len(cache), len(index))
    with open(REK / "frame.csv", encoding="utf-8") as f:
        frame_csv = list(csv.DictReader(f))

    tmp = F_KASUS.with_name(F_KASUS.name + ".partial")
    folder_ini, mesin_on, mesin_off = None, None, None
    sama_v1 = 0
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as out:
        meta = {"tipe": "meta", "jumlah": len(cache), "sha256_config_yaml": sha_config,
                "config_on": config_web(config), "config_off": config_web(config_off)}
        out.write(json.dumps(meta) + "\n")
        for i, (c, r) in enumerate(zip(cache, index)):
            if r["folder"] != folder_ini:
                folder_ini, mesin_on, mesin_off = r["folder"], MesinLogika(config), MesinLogika(config_off)
            ts = datetime.fromisoformat(r["waktu"]).timestamp()
            mask_kode = None
            mask = None
            if c["mask"] is not None:
                bits, shape = c["mask"]
                mask_kode = ks.enkode_bits(bits, shape)
                mask = np.unpackbits(bits, axis=1, count=shape[1] * shape[2]).astype(bool).reshape(shape)  # = replay.pulihkan_mask
            hd = {"objek": c["objek"], "mask_seg": mask, "kelas_seg": c["kelas_seg"],
                  "nama_kelas_seg": c["nama_kelas_seg"], "waktu_ms": c["waktu_ms"]}
            k_on = mesin_on.proses(hd, r["sesi"], waktu_s=ts)
            k_off = mesin_off.proses(hd, r["sesi"], waktu_s=ts)
            p = k_off["peringatan"]
            sama_v1 += ((p["pesan"] if p else "") == frame_csv[i]["replay_peringatan"]
                        and str(p["tingkat"] if p else "") == frame_csv[i]["replay_tingkat"])
            out.write(json.dumps({
                "tipe": "frame", "i": i, "folder": r["folder"], "sesi": r["sesi"], "waktu_s": ts,
                "masukan": ks.enkode_masukan(hd, mask_kode),
                "keluar": ks.salin_json(k_on), "keluar_off": ks.salin_json(k_off),
            }) + "\n")
            if (i + 1) % 2000 == 0:
                print(f"  {i + 1}/{len(cache)}", flush=True)
    tmp.replace(F_KASUS)
    print(f"sanity: replay v1 (v1.1 mati) == frame.csv: {sama_v1}/{len(cache)}")
    print(f"frame: {len(cache)} -> {F_KASUS} ({F_KASUS.stat().st_size / 1e6:.1f} MB)")
    return 0 if sama_v1 == len(cache) else 1


if __name__ == "__main__":
    sys.exit(main())
