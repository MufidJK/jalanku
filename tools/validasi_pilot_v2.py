"""validasi_pilot_v2.py - cek struktur JSON hasil autolabel_v2 di data/pilot-v2 (tanpa membuka X-AnyLabeling).

Dijalankan dari root repo: python tools/validasi_pilot_v2.py
Memeriksa: 249 JSON lengkap, kunci sama dengan format X-AnyLabeling, label ada di classes.txt, titik di dalam gambar,
gambar hard link ke data/pilot/images, tidak ada frame lokasi test, JSON lama di data/pilot/images tidak tersentuh.
Setelah review: shape tanpa description auto-v2 (tambahan/editan manual) bukan error, hanya dihitung.
"""
import csv
import json
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np

out = Path("data/pilot-v2")
kelas = Path("data/pilot/classes.txt").read_text().split()
TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
src = sorted(Path("data/pilot/images").glob("*.jpg"))
js = sorted(out.glob("*.json"))
err = []
lab, diff, flagged, manual = Counter(), Counter(), 0, 0
for f in src:
    j = out / (f.stem + ".json")
    if not j.exists():
        err.append(f"tidak ada json {f.name}")
        continue
    d = json.loads(j.read_text(encoding="utf-8"))
    for k in ("version", "flags", "shapes", "imagePath", "imageData", "imageHeight", "imageWidth"):
        if k not in d:
            err.append(f"{f.name} tanpa {k}")
    if d["imageData"] is not None or d["imagePath"] != f.name or (d["imageWidth"], d["imageHeight"]) != (1080, 1920):
        err.append(f"{f.name} header salah")
    if not all(isinstance(v, bool) for v in d["flags"].values()):
        err.append(f"{f.name} flags bukan bool")
    flagged += bool(d["flags"].get("perlu_cek"))
    if not (out / f.name).exists() or not os.path.samefile(out / f.name, f):
        err.append(f"{f.name} bukan hard link ke pilot/images")
    for s in d["shapes"]:
        p = np.array(s["points"], float)
        # Data hasil review: shape tambahan/editan manual tidak punya description auto-v2, itu bukan error.
        # Cukup cek polygon (atau rectangle, mulai audit label 11 Nov 2026: shape label-kurang boleh digambar sebagai kotak) >= 3 titik dan label valid.
        if s.get("shape_type") not in ("polygon", "rectangle") or len(p) < 3 or s["label"] not in kelas:
            err.append(f"{f.name} shape buruk {s['label']}")
        elif p.min() < -1 or p[:, 0].max() > 1081 or p[:, 1].max() > 1921:
            err.append(f"{f.name} titik di luar gambar")
        manual += not (s.get("description") or "").startswith("auto-v2")
        lab[s["label"]] += 1
        diff[s["label"]] += bool(s.get("difficult"))
print("json", len(js), "| gambar", len(list(out.glob("*.jpg"))), "| error", len(err), err[:8])
print("test di output:", sum(p.name.startswith(TEST) for p in out.glob("*")))
print("frame perlu_cek:", flagged)
print(f"{'kelas':16s}{'total':>6s}{'difficult':>10s}")
for k in kelas:
    print(f"{k:16s}{lab[k]:6d}{diff[k]:10d}")
print("total shape", sum(lab.values()), "difficult", sum(diff.values()), "| tanpa description auto-v2 (manual):", manual)
old = list(Path("data/pilot/images").glob("*.json"))
print("json lama data/pilot/images tidak tersentuh (mtime < 1 jam):", sum(time.time() - q.stat().st_mtime > 3600 for q in old), "/", len(old))
rows = list(csv.DictReader(open(out / "review_list.csv", encoding="utf-8")))
print("review_list baris", len(rows), "| prioritas>=3", sum(int(r["prioritas"]) >= 3 for r in rows), "| prioritas 0", sum(int(r["prioritas"]) == 0 for r in rows))
print("5 teratas:", [(r["filename"][:26], r["prioritas"]) for r in rows[:5]])
c = Counter()
for r in rows:
    for x in r["alasan"].split("; "):
        if x:
            c[x.split(" x")[0]] += 1
print(dict(c))
sh = Counter()
for r in rows:
    sh["objek_kelas_kosong"] += sum(int(r[k]) for k in kelas[:7] + kelas[9:]) == 0
print(dict(sh))
