"""validasi_test_set.py - validasi struktur JSON test set (data/test-review) setelah review manual.

Adaptasi dari tools/validasi_pilot_v2.py (file itu tidak diubah). Hanya membaca, tidak mengubah apa pun.
Dijalankan dari root repo:  python tools/validasi_test_set.py [--folder data/test-review] [--daftar data/test-review/daftar_test.csv]

Memeriksa:
  - tiap baris daftar_test.csv punya gambar + JSON, tidak ada JSON/gambar lebih;
  - kunci JSON sama dengan format X-AnyLabeling, imagePath cocok, ukuran 1080x1920, imageData None;
  - tipe shape polygon/rectangle, >= 3 titik, label ada di classes.txt, titik di dalam gambar (toleransi 1 px);
  - gambar hard link ke data/frame-blur (sumber read-only);
  - TIDAK ADA frame test (selasar-lt11*, pot-lt11*, taman-ubm*) di folder training/validasi/cache lain;
  - kotak beda kelas yang hampir sama (IoU > 0.9) di antara kelas kotak (R6: satu objek satu kelas).
Aturan R4/R6 sama dilakukan oleh tools/cek_test_set.py.
"""
import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np

import cek_test_set as cts  # tools/ ada di sys.path saat skrip dijalankan

TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
KELAS = cts.KELAS


def cari_bocor(data_root, folder_test):
    """Nama file frame test di folder data/ lain (di luar folder test) dan di cache label."""
    bocor = []
    aman = {"test-review", "test-review-auto-backup", "test-review-aux", "frame-blur"}
    for p in Path(data_root).iterdir():
        if p.name in aman or p.name.startswith("dataset-test-") or not p.is_dir():
            continue
        for f in p.rglob("*"):
            if f.is_file() and f.name.startswith(TEST):
                bocor.append(str(f))
            elif f.suffix == ".cache":
                try:
                    if any(t in f.read_bytes().decode("latin-1") for t in TEST):
                        bocor.append(str(f))
                except OSError:
                    pass
    return bocor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default="data/test-review")
    ap.add_argument("--daftar", default="data/test-review/daftar_test.csv")
    a = ap.parse_args()
    out = Path(a.folder)
    err, warn = [], []
    daftar = [r["frame"] for r in csv.DictReader(open(a.daftar, encoding="utf-8"))]
    daftar = [Path(x).stem for x in daftar]
    js = sorted(out.glob("*.json"))
    jpg = sorted(out.glob("*.jpg"))
    err += [f"daftar tanpa json: {s}" for s in daftar if not (out / f"{s}.json").exists()]
    err += [f"daftar tanpa jpg: {s}" for s in daftar if not (out / f"{s}.jpg").exists()]
    err += [f"json di luar daftar: {j.stem}" for j in js if j.stem not in daftar]
    err += [f"jpg di luar daftar: {j.stem}" for j in jpg if j.stem not in daftar]
    lab, kosong, flagged, checked, manual, bukan_tepat = Counter(), [], 0, 0, 0, Counter()
    tipe = Counter()
    for j in js:
        d = json.loads(j.read_text(encoding="utf-8"))
        n = j.stem
        for k in ("version", "flags", "shapes", "imagePath", "imageData", "imageHeight", "imageWidth"):
            if k not in d:
                err.append(f"{n} tanpa {k}")
        if d.get("imageData") is not None or d.get("imagePath") != n + ".jpg" or (d["imageWidth"], d["imageHeight"]) != (1080, 1920):
            err.append(f"{n} header salah")
        if not all(isinstance(v, bool) for v in d["flags"].values()):
            err.append(f"{n} flags bukan bool")
        flagged += bool(d["flags"].get("perlu_cek"))
        checked += bool(d.get("checked"))
        src = Path("data/frame-blur") / n.rsplit("_t", 1)[0] / (n + ".jpg")
        if not src.exists() or not os.path.samefile(src, out / (n + ".jpg")):
            err.append(f"{n} bukan hard link ke frame-blur")
        if not d["shapes"]:
            kosong.append(n)
        boxes = []
        for i, s in enumerate(d["shapes"]):
            p = np.array(s["points"], float)
            tipe[s.get("shape_type")] += 1
            if s.get("shape_type") not in ("polygon", "rectangle") or len(p) < 3 or s["label"] not in KELAS:
                err.append(f"{n}#{i} shape buruk {s['label']} {s.get('shape_type')}")
                continue
            if p.min() < -1 or p[:, 0].max() > 1081 or p[:, 1].max() > 1921:
                err.append(f"{n}#{i} titik di luar gambar")
            manual += not (s.get("description") or "").startswith("auto-v2")
            lab[s["label"]] += 1
            if s["label"] in cts.KOTAK and s["label"] != "tangga":
                boxes.append((i, s["label"], cts.bbox(s["points"], 1080, 1920)))
        for x in range(len(boxes)):
            for y in range(x + 1, len(boxes)):
                if boxes[x][1] != boxes[y][1] and cts.iou(boxes[x][2], boxes[y][2]) > 0.9:
                    warn.append(f"{n}: #{boxes[x][0]} {boxes[x][1]} dan #{boxes[y][0]} {boxes[y][1]} IoU {cts.iou(boxes[x][2], boxes[y][2]):.2f} (satu objek dua kelas?)")
    bocor = cari_bocor("data", out)
    print("json", len(js), "| jpg", len(jpg), "| daftar", len(daftar), "| error", len(err))
    for e in err[:30]:
        print("  ERROR", e)
    print("kebocoran frame test ke folder data lain:", len(bocor))
    for b in bocor[:10]:
        print("  BOCOR", b)
    print("frame perlu_cek (flag):", flagged, "| checked=true:", checked, "| frame kosong:", len(kosong), kosong)
    print("tipe shape:", dict(tipe))
    print(f"{'kelas':16s}{'shape':>6s}")
    for k in KELAS:
        print(f"{k:16s}{lab[k]:6d}")
    print("total shape", sum(lab.values()), "| tanpa description auto-v2 (tambahan/editan manual):", manual)
    print("peringatan (bukan error):", len(warn))
    for w in warn:
        print("  ", w)
    raise SystemExit(1 if err or bocor else 0)


if __name__ == "__main__":
    main()
