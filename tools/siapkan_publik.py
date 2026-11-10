"""siapkan_publik.py - unduh, verifikasi, petakan ulang dataset publik JalanKu.

Dijalankan dari root repo. Semua keluaran ada di data/publik/<nama>/ (tidak masuk git).

Subperintah:
  unduh-roboflow <nama>     unduh export YOLOv8 dari Roboflow (resume otomatis), lalu unzip ke raw/
                            nama: ood | unstructured | trotoar   (rod dan lemnix dari Kaggle: kaggle datasets download)
  verifikasi <nama>         hitung gambar per split, kotak/mask per kelas asli -> verifikasi.json
  konversi <nama>           remap ke kelas JalanKu (kotak) + resize 640 sisi panjang -> <nama>/jalanku/, manifest.csv
  konversi-lemnix           mask VOC lemnix -> polygon YOLO seg (jalur_jalan=0) + resize 640 -> lemnix/jalanku/
  terpilih <nama>           filter kotak kecil + pilih gambar (pool) + isi label COCO (yolo11x.pt, conf 0.5) -> terpilih/
  dedup <nama>              buang gambar hasil augmentasi/near-duplicate (embedding + verifikasi ORB) -> dedup.csv
  sheet-dedup <nama>        contact sheet 12 grup duplikat (hijau = dipertahankan)
  sheet-coco <nama>         contact sheet kotak asli (hijau) vs coco_fill (merah)
  statistik <nama>          gambar/kotak per kelas JalanKu setelah remap + persentase kotak terlalu kecil
  sheet-kotak <nama> [--jalanku]     contact sheet ~20 gambar acak dengan kotak (kelas asli, atau kelas JalanKu)
  sheet-crop <nama> <id_kelas>       30 potongan acak satu kelas asli (cek: batang saja atau seluruh pohon)
  sheet-lemnix              contact sheet 20 gambar lemnix acak dengan overlay mask (seed tetap)

Contoh:
  python tools/siapkan_publik.py unduh-roboflow ood
  python tools/siapkan_publik.py verifikasi ood

Kredensial:
  ROBOFLOW_API_KEY dibaca dari .env di root repo. Key TIDAK PERNAH dicetak
  (pesan error disaring lewat _bersih()).
"""
import argparse
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PUBLIK = ROOT / "data" / "publik"

ROBOFLOW = {
    # nama: (workspace, project, versi)
    "ood": ("fpn", "ood-pbnro", 1),
    "unstructured": ("mtechcv", "unstructured-road-obstacle-detection", 11),
    "trotoar": ("jeka-workspace", "dataset-labelled-sqkiz", 1),
}


def _key():
    for baris in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if baris.startswith("ROBOFLOW_API_KEY="):
            return baris.split("=", 1)[1].strip().strip("\"'")
    sys.exit("ROBOFLOW_API_KEY tidak ada di .env")


def _bersih(teks):
    return str(teks).replace(_key(), "***")


def _get_json(url, params, tries=8):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            print(f"  percobaan {i + 1}/{tries} gagal: {_bersih(type(e).__name__)}", flush=True)
            time.sleep(5 * (i + 1))
    sys.exit("gagal ambil info export")


def unduh_roboflow(nama):
    ws, pj, ver = ROBOFLOW[nama]
    raw = PUBLIK / nama / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    info = _get_json(f"https://api.roboflow.com/{ws}/{pj}/{ver}/yolov8", {"api_key": _key()})
    link = info["export"]["link"]
    zp = raw / "export.zip"
    for i in range(200):
        mulai = zp.stat().st_size if zp.exists() else 0
        try:
            with requests.get(link, stream=True, timeout=120,
                              headers={"Range": f"bytes={mulai}-"} if mulai else {}) as r:
                if r.status_code == 416:  # sudah lengkap
                    break
                r.raise_for_status()
                total = mulai + int(r.headers.get("Content-Length", 0))
                with open(zp, "ab" if mulai and r.status_code == 206 else "wb") as f:
                    for ch in r.iter_content(1 << 20):
                        f.write(ch)
                if zp.stat().st_size >= total:
                    break
        except Exception as e:  # noqa: BLE001
            print(f"  putus ({_bersih(type(e).__name__)}), lanjut dari {zp.stat().st_size / 1e6:.0f} MB", flush=True)
            time.sleep(5)
    with zipfile.ZipFile(zp) as z:
        z.extractall(raw)
    print(f"{nama}: selesai, {sum(1 for _ in raw.rglob('*'))} entri di {raw}")


RAW_ROOT = {
    "rod": "rod/raw/ROD-Dataset/dataset",
    "ood": "ood/raw",
    "unstructured": "unstructured/raw",
    "trotoar": "trotoar/raw",
}
SPLIT_DIR = {"train": "train", "valid": "valid", "test": "test"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def baca_nama_kelas(root):
    import yaml
    nama = yaml.safe_load((root / "data.yaml").read_text(encoding="utf-8"))["names"]
    if isinstance(nama, dict):
        nama = [nama[k] for k in sorted(nama)]
    return list(nama)


def baca_label(path):
    """Baca label YOLO (kotak 5 kolom, atau polygon). Kembalikan [(id, xc, yc, w, h)] ternormalisasi."""
    hasil = []
    if not path.exists():
        return hasil
    for baris in path.read_text(encoding="utf-8").splitlines():
        t = baris.split()
        if len(t) < 5:
            continue
        c = int(float(t[0]))
        v = [float(x) for x in t[1:]]
        if len(t) == 5:
            hasil.append((c, *v))
        else:  # polygon -> kotak
            xs, ys = v[0::2], v[1::2]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            hasil.append((c, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0))
    return hasil


def verifikasi(nama):
    from collections import Counter

    root = PUBLIK / RAW_ROOT[nama]
    kelas = baca_nama_kelas(root)
    rep = {"nama": nama, "kelas_asli": kelas, "split": {}}
    for sp in SPLIT_DIR:
        d = root / SPLIT_DIR[sp] / "images"
        if not d.exists():
            continue
        gambar = sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXT)
        kotak, gbr_kelas, tanpa_label, satu_objek, tanpa_pasangan = Counter(), Counter(), 0, 0, 0
        for g in gambar:
            lp = root / SPLIT_DIR[sp] / "labels" / (g.stem + ".txt")
            if not lp.exists():
                tanpa_pasangan += 1
            lab = baca_label(lp)
            if not lab:
                tanpa_label += 1
            if len(lab) == 1:
                satu_objek += 1
            for c in {l[0] for l in lab}:
                gbr_kelas[c] += 1
            for l in lab:
                kotak[l[0]] += 1
        rep["split"][sp] = {
            "gambar": len(gambar), "tanpa_file_label": tanpa_pasangan, "tanpa_objek": tanpa_label,
            "tepat_1_objek": satu_objek,
            "kotak": {f"{c}:{kelas[c] if c < len(kelas) else '?'}": n for c, n in sorted(kotak.items())},
            "gambar_per_kelas": {f"{c}:{kelas[c] if c < len(kelas) else '?'}": n for c, n in sorted(gbr_kelas.items())},
        }
    (PUBLIK / nama / "verifikasi.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"== {nama}: {len(kelas)} kelas")
    for sp, r in rep["split"].items():
        print(f"  {sp}: {r['gambar']} gambar, tanpa objek {r['tanpa_objek']}, tepat 1 objek {r['tepat_1_objek']}, "
              f"tanpa file label {r['tanpa_file_label']}, total kotak {sum(r['kotak'].values())}")
    tot = Counter()
    for r in rep["split"].values():
        tot.update(r["kotak"])
    print("  kotak per kelas asli (semua split):", dict(tot))
    return rep


def _semua_gambar(root):
    hasil = []
    for sp in SPLIT_DIR:
        d = root / SPLIT_DIR[sp] / "images"
        if d.exists():
            hasil += [(sp, p) for p in sorted(d.iterdir()) if p.suffix.lower() in IMG_EXT]
    return hasil


WARNA = [(230, 25, 75), (60, 180, 75), (255, 165, 0), (0, 130, 200), (145, 30, 180), (70, 240, 240),
         (240, 50, 230), (210, 245, 60), (0, 128, 128), (170, 110, 40), (128, 0, 0), (0, 0, 128)]


def sheet_kotak(nama, jalanku=False, n=20, seed=20261109, kolom=5, sisi=384):
    import random

    from PIL import Image, ImageDraw

    if jalanku:
        root, kelas = PUBLIK / nama / "jalanku", KELAS_KOTAK
    else:
        root = PUBLIK / RAW_ROOT[nama]
        kelas = baca_nama_kelas(root)
    semua = _semua_gambar(root)
    pilih = random.Random(seed).sample(semua, min(n, len(semua)))
    baris = (len(pilih) + kolom - 1) // kolom
    kanvas = Image.new("RGB", (kolom * sisi, baris * (sisi + 22)), "white")
    d0 = ImageDraw.Draw(kanvas)
    for i, (sp, g) in enumerate(pilih):
        im = Image.open(g).convert("RGB")
        W, H = im.size
        t = im.copy()
        t.thumbnail((sisi, sisi))
        sx, sy = t.size[0] / W, t.size[1] / H
        d = ImageDraw.Draw(t)
        lab = baca_label(root / SPLIT_DIR[sp] / "labels" / (g.stem + ".txt"))
        for c, xc, yc, w, h in lab:
            x0, y0, x1, y1 = (xc - w / 2) * W * sx, (yc - h / 2) * H * sy, (xc + w / 2) * W * sx, (yc + h / 2) * H * sy
            warna = WARNA[c % len(WARNA)]
            d.rectangle([x0, y0, x1, y1], outline=warna, width=2)
            d.text((x0 + 2, y0 + 1), (kelas[c] if c < len(kelas) else str(c))[:14], fill=warna, font=_font())
        x, y = (i % kolom) * sisi, (i // kolom) * (sisi + 22)
        kanvas.paste(t, (x, y + 22))
        d0.text((x + 4, y + 2), f"{sp} {g.stem[:22]} n={len(lab)}", fill="black", font=_font())
    out = PUBLIK / nama / ("sheet_jalanku_acak.jpg" if jalanku else "sheet_asli_acak.jpg")
    kanvas.save(out, quality=88)
    print("tulis", out)


def sheet_crop(nama, id_kelas, n=30, seed=20261109, kolom=6, sisi=256):
    import random

    from PIL import Image, ImageDraw

    root = PUBLIK / RAW_ROOT[nama]
    kelas = baca_nama_kelas(root)
    kand = []
    for sp, g in _semua_gambar(root):
        for l in baca_label(root / SPLIT_DIR[sp] / "labels" / (g.stem + ".txt")):
            if l[0] == id_kelas:
                kand.append((g, l))
    pilih = random.Random(seed).sample(kand, min(n, len(kand)))
    baris = (len(pilih) + kolom - 1) // kolom
    kanvas = Image.new("RGB", (kolom * sisi, baris * sisi), "white")
    for i, (g, (c, xc, yc, w, h)) in enumerate(pilih):
        im = Image.open(g).convert("RGB")
        W, H = im.size
        x0, y0, x1, y1 = (xc - w / 2) * W, (yc - h / 2) * H, (xc + w / 2) * W, (yc + h / 2) * H
        mx, my = (x1 - x0) * 0.35, (y1 - y0) * 0.35
        cx0, cy0, cx1, cy1 = max(0, x0 - mx), max(0, y0 - my), min(W, x1 + mx), min(H, y1 + my)
        crop = im.crop((int(cx0), int(cy0), int(cx1), int(cy1)))
        sc = min(sisi / crop.size[0], sisi / crop.size[1])
        crop = crop.resize((max(1, int(crop.size[0] * sc)), max(1, int(crop.size[1] * sc))))
        d = ImageDraw.Draw(crop)
        d.rectangle([(x0 - cx0) * sc, (y0 - cy0) * sc, (x1 - cx0) * sc, (y1 - cy0) * sc], outline=(255, 0, 0), width=2)
        kanvas.paste(crop, ((i % kolom) * sisi, (i // kolom) * sisi))
    out = PUBLIK / nama / f"sheet_crop_{id_kelas}_{kelas[id_kelas].replace(' ', '_')}.jpg"
    kanvas.save(out, quality=88)
    print("tulis", out, f"({len(kand)} kotak tersedia)")


KELAS_KOTAK = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"]


# ---------------------------------------------------------------- pemetaan -> kelas JalanKu (kotak)
# Sumber: docs/survei-dataset.md + docs/kelas.md v1.5. Kelas yang tidak ada di tabel = dibuang.
# Nilai: id JalanKu (0 pilar,1 pohon,2 tepian,3 orang,4 tanaman_pot,5 kursi,6 kendaraan,7 tangga)
# atau "POHON_PENUH" = kotak seluruh pohon (bentrok aturan batang saja) -> gambar dibuang.
PETA_NAMA = {
    "rod": {  # ROD 'Road' (jalan_kendaraan) sengaja TIDAK dipetakan: bukan kelas kotak
        "Bike": 6, "Car": 6, "Motorcycle": 6, "Truck": 6, "Bus": 6, "Person": 3, "Stairs": 7,
        "Electrical Pole": 0, "Bench": 5, "Chair": 5, "Plant Pot": 4, "Tree": "POHON_PENUH",
    },
    "ood": {
        "curb": 2, "pole": 0, "street_light": 0, "spherical_roadblock": 0, "warning_column": 0,
        "person": 3, "car": 6, "motorcycle": 6, "bicycle": 6, "bus": 6, "truck": 6,
        "bench": 5, "stairs": 7, "tree": "POHON_PENUH",
    },
    "unstructured": {
        "tree": 1, "vehicle": 6, "two-wheeler": 6, "pole": 0, "stairs": 7,
    },
}
# Lingkungan Trotoar: nama kelas rusak, dipetakan lewat ID (hanya 0-11 dan 21 dipakai; 12-20 diabaikan)
PETA_ID_TROTOAR = {1: 6, 2: 3, 3: 1, 4: 0, 5: 4, 6: 0, 7: 5, 9: 6, 21: 0}
SURVEI_TROTOAR = {0: 539, 1: 2843, 2: 3835, 3: 2445, 4: 187, 5: 123, 6: 2464, 7: 938, 8: 441,
                  9: 3765, 10: 48, 11: 44, 21: 1770}  # jumlah kotak per ID menurut survei
SISI_MAKS = 640


def _peta_kelas(nama, kelas):
    """Kembalikan dict id_asli -> id JalanKu / 'POHON_PENUH' / None (dibuang)."""
    if nama == "trotoar":
        return {i: PETA_ID_TROTOAR.get(i) for i in range(len(kelas))}
    peta = PETA_NAMA[nama]
    return {i: peta.get(n) for i, n in enumerate(kelas)}


def _proses_gambar(args):
    """Worker: baca gambar+label asli, petakan, resize, tulis. Hasil dipakai untuk manifest."""
    from PIL import Image

    nama, sp, g, root, out, peta, mode_pohon = args
    root, out, g = Path(root), Path(out), Path(g)
    lab = baca_label(root / SPLIT_DIR[sp] / "labels" / (g.stem + ".txt"))
    baru = [(peta[c], xc, yc, w, h) for c, xc, yc, w, h in lab if peta.get(c) is not None]
    punya_penuh = any(b[0] == "POHON_PENUH" for b in baru)
    im = Image.open(g)
    W, H = im.size
    try:
        orient = im.getexif().get(274, 1)
    except Exception:  # noqa: BLE001
        orient = 1
    baris = dict(dataset=nama, split_asli=sp, file=g.name, w=W, h=H, orient=orient,
                 n_asli=len(lab), n_jalanku=0, status="")
    if not lab:
        baris["status"] = "kosong_asli"
        return baris
    if punya_penuh and mode_pohon == "buang_gambar":
        baris["status"] = "dibuang_pohon_penuh"
        return baris
    if mode_pohon == "pakai":  # hanya kalau sudah diputuskan: kotak pohon penuh dianggap pohon
        baru = [(1 if b[0] == "POHON_PENUH" else b[0], *b[1:]) for b in baru]
    baru = [b for b in baru if b[0] != "POHON_PENUH"]
    if not baru:
        baris["status"] = "kosong_setelah_remap"
        return baris
    im = im.convert("RGB")
    if max(W, H) > SISI_MAKS:  # hanya diperkecil, tidak pernah diperbesar
        sc = SISI_MAKS / max(W, H)
        im = im.resize((max(1, round(W * sc)), max(1, round(H * sc))), Image.LANCZOS)
    (out / sp / "images").mkdir(parents=True, exist_ok=True)
    (out / sp / "labels").mkdir(parents=True, exist_ok=True)
    stem = f"{nama}_{g.stem}"
    im.save(out / sp / "images" / f"{stem}.jpg", quality=92)  # tanpa EXIF
    with open(out / sp / "labels" / f"{stem}.txt", "w", encoding="utf-8") as f:
        for c, xc, yc, w, h in baru:
            x0, y0, x1, y1 = max(0, xc - w / 2), max(0, yc - h / 2), min(1, xc + w / 2), min(1, yc + h / 2)
            if x1 - x0 <= 0 or y1 - y0 <= 0:
                continue
            f.write(f"{c} {(x0 + x1) / 2:.6f} {(y0 + y1) / 2:.6f} {x1 - x0:.6f} {y1 - y0:.6f}\n")
            baris["n_jalanku"] += 1
    baris["status"] = "ok"
    return baris


def konversi(nama, mode_pohon="buang_gambar"):
    import csv
    from collections import Counter
    from concurrent.futures import ProcessPoolExecutor

    root = PUBLIK / RAW_ROOT[nama]
    out = PUBLIK / nama / "jalanku"
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} sudah ada isinya; hapus manual (atau minta izin) sebelum konversi ulang")
    kelas = baca_nama_kelas(root)
    peta = _peta_kelas(nama, kelas)
    tugas = [(nama, sp, str(g), str(root), str(out), peta, mode_pohon) for sp, g in _semua_gambar(root)]
    with ProcessPoolExecutor() as ex:
        hasil = list(ex.map(_proses_gambar, tugas, chunksize=64))
    with open(PUBLIK / nama / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(hasil[0]))
        w.writeheader()
        w.writerows(hasil)
    # hitung ulang kotak JalanKu dari label yang benar-benar ditulis
    per_kelas, per_split = Counter(), Counter()
    for sp in SPLIT_DIR:
        d = out / sp / "labels"
        if d.exists():
            for lp in d.glob("*.txt"):
                for l in baca_label(lp):
                    per_kelas[KELAS_KOTAK[l[0]]] += 1
                    per_split[(sp, KELAS_KOTAK[l[0]])] += 1
    st = Counter((r["split_asli"], r["status"]) for r in hasil)
    print(f"== {nama}: status per split asli")
    for k, v in sorted(st.items()):
        print("  ", k, v)
    print("  kotak JalanKu:", {k: per_kelas[k] for k in KELAS_KOTAK})
    print("  EXIF orientasi != 1:", sum(1 for r in hasil if r["orient"] not in (0, 1)))
    if nama == "trotoar":
        tot = Counter()
        for sp in SPLIT_DIR:
            d = root / sp / "labels"
            if d.exists():
                for lp in d.glob("*.txt"):
                    tot.update(l[0] for l in baca_label(lp))
        for i, n in SURVEI_TROTOAR.items():
            if tot[i] != n:
                print(f"  BEDA SURVEI: ID {i} survei {n} vs unduhan {tot[i]}")
        print("  cek ID Trotoar vs survei selesai")


def konversi_lemnix(eps=0.002, luas_min=0.0005):
    """Mask VOC lemnix (nilai 1) -> polygon YOLO seg kelas 0 (jalur_jalan), gambar 640 sisi panjang.

    PERINGATAN: mask 1 hanya jalur guiding block (ubin kuning), BUKAN seluruh trotoar. Lihat docs/dataset-publik.md.
    """
    import csv

    import cv2
    import numpy as np
    from PIL import Image

    raw = PUBLIK / "lemnix" / "raw"
    out = PUBLIK / "lemnix" / "jalanku"
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} sudah ada isinya; hapus manual (atau minta izin) sebelum konversi ulang")
    split = {}
    for sp, f in (("train", "train.txt"), ("valid", "val.txt")):
        for k in (raw / "ImageSets" / "Segmentation" / f).read_text().split():
            split[k] = sp
    baris = []
    for k, sp in sorted(split.items()):
        im = Image.open(raw / "JPEGImages" / f"{k}.jpg").convert("RGB")
        m = (np.array(Image.open(raw / "SegmentationClass" / f"{k}.png")) == 1).astype(np.uint8)
        W, H = im.size
        sc = min(1.0, SISI_MAKS / max(W, H))
        nw, nh = max(1, round(W * sc)), max(1, round(H * sc))
        im = im.resize((nw, nh), Image.LANCZOS)
        m = cv2.resize(m, (nw, nh), interpolation=cv2.INTER_NEAREST)
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        baris_label = []
        for c in cs:
            if cv2.contourArea(c) < luas_min * nw * nh:
                continue
            c = cv2.approxPolyDP(c, eps * cv2.arcLength(c, True), True).reshape(-1, 2)
            if len(c) < 3:
                continue
            baris_label.append("0 " + " ".join(f"{x / nw:.5f} {y / nh:.5f}" for x, y in c))
        (out / sp / "images").mkdir(parents=True, exist_ok=True)
        (out / sp / "labels").mkdir(parents=True, exist_ok=True)
        im.save(out / sp / "images" / f"lemnix_{k}.jpg", quality=92)
        (out / sp / "labels" / f"lemnix_{k}.txt").write_text("\n".join(baris_label), encoding="utf-8")
        baris.append(dict(dataset="lemnix", split_asli=sp, file=f"{k}.jpg", w=W, h=H, n_polygon=len(baris_label)))
    with open(PUBLIK / "lemnix" / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(baris[0]))
        w.writeheader()
        w.writerows(baris)
    print("lemnix:", len(baris), "gambar,", sum(b["n_polygon"] for b in baris), "polygon;",
          "tanpa polygon:", sum(1 for b in baris if b["n_polygon"] == 0))


def statistik(nama):
    """Gambar dan kotak per kelas JalanKu + kotak kecil (aturan kelas.md, di gambar 640)."""
    from collections import Counter

    from PIL import Image

    out = PUBLIK / nama / "jalanku"
    kotak, gambar, kecil = Counter(), Counter(), Counter()
    n_img = 0
    for sp in SPLIT_DIR:
        d = out / sp / "labels"
        if not d.exists():
            continue
        for lp in d.glob("*.txt"):
            n_img += 1
            im = Image.open(out / sp / "images" / (lp.stem + ".jpg"))
            W, H = im.size
            lab = baca_label(lp)
            for c in {l[0] for l in lab}:
                gambar[KELAS_KOTAK[c]] += 1
            for c, xc, yc, w, h in lab:
                k = KELAS_KOTAK[c]
                kotak[k] += 1
                pj, pd = max(w * W, h * H), min(w * W, h * H)
                tipis = k in ("pilar", "pohon", "tepian")
                if (pj < 32 or pd < 8) if tipis else pd < 32:
                    kecil[k] += 1
    print(f"== {nama}: {n_img} gambar berlabel")
    print("  {:12s} {:>7s} {:>7s} {:>12s}".format("kelas", "gambar", "kotak", "terlalu kecil"))
    for k in KELAS_KOTAK:
        if kotak[k]:
            print("  {:12s} {:7d} {:7d} {:7d} ({:.0f}%)".format(k, gambar[k], kotak[k], kecil[k], 100 * kecil[k] / kotak[k]))


# ---------------------------------------------------------------- tahap terpilih (keputusan P1)
# Filter kotak kecil (kelas.md, gambar 640) + pemilihan gambar + isi label dari COCO (yolo11x.pt).
# Keluaran: <nama>/terpilih/{train,valid,test}/{images,labels} (hard link gambar), manifest_kotak.csv, manifest_gambar.csv
COCO_KE_JALANKU = {0: 3, 1: 6, 2: 6, 3: 6, 5: 6, 7: 6, 13: 5, 56: 5, 58: 4}
# 0 person->orang; bicycle/car/motorcycle/bus/truck->kendaraan; bench/chair->kursi; potted plant->tanaman_pot
ID_KELAS = {n: i for i, n in enumerate(KELAS_KOTAK)}
POOL = {  # aturan pemilihan gambar (dihitung dari label asli yang lolos filter, sebelum isi COCO)
    "trotoar": ("semua", set()),
    "unstructured": ("semua", set()),
    "ood": ("bukan_hanya", {ID_KELAS["orang"], ID_KELAS["kendaraan"]}),  # buang gambar yang hanya orang/kendaraan
    "rod": ("harus_punya", {ID_KELAS["tangga"], ID_KELAS["tanaman_pot"], ID_KELAS["kursi"]}),
}


def kotak_kecil(c, w_px, h_px):
    """Aturan kelas.md di gambar 640: umum sisi pendek < 32; tipis (pilar/pohon/tepian) panjang < 32 atau pendek < 8."""
    pj, pd = max(w_px, h_px), min(w_px, h_px)
    if KELAS_KOTAK[c] in ("pilar", "pohon", "tepian"):
        return pj < 32 or pd < 8
    return pd < 32


def _iou_ioa(a, b):
    """a, b = (xc, yc, w, h) ternormalisasi. Kembalikan (IoU, interseksi / luas kotak terkecil)."""
    ax0, ay0, ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx0, by0, bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw, ih = max(0.0, min(ax1, bx1) - max(ax0, bx0)), max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    ua, ub = a[2] * a[3], b[2] * b[3]
    return inter / (ua + ub - inter + 1e-12), inter / (min(ua, ub) + 1e-12)


def terpilih(nama, conf=0.5, model_path="yolo11x.pt"):
    import csv
    from collections import Counter

    from PIL import Image
    from ultralytics import YOLO

    src = PUBLIK / nama / "jalanku"
    out = PUBLIK / nama / "terpilih"
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} sudah ada isinya; hapus manual (atau minta izin) sebelum jalan ulang")
    mode, kelas_pool = POOL[nama]
    gambar_rows, kandidat = [], []
    for sp in SPLIT_DIR:
        d = src / sp / "images"
        if not d.exists():
            continue
        for g in sorted(d.glob("*.jpg")):
            W, H = Image.open(g).size
            asli = baca_label(src / sp / "labels" / (g.stem + ".txt"))
            kept = [l for l in asli if not kotak_kecil(l[0], l[3] * W, l[4] * H)]
            kc = {l[0] for l in kept}
            status = "kandidat"
            if not kept:
                status = "kosong_setelah_filter_kecil"
            elif mode == "bukan_hanya" and kc <= kelas_pool:
                status = "di_luar_pool"
            elif mode == "harus_punya" and not (kc & kelas_pool):
                status = "di_luar_pool"
            row = dict(dataset=nama, split_asli=sp, image=g.name, w=W, h=H, n_asli=len(asli), n_lolos_filter=len(kept),
                       n_coco_fill=0, status=status)
            gambar_rows.append(row)
            if status == "kandidat":
                kandidat.append((row, sp, g, asli, kept, W, H))
    print(f"{nama}: {len(gambar_rows)} gambar -> kandidat {len(kandidat)}", flush=True)
    import torch

    torch.backends.cudnn.benchmark = False  # bentuk input tetap 640x640 (rect=False): hindari OOM autotune cuDNN
    model = YOLO(model_path)
    cls = list(COCO_KE_JALANKU)
    kotak_rows, tambah, nested = [], Counter(), Counter()
    paths = [str(k[2]) for k in kandidat]
    def prediksi():  # per chunk 8 gambar (stream=True dengan list panjang bikin OOM di GPU 8 GB ini)
        for i in range(0, len(paths), 8):
            yield from model.predict(paths[i:i + 8], batch=8, conf=conf, classes=cls, imgsz=640, rect=False,
                                     verbose=False)

    for k, res in zip(kandidat, prediksi()):
        row, sp, g, asli, kept, W, H = k
        baru = []
        for (x0, y0, x1, y1), c, cf in zip(res.boxes.xyxyn.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
            jc = COCO_KE_JALANKU[int(c)]
            b = ((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)
            if kotak_kecil(jc, b[2] * W, b[3] * H):
                continue
            iou_max, ioa_max = 0.0, 0.0
            for l in asli:  # dibandingkan dengan label asli (sebelum filter kecil), kelas JalanKu yang sama
                if l[0] == jc:
                    i, a = _iou_ioa(b, l[1:])
                    iou_max, ioa_max = max(iou_max, i), max(ioa_max, a)
            if iou_max > 0.5:
                continue
            baru.append((jc, *b, cf, ioa_max))
        for l in kept:
            kotak_rows.append(dict(dataset=nama, image=g.name, kelas=KELAS_KOTAK[l[0]], xc=l[1], yc=l[2], w=l[3], h=l[4],
                                   source="asli", conf="", ioa_dengan_asli=""))
        for jc, xc, yc, w, h, cf, ioa in baru:
            kotak_rows.append(dict(dataset=nama, image=g.name, kelas=KELAS_KOTAK[jc], xc=xc, yc=yc, w=w, h=h,
                                   source="coco_fill", conf=round(cf, 3), ioa_dengan_asli=round(ioa, 3)))
            tambah[KELAS_KOTAK[jc]] += 1
            if ioa >= 0.8:
                nested[KELAS_KOTAK[jc]] += 1
        row["n_coco_fill"] = len(baru)
        (out / sp / "images").mkdir(parents=True, exist_ok=True)
        (out / sp / "labels").mkdir(parents=True, exist_ok=True)
        tujuan = out / sp / "images" / g.name
        try:
            os.link(g, tujuan)
        except OSError:
            shutil.copy2(g, tujuan)
        with open(out / sp / "labels" / (g.stem + ".txt"), "w", encoding="utf-8") as f:
            for l in kept:
                f.write(f"{l[0]} {l[1]:.6f} {l[2]:.6f} {l[3]:.6f} {l[4]:.6f}\n")
            for jc, xc, yc, w, h, cf, ioa in baru:
                f.write(f"{jc} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
    for nm, rows in (("manifest_gambar.csv", gambar_rows), ("manifest_kotak.csv", kotak_rows)):
        with open(PUBLIK / nama / nm, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    st = Counter(r["status"] for r in gambar_rows)
    print(f"== {nama}: status gambar {dict(st)}")
    print("  kotak asli lolos filter:", dict(Counter(r["kelas"] for r in kotak_rows if r["source"] == "asli")))
    print("  kotak coco_fill ditambah:", {k: tambah[k] for k in KELAS_KOTAK if tambah[k]}, "total", sum(tambah.values()))
    print("  (diagnostik) coco_fill yang bersarang >=80% di kotak asli sekelas:", dict(nested))
    print("  gambar yang dapat >=1 kotak coco_fill:", sum(1 for r in gambar_rows if r["n_coco_fill"]))


def sheet_coco(nama, n=20, seed=20261110, kolom=5, sisi=384):
    """Contact sheet: kotak asli (hijau) vs kotak coco_fill (merah) pada gambar yang mendapat tambahan."""
    import csv
    import random
    from collections import defaultdict

    from PIL import Image, ImageDraw

    per = defaultdict(list)
    for r in csv.DictReader(open(PUBLIK / nama / "manifest_kotak.csv", encoding="utf-8")):
        per[r["image"]].append(r)
    ada = sorted(k for k, v in per.items() if any(x["source"] == "coco_fill" for x in v))
    gm = {r["image"]: r["split_asli"] for r in csv.DictReader(open(PUBLIK / nama / "manifest_gambar.csv", encoding="utf-8"))}
    pilih = random.Random(seed).sample(ada, min(n, len(ada)))
    baris = (len(pilih) + kolom - 1) // kolom
    kanvas = Image.new("RGB", (kolom * sisi, baris * (sisi + 22)), "white")
    d0 = ImageDraw.Draw(kanvas)
    for i, k in enumerate(pilih):
        im = Image.open(PUBLIK / nama / "terpilih" / gm[k] / "images" / k).convert("RGB")
        W, H = im.size
        t = im.copy()
        t.thumbnail((sisi, sisi))
        sx, sy = t.size[0] / W, t.size[1] / H
        d = ImageDraw.Draw(t)
        for r in per[k]:
            xc, yc, w, h = (float(r[z]) for z in ("xc", "yc", "w", "h"))
            warna = (0, 200, 0) if r["source"] == "asli" else (255, 0, 0)
            d.rectangle([(xc - w / 2) * W * sx, (yc - h / 2) * H * sy, (xc + w / 2) * W * sx, (yc + h / 2) * H * sy],
                        outline=warna, width=2)
            d.text(((xc - w / 2) * W * sx + 2, (yc - h / 2) * H * sy + 1), r["kelas"][:10], fill=warna, font=_font())
        x, y = (i % kolom) * sisi, (i // kolom) * (sisi + 22)
        kanvas.paste(t, (x, y + 22))
        na = sum(1 for r in per[k] if r["source"] == "asli")
        d0.text((x + 4, y + 2), f"{k[:20]} asli={na} coco={len(per[k]) - na}", fill="black", font=_font())
    out = PUBLIK / nama / "sheet_coco_fill.jpg"
    kanvas.save(out, quality=88)
    print("tulis", out)


# ---------------------------------------------------------------- dedup gambar hasil augmentasi (keputusan P2)
# Kandidat pasangan = kemiripan embedding ResNet50 (grayscale, + versi flip) >= SIM_KANDIDAT.
# Pasangan salinan: inlier ORB+RANSAC >= INLIER_A, atau embedding >= SIM_B dengan himpunan kelas label asli identik.
# Greedy bintang mulai dari gambar paling bersih (piksel hitam sedikit, bukan grayscale).
SIM_KANDIDAT = 0.82
INLIER_A = 30  # aturan A: inlier ORB+RANSAC
SIM_B = 0.85  # aturan B: embedding + label asli identik


def _fitur_orb(path):
    import cv2
    import numpy as np

    g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    hitam = (g <= 10).astype(np.uint8)
    boleh = (cv2.dilate(hitam, np.ones((15, 15), np.uint8)) == 0).astype(np.uint8) * 255  # jauhi cutout/border hitam
    orb = cv2.ORB_create(nfeatures=800)
    keluar = []
    for img, m in ((g, boleh), (cv2.flip(g, 1), cv2.flip(boleh, 1))):
        kp, des = orb.detectAndCompute(img, m)
        keluar.append((np.float32([k.pt for k in kp]) if kp else np.zeros((0, 2), np.float32), des))
    return keluar, float(hitam.mean())


def _inlier(fa, fb):
    """Jumlah inlier terbaik antara fitur a dan fitur b (asli atau flip)."""
    import cv2
    import numpy as np

    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    pa, da = fa[0]
    terbaik = 0
    for pb, db in fb:
        if da is None or db is None or len(da) < 8 or len(db) < 8:
            continue
        cocok = [m[0] for m in bf.knnMatch(da, db, k=2) if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
        if len(cocok) < 8:
            continue
        src = np.float32([pa[m.queryIdx] for m in cocok])
        dst = np.float32([pb[m.trainIdx] for m in cocok])
        M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0)
        if inl is not None:
            terbaik = max(terbaik, int(inl.sum()))
    return terbaik


def dedup(nama):
    """Dedup near-duplicate hasil augmentasi. Pasangan = salinan kalau:
       (A) inlier ORB+RANSAC >= INLIER_A, atau
       (B) kemiripan embedding >= SIM_B DAN himpunan kelas label asli (kotak asli yang lolos filter) identik.
       Greedy bintang: urut dari gambar paling bersih (sedikit piksel hitam, bukan grayscale); gambar dibuang hanya
       kalau punya pasangan LANGSUNG ke gambar yang sudah dipertahankan (tanpa chaining antar grup)."""
    import csv
    from collections import Counter, defaultdict

    import numpy as np
    import torch
    import torchvision
    from PIL import Image

    gm = [r for r in csv.DictReader(open(PUBLIK / nama / "manifest_gambar.csv", encoding="utf-8"))
          if r["status"] == "kandidat"]
    paths = [PUBLIK / nama / "terpilih" / r["split_asli"] / "images" / r["image"] for r in gm]
    names = [r["image"] for r in gm]
    n = len(names)
    sig = defaultdict(Counter)
    for r in csv.DictReader(open(PUBLIK / nama / "manifest_kotak.csv", encoding="utf-8")):
        if r["source"] == "asli":
            sig[r["image"]][r["kelas"]] += 1
    tanda = [tuple(sorted(sig[x].items())) for x in names]
    m = torchvision.models.resnet50(weights=torchvision.models.ResNet50_Weights.IMAGENET1K_V2)
    m.fc = torch.nn.Identity()
    m = m.cuda().eval()
    mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1).cuda()
    std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1).cuda()

    def muat(p):
        im = Image.open(p).convert("L").convert("RGB").resize((224, 224), Image.BILINEAR)
        return torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1).float() / 255

    E, EF = [], []
    with torch.no_grad():
        for i in range(0, n, 64):
            x = (torch.stack([muat(p) for p in paths[i:i + 64]]).cuda() - mean) / std
            E.append(torch.nn.functional.normalize(m(x), dim=1).cpu())
            EF.append(torch.nn.functional.normalize(m(torch.flip(x, dims=[3])), dim=1).cpu())
    E, EF = torch.cat(E), torch.cat(EF)
    S = torch.maximum(E @ E.T, E @ EF.T).numpy()
    ii, jj = np.where(np.triu(S >= SIM_KANDIDAT, 1))
    print(f"{nama}: {n} gambar, pasangan kandidat (sim >= {SIM_KANDIDAT}): {len(ii)}", flush=True)
    del m
    torch.cuda.empty_cache()
    perlu = sorted(set(ii.tolist()) | set(jj.tolist()))
    fitur = {i: _fitur_orb(paths[i])[0] for i in perlu}
    adj, aturan = defaultdict(set), {}
    pasangan = []
    for a, b in zip(ii.tolist(), jj.tolist()):
        k = _inlier(fitur[a], fitur[b])
        s = float(S[a, b])
        pasangan.append((a, b, k, round(s * 1000)))
        dup = None
        if k >= INLIER_A:
            dup = "A"
        elif s >= SIM_B and tanda[a] == tanda[b]:
            dup = "B"
        if dup:
            adj[a].add(b)
            adj[b].add(a)
            aturan[(a, b)] = aturan[(b, a)] = dup
    np.save(PUBLIK / nama / "dedup_pasangan.npy", np.array(pasangan))
    np.save(PUBLIK / nama / "dedup_nama.npy", np.array(names))
    # skor augmentasi (kecil = bersih)
    skor = []
    for i, p in enumerate(paths):
        g = np.asarray(Image.open(p).convert("RGB"), np.float32) / 255
        sat = float((g.max(2) - g.min(2)).mean())
        hit = float((g.max(2) <= 10 / 255).mean())
        skor.append(hit + (0.5 if sat < 0.03 else 0.0))
    order = sorted(range(n), key=lambda i: (round(skor[i], 4), -sum(sig[names[i]].values()), names[i]))
    simpan, dari = set(), {}
    for i in order:
        kenal = [j for j in sorted(adj[i], key=lambda j: order.index(j)) if j in simpan]
        if kenal:
            dari[i] = kenal[0]
        else:
            simpan.add(i)
    baris = []
    ukuran = Counter(dari.values())
    for i in range(n):
        j = i if i in simpan else dari[i]
        baris.append(dict(image=names[i], grup=names[j], ukuran_grup=1 + ukuran[j], simpan=int(i in simpan),
                          aturan="" if i in simpan else aturan[(i, j)], skor_augmentasi=round(skor[i], 4)))
    with open(PUBLIK / nama / "dedup.csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(baris[0]))
        w.writeheader()
        w.writerows(baris)
    print(f"  pasangan salinan: aturan A {sum(1 for v in aturan.values() if v == 'A') // 2}, "
          f"aturan B {sum(1 for v in aturan.values() if v == 'B') // 2}")
    print(f"  dipertahankan {len(simpan)} dari {n}; dibuang {len(dari)}; bintang terbesar {max(ukuran.values()) + 1}")
    print("  ukuran bintang (jumlah gambar per grup):", dict(sorted(Counter(v + 1 for v in ukuran.values()).items())),
          "| tanpa salinan:", len(simpan) - len(ukuran))
    print("  dibuang per aturan:", dict(Counter(aturan[(i, dari[i])] for i in dari)))
    trio = [x for x in ("rod_IMG_13316.jpg", "rod_IMG_13318.jpg", "rod_IMG_13330.jpg") if x in names]
    print("  trio:", [(x, "simpan" if names.index(x) in simpan else "dibuang") for x in trio])


def sheet_dedup(nama, n_grup=12, seed=20261110, maks_anggota=4, sisi=240):
    import csv
    import random
    from collections import defaultdict

    from PIL import Image, ImageDraw

    gm = {r["image"]: r["split_asli"] for r in csv.DictReader(open(PUBLIK / nama / "manifest_gambar.csv", encoding="utf-8"))}
    g = defaultdict(list)
    for r in csv.DictReader(open(PUBLIK / nama / "dedup.csv", encoding="utf-8")):
        g[r["grup"]].append(r)
    besar = sorted(k for k, v in g.items() if len(v) >= 2)
    pilih = random.Random(seed).sample(besar, min(n_grup, len(besar)))
    kanvas = Image.new("RGB", (maks_anggota * sisi, len(pilih) * (sisi + 20)), "white")
    d = ImageDraw.Draw(kanvas)
    for gi, k in enumerate(pilih):
        d.text((4, gi * (sisi + 20) + 2), f"grup {k}: {len(g[k])} gambar (hijau = dipertahankan)", fill="black", font=_font())
        for mi, r in enumerate(g[k][:maks_anggota]):
            im = Image.open(PUBLIK / nama / "terpilih" / gm[r["image"]] / "images" / r["image"]).convert("RGB")
            im.thumbnail((sisi - 6, sisi - 6))
            x, y = mi * sisi, gi * (sisi + 20) + 20
            kanvas.paste(im, (x + 3, y + 3))
            d.rectangle([x + 1, y + 1, x + sisi - 2, y + sisi - 2], outline=(0, 170, 0) if r["simpan"] == "1" else (200, 0, 0), width=3)
    out = PUBLIK / nama / "sheet_dedup.jpg"
    kanvas.save(out, quality=88)
    print("tulis", out, f"({len(besar)} grup berukuran >= 2)")


def _font():
    from PIL import ImageFont
    try:
        return ImageFont.truetype("arial.ttf", 16)
    except OSError:
        return ImageFont.load_default()


def sheet_lemnix(n=20, seed=20261109, kolom=5, sisi=384):
    """Contact sheet gambar lemnix dengan mask (nilai 1) ditimpa warna merah transparan."""
    import random

    import numpy as np
    from PIL import Image, ImageDraw

    raw = PUBLIK / "lemnix" / "raw"
    ids = sorted(p.stem for p in (raw / "SegmentationClass").glob("*.png"))
    pilih = random.Random(seed).sample(ids, n)
    baris = (n + kolom - 1) // kolom
    kanvas = Image.new("RGB", (kolom * sisi, baris * (sisi + 22)), "white")
    d = ImageDraw.Draw(kanvas)
    for i, k in enumerate(pilih):
        im = Image.open(raw / "JPEGImages" / f"{k}.jpg").convert("RGB")
        m = np.array(Image.open(raw / "SegmentationClass" / f"{k}.png")) == 1
        a = np.array(im).astype(np.float32)
        a[m] = 0.55 * a[m] + 0.45 * np.array([255, 0, 0], np.float32)
        t = Image.fromarray(a.astype(np.uint8))
        t.thumbnail((sisi, sisi))
        x, y = (i % kolom) * sisi, (i // kolom) * (sisi + 22)
        kanvas.paste(t, (x, y + 22))
        d.text((x + 4, y + 2), f"{k}  mask1={m.mean() * 100:.0f}%", fill="black", font=_font())
    out = PUBLIK / "lemnix" / "sheet_lemnix_acak.jpg"
    kanvas.save(out, quality=88)
    print("tulis", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for c in ("unduh-roboflow", "verifikasi"):
        sp.add_parser(c).add_argument("nama")
    sp.add_parser("sheet-lemnix")
    sp.add_parser("konversi-lemnix")
    sp.add_parser("dedup").add_argument("nama")
    sp.add_parser("sheet-dedup").add_argument("nama")
    sp.add_parser("terpilih").add_argument("nama")
    sp.add_parser("sheet-coco").add_argument("nama")
    sp.add_parser("statistik").add_argument("nama")
    q = sp.add_parser("konversi")
    q.add_argument("nama")
    q.add_argument("--pohon", choices=["buang_gambar", "pakai"], default="buang_gambar")
    q = sp.add_parser("sheet-kotak")
    q.add_argument("nama")
    q.add_argument("--jalanku", action="store_true")
    q = sp.add_parser("sheet-crop")
    q.add_argument("nama")
    q.add_argument("id_kelas", type=int)
    a = ap.parse_args()
    if a.cmd == "unduh-roboflow":
        unduh_roboflow(a.nama)
    elif a.cmd == "verifikasi":
        verifikasi(a.nama)
    elif a.cmd == "konversi":
        konversi(a.nama, a.pohon)
    elif a.cmd == "dedup":
        dedup(a.nama)
    elif a.cmd == "sheet-dedup":
        sheet_dedup(a.nama)
    elif a.cmd == "terpilih":
        terpilih(a.nama)
    elif a.cmd == "sheet-coco":
        sheet_coco(a.nama)
    elif a.cmd == "konversi-lemnix":
        konversi_lemnix()
    elif a.cmd == "statistik":
        statistik(a.nama)
    elif a.cmd == "sheet-kotak":
        sheet_kotak(a.nama, a.jalanku)
    elif a.cmd == "sheet-crop":
        sheet_crop(a.nama, a.id_kelas)
    elif a.cmd == "sheet-lemnix":
        sheet_lemnix()


if __name__ == "__main__":
    main()
