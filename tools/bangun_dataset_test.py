"""bangun_dataset_test.py - bangun dataset YOLO TEST (kotak dan segmentasi) dari data/test-review (91 frame, review penuh).

Dijalankan dari root repo:  python tools/bangun_dataset_test.py [--validasi-saja]

Konversi dan urutan kelas SAMA dengan tools/bangun_dataset_kampus.py (versi v2):
  - kotak (data/dataset-test-kotak): 0 pilar, 1 pohon, 2 tepian, 3 orang, 4 tanaman_pot, 5 kursi, 6 kendaraan, 7 tangga.
    Kotak = bounding box titik shape (polygon atau rectangle), dipotong ke gambar. Semua shape tangga per frame digabung
    jadi satu kotak.
  - segmentasi (data/dataset-test-seg): 0 jalur_jalan, 1 jalan_kendaraan, 2 tangga (polygon YOLO seg; rectangle = 4 titik).
  - Semua 91 frame ikut, termasuk yang tanpa objek kelas itu (label kosong = background).
  - Gambar hard link dari data/test-review (yang sendirinya hard link ke data/frame-blur, read-only).
Hanya frame lokasi test yang boleh masuk; folder keluaran harus kosong (tidak menimpa). Tidak ada model yang dijalankan.
data.yaml: ada `test:`; `train:` dan `val:` juga diisi menunjuk folder yang sama HANYA karena Ultralytics 8.4.x menolak YAML
tanpa train dan val. Jangan dipakai untuk melatih atau memilih pengaturan.
"""
import argparse
import csv
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np

SUMBER = Path("data/test-review")
OUT_KOTAK = Path("data/dataset-test-kotak")
OUT_SEG = Path("data/dataset-test-seg")
TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
KELAS_SEG = ["jalur_jalan", "jalan_kendaraan", "tangga"]
KELAS_KOTAK = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"]


def taut(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def tulis_yaml(d, kelas):
    isi = (
        f"path: {d.resolve().as_posix()}\n"
        "# Test set: dievaluasi SEKALI di akhir (baseline dan model ronde 2 bersama). Jangan untuk memilih pengaturan.\n"
        "test: images/test\n"
        "# train dan val menunjuk folder yang sama HANYA karena Ultralytics 8.4.x mewajibkan keduanya ada di YAML.\n"
        "# Jangan dipakai untuk pelatihan.\n"
        "train: images/test\n"
        "val: images/test\n"
        "names:\n" + "".join(f"  {i}: {k}\n" for i, k in enumerate(kelas))
    )
    (d / "data.yaml").write_text(isi, encoding="utf-8")


def bangun():
    for d in (OUT_KOTAK, OUT_SEG):
        if d.exists() and any(d.rglob("*")):
            raise SystemExit(f"BERHENTI: {d} sudah berisi file; tidak ditimpa.")
        (d / "images/test").mkdir(parents=True, exist_ok=True)
        (d / "labels/test").mkdir(parents=True, exist_ok=True)
    id_seg = {k: i for i, k in enumerate(KELAS_SEG)}
    id_kotak = {k: i for i, k in enumerate(KELAS_KOTAK)}
    js = sorted(SUMBER.glob("*.json"))
    assert len(js) == 91, f"harus 91 JSON, ada {len(js)}"
    baris = []
    for j in js:
        stem = j.stem
        if not stem.startswith(TEST):
            raise RuntimeError(f"BERHENTI: {stem} bukan frame lokasi test")
        d = json.loads(j.read_text(encoding="utf-8"))
        w, h = float(d["imageWidth"]), float(d["imageHeight"])
        seg, kotak, tangga = [], [], []
        for s in d["shapes"]:
            lab = s["label"]
            pts = np.asarray(s["points"], float)
            if len(pts) < 3:
                continue
            if lab in id_seg:
                q = pts.copy()
                q[:, 0] = np.clip(q[:, 0], 0.0, w) / w
                q[:, 1] = np.clip(q[:, 1], 0.0, h) / h
                seg.append(f"{id_seg[lab]} " + " ".join(f"{x:.6f} {y:.6f}" for x, y in q))
            if lab == "tangga":
                tangga.append(pts)
            elif lab in id_kotak:
                x1, y1 = np.clip(pts.min(0), 0.0, [w, h])
                x2, y2 = np.clip(pts.max(0), 0.0, [w, h])
                if x2 > x1 and y2 > y1:
                    kotak.append((lab, x1, y1, x2, y2))
        if tangga:
            a = np.vstack(tangga)
            x1, y1 = np.clip(a.min(0), 0.0, [w, h])
            x2, y2 = np.clip(a.max(0), 0.0, [w, h])
            if x2 > x1 and y2 > y1:
                kotak.append(("tangga", x1, y1, x2, y2))
        kl = [f"{id_kotak[lab]} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}"
              for lab, x1, y1, x2, y2 in kotak]
        for out, lines in ((OUT_KOTAK, kl), (OUT_SEG, seg)):
            taut(SUMBER / f"{stem}.jpg", out / "images/test" / f"{stem}.jpg")
            (out / "labels/test" / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        baris.append([f"{stem}.jpg", stem.split("_")[0], len(seg), len(kl)])
    tulis_yaml(OUT_KOTAK, KELAS_KOTAK)
    tulis_yaml(OUT_SEG, KELAS_SEG)
    for out in (OUT_KOTAK, OUT_SEG):
        with open(out / "daftar_frame.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["filename", "lokasi", "n_polygon_seg", "n_kotak"])
            wr.writerows(baris)


def validasi():
    from ultralytics.cfg import DEFAULT_CFG
    from ultralytics.data.dataset import YOLODataset

    for out, kelas, task in ((OUT_KOTAK, KELAS_KOTAK, "detect"), (OUT_SEG, KELAS_SEG, "segment")):
        ds = YOLODataset(img_path=str(out / "images/test"), imgsz=640, augment=False, hyp=DEFAULT_CFG, rect=False, cache=False,
                         single_cls=False, stride=32, pad=0.0, prefix="", task=task,
                         data={"names": dict(enumerate(kelas)), "channels": 3, "nc": len(kelas)})
        c, kosong = Counter(), 0
        for lb in ds.labels:
            kosong += len(lb["cls"]) == 0
            for k in np.asarray(lb["cls"]).reshape(-1).astype(int):
                c[kelas[k]] += 1
        # label dari txt langsung (cek terhadap yang dibaca Ultralytics)
        n_txt = sum(len([x for x in p.read_text().splitlines() if x.strip()]) for p in (out / "labels/test").glob("*.txt"))
        print(f"{out.name} ({task}): gambar {len(ds.labels)}, label txt {len(list((out / 'labels/test').glob('*.txt')))}, "
              f"background kosong {kosong}, instance dibaca Ultralytics {sum(c.values())} (txt {n_txt})")
        print("  per kelas:", {k: c[k] for k in kelas})
        # YOLODataset membuang baris korup dan melaporkannya lewat cache; cek flag dari cache file
        cache = np.load(out / "labels/test.cache", allow_pickle=True).item()
        print(f"  cache: found {cache['results'][0]}, missing {cache['results'][1]}, empty {cache['results'][2]}, corrupt {cache['results'][3]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validasi-saja", action="store_true")
    a = ap.parse_args()
    if not a.validasi_saja:
        bangun()
        print("dataset dibangun:", OUT_KOTAK, OUT_SEG)
    validasi()


if __name__ == "__main__":
    sys.exit(main())
