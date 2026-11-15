"""Cek kebocoran taman-ubm pada frame TERPILIH ronde 4 (prompt ronde 4, aturan 7). Memakai fungsi tools/ronde2_cek_bocor.py.

Embedding GENERIK (ResNet50 ImageNet, bukan model JalanKu). Frame mentah taman-ubm di data/frame-blur hanya dibaca untuk
cek kebocoran ini (sama dengan cek ronde 2). Tidak ada berkas yang diubah. Kontrol positif: 16 frame yang sudah dikeluarkan.
Keluaran: data/ronde4/bocor/ (skor.csv, sheet_*.png).   python tools/ronde4_cek_bocor.py [--daftar pilihan.csv | folder review]
"""
import csv
import glob
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ronde2_cek_bocor as b  # noqa: E402

ROOT = b.ROOT
OUT = os.path.join(ROOT, "data", "ronde4", "bocor")


def main():
    os.makedirs(OUT, exist_ok=True)
    kand = {}
    src = sys.argv[sys.argv.index("--daftar") + 1] if "--daftar" in sys.argv else os.path.join(ROOT, "data", "ronde4", "pilihan.csv")
    if os.path.isdir(src):
        for p in glob.glob(os.path.join(src, "*.jpg")):
            kand[os.path.splitext(os.path.basename(p))[0]] = (p, "ronde4")
    else:
        for r in csv.DictReader(open(src, encoding="utf-8")):
            kand[r["stem"]] = (os.path.join(ROOT, "data", "frame-blur", r["video"], r["stem"] + ".jpg"), "ronde4")
    for r in csv.DictReader(open(os.path.join(ROOT, "data", "ronde2", "bocor", "dikeluarkan.csv"), encoding="utf-8")):
        s = r["stem"]
        kand[s] = (os.path.join(ROOT, "data", "frame-blur", b.video(s), s + ".jpg"), "KONTROL-dikeluarkan")
    ref = {}
    for p in glob.glob(os.path.join(ROOT, "data", "dataset-kampus-kotak-v3", "images", "train", "*.jpg")):
        ref[os.path.splitext(os.path.basename(p))[0]] = p
    for s in list(kand) + list(ref):
        assert not b.lokasi(s).startswith(("selasar-lt11", "pot-lt11", "taman-ubm")), s
    taman = sorted(glob.glob(os.path.join(ROOT, "data", "frame-blur", "taman-ubm*", "*.jpg")))
    stems, rstems = sorted(kand), sorted(ref)
    print(f"kandidat {len(stems)} (kontrol {sum(v[1] != 'ronde4' for v in kand.values())}), referensi train v3 {len(rstems)}, taman-ubm {len(taman)}")
    F = b.Fitur()
    Gc, Pc = F([kand[s][0] for s in stems])
    Gt, Pt = F(taman)
    _, Pr = F([ref[s] for s in rstems])
    H = b.skor(stems, Gc, Pc, Gt, Pt.reshape(-1, Pt.shape[-1]).half(), Pr.half(), [b.lokasi(s) for s in rstems], b.lokasi)
    for h in H:
        h["sumber"] = kand[h["stem"]][1]
    for key in ("patch", "glob"):
        for r, h in enumerate(sorted(H, key=lambda h: -h[key])):
            h["rank_" + key] = r + 1
    for h in H:
        h["rank_gab"] = (h["rank_patch"] + h["rank_glob"]) / 2
    H.sort(key=lambda h: h["rank_gab"])
    with open(os.path.join(OUT, "skor.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["urut", "stem", "sumber", "lokasi", "skor_patch", "skor_global", "rank_patch", "rank_global", "taman_terdekat_patch"])
        for i, h in enumerate(H):
            wr.writerow([i + 1, h["stem"], h["sumber"], b.lokasi(h["stem"]), f"{h['patch']:.4f}", f"{h['glob']:.4f}", h["rank_patch"],
                         h["rank_glob"], os.path.basename(taman[h["patch_taman"]])])
    # sheet: HANYA thumbnail kandidat (lokasi training); frame taman-ubm tidak digambar
    per, kol = 30, 10
    for n, a in enumerate(range(0, min(len(H), 60), per)):
        tiles = []
        for i, h in enumerate(H[a:a + per]):
            s = h["stem"]
            lab = [f"#{a + i + 1} {h['sumber'][:8]}", b.lokasi(s)[:22], s.rsplit('_', 2)[1] + f" t={b.waktu(s):.0f}s",
                   f"patch {h['patch']:.3f} (r{h['rank_patch']})", f"global {h['glob']:.3f} (r{h['rank_glob']})"]
            tiles.append(b.thumb(kand[s][0], patches=h["patch_idx"], teks=lab,
                                 warna=(0, 0, 255) if h["sumber"].startswith("KONTROL") else (0, 255, 255)))
        while len(tiles) % kol:
            tiles.append(np.full_like(tiles[0], 40))
        cv2.imwrite(os.path.join(OUT, f"sheet_{n + 1}.png"), np.vstack([np.hstack(tiles[r:r + kol]) for r in range(0, len(tiles), kol)]))
    for i, h in enumerate(H[:40]):
        print(f"{i + 1:3d} {h['sumber'][:8]:8s} {h['stem']:66s} patch {h['patch']:.3f} r{h['rank_patch']:<4d} glob {h['glob']:.3f} r{h['rank_glob']}")


if __name__ == "__main__":
    main()
