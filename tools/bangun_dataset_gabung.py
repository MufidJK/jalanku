"""bangun_dataset_gabung.py - gabungkan dataset kampus + dataset publik terpilih (Section 6, Checkpoint P2).

Dijalankan dari root repo.

Masukan (hanya dibaca, tidak diubah):
  data/dataset-kampus-kotak, data/dataset-kampus-seg        dataset kampus (Stage 5)
  data/publik/<nama>/terpilih/ + manifest_gambar.csv + manifest_kotak.csv   hasil `siapkan_publik.py terpilih`
  data/publik/<nama>/dedup.csv                                 hasil `siapkan_publik.py dedup` (dipakai kalau ada)

Keluaran:
  data/dataset-gabung-kotak/   train = kampus train (di-oversample) + publik terpilih; val = kampus val saja
  data/dataset-gabung-seg/     kampus saja (lemnix dibuang di P1), train/val sama dengan dataset-kampus-seg
  Tiap dataset: images/{train,val}, labels/{train,val}, data.yaml, sumber.csv (asal tiap gambar: campus/trotoar/...)
  Dataset kotak juga: kotak_akhir.csv (tiap kotak publik: asli/coco_fill, dipakai atau alasan dibuang)

Aturan:
  - val = kampus val saja (dapsut, perpus-lt9-ubm-tower, tangga-naik-lt9-lt10-ubm-tower; 54 frame).
  - Lokasi test (selasar-lt11, pot-lt11, taman-ubm) ditolak keras.
  - Gambar di-hard-link (fallback salin). Duplikat oversample: gambar di-hard-link, label disalin, nama <stem>__r1, __r2, ...
  - Dedup: kalau <nama>/dedup.csv ada, hanya gambar dengan simpan=1 yang masuk pool (ROD: salinan augmentasi dibuang).
  - Pemilihan gambar publik per dataset: round-robin berbasis kelas (selalu ambil gambar untuk kelas yang jumlah
    kotaknya paling sedikit di antara yang terpilih), seed tetap, sampai batas --cap.
  - Pengetat COCO fill (keputusan P2; aktif kalau --skip-nested / --skip-lintas-iou diberikan):
      * kotak coco_fill yang bersarang (interseksi / luas kotak terkecil >= --skip-nested) di kotak asli sekelas dibuang;
      * kotak coco_fill yang IoU-nya > --skip-lintas-iou dengan kotak asli KELAS LAIN dibuang;
      * khusus tanaman_pot: kalau kotak COCO dan kotak asli bersarang, kotak yang LEBIH BESAR (pot + tanaman, satu objek
        sesuai kelas.md) dipakai dan yang lebih kecil (pot saja) dibuang, dari sumber mana pun. Kalau satu kotak COCO
        menampung >= 2 kotak asli tanaman_pot, kotak COCO dibuang (jangan menggabung dua objek).
  - Tidak menimpa: kalau folder keluaran sudah berisi, berhenti. Pengecualian: --ganti-kotak menghapus HANYA
    data/dataset-gabung-kotak lalu membangunnya ulang; --hanya-kotak tidak menyentuh dataset-gabung-seg sama sekali.

Contoh:
  python tools/bangun_dataset_gabung.py --dry-run --skip-nested 0.8 --skip-lintas-iou 0.5
  python tools/bangun_dataset_gabung.py --skip-nested 0.8 --skip-lintas-iou 0.5 --hanya-kotak --ganti-kotak
  python tools/bangun_dataset_gabung.py --oversample 4 --cap trotoar=700 --cap ood=600 --seed 20261110
"""
import argparse
import csv
import os
import random
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIK = ROOT / "data" / "publik"
KAMPUS_KOTAK = ROOT / "data" / "dataset-kampus-kotak"
KAMPUS_SEG = ROOT / "data" / "dataset-kampus-seg"
OUT_KOTAK = ROOT / "data" / "dataset-gabung-kotak"
OUT_SEG = ROOT / "data" / "dataset-gabung-seg"

KELAS_KOTAK = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"]
ID_POT = KELAS_KOTAK.index("tanaman_pot")
KELAS_SEG = ["jalur_jalan", "jalan_kendaraan", "tangga"]
TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
CAP_DEFAULT = {"trotoar": 700, "unstructured": 600, "ood": 600, "rod": 400}
IMG_EXT = {".jpg", ".jpeg", ".png"}


def tautkan(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def iou_ioa(a, b):
    """a, b = (xc, yc, w, h) ternormalisasi. Kembalikan (IoU, interseksi / luas kotak terkecil)."""
    ax0, ay0, ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx0, by0, bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw, ih = max(0.0, min(ax1, bx1) - max(ax0, bx0)), max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    ua, ub = a[2] * a[3], b[2] * b[3]
    return inter / (ua + ub - inter + 1e-12), inter / (min(ua, ub) + 1e-12)


def baca_kampus(split):
    """Kembalikan [(nama_gambar, path_gambar, path_label, Counter kelas->kotak)] dari dataset-kampus-kotak."""
    hasil = []
    for g in sorted((KAMPUS_KOTAK / "images" / split).iterdir()):
        if g.suffix.lower() not in IMG_EXT:
            continue
        assert not g.name.startswith(TEST), f"lokasi test terdeteksi: {g.name}"
        lp = KAMPUS_KOTAK / "labels" / split / (g.stem + ".txt")
        cs = Counter(KELAS_KOTAK[int(l.split()[0])] for l in lp.read_text().splitlines() if l.strip())
        hasil.append((g.name, g, lp, cs))
    return hasil


def baca_publik(nama, skip_nested, skip_lintas, pakai_dedup=True):
    """Kembalikan (data, stat, n_dedup_dibuang).
    data: nama_gambar -> dict(split, path, kotak=[(kelas_id, xc, yc, w, h, source)], buang=[(kelas_id, xc, yc, w, h, source, alasan)])."""
    gm = {r["image"]: r for r in csv.DictReader(open(PUBLIK / nama / "manifest_gambar.csv", encoding="utf-8"))
          if r["status"] == "kandidat"}
    n_dedup = 0
    dd = PUBLIK / nama / "dedup.csv"
    if pakai_dedup and dd.exists():
        simpan = {r["image"] for r in csv.DictReader(open(dd, encoding="utf-8")) if r["simpan"] == "1"}
        n_dedup = sum(1 for k in gm if k not in simpan)
        gm = {k: v for k, v in gm.items() if k in simpan}
    per = defaultdict(list)
    for r in csv.DictReader(open(PUBLIK / nama / "manifest_kotak.csv", encoding="utf-8")):
        if r["image"] in gm:
            per[r["image"]].append(r)
    hasil, stat = {}, Counter()

    def bx(r):
        return tuple(float(r[z]) for z in ("xc", "yc", "w", "h"))

    for im, g in gm.items():
        asli = [(KELAS_KOTAK.index(r["kelas"]), bx(r)) for r in per[im] if r["source"] == "asli"]
        aktif = [True] * len(asli)
        kotak, buang = [], []
        for r in per[im]:
            if r["source"] != "coco_fill":
                continue
            cid, b = KELAS_KOTAK.index(r["kelas"]), bx(r)
            if skip_lintas and any(ac != cid and iou_ioa(b, ab)[0] > skip_lintas for ac, ab in asli):
                buang.append((cid, *b, "coco_fill", "coco_lintas_kelas"))
                stat["coco_lintas_kelas"] += 1
                continue
            if cid == ID_POT and skip_nested:
                nest = [k for k, (ac, ab) in enumerate(asli) if ac == ID_POT and aktif[k] and iou_ioa(b, ab)[1] >= skip_nested]
                if len(nest) >= 2:
                    buang.append((cid, *b, "coco_fill", "coco_pot_menggabung_2_objek"))
                    stat["coco_pot_menggabung_2_objek"] += 1
                elif len(nest) == 1:
                    k = nest[0]
                    if b[2] * b[3] > asli[k][1][2] * asli[k][1][3]:  # COCO lebih besar: pot + tanaman, ganti kotak pot saja
                        aktif[k] = False
                        buang.append((cid, *asli[k][1], "asli", "asli_pot_diganti_coco"))
                        stat["asli_pot_diganti_coco"] += 1
                        kotak.append((cid, *b, "coco_fill"))
                    else:
                        buang.append((cid, *b, "coco_fill", "coco_pot_lebih_kecil"))
                        stat["coco_pot_lebih_kecil"] += 1
                else:
                    kotak.append((cid, *b, "coco_fill"))
                continue
            if skip_nested and float(r["ioa_dengan_asli"] or 0) >= skip_nested:
                buang.append((cid, *b, "coco_fill", "coco_bersarang_sekelas"))
                stat["coco_bersarang_sekelas"] += 1
                continue
            kotak.append((cid, *b, "coco_fill"))
        kotak = [(ac, *ab, "asli") for k, (ac, ab) in enumerate(asli) if aktif[k]] + kotak
        p = PUBLIK / nama / "terpilih" / g["split_asli"] / "images" / im
        hasil[im] = dict(split=g["split_asli"], path=p, kotak=kotak, buang=buang)
    return hasil, stat, n_dedup


def pilih_seimbang(data, cap, rng):
    """Round-robin berbasis kelas: ambil gambar untuk kelas dengan jumlah kotak terpilih paling sedikit."""
    if len(data) <= cap:
        return sorted(data)
    kand = defaultdict(list)
    for im in sorted(data):
        for c in {k[0] for k in data[im]["kotak"]}:
            kand[c].append(im)
    for c in kand:
        rng.shuffle(kand[c])
    ptr, terpilih, set_t, hitung = Counter(), [], set(), Counter()
    while len(terpilih) < cap:
        avail = []
        for c in kand:  # lewati yang sudah terpilih
            while ptr[c] < len(kand[c]) and kand[c][ptr[c]] in set_t:
                ptr[c] += 1
            if ptr[c] < len(kand[c]):
                avail.append(c)
        if not avail:
            break
        c = min(avail, key=lambda c: (hitung[c], c))
        im = kand[c][ptr[c]]
        terpilih.append(im)
        set_t.add(im)
        for k in data[im]["kotak"]:
            hitung[k[0]] += 1
    return terpilih


def tabel(baris, judul):
    print(f"\n{judul}")
    print(f"{'sumber':26s} {'gambar':>6s} " + " ".join(f"{k[:7]:>7s}" for k in KELAS_KOTAK) + f" {'total':>7s}")
    for nama, n, c in baris:
        print(f"{nama:26s} {n:6d} " + " ".join(f"{c[k]:7d}" for k in KELAS_KOTAK) + f" {sum(c.values()):7d}")


def validasi(d, task, names):
    """Validasi dengan Ultralytics YOLODataset: hitung gambar korup, gambar latar kosong, instance per kelas."""
    from ultralytics.cfg import DEFAULT_CFG
    from ultralytics.data.dataset import YOLODataset

    data = {"names": dict(enumerate(names)), "nc": len(names), "channels": 3}
    for split in ("train", "val"):
        folder = d / "images" / split
        n_file = sum(1 for p in folder.iterdir() if p.suffix.lower() in IMG_EXT)
        ds = YOLODataset(img_path=str(folder), imgsz=640, augment=False, hyp=DEFAULT_CFG, rect=False, batch_size=16,
                         stride=32, pad=0.5, single_cls=False, data=data, task=task, cache=False)
        cnt, kosong = Counter(), 0
        for lb in ds.labels:
            cls = lb["cls"].reshape(-1).astype(int)
            kosong += int(cls.size == 0)
            cnt.update(cls.tolist())
        print(f"  [{task}] {split}: {n_file} file gambar, {len(ds.labels)} lolos -> korup {n_file - len(ds.labels)}, "
              f"latar kosong {kosong}, instance {sum(cnt.values())}")
        print("    " + ", ".join(f"{names[i]}={cnt[i]}" for i in range(len(names))))


def sheet_akhir(nama="rod", n=20, seed=20261110, kolom=5, sisi=384):
    """Contact sheet dataset gabung: hijau = kotak asli dipakai, merah = coco_fill dipakai, biru = kotak asli pot yang diganti."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    per = defaultdict(list)
    for r in csv.DictReader(open(OUT_KOTAK / "kotak_akhir.csv", encoding="utf-8")):
        if r["dataset"] == nama:
            per[r["image"]].append(r)
    ada = sorted(k for k, v in per.items() if any(x["source"] == "coco_fill" or x["status"] == "asli_pot_diganti_coco" for x in v))
    pilih = random.Random(seed).sample(ada, min(n, len(ada)))
    baris = (len(pilih) + kolom - 1) // kolom
    kanvas = Image.new("RGB", (kolom * sisi, baris * (sisi + 22)), "white")
    d0 = ImageDraw.Draw(kanvas)
    for i, k in enumerate(pilih):
        im = Image.open(OUT_KOTAK / "images" / "train" / k).convert("RGB")
        W, H = im.size
        t = im.copy()
        t.thumbnail((sisi, sisi))
        sx, sy = t.size[0] / W, t.size[1] / H
        d = ImageDraw.Draw(t)
        for r in per[k]:
            if r["status"] not in ("dipakai", "asli_pot_diganti_coco"):
                continue
            xc, yc, w, h = (float(r[z]) for z in ("xc", "yc", "w", "h"))
            warna = (0, 90, 255) if r["status"] == "asli_pot_diganti_coco" else ((0, 200, 0) if r["source"] == "asli" else (255, 0, 0))
            d.rectangle([(xc - w / 2) * W * sx, (yc - h / 2) * H * sy, (xc + w / 2) * W * sx, (yc + h / 2) * H * sy], outline=warna, width=2)
            d.text(((xc - w / 2) * W * sx + 2, (yc - h / 2) * H * sy + 1), r["kelas"][:10], fill=warna, font=font)
        x, y = (i % kolom) * sisi, (i // kolom) * (sisi + 22)
        kanvas.paste(t, (x, y + 22))
        dp = sum(1 for r in per[k] if r["status"] == "dipakai")
        nc = sum(1 for r in per[k] if r["status"] == "dipakai" and r["source"] == "coco_fill")
        d0.text((x + 4, y + 2), f"{k[:20]} dipakai={dp} coco={nc}", fill="black", font=font)
    out = PUBLIK / nama / "sheet_coco_fill.jpg"
    if out.exists():
        cad = PUBLIK / nama / "sheet_coco_fill_sebelum_ketat.jpg"
        if not cad.exists():
            out.rename(cad)  # simpan versi lama, tidak menimpa
    kanvas.save(out, quality=88)
    print("tulis", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--oversample", type=int, default=4, help="berapa kali kampus train dipakai (1 = tanpa)")
    ap.add_argument("--cap", action="append", default=[], metavar="NAMA=N", help="batas gambar per dataset publik")
    ap.add_argument("--seed", type=int, default=20261110)
    ap.add_argument("--skip-nested", type=float, default=0.0, help="ambang IoA bersarang untuk coco_fill (0 = mati)")
    ap.add_argument("--skip-lintas-iou", type=float, default=0.0, help="buang coco_fill dengan IoU > nilai ini ke kotak asli kelas lain")
    ap.add_argument("--tanpa-dedup", action="store_true", help="abaikan dedup.csv")
    ap.add_argument("--hanya-kotak", action="store_true", help="jangan menyentuh dataset-gabung-seg")
    ap.add_argument("--ganti-kotak", action="store_true", help="hapus data/dataset-gabung-kotak lalu bangun ulang")
    ap.add_argument("--dry-run", action="store_true", help="hanya cetak tabel, tidak menulis apa pun")
    a = ap.parse_args()
    caps = dict(CAP_DEFAULT)
    for c in a.cap:
        k, v = c.split("=")
        caps[k] = int(v)
    rng = random.Random(a.seed)

    kt, kv = baca_kampus("train"), baca_kampus("val")
    pub, terpilih_pub, stat_pool, n_dedup = {}, {}, {}, {}
    for nama in CAP_DEFAULT:
        pub[nama], stat_pool[nama], n_dedup[nama] = baca_publik(nama, a.skip_nested, a.skip_lintas_iou, not a.tanpa_dedup)
        terpilih_pub[nama] = pilih_seimbang(pub[nama], caps[nama], rng)

    camp_box = Counter()
    for _, _, _, cs in kt:
        camp_box.update(cs)
    camp_x = Counter({k: v * a.oversample for k, v in camp_box.items()})
    barisan = [("campus train (x1)", len(kt), camp_box), (f"campus train (x{a.oversample})", len(kt) * a.oversample, camp_x)]
    tot_pub_img, tot_box = 0, Counter(camp_x)
    stat_pilih = {}
    for nama in CAP_DEFAULT:
        asli, coco = Counter(), Counter()
        st = Counter()
        for im in terpilih_pub[nama]:
            for k in pub[nama][im]["kotak"]:
                (asli if k[5] == "asli" else coco)[KELAS_KOTAK[k[0]]] += 1
            for b in pub[nama][im]["buang"]:
                st[b[6]] += 1
        stat_pilih[nama] = st
        barisan.append((f"{nama} terpilih: asli", len(terpilih_pub[nama]), asli))
        barisan.append((f"{nama} terpilih: coco_fill", len(terpilih_pub[nama]), coco))
        tot_pub_img += len(terpilih_pub[nama])
        tot_box.update(asli)
        tot_box.update(coco)
    barisan.append(("TOTAL train", len(kt) * a.oversample + tot_pub_img, tot_box))
    tabel(barisan, "Kotak per kelas per sumber (train)")
    n_train = len(kt) * a.oversample + tot_pub_img
    print(f"\nGambar train: kampus {len(kt) * a.oversample} (x{a.oversample}) + publik {tot_pub_img} = {n_train}; "
          f"porsi kampus {100 * len(kt) * a.oversample / n_train:.1f}%")
    for nama in CAP_DEFAULT:
        print(f"  {nama}: {len(terpilih_pub[nama])} gambar ({100 * len(terpilih_pub[nama]) / n_train:.1f}% dari train, "
              f"{100 * len(terpilih_pub[nama]) / tot_pub_img:.0f}% dari publik); pool {len(pub[nama])}"
              f"{f' (setelah dedup; {n_dedup[nama]} salinan dibuang)' if n_dedup[nama] else ''}")
        print(f"     pengetat, seluruh pool: {dict(stat_pool[nama])}")
        print(f"     pengetat, gambar terpilih: {dict(stat_pilih[nama])}")
    camp_val = Counter()
    for _, _, _, cs in kv:
        camp_val.update(cs)
    tabel([("campus val", len(kv), camp_val)], "Validasi (kampus saja)")
    if a.dry_run:
        return

    if a.ganti_kotak and OUT_KOTAK.exists():
        assert OUT_KOTAK.resolve() == (ROOT / "data" / "dataset-gabung-kotak").resolve()
        n_file = sum(1 for _ in OUT_KOTAK.rglob("*") if _.is_file())
        print(f"\nMenghapus {OUT_KOTAK} ({n_file} file; hanya tautan, sumbernya tidak ikut terhapus) lalu membangun ulang.")
        shutil.rmtree(OUT_KOTAK)
    cek = (OUT_KOTAK,) if a.hanya_kotak else (OUT_KOTAK, OUT_SEG)
    for d in cek:
        if d.exists() and any(d.iterdir()):
            sys.exit(f"{d} sudah ada isinya; tidak ditimpa. Minta izin hapus dulu.")
    # ---- bangun dataset kotak
    sumber, akhir = [], []
    for split, data in (("train", kt), ("val", kv)):
        (OUT_KOTAK / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUT_KOTAK / "labels" / split).mkdir(parents=True, exist_ok=True)
        ulang = a.oversample if split == "train" else 1
        for nm, g, lp, cs in data:
            for r in range(ulang):
                stem = g.stem if r == 0 else f"{g.stem}__r{r}"
                tautkan(g, OUT_KOTAK / "images" / split / (stem + g.suffix))
                dst = OUT_KOTAK / "labels" / split / (stem + ".txt")
                if r == 0:
                    tautkan(lp, dst)
                else:
                    shutil.copy2(lp, dst)
                sumber.append(dict(split=split, image=stem + g.suffix, sumber="campus", asli=nm, ulang=r,
                                   n_asli=sum(cs.values()), n_coco=0))
    for nama in CAP_DEFAULT:
        for im in terpilih_pub[nama]:
            d = pub[nama][im]
            assert not im.startswith(TEST)
            tautkan(d["path"], OUT_KOTAK / "images" / "train" / im)
            with open(OUT_KOTAK / "labels" / "train" / (Path(im).stem + ".txt"), "w", encoding="utf-8") as f:
                for c, xc, yc, w, h, _ in d["kotak"]:
                    f.write(f"{c} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
            for c, xc, yc, w, h, src in d["kotak"]:
                akhir.append(dict(dataset=nama, image=im, kelas=KELAS_KOTAK[c], xc=xc, yc=yc, w=w, h=h, source=src, status="dipakai"))
            for c, xc, yc, w, h, src, alasan in d["buang"]:
                akhir.append(dict(dataset=nama, image=im, kelas=KELAS_KOTAK[c], xc=xc, yc=yc, w=w, h=h, source=src, status=alasan))
            sumber.append(dict(split="train", image=im, sumber=nama, asli=im, ulang=0,
                               n_asli=sum(1 for k in d["kotak"] if k[5] == "asli"),
                               n_coco=sum(1 for k in d["kotak"] if k[5] == "coco_fill")))
    for nm, rows in (("sumber.csv", sumber), ("kotak_akhir.csv", akhir)):
        with open(OUT_KOTAK / nm, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    (OUT_KOTAK / "data.yaml").write_text(
        f"path: {OUT_KOTAK.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {i}: {k}\n" for i, k in enumerate(KELAS_KOTAK)), encoding="utf-8")
    # ---- bangun dataset seg (kampus saja), dilewati kalau --hanya-kotak
    if not a.hanya_kotak:
        sumber_seg = []
        for split in ("train", "val"):
            (OUT_SEG / "images" / split).mkdir(parents=True, exist_ok=True)
            (OUT_SEG / "labels" / split).mkdir(parents=True, exist_ok=True)
            for g in sorted((KAMPUS_SEG / "images" / split).iterdir()):
                if g.suffix.lower() not in IMG_EXT:
                    continue
                assert not g.name.startswith(TEST)
                tautkan(g, OUT_SEG / "images" / split / g.name)
                tautkan(KAMPUS_SEG / "labels" / split / (g.stem + ".txt"), OUT_SEG / "labels" / split / (g.stem + ".txt"))
                sumber_seg.append(dict(split=split, image=g.name, sumber="campus"))
        with open(OUT_SEG / "sumber.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(sumber_seg[0]))
            w.writeheader()
            w.writerows(sumber_seg)
        (OUT_SEG / "data.yaml").write_text(
            f"path: {OUT_SEG.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n"
            + "".join(f"  {i}: {k}\n" for i, k in enumerate(KELAS_SEG)), encoding="utf-8")
    print("\nDataset ditulis. Validasi Ultralytics YOLODataset:")
    validasi(OUT_KOTAK, "detect", KELAS_KOTAK)
    if not a.hanya_kotak:
        validasi(OUT_SEG, "segment", KELAS_SEG)
    sheet_akhir("rod")


if __name__ == "__main__":
    main()
