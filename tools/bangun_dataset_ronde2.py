"""bangun_dataset_ronde2.py - dataset ronde 2: varian v2bersih (v2 tanpa frame bocor) dan v3 (v2bersih + frame ronde 2).

Dijalankan dari root repo:
  python tools/bangun_dataset_ronde2.py v2bersih
  python tools/bangun_dataset_ronde2.py v3
  python tools/bangun_dataset_ronde2.py cek-konversi   # konversi JSON->YOLO di sini = bangun_dataset_kampus.py (uji di train v2)

Dataset yang ada tidak diubah dan tool lama tidak diubah. Semua keluaran diturunkan dari folder -v2 lewat hard link:
  data/dataset-kampus-{kotak,seg}-<varian>
      train = train v2 dikurangi frame di data/ronde2/bocor/dikeluarkan.csv (kebocoran taman-ubm, keputusan Jeka A1/A2)
              (+ untuk v3: frame data/ronde2-review/*.json dikonversi seperti bangun_dataset_kampus.py, R4 diterapkan)
      val   = berkas val v2 di-hard-link (byte-identik, dicek dengan SHA-256)
  data/dataset-gabung-kotak-<varian>
      bagian publik = baris non-campus dari dataset-gabung-kotak-v2/sumber.csv, gambar + label di-hard-link (byte-identik)
      bagian kampus = kampus-kotak-<varian> train, oversample 4 (nama <stem>__r1..__r3, sama dengan bangun_dataset_gabung.py)
      val = val gabung-kotak-v2 (byte-identik)
  data/dataset-gabung-seg-<varian> = kampus-seg-<varian> (sama seperti bangun_dataset_gabung.py: seg hanya kampus)
Menolak jalan kalau folder keluaran sudah berisi. Assert: tidak ada lokasi val/test atau frame dikeluarkan di train.

R4 untuk frame ronde 2 (tanpa pengecualian): shape kelas kotak di bawah ambang dibuang dari dataset kotak; tangga dicek
pada kotak gabungan per frame, kalau gagal dibuang dari kotak DAN seg (sama dengan audit v2 yang menghapus shape-nya).
"""
import csv
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import cek_test_set as cts  # noqa: E402

D = Path("data")
TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
LOKASI_VAL = ("dapsut", "perpus-lt9-ubm-tower", "tangga-naik-lt9-lt10-ubm-tower")
KELAS_SEG = ["jalur_jalan", "jalan_kendaraan", "tangga"]
KELAS_KOTAK = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"]
OVERSAMPLE = 4
REVIEW = D / "ronde2-review"
DIKELUARKAN = D / "ronde2" / "bocor" / "dikeluarkan.csv"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def taut(src, dst):
    os.link(src, dst)


def lokasi(stem):
    return stem.split("_")[0]


def tulis_yaml(out, kelas):
    (out / "data.yaml").write_text(
        f"path: {out.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {i}: {k}\n" for i, k in enumerate(kelas)), encoding="utf-8")


def konversi(d, r4=True):
    """JSON X-AnyLabeling -> (baris seg, baris kotak, Counter R4 dibuang). Sama dengan bangun_dataset_kampus.py + R4."""
    w, h = float(d.get("imageWidth", 1080)), float(d.get("imageHeight", 1920))
    shapes = [s for s in d["shapes"] if len(s["points"]) >= 3]
    buang = Counter()
    tp = [np.asarray(s["points"], float) for s in shapes if s["label"] == "tangga"]
    tangga_ok = bool(tp) and (not r4 or cts.lolos_r4("tangga", cts.bbox(np.vstack(tp), w, h)))
    if tp and not tangga_ok:
        buang["tangga"] += 1
    seg = []
    for s in shapes:
        if s["label"] not in KELAS_SEG or (s["label"] == "tangga" and not tangga_ok):
            continue
        p = np.asarray(s["points"], float)
        p[:, 0] = np.clip(p[:, 0], 0.0, w) / w
        p[:, 1] = np.clip(p[:, 1], 0.0, h) / h
        seg.append(f"{KELAS_SEG.index(s['label'])} " + " ".join(f"{x:.6f} {y:.6f}" for x, y in p))
    items = []
    for s in shapes:
        lab = s["label"]
        if lab not in KELAS_KOTAK or lab == "tangga":
            continue
        p = np.asarray(s["points"], float)
        x1, y1 = np.clip(p.min(0), 0.0, [w, h])
        x2, y2 = np.clip(p.max(0), 0.0, [w, h])
        if not (x2 > x1 and y2 > y1):
            continue
        if r4 and not cts.lolos_r4(lab, (x1, y1, x2, y2)):
            buang[lab] += 1
            continue
        items.append((lab, x1, y1, x2, y2))
    if tangga_ok:
        t = np.vstack(tp)
        x1, y1 = np.clip(t.min(0), 0.0, [w, h])
        x2, y2 = np.clip(t.max(0), 0.0, [w, h])
        if x2 > x1 and y2 > y1:
            items.append(("tangga", x1, y1, x2, y2))
    kotak = [f"{KELAS_KOTAK.index(l)} {((a + c) / 2) / w:.6f} {((b + e) / 2) / h:.6f} {(c - a) / w:.6f} {(e - b) / h:.6f}"
             for l, a, b, c, e in items]
    return seg, kotak, buang


def teks(lines):
    return "\n".join(lines) + ("\n" if lines else "")


def baca_dikeluarkan():
    rows = list(csv.DictReader(open(DIKELUARKAN, encoding="utf-8")))
    assert len(rows) == 16, len(rows)
    return {r["stem"] for r in rows}


def siap(out):
    if out.exists() and any(out.rglob("*")):
        raise SystemExit(f"BERHENTI: {out} sudah berisi file; tidak ditimpa.")
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (out / sub).mkdir(parents=True, exist_ok=True)


def salin_split(src, dst, split, kecuali=frozenset()):
    """hard link gambar + label satu split; kembalikan daftar stem."""
    st = []
    for g in sorted((src / "images" / split).glob("*.jpg")):
        if g.stem in kecuali:
            continue
        taut(g, dst / "images" / split / g.name)
        taut(src / "labels" / split / f"{g.stem}.txt", dst / "labels" / split / f"{g.stem}.txt")
        st.append(g.stem)
    return st


def cek_val_identik(a, b):
    fa = sorted(p.relative_to(a) for p in (a / "images" / "val").glob("*")) + \
         sorted(p.relative_to(a) for p in (a / "labels" / "val").glob("*"))
    fb = sorted(p.relative_to(b) for p in (b / "images" / "val").glob("*")) + \
         sorted(p.relative_to(b) for p in (b / "labels" / "val").glob("*"))
    assert fa == fb, f"daftar val beda {a} vs {b}"
    for r in fa:
        assert sha(a / r) == sha(b / r), f"val tidak byte-identik: {r}"
    return len(fa)


def cek_train(out, kecuali):
    for g in (out / "images" / "train").glob("*"):
        stem = g.stem.split("__r")[0]
        lok = lokasi(stem)
        assert not lok.startswith(TEST), f"lokasi TEST di train: {g.name}"
        assert lok not in LOKASI_VAL, f"lokasi VAL di train: {g.name}"
        assert stem not in kecuali, f"frame dikeluarkan ada di train: {g.name}"
    for g in (out / "images" / "val").glob("*"):
        assert lokasi(g.stem) in LOKASI_VAL, f"bukan lokasi val di val: {g.name}"


def bangun(varian):
    assert varian in ("v2bersih", "v3")
    kecuali = baca_dikeluarkan()
    v2k, v2s = D / "dataset-kampus-kotak-v2", D / "dataset-kampus-seg-v2"
    ok, os_ = D / f"dataset-kampus-kotak-{varian}", D / f"dataset-kampus-seg-{varian}"
    gk, gs = D / f"dataset-gabung-kotak-{varian}", D / f"dataset-gabung-seg-{varian}"
    for o in (ok, os_, gk, gs):
        siap(o)
    v2_train = {p.stem for p in (v2k / "images" / "train").glob("*.jpg")}
    keluar_train = sorted(v2_train & kecuali)
    print(f"[{varian}] frame train v2 dikeluarkan: {len(keluar_train)}")
    # ---- kampus: dari v2
    daftar = []
    for src, dst in ((v2k, ok), (v2s, os_)):
        for split in ("train", "val"):
            st = salin_split(src, dst, split, kecuali if split == "train" else frozenset())
            if src is v2k:
                daftar += [(f"{s}.jpg", lokasi(s), split, "v2") for s in st]
    # ---- v3: frame ronde 2
    r4 = Counter()
    n_baru = 0
    if varian == "v3":
        for j in sorted(REVIEW.glob("*.json")):
            stem = j.stem
            assert stem not in kecuali, stem
            lok = lokasi(stem)
            assert not lok.startswith(TEST) and lok not in LOKASI_VAL, f"lokasi terlarang di ronde 2: {stem}"
            assert stem not in v2_train, f"ronde 2 sudah ada di v2: {stem}"
            seg, kotak, buang = konversi(json.loads(j.read_text(encoding="utf-8")))
            r4.update(buang)
            img = REVIEW / f"{stem}.jpg"
            for dst, lines in ((ok, kotak), (os_, seg)):
                taut(img, dst / "images" / "train" / img.name)
                (dst / "labels" / "train" / f"{stem}.txt").write_text(teks(lines), encoding="utf-8")
            daftar.append((img.name, lok, "train", "ronde2"))
            n_baru += 1
        print(f"[{varian}] frame ronde 2 ditambahkan: {n_baru}; R4 dibuang: {sum(r4.values())} {dict(r4)}")
    for o, kelas in ((ok, KELAS_KOTAK), (os_, KELAS_SEG)):
        tulis_yaml(o, kelas)
        with open(o / "daftar_frame.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["filename", "lokasi", "split", "sumber"])
            w.writerows(sorted(daftar))
    # ---- gabung kotak: publik byte-identik dari gabung-kotak-v2, kampus oversample 4
    g2 = D / "dataset-gabung-kotak-v2"
    sumber = []
    kampus_train = sorted((ok / "images" / "train").glob("*.jpg"))
    for g in kampus_train:
        lp = ok / "labels" / "train" / f"{g.stem}.txt"
        n = sum(1 for l in lp.read_text().splitlines() if l.strip())
        for r in range(OVERSAMPLE):
            stem = g.stem if r == 0 else f"{g.stem}__r{r}"
            taut(g, gk / "images" / "train" / f"{stem}.jpg")
            dst = gk / "labels" / "train" / f"{stem}.txt"
            taut(lp, dst) if r == 0 else shutil.copy2(lp, dst)
            sumber.append(dict(split="train", image=f"{stem}.jpg", sumber="campus", asli=g.name, ulang=r, n_asli=n, n_coco=0))
    n_pub = 0
    for row in csv.DictReader(open(g2 / "sumber.csv", encoding="utf-8")):
        if row["sumber"] == "campus":
            continue
        assert row["split"] == "train"
        im = row["image"]
        taut(g2 / "images" / "train" / im, gk / "images" / "train" / im)
        lab = Path(im).stem + ".txt"
        taut(g2 / "labels" / "train" / lab, gk / "labels" / "train" / lab)
        sumber.append(row)
        n_pub += 1
    salin_split(g2, gk, "val")
    for r in csv.DictReader(open(g2 / "sumber.csv", encoding="utf-8")):
        if r["split"] == "val":
            sumber.append(r)
    with open(gk / "sumber.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["split", "image", "sumber", "asli", "ulang", "n_asli", "n_coco"])
        w.writeheader()
        w.writerows(sumber)
    taut(g2 / "kotak_akhir.csv", gk / "kotak_akhir.csv")
    tulis_yaml(gk, KELAS_KOTAK)
    # ---- gabung seg = kampus seg
    sumber_seg = []
    for split in ("train", "val"):
        for s in salin_split(os_, gs, split):
            sumber_seg.append(dict(split=split, image=f"{s}.jpg", sumber="campus"))
    with open(gs / "sumber.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["split", "image", "sumber"])
        w.writeheader()
        w.writerows(sumber_seg)
    tulis_yaml(gs, KELAS_SEG)
    # ---- cek
    for o in (ok, os_, gk, gs):
        cek_train(o, kecuali)
    nv = [cek_val_identik(v2k, ok), cek_val_identik(v2s, os_), cek_val_identik(g2, gk), cek_val_identik(D / "dataset-gabung-seg-v2", gs)]
    for row in sumber:  # publik byte-identik
        if row["sumber"] != "campus":
            im = row["image"]
            assert os.path.samefile(g2 / "images" / "train" / im, gk / "images" / "train" / im)
            lab = Path(im).stem + ".txt"
            assert sha(g2 / "labels" / "train" / lab) == sha(gk / "labels" / "train" / lab)
    nk = len(kampus_train)
    n_tr = nk * OVERSAMPLE + n_pub
    print(f"[{varian}] kampus train {nk} frame (x{OVERSAMPLE} = {nk * OVERSAMPLE}) + publik {n_pub} = {n_tr} gambar train; "
          f"porsi kampus {100 * nk * OVERSAMPLE / n_tr:.1f}%")
    print(f"[{varian}] val byte-identik dengan v2 (berkas dicek SHA-256): kampus-kotak {nv[0]}, kampus-seg {nv[1]}, "
          f"gabung-kotak {nv[2]}, gabung-seg {nv[3]}; publik {n_pub} gambar + label identik")
    print(f"[{varian}] assert lolos: tidak ada lokasi val/test atau frame dikeluarkan di train")
    hitung(gk, KELAS_KOTAK, "gabung-kotak")
    hitung(os_, KELAS_SEG, "kampus-seg")
    hitung(ok, KELAS_KOTAK, "kampus-kotak")


def hitung(o, kelas, nama):
    for split in ("train", "val"):
        c = Counter()
        n = 0
        for lp in (o / "labels" / split).glob("*.txt"):
            n += 1
            c.update(int(l.split()[0]) for l in lp.read_text().splitlines() if l.strip())
        print(f"   {nama} {split}: {n} gambar | " + ", ".join(f"{k}={c[i]}" for i, k in enumerate(kelas)))


def cek_konversi():
    """Konversi ulang JSON pilot-v2 untuk frame train v2 dan bandingkan dengan label v2 (harus identik)."""
    beda = 0
    n = 0
    for lp in sorted((D / "dataset-kampus-kotak-v2" / "labels" / "train").glob("*.txt")):
        stem = lp.stem
        j = D / "pilot-v2-blind" / f"{stem}.json"
        j = j if j.exists() else D / "pilot-v2" / f"{stem}.json"
        seg, kotak, buang = konversi(json.loads(j.read_text(encoding="utf-8")), r4=False)
        n += 1
        if teks(kotak) != lp.read_text() or teks(seg) != (D / "dataset-kampus-seg-v2" / "labels" / "train" / f"{stem}.txt").read_text():
            beda += 1
    print(f"cek konversi: {n} frame train v2, beda {beda}")


if __name__ == "__main__":
    a = sys.argv[1]
    cek_konversi() if a == "cek-konversi" else bangun(a)
