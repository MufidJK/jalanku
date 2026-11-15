"""bangun_dataset_ronde4.py - dataset v4 (ronde 4): v3 + frame hasil review data/ronde4-review/ (R4 tanpa pengecualian).

  python tools/bangun_dataset_ronde4.py v4

Semua keluaran diturunkan dari folder -v3 lewat hard link; folder v1/v2/v2bersih/v3/test dan tool lama tidak diubah:
  data/dataset-kampus-{kotak,seg}-v4: train = train v3 + frame ronde 4; val = val v3 (= val v2, dicek SHA-256 terhadap v2 DAN v3)
  data/dataset-gabung-kotak-v4: publik = baris non-campus gabung-kotak-v3/sumber.csv (hard link, byte-identik),
                                kampus = kampus-kotak-v4 train x4 (nama __r1..__r3), val = val gabung-kotak-v3
  data/dataset-gabung-seg-v4 = kampus-seg-v4
Menolak jalan kalau folder keluaran sudah berisi. Assert: tidak ada lokasi val/test, frame dikeluarkan, atau frame di rentang
bocor (ronde4_pilih.BOCOR) di train.
"""
import csv
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bangun_dataset_ronde2 as b2  # noqa: E402
from bangun_dataset_ronde2 import (D, KELAS_KOTAK, KELAS_SEG, OVERSAMPLE, TEST, LOKASI_VAL, baca_dikeluarkan, cek_train, cek_val_identik,  # noqa: E402
                                   hitung, konversi, lokasi, salin_split, sha, siap, taut, teks, tulis_yaml)
import ronde4_pilih as p4  # noqa: E402

REVIEW = D / "ronde4-review"


def bangun():
    kecuali = baca_dikeluarkan()
    v2k, v2s = D / "dataset-kampus-kotak-v2", D / "dataset-kampus-seg-v2"
    v3k, v3s = D / "dataset-kampus-kotak-v3", D / "dataset-kampus-seg-v3"
    g2, g3, g3s = D / "dataset-gabung-kotak-v2", D / "dataset-gabung-kotak-v3", D / "dataset-gabung-seg-v3"
    ok, os_ = D / "dataset-kampus-kotak-v4", D / "dataset-kampus-seg-v4"
    gk, gs = D / "dataset-gabung-kotak-v4", D / "dataset-gabung-seg-v4"
    for o in (ok, os_, gk, gs):
        siap(o)
    daftar = [dict(r) for r in csv.DictReader(open(v3k / "daftar_frame.csv", encoding="utf-8"))]
    for src, dst in ((v3k, ok), (v3s, os_)):
        for split in ("train", "val"):
            salin_split(src, dst, split)
    v3_train = {g.stem for g in (v3k / "images" / "train").glob("*.jpg")}
    r4, n_baru = Counter(), 0
    for j in sorted(REVIEW.glob("*.json")):
        stem = j.stem
        lok = lokasi(stem)
        video, t = stem.rsplit("_t", 1)
        assert stem not in kecuali, f"frame dikeluarkan: {stem}"
        assert not lok.startswith(TEST) and lok not in LOKASI_VAL, f"lokasi terlarang: {stem}"
        assert not p4.di_bocor(video, int(t) / 1000.0), f"frame di rentang bocor: {stem}"
        assert stem not in v3_train, f"sudah ada di v3: {stem}"
        seg, kotak, buang = konversi(json.loads(j.read_text(encoding="utf-8")))
        r4.update(buang)
        img = REVIEW / f"{stem}.jpg"
        for dst, lines in ((ok, kotak), (os_, seg)):
            taut(img, dst / "images" / "train" / img.name)
            (dst / "labels" / "train" / f"{stem}.txt").write_text(teks(lines), encoding="utf-8")
        daftar.append(dict(filename=img.name, lokasi=lok, split="train", sumber="ronde4"))
        n_baru += 1
    print(f"[v4] frame ronde 4 ditambahkan: {n_baru}; R4 dibuang: {sum(r4.values())} {dict(r4)}")
    for o, kelas in ((ok, KELAS_KOTAK), (os_, KELAS_SEG)):
        tulis_yaml(o, kelas)
        with open(o / "daftar_frame.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["filename", "lokasi", "split", "sumber"])
            w.writeheader()
            w.writerows(sorted(daftar, key=lambda r: (r["filename"], r["split"])))
    # gabung kotak
    sumber, n_pub = [], 0
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
    for row in csv.DictReader(open(g3 / "sumber.csv", encoding="utf-8")):
        if row["sumber"] == "campus":
            continue
        assert row["split"] == "train"
        im = row["image"]
        taut(g3 / "images" / "train" / im, gk / "images" / "train" / im)
        lab = Path(im).stem + ".txt"
        taut(g3 / "labels" / "train" / lab, gk / "labels" / "train" / lab)
        sumber.append(row)
        n_pub += 1
    salin_split(g3, gk, "val")
    for r in csv.DictReader(open(g3 / "sumber.csv", encoding="utf-8")):
        if r["split"] == "val":
            sumber.append(r)
    with open(gk / "sumber.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["split", "image", "sumber", "asli", "ulang", "n_asli", "n_coco"])
        w.writeheader()
        w.writerows(sumber)
    if (g3 / "kotak_akhir.csv").exists():
        taut(g3 / "kotak_akhir.csv", gk / "kotak_akhir.csv")
    tulis_yaml(gk, KELAS_KOTAK)
    sumber_seg = []
    for split in ("train", "val"):
        for s in salin_split(os_, gs, split):
            sumber_seg.append(dict(split=split, image=f"{s}.jpg", sumber="campus"))
    with open(gs / "sumber.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["split", "image", "sumber"])
        w.writeheader()
        w.writerows(sumber_seg)
    tulis_yaml(gs, KELAS_SEG)
    # cek
    for o in (ok, os_, gk, gs):
        cek_train(o, kecuali)
        for g in (o / "images" / "train").glob("*"):
            stem = g.stem.split("__r")[0]
            if "_t" not in stem or not stem.rsplit("_t", 1)[1].isdigit():
                continue  # gambar publik
            assert not p4.di_bocor(stem.rsplit("_t", 1)[0], int(stem.rsplit("_t", 1)[1]) / 1000.0) or stem in v3_train, f"rentang bocor di train: {g.name}"
    nv = [cek_val_identik(v2k, ok), cek_val_identik(v3k, ok), cek_val_identik(v2s, os_), cek_val_identik(v3s, os_),
          cek_val_identik(g2, gk), cek_val_identik(g3, gk), cek_val_identik(D / "dataset-gabung-seg-v2", gs), cek_val_identik(g3s, gs)]
    for row in sumber:
        if row["sumber"] != "campus":
            im = row["image"]
            assert os.path.samefile(g3 / "images" / "train" / im, gk / "images" / "train" / im)
            lab = Path(im).stem + ".txt"
            assert sha(g3 / "labels" / "train" / lab) == sha(gk / "labels" / "train" / lab)
            assert sha(g2 / "labels" / "train" / lab) == sha(gk / "labels" / "train" / lab)  # sama dengan v2 juga
    nk = len(kampus_train)
    n_tr = nk * OVERSAMPLE + n_pub
    print(f"[v4] kampus train {nk} frame (v3 {len(v3_train)} + {n_baru}) x{OVERSAMPLE} = {nk * OVERSAMPLE} + publik {n_pub} = {n_tr} gambar train; "
          f"porsi kampus {100 * nk * OVERSAMPLE / n_tr:.1f}% (v3: {100 * len(v3_train) * OVERSAMPLE / (len(v3_train) * OVERSAMPLE + n_pub):.1f}%)")
    print(f"[v4] val byte-identik dengan v2 dan v3 (SHA-256, berkas): {nv}; publik {n_pub} gambar + label identik dengan v3 dan v2")
    print("[v4] assert lolos: tidak ada lokasi val/test, frame dikeluarkan, atau rentang bocor baru di train")
    hitung(gk, KELAS_KOTAK, "gabung-kotak")
    hitung(os_, KELAS_SEG, "kampus-seg")
    hitung(ok, KELAS_KOTAK, "kampus-kotak")


if __name__ == "__main__":
    if sys.argv[1:] != ["v4"]:
        sys.exit(__doc__)
    bangun()
