"""bangun_dataset_kampus.py - Stage 5: bangun dataset YOLO kotak & segmentasi dari 249 frame pilot.

Dijalankan dari root repo: python tools/bangun_dataset_kampus.py

Opsi (default = perilaku lama, tidak berubah):
  --akhiran=-v2      tulis ke data/dataset-kampus-seg-v2 dan data/dataset-kampus-kotak-v2 (versi baru, dipakai setelah audit
                       label 11 Nov 2026). Dengan akhiran, menolak jalan kalau folder keluaran sudah berisi file.
  --json-akar DIR      baca JSON dari DIR/pilot-v2 dan DIR/pilot-v2-blind (default: data/pilot-v2 dan data/pilot-v2-blind);
                       dipakai untuk membangun varian "v2-noR4" dari data/audit-kampus/sumber-noR4.

Sumber label (Keputusan Checkpoint 4):
  - 15 frame blind : data/pilot-v2-blind/*.json (ground truth bebas bias)
  - 234 frame lain : data/pilot-v2/*.json (hasil review manusia)

Aturan:
  - Lokasi test (selasar-lt11, pot-lt11, taman-ubm) ditolak keras.
  - Gambar di-hardlink dari data/pilot/images/ (tidak menyentuh data/frame-blur/).
  - Split train/val per lokasi (semua frame satu lokasi masuk split yang sama):
      val   (3 lokasi, 54 frame, 21,7%): dapsut, perpus-lt9-ubm-tower, tangga-naik-lt9-lt10-ubm-tower
      train (12 lokasi, 195 frame, 78,3%): 12 lokasi sisanya
  - dataset-kampus-seg   : 0 jalur_jalan, 1 jalan_kendaraan, 2 tangga (polygon YOLO seg)
  - dataset-kampus-kotak : 0 pilar, 1 pohon, 2 tepian, 3 orang, 4 tanaman_pot, 5 kursi, 6 kendaraan, 7 tangga
    * Kotak = bounding box dari titik polygon.
    * Semua shape tangga dalam satu frame digabung jadi satu objek kotak per frame.
"""
import argparse
import csv
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

PILOT_IMG = Path("data/pilot/images")
REVIEW = Path("data/pilot-v2")
BLIND = Path("data/pilot-v2-blind")
OUT_SEG = Path("data/dataset-kampus-seg")
OUT_KOTAK = Path("data/dataset-kampus-kotak")

TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
LOKASI_VAL = ("dapsut", "perpus-lt9-ubm-tower", "tangga-naik-lt9-lt10-ubm-tower")

KELAS_SEG = ["jalur_jalan", "jalan_kendaraan", "tangga"]
KELAS_KOTAK = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"]


def taut(src: Path, dst: Path):
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def tulis_yaml(out_dir: Path, kelas: list[str]):
    isi = (
        f"path: {out_dir.resolve().as_posix()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"names:\n"
        + "".join(f"  {i}: {k}\n" for i, k in enumerate(kelas))
    )
    (out_dir / "data.yaml").write_text(isi, encoding="utf-8")


def main():
    global OUT_SEG, OUT_KOTAK
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--akhiran", default="", help="akhiran nama folder keluaran, mis. -v2 (default: kosong = data/dataset-kampus-*)")
    ap.add_argument("--json-akar", default=None, help="akar JSON pengganti (berisi pilot-v2/ dan pilot-v2-blind/)")
    a = ap.parse_args()
    review_dir = Path(a.json_akar) / "pilot-v2" if a.json_akar else REVIEW
    blind_json_dir = Path(a.json_akar) / "pilot-v2-blind" if a.json_akar else BLIND
    if a.akhiran:
        OUT_SEG = Path(f"data/dataset-kampus-seg{a.akhiran}")
        OUT_KOTAK = Path(f"data/dataset-kampus-kotak{a.akhiran}")
        for d in (OUT_SEG, OUT_KOTAK):
            if d.exists() and any(d.rglob("*")):
                raise SystemExit(f"BERHENTI: {d} sudah berisi file; tidak ditimpa.")
    elif a.json_akar:
        raise SystemExit("BERHENTI: --json-akar wajib dipakai bersama --akhiran (jangan menimpa dataset lama).")
    imgs = sorted(PILOT_IMG.glob("*.jpg"))
    assert len(imgs) == 249, f"Jumlah gambar pilot harus 249, ditemukan {len(imgs)}"
    if any(p.name.startswith(TEST) for p in imgs):
        raise RuntimeError("BERHENTI: ditemukan frame lokasi test di input!")

    blind_stems = {p.stem for p in BLIND.glob("*.jpg")}
    assert len(blind_stems) == 15, f"Blind set harus 15 frame, ditemukan {len(blind_stems)}"

    for d in (OUT_SEG, OUT_KOTAK):
        for sub in ("images/train", "images/val", "labels/train", "labels/val"):
            (d / sub).mkdir(parents=True, exist_ok=True)

    id_seg = {k: i for i, k in enumerate(KELAS_SEG)}
    id_kotak = {k: i for i, k in enumerate(KELAS_KOTAK)}

    stat_frame = Counter()
    stat_kosong_seg = Counter()
    stat_kosong_kotak = Counter()
    stat_seg = defaultdict(Counter)
    stat_seg_frame = defaultdict(Counter)
    stat_kotak = defaultdict(Counter)
    stat_kotak_frame = defaultdict(Counter)
    stat_lokasi = defaultdict(lambda: {"split": "", "frame": 0, "sumber_blind": 0})
    baris_csv = []

    for img_path in imgs:
        stem = img_path.stem
        lokasi = stem.split("_")[0]
        if lokasi.startswith(TEST):
            raise RuntimeError(f"BERHENTI: lokasi test {lokasi}")
        split = "val" if lokasi in LOKASI_VAL else "train"
        sumber_dir = blind_json_dir if stem in blind_stems else review_dir
        sumber_nama = "blind" if stem in blind_stems else "review"
        js_path = sumber_dir / f"{stem}.json"
        if not js_path.exists():
            raise FileNotFoundError(f"JSON tidak ditemukan: {js_path}")

        d = json.loads(js_path.read_text(encoding="utf-8"))
        w = float(d.get("imageWidth", 1080))
        h = float(d.get("imageHeight", 1920))
        shapes = d["shapes"]

        stat_frame[split] += 1
        stat_lokasi[lokasi]["split"] = split
        stat_lokasi[lokasi]["frame"] += 1
        stat_lokasi[lokasi]["sumber_blind"] += int(stem in blind_stems)

        # 1. Dataset segmentasi (0 jalur_jalan, 1 jalan_kendaraan, 2 tangga)
        seg_lines = []
        seg_hadir = set()
        for s in shapes:
            lab = s["label"]
            if lab not in id_seg:
                continue
            pts = np.asarray(s["points"], float)
            if len(pts) < 3:
                continue
            pts[:, 0] = np.clip(pts[:, 0], 0.0, w) / w
            pts[:, 1] = np.clip(pts[:, 1], 0.0, h) / h
            koord = " ".join(f"{px:.6f} {py:.6f}" for px, py in pts)
            seg_lines.append(f"{id_seg[lab]} {koord}")
            stat_seg[split][lab] += 1
            seg_hadir.add(lab)
        for lab in seg_hadir:
            stat_seg_frame[split][lab] += 1
        if not seg_lines:
            stat_kosong_seg[split] += 1

        taut(img_path, OUT_SEG / "images" / split / img_path.name)
        (OUT_SEG / "labels" / split / f"{stem}.txt").write_text(
            "\n".join(seg_lines) + ("\n" if seg_lines else ""), encoding="utf-8"
        )

        # 2. Dataset kotak (0..7, tangga digabung jadi 1 kotak per frame)
        kotak_items = []
        tangga_pts = []
        kotak_hadir = set()
        for s in shapes:
            lab = s["label"]
            if lab not in id_kotak:
                continue
            pts = np.asarray(s["points"], float)
            if len(pts) < 3:
                continue
            if lab == "tangga":
                tangga_pts.append(pts)
            else:
                x1, y1 = np.clip(pts.min(0), 0.0, [w, h])
                x2, y2 = np.clip(pts.max(0), 0.0, [w, h])
                if x2 > x1 and y2 > y1:
                    kotak_items.append((lab, x1, y1, x2, y2))
        if tangga_pts:
            semua_t = np.vstack(tangga_pts)
            x1, y1 = np.clip(semua_t.min(0), 0.0, [w, h])
            x2, y2 = np.clip(semua_t.max(0), 0.0, [w, h])
            if x2 > x1 and y2 > y1:
                kotak_items.append(("tangga", x1, y1, x2, y2))

        kotak_lines = []
        for lab, x1, y1, x2, y2 in kotak_items:
            xc = ((x1 + x2) / 2.0) / w
            yc = ((y1 + y2) / 2.0) / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            kotak_lines.append(f"{id_kotak[lab]} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
            stat_kotak[split][lab] += 1
            kotak_hadir.add(lab)
        for lab in kotak_hadir:
            stat_kotak_frame[split][lab] += 1
        if not kotak_lines:
            stat_kosong_kotak[split] += 1

        taut(img_path, OUT_KOTAK / "images" / split / img_path.name)
        (OUT_KOTAK / "labels" / split / f"{stem}.txt").write_text(
            "\n".join(kotak_lines) + ("\n" if kotak_lines else ""), encoding="utf-8"
        )

        baris_csv.append([img_path.name, lokasi, split, sumber_nama, len(seg_lines), len(kotak_lines)])

    tulis_yaml(OUT_SEG, KELAS_SEG)
    tulis_yaml(OUT_KOTAK, KELAS_KOTAK)

    for d in (OUT_SEG, OUT_KOTAK):
        with open(d / "daftar_frame.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["filename", "lokasi", "split", "sumber_gt", "n_polygon_seg", "n_kotak"])
            wr.writerows(baris_csv)

    print(f"Total gambar: {sum(stat_frame.values())} | train: {stat_frame['train']} | val: {stat_frame['val']}")
    print(f"Frame kosong seg   -> train: {stat_kosong_seg['train']}, val: {stat_kosong_seg['val']}")
    print(f"Frame kosong kotak -> train: {stat_kosong_kotak['train']}, val: {stat_kosong_kotak['val']}")

    print("\n=== DATASET SEGMENTASI (data/dataset-kampus-seg) ===")
    print(f"{'ID':>2s} {'Kelas':16s} {'Train poly':>11s} {'Train frm':>10s} {'Val poly':>9s} {'Val frm':>8s} {'Total poly':>11s}")
    for i, k in enumerate(KELAS_SEG):
        tp, tf = stat_seg["train"][k], stat_seg_frame["train"][k]
        vp, vf = stat_seg["val"][k], stat_seg_frame["val"][k]
        print(f"{i:2d} {k:16s} {tp:11d} {tf:10d} {vp:9d} {vf:8d} {tp + vp:11d}")

    print("\n=== DATASET KOTAK (data/dataset-kampus-kotak) ===")
    print(f"{'ID':>2s} {'Kelas':16s} {'Train box':>11s} {'Train frm':>10s} {'Val box':>9s} {'Val frm':>8s} {'Total box':>11s}")
    for i, k in enumerate(KELAS_KOTAK):
        tb, tf = stat_kotak["train"][k], stat_kotak_frame["train"][k]
        vb, vf = stat_kotak["val"][k], stat_kotak_frame["val"][k]
        print(f"{i:2d} {k:16s} {tb:11d} {tf:10d} {vb:9d} {vf:8d} {tb + vb:11d}")


if __name__ == "__main__":
    main()

