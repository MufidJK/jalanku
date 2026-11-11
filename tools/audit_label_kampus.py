"""audit_label_kampus.py - audit label kampus (249 frame pilot, train + val) terhadap aturan R1-R5 (kelas.md v1.6).

Dijalankan dari root repo. TAHAP A (default) HANYA MEMBACA label; semua keluaran ke data/audit-kampus/ (di-gitignore).
Tidak mengubah JSON label, dataset, runs/, atau models/.

Sumber label (sama dengan tools/bangun_dataset_kampus.py):
  15 frame blind -> data/pilot-v2-blind/<stem>.json ; 234 frame lain -> data/pilot-v2/<stem>.json
ID shape: <frame-stem>#<indeks shape di JSON, mulai 0>.

Aksi (--aksi):
  periksa   R4 (ukuran), duplikat (IoU > 0.9, kelas sama), titik di luar gambar -> cek_programatik.csv, semua_shape.csv;
            cross-check jumlah kotak dari JSON vs label dataset-kampus-kotak.
  sheet     review sheet pilar / orang / tanaman_pot per lokasi (val dulu): thumbnail frame dengan satu shape +
            crop zoom dengan konteks, ID di tiap tile -> sheet/*.jpg, sheet/indeks.csv
  petunjuk  petunjuk model (VAL saja) dari runs/baseline/eval/kotak-gabung/galat.json: (a) GT pilar/orang/tanaman_pot yang
            tidak ditemukan, (b) prediksi conf >= 0.5 tanpa GT yang cocok -> petunjuk_model.csv, sheet_petunjuk/*.jpg
            (hanya membaca galat.json; tidak ada inferensi baru)
  ringkas   gabungkan cek programatik + usulan_visual.csv + usulan_model.csv (ditulis manual setelah melihat sheet)
            -> kandidat.csv, ringkasan.md
  semua     periksa, sheet, petunjuk, ringkas

TAHAP B (mengubah label, hanya setelah persetujuan Jeka):
  --terapkan <csv>   hapus TEPAT shape ber-ID di csv (data/audit-kampus/final_usulan.csv) dari JSON sumber.
                     Tiap shape diverifikasi (kelas + bbox + hash titik) sebelum dihapus; JSON ditulis ulang dengan gaya
                     serialisasi asli (X-AnyLabeling, imageData null). Frame yang jadi kosong: shapes [] + description
                     "frame kosong, sudah dicek audit". Cadangan ke data/pilot-v2-tune/sebelum-audit/<pilot-v2|pilot-v2-blind>/
                     (menolak jalan kalau folder cadangan sudah berisi file). Keluaran: data/audit-kampus/diterapkan.csv
                     dan data/audit-kampus/sebelum_sesudah/*.jpg.
  --uji              dengan --terapkan: hanya verifikasi, tidak menulis apa pun.

Contoh:
  python tools/audit_label_kampus.py --aksi periksa
  python tools/audit_label_kampus.py --aksi sheet
  python tools/audit_label_kampus.py --aksi semua
"""
import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PILOT_IMG = ROOT / "data" / "pilot" / "images"
REVIEW = ROOT / "data" / "pilot-v2"
BLIND = ROOT / "data" / "pilot-v2-blind"
DS_KOTAK = ROOT / "data" / "dataset-kampus-kotak"
GALAT = ROOT / "runs" / "baseline" / "eval" / "kotak-gabung" / "galat.json"
OUT = ROOT / "data" / "audit-kampus"

TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
LOKASI_VAL = ("dapsut", "perpus-lt9-ubm-tower", "tangga-naik-lt9-lt10-ubm-tower")
KELAS_KOTAK = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"]
KELAS_PERMUKAAN = ("jalur_jalan", "jalan_kendaraan")
TIPIS = ("pilar", "pohon", "tepian")
NORMAL = ("orang", "tanaman_pot", "kursi", "kendaraan")
KELAS_SHEET = ("pilar", "orang", "tanaman_pot")
MIN_SISI = 96.0
MIN_TIPIS = 24.0
IOU_DUP = 0.9
CONF_PETUNJUK = 0.5

KOLOM_KANDIDAT = ["id", "frame", "split", "lokasi", "sumber_json", "kelas", "bbox", "aturan", "usul", "alasan"]


# ------------------------------------------------------------------ muat data
def muat_frame():
    """-> list dict(stem, lokasi, split, sumber, json, w, h, shapes). Aturan sumber identik dengan bangun_dataset_kampus.py."""
    imgs = sorted(PILOT_IMG.glob("*.jpg"))
    assert len(imgs) == 249, f"harus 249 gambar pilot, ditemukan {len(imgs)}"
    blind = {p.stem for p in BLIND.glob("*.jpg")}
    assert len(blind) == 15, f"blind harus 15, ditemukan {len(blind)}"
    hasil = []
    for p in imgs:
        stem = p.stem
        lokasi = stem.split("_")[0]
        if lokasi.startswith(TEST):
            raise RuntimeError(f"BERHENTI: lokasi test {lokasi}")
        sumber = "blind" if stem in blind else "review"
        jp = (BLIND if stem in blind else REVIEW) / f"{stem}.json"
        d = json.loads(jp.read_text(encoding="utf-8"))
        hasil.append(dict(stem=stem, lokasi=lokasi, split="val" if lokasi in LOKASI_VAL else "train", sumber=sumber,
                          json=jp, w=float(d.get("imageWidth", 1080)), h=float(d.get("imageHeight", 1920)),
                          shapes=d["shapes"]))
    return hasil


def bbox_klip(pts, w, h):
    """bbox titik polygon, di-clip ke gambar (sama dengan builder dataset)."""
    p = np.asarray(pts, float)
    x1, y1 = np.clip(p.min(0), 0.0, [w, h])
    x2, y2 = np.clip(p.max(0), 0.0, [w, h])
    return float(x1), float(y1), float(x2), float(y2)


def rel(p):
    try:
        return str(Path(p).relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def fmt_bbox(b):
    return "[" + ", ".join(str(int(round(v))) for v in b) + "]"


def iou(a, b):
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def inventaris(frames):
    """Semua shape kelas kotak (0-7) -> list dict. Mirror builder: <3 titik atau bbox kosong dilewati."""
    baris = []
    for f in frames:
        for i, s in enumerate(f["shapes"]):
            lab = s["label"]
            if lab in KELAS_PERMUKAAN:
                continue
            pts = s["points"]
            ada = len(pts) >= 3
            b = bbox_klip(pts, f["w"], f["h"]) if ada else None
            valid = ada and b[2] > b[0] and b[3] > b[1]
            baris.append(dict(id=f"{f['stem']}#{i}", stem=f["stem"], idx=i, split=f["split"], lokasi=f["lokasi"],
                              sumber=f["sumber"], json=rel(f["json"]), kelas=lab, bbox=b, valid=valid,
                              difficult=bool(s.get("difficult")), desc=(s.get("description") or ""), w=f["w"], h=f["h"]))
    return baris


# ------------------------------------------------------------------ periksa
def cek_ukuran(r):
    """R4 untuk satu shape (bukan tangga). -> (melanggar, alasan)."""
    b = r["bbox"]
    bw, bh = b[2] - b[0], b[3] - b[1]
    pendek, panjang = min(bw, bh), max(bw, bh)
    if r["kelas"] in TIPIS:
        gagal = []
        if panjang < MIN_SISI:
            gagal.append(f"sisi panjang {panjang:.0f} < {MIN_SISI:.0f}")
        if pendek < MIN_TIPIS:
            gagal.append(f"sisi pendek {pendek:.0f} < {MIN_TIPIS:.0f}")
        return bool(gagal), "; ".join(gagal) + f" (kotak {bw:.0f}x{bh:.0f})"
    if pendek < MIN_SISI:
        return True, f"sisi pendek {pendek:.0f} < {MIN_SISI:.0f} (kotak {bw:.0f}x{bh:.0f})"
    return False, ""


def periksa(frames, inv):
    OUT.mkdir(parents=True, exist_ok=True)
    cek = []

    # R4 per shape (tangga: kotak gabungan per frame, dicek terpisah di bawah)
    for r in inv:
        if not r["valid"] or r["kelas"] == "tangga":
            continue
        gagal, alasan = cek_ukuran(r)
        if gagal:
            cek.append(dict(id=r["id"], frame=r["stem"], split=r["split"], lokasi=r["lokasi"], sumber_json=r["json"],
                            kelas=r["kelas"], bbox=fmt_bbox(r["bbox"]), aturan="R4", usul="hapus",
                            alasan=alasan + (" [difficult]" if r["difficult"] else "")))
    # tangga: semua shape tangga satu frame digabung jadi satu kotak (keputusan LOG); R4 dicek pada kotak gabungan
    per_frame_t = defaultdict(list)
    for f in frames:
        for i, s in enumerate(f["shapes"]):
            if s["label"] == "tangga" and len(s["points"]) >= 3:
                per_frame_t[f["stem"]].append((f, i, np.asarray(s["points"], float)))
    for stem, lst in per_frame_t.items():
        f = lst[0][0]
        b = bbox_klip(np.vstack([x[2] for x in lst]), f["w"], f["h"])
        bw, bh = b[2] - b[0], b[3] - b[1]
        if min(bw, bh) < MIN_SISI:
            cek.append(dict(id=f"{stem}#" + "+".join(str(x[1]) for x in lst), frame=stem, split=f["split"], lokasi=f["lokasi"],
                            sumber_json=rel(f["json"]), kelas="tangga", bbox=fmt_bbox(b), aturan="R4", usul="hapus",
                            alasan=f"kotak tangga gabungan sisi pendek {min(bw, bh):.0f} < {MIN_SISI:.0f}"))

    # duplikat IoU > 0.9 kelas sama (kelas kotak selain tangga) -> di luar R1-R5
    per = defaultdict(list)
    for r in inv:
        if r["valid"] and r["kelas"] != "tangga":
            per[(r["stem"], r["kelas"])].append(r)
    n_dup = 0
    for (stem, kelas), lst in per.items():
        for a in range(len(lst)):
            for c in range(a + 1, len(lst)):
                v = iou(lst[a]["bbox"], lst[c]["bbox"])
                if v > IOU_DUP:
                    n_dup += 1
                    r = lst[c]
                    cek.append(dict(id=r["id"], frame=stem, split=r["split"], lokasi=r["lokasi"], sumber_json=r["json"],
                                    kelas=kelas, bbox=fmt_bbox(r["bbox"]), aturan="-", usul="ragu",
                                    alasan=f"duplikat/hampir duplikat dengan #{lst[a]['idx']} (IoU kotak {v:.2f}); tidak tercakup R1-R5"))
    # titik di luar gambar (semua kelas termasuk permukaan), toleransi 1 px
    n_luar = 0
    for f in frames:
        for i, s in enumerate(f["shapes"]):
            p = np.asarray(s["points"], float)
            if len(p) and (p.min() < -1 or p[:, 0].max() > f["w"] + 1 or p[:, 1].max() > f["h"] + 1):
                n_luar += 1
                cek.append(dict(id=f"{f['stem']}#{i}", frame=f["stem"], split=f["split"], lokasi=f["lokasi"],
                                sumber_json=rel(f["json"]), kelas=s["label"],
                                bbox=fmt_bbox(bbox_klip(p, f["w"], f["h"])) if len(p) >= 3 else "[]", aturan="-", usul="ragu",
                                alasan=f"titik di luar gambar (x {p[:, 0].min():.0f}..{p[:, 0].max():.0f}, y {p[:, 1].min():.0f}..{p[:, 1].max():.0f}); "
                                       "builder meng-clip, tidak tercakup R1-R5"))
    tulis_csv(OUT / "cek_programatik.csv", cek, KOLOM_KANDIDAT)

    # inventaris semua shape kotak
    ket = ["id", "frame", "split", "lokasi", "sumber_json", "kelas", "bbox", "lebar", "tinggi", "difficult", "description"]
    rows = []
    for r in inv:
        b = r["bbox"]
        rows.append(dict(id=r["id"], frame=r["stem"], split=r["split"], lokasi=r["lokasi"], sumber_json=r["json"],
                         kelas=r["kelas"], bbox=fmt_bbox(b) if b else "[]", lebar=int(round(b[2] - b[0])) if b else "",
                         tinggi=int(round(b[3] - b[1])) if b else "", difficult=int(r["difficult"]), description=r["desc"][:60]))
    tulis_csv(OUT / "semua_shape.csv", rows, ket)

    # cross-check: jumlah kotak per kelas per split dari JSON vs label dataset-kampus-kotak
    dari_json = hitung_kotak_dari_json(frames)
    dari_txt = {sp: Counter() for sp in ("train", "val")}
    for sp in ("train", "val"):
        for lp in (DS_KOTAK / "labels" / sp).glob("*.txt"):
            for ln in lp.read_text().splitlines():
                if ln.strip():
                    dari_txt[sp][KELAS_KOTAK[int(ln.split()[0])]] += 1
    cocok = all(dari_json[sp] == dari_txt[sp] for sp in ("train", "val"))
    print(f"cross-check JSON vs data/dataset-kampus-kotak/labels: {'COCOK' if cocok else 'BEDA'}")
    for sp in ("train", "val"):
        print(f"  {sp}: " + ", ".join(f"{k}={dari_json[sp][k]}" for k in KELAS_KOTAK) + f" (total {sum(dari_json[sp].values())})")
        if dari_json[sp] != dari_txt[sp]:
            print(f"  !! txt {sp}: " + ", ".join(f"{k}={dari_txt[sp][k]}" for k in KELAS_KOTAK))
    c = Counter((x["aturan"], x["split"], x["kelas"]) for x in cek)
    print(f"cek_programatik.csv: {len(cek)} baris (R4 {sum(1 for x in cek if x['aturan'] == 'R4')}, duplikat {n_dup}, titik luar {n_luar})")
    for k, v in sorted(c.items()):
        print("  ", k, v)
    return cek, dari_json


def hitung_kotak_dari_json(frames, hapus_id=None):
    """Hitung instance kotak per kelas per split seperti builder (tangga digabung). hapus_id: set ID shape yang diabaikan."""
    hapus_id = hapus_id or set()
    cnt = {"train": Counter(), "val": Counter()}
    for f in frames:
        ada_t = False
        pts_t = []
        for i, s in enumerate(f["shapes"]):
            lab = s["label"]
            if lab not in KELAS_KOTAK or len(s["points"]) < 3 or f"{f['stem']}#{i}" in hapus_id:
                continue
            if lab == "tangga":
                pts_t.append(np.asarray(s["points"], float))
                continue
            b = bbox_klip(s["points"], f["w"], f["h"])
            if b[2] > b[0] and b[3] > b[1]:
                cnt[f["split"]][lab] += 1
        if pts_t:
            b = bbox_klip(np.vstack(pts_t), f["w"], f["h"])
            if b[2] > b[0] and b[3] > b[1]:
                cnt[f["split"]]["tangga"] += 1
    return cnt


def tulis_csv(path, rows, kolom):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=kolom, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ tile / sheet
TW, TH, HDR = 600, 412, 36
BODY = TH - HDR
WARNA_FOKUS = (0, 0, 255)       # BGR merah
WARNA_POLY = (255, 0, 255)      # magenta
WARNA_BOX = (0, 255, 255)       # kuning


def tile(img, bbox, poly, judul1, judul2, warna=WARNA_FOKUS):
    """Satu tile: header 2 baris + [thumbnail frame penuh | crop zoom dengan konteks]."""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = bbox
    # thumbnail
    sc = BODY / h
    th = cv2.resize(img, (max(1, int(w * sc)), BODY), interpolation=cv2.INTER_AREA)
    cv2.rectangle(th, (int(x1 * sc), int(y1 * sc)), (int(x2 * sc), int(y2 * sc)), warna, 2)
    # crop persegi dengan konteks
    bw, bh = x2 - x1, y2 - y1
    S = float(np.clip(max(bw, bh) * 2.2, 360, min(w, h)))
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    rx1 = float(np.clip(cx - S / 2, 0, w - S))
    ry1 = float(np.clip(cy - S / 2, 0, h - S))
    crop = img[int(ry1):int(ry1 + S), int(rx1):int(rx1 + S)].copy()
    k = 1.0  # gambar anotasi di resolusi asli crop, lalu diperkecil
    if poly is not None and len(poly) >= 3:
        pp = np.round((np.asarray(poly) - [rx1, ry1]) * k).astype(np.int32)
        cv2.polylines(crop, [pp], True, WARNA_POLY, max(2, int(S / 200)))
    cv2.rectangle(crop, (int((x1 - rx1)), int((y1 - ry1))), (int((x2 - rx1)), int((y2 - ry1))), WARNA_BOX, max(1, int(S / 400)))
    pw = TW - th.shape[1]
    cs = min(pw / crop.shape[1], BODY / crop.shape[0])
    crop = cv2.resize(crop, (max(1, int(crop.shape[1] * cs)), max(1, int(crop.shape[0] * cs))), interpolation=cv2.INTER_AREA)
    kanvas = np.full((TH, TW, 3), 255, np.uint8)
    kanvas[HDR:HDR + BODY, : th.shape[1]] = th
    kanvas[HDR:HDR + crop.shape[0], th.shape[1]: th.shape[1] + crop.shape[1]] = crop
    cv2.putText(kanvas, judul1, (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(kanvas, judul2, (3, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 160), 1, cv2.LINE_AA)
    cv2.rectangle(kanvas, (0, 0), (TW - 1, TH - 1), (180, 180, 180), 1)
    return kanvas


def susun(tiles, kolom=3):
    baris = []
    for i in range(0, len(tiles), kolom):
        r = tiles[i:i + kolom]
        while len(r) < kolom:
            r.append(np.full((TH, TW, 3), 235, np.uint8))
        baris.append(np.hstack(r))
    return np.vstack(baris)


def urutan_lokasi(inv):
    lok = sorted({(r["split"], r["lokasi"]) for r in inv}, key=lambda t: (0 if t[0] == "val" else 1, t[1]))
    return lok


def buat_sheet(frames, inv):
    d = OUT / "sheet"
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.jpg"):
        old.unlink()  # hanya keluaran tool ini sendiri di folder audit baru
    fmap = {f["stem"]: f for f in frames}
    indeks = []
    n_per_sheet = 9
    urut = 0
    for split, lokasi in urutan_lokasi(inv):
        for kelas in KELAS_SHEET:
            items = sorted([r for r in inv if r["lokasi"] == lokasi and r["kelas"] == kelas and r["valid"]],
                           key=lambda r: (r["stem"], r["idx"]))
            if not items:
                continue
            urut += 1
            tiles, bagian = [], 0
            cache = {}
            for j, r in enumerate(items):
                if r["stem"] not in cache:
                    cache = {r["stem"]: cv2.imread(str(PILOT_IMG / f"{r['stem']}.jpg"))}
                img = cache[r["stem"]]
                f = fmap[r["stem"]]
                poly = f["shapes"][r["idx"]]["points"]
                b = r["bbox"]
                j2 = f"{kelas} {int(b[2] - b[0])}x{int(b[3] - b[1])}" + (" difficult" if r["difficult"] else "") + f" [{r['sumber']}]"
                tiles.append(tile(img, b, poly, r["id"], j2))
                indeks.append(dict(sheet="", id=r["id"], split=split, lokasi=lokasi, kelas=kelas, bbox=fmt_bbox(b)))
                if len(tiles) == n_per_sheet or j == len(items) - 1:
                    bagian += 1
                    nama = f"{urut:02d}_{split}_{lokasi}_{kelas}_{bagian:02d}.jpg"
                    cv2.imwrite(str(d / nama), susun(tiles), [cv2.IMWRITE_JPEG_QUALITY, 85])
                    for x in indeks[-len(tiles):]:
                        x["sheet"] = nama
                    tiles = []
    tulis_csv(d / "indeks.csv", indeks, ["sheet", "id", "split", "lokasi", "kelas", "bbox"])
    cnt = Counter((x["split"], x["kelas"]) for x in indeks)
    print(f"sheet: {len(list(d.glob('*.jpg')))} berkas, {len(indeks)} tile -> {rel(d)}")
    for k, v in sorted(cnt.items(), key=lambda t: (t[0][0] != "val", t[0])):
        print("  ", k, v)


# ------------------------------------------------------------------ petunjuk model (val)
def cocok_gt(inv, stem, xyxy, tol=2.5):
    """Cari shape kotak yang bboxnya = xyxy (dibulatkan) di frame itu."""
    for r in inv:
        if r["stem"] == stem.replace(".jpg", "") and r["valid"] and r["kelas"] != "tangga":
            if all(abs(a - b) <= tol for a, b in zip(r["bbox"], xyxy)):
                yield r


def petunjuk(frames, inv):
    g = json.loads(GALAT.read_text(encoding="utf-8"))
    d = OUT / "sheet_petunjuk"
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.jpg"):
        old.unlink()
    fmap = {f["stem"]: f for f in frames}
    rows, tiles_fn, tiles_fp = [], [], []
    for x in g["fn_daftar"]:
        if x["kelas"] not in KELAS_SHEET:
            continue
        stem = x["gambar"][:-4]
        if fmap[stem]["split"] != "val":
            raise RuntimeError("galat.json harus val saja")
        m = list(cocok_gt(inv, stem, x["xyxy"]))
        shape = m[0] if m else None
        rid = shape["id"] if shape else f"{stem}#?"
        rows.append(dict(id=rid, jenis="GT tidak ditemukan", frame=stem, split="val", lokasi=fmap[stem]["lokasi"], kelas=x["kelas"],
                         bbox=fmt_bbox(x["xyxy"]), conf="", tertukar_dengan=x["tertukar_dengan"] or ""))
        img = cv2.imread(str(PILOT_IMG / x["gambar"]))
        poly = fmap[stem]["shapes"][shape["idx"]]["points"] if shape else None
        tiles_fn.append((rid, tile(img, x["xyxy"], poly, "H-FN " + rid, f"GT {x['kelas']} tak ditemukan model" +
                                  (f" (diprediksi {x['tertukar_dengan']})" if x["tertukar_dengan"] else ""), (0, 160, 0))))
    k = Counter()
    for x in sorted(g["fp_daftar"], key=lambda t: (t["gambar"], -t["conf"])):
        if x["conf"] < CONF_PETUNJUK:
            continue
        stem = x["gambar"][:-4]
        k[stem] += 1
        rid = f"{stem}@pred{k[stem]}"
        rows.append(dict(id=rid, jenis="prediksi tanpa GT", frame=stem, split="val", lokasi=fmap[stem]["lokasi"], kelas=x["kelas"],
                         bbox=fmt_bbox(x["xyxy"]), conf=x["conf"], tertukar_dengan=x["tertukar_dengan"] or ""))
        img = cv2.imread(str(PILOT_IMG / x["gambar"]))
        tiles_fp.append((rid, tile(img, x["xyxy"], None, "H-FP " + rid, f"prediksi {x['kelas']} conf {x['conf']:.2f} tanpa GT" +
                                  (f" (GT kelas {x['tertukar_dengan']})" if x["tertukar_dengan"] else ""), (0, 0, 255))))
    tulis_csv(OUT / "petunjuk_model.csv", rows, ["id", "jenis", "frame", "split", "lokasi", "kelas", "bbox", "conf", "tertukar_dengan"])
    for nama, tl in (("fn", tiles_fn), ("fp", tiles_fp)):
        for i in range(0, len(tl), 9):
            cv2.imwrite(str(d / f"{nama}_{i // 9 + 1:02d}.jpg"), susun([t for _, t in tl[i:i + 9]]), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"petunjuk_model.csv: {len(rows)} baris (GT tak ditemukan {len(tiles_fn)}, prediksi tanpa GT conf>={CONF_PETUNJUK} {len(tiles_fp)})")
    print("  urutan tile per sheet:", {n: [i for i, _ in tl] for n, tl in (("fn", tiles_fn), ("fp", tiles_fp))} if False else "lihat petunjuk_model.csv")


# ------------------------------------------------------------------ ringkas
def baca_usulan(nama):
    p = OUT / nama
    if not p.exists():
        return []
    return list(csv.DictReader(open(p, encoding="utf-8")))


def ringkas(frames, inv, cek):
    peta = {r["id"]: r for r in inv}
    kand = {}   # id -> dict, aturan digabung

    def tambah(baris):
        i = baris["id"]
        if i in kand:
            k = kand[i]
            gabung = set(k["aturan"].split("+")) | set(baris["aturan"].split("+"))
            if len(gabung) > 1:
                gabung.discard("-")   # '-' = tidak ada aturan; buang kalau ada aturan nyata
            k["aturan"] = "+".join(sorted(gabung))
            if k["usul"] != baris["usul"]:
                urut = {"hapus": 0, "ragu": 1, "label kurang": 2}
                k["usul"] = min((k["usul"], baris["usul"]), key=lambda u: urut.get(u, 9))
            k["alasan"] += " | " + baris["alasan"]
        else:
            kand[i] = dict(baris)

    for b in cek:
        tambah(b)
    for u in baca_usulan("usulan_visual.csv"):
        r = peta.get(u["id"])
        if r is None:
            raise RuntimeError(f"usulan_visual.csv: ID tidak dikenal {u['id']}")
        tambah(dict(id=u["id"], frame=r["stem"], split=r["split"], lokasi=r["lokasi"], sumber_json=r["json"], kelas=r["kelas"],
                    bbox=fmt_bbox(r["bbox"]), aturan=u["aturan"], usul=u["usul"], alasan=u["alasan"]))
    pm = {x["id"]: x for x in csv.DictReader(open(OUT / "petunjuk_model.csv", encoding="utf-8"))} if (OUT / "petunjuk_model.csv").exists() else {}
    for u in baca_usulan("usulan_model.csv"):
        p = pm.get(u["id"])
        if p is None:
            raise RuntimeError(f"usulan_model.csv: ID tidak dikenal {u['id']}")
        fr = next(f for f in frames if f["stem"] == p["frame"])
        tambah(dict(id=u["id"], frame=p["frame"], split="val", lokasi=p["lokasi"], sumber_json=rel(fr["json"]), kelas=p["kelas"],
                    bbox=p["bbox"], aturan=u["aturan"], usul=u["usul"], alasan="[petunjuk model: " + u["jenis"] + "] " + u["alasan"]))
    rows = sorted(kand.values(), key=lambda r: (0 if r["split"] == "val" else 1, r["lokasi"], r["frame"], r["id"]))
    tulis_csv(OUT / "kandidat.csv", rows, KOLOM_KANDIDAT)

    # ringkasan
    sk = (lambda r: r["aturan"].split("+"))
    tabel = defaultdict(Counter)   # (usul) -> Counter[(aturan, split, kelas)]
    for r in rows:
        for a in sk(r):
            tabel[r["usul"]][(a, r["split"], r["kelas"])] += 1
    md = ["# Ringkasan audit label kampus (Tahap A, belum ada yang diubah)", "",
          f"Sumber: {len(frames)} frame (train {sum(f['split'] == 'train' for f in frames)}, val {sum(f['split'] == 'val' for f in frames)}). "
          "Kandidat lengkap: `kandidat.csv`. Satu ID bisa kena lebih dari satu aturan (ditulis `R1+R4`); tabel di bawah menghitung per aturan, "
          "jadi jumlahnya bisa lebih besar daripada jumlah ID unik.", ""]
    for usul in ("hapus", "ragu", "label kurang"):
        md += [f"## Usul: {usul}", "", "| Aturan | Split | Kelas | Jumlah |", "|---|---|---|---|"]
        t = tabel.get(usul, Counter())
        if not t:
            md.append("| - | - | - | 0 |")
        for (a, sp, kl), v in sorted(t.items(), key=lambda z: (z[0][0], z[0][1] != "val", z[0][2])):
            md.append(f"| {a} | {sp} | {kl} | {v} |")
        md.append("")
    ids_hapus = {r["id"] for r in rows if r["usul"] == "hapus" and "#" in r["id"] and "@" not in r["id"]}
    # tangga gabungan: ID bisa berbentuk stem#3+4 -> perluas
    ids_hapus_shape = set()
    for i in ids_hapus:
        stem, idx = i.split("#", 1)
        for z in idx.split("+"):
            ids_hapus_shape.add(f"{stem}#{z}")
    ids_ragu = {r["id"] for r in rows if r["usul"] == "ragu" and "@" not in r["id"] and r["aturan"] != "-"}
    ids_ragu_shape = set()
    for i in ids_ragu:
        stem, idx = i.split("#", 1)
        for z in idx.split("+"):
            ids_ragu_shape.add(f"{stem}#{z}")
    awal = hitung_kotak_dari_json(frames)
    sesudah_h = hitung_kotak_dari_json(frames, ids_hapus_shape)
    sesudah_hr = hitung_kotak_dari_json(frames, ids_hapus_shape | ids_ragu_shape)
    for sp in ("val", "train"):
        md += [f"## Instance kotak {sp} yang tersisa", "",
               "| Kelas | Sekarang | Setelah hapus | Setelah hapus + ragu |", "|---|---|---|---|"]
        for k in KELAS_KOTAK:
            md.append(f"| {k} | {awal[sp][k]} | {sesudah_h[sp][k]} | {sesudah_hr[sp][k]} |")
        md.append(f"| **total** | {sum(awal[sp].values())} | {sum(sesudah_h[sp].values())} | {sum(sesudah_hr[sp].values())} |")
        md.append("")
    kl = baca_usulan("klasifikasi_petunjuk.csv")
    if kl:
        kat = defaultdict(Counter)
        for x in kl:
            kat[x["kategori"]][(x["jenis"], x["kelas"])] += 1
        md += ["## Petunjuk model (val saja; hanya petunjuk, bukan keputusan)", "",
               f"{len(kl)} petunjuk (GT tidak ditemukan + prediksi conf >= {CONF_PETUNJUK} tanpa GT), diklasifikasi dari review sheet_petunjuk/. "
               "Detail per ID: `klasifikasi_petunjuk.csv`.", "",
               "| Kategori | Jumlah | Rincian jenis / kelas |", "|---|---|---|"]
        for k, c in sorted(kat.items(), key=lambda z: -sum(z[1].values())):
            rinci = ", ".join(f"{j.split()[0]} {kl_}: {n}" for (j, kl_), n in sorted(c.items()))
            md.append(f"| {k} | {sum(c.values())} | {rinci} |")
        md.append("")
        md += ["### Daftar 'label kurang' (kamu yang menambah di X-AnyLabeling; saya tidak menggambar shape baru)", "",
               "| ID prediksi | Kelas | bbox | Alasan |", "|---|---|---|---|"]
        for x in kl:
            if x["kategori"] == "label-kurang":
                pm_row = pm.get(x["id"], {})
                md.append(f"| {x['id']} | {x['kelas']} | {pm_row.get('bbox', '')} | {x['catatan']} |")
        md.append("")
    md += ["Catatan: 'ragu' dan 'label kurang' dari petunjuk model tidak ikut dihitung sebagai penghapusan kecuali pada kolom 'hapus + ragu'. "
           "Baris dengan aturan `-` (duplikat, titik di luar gambar) tidak dihitung di kolom mana pun karena tidak tercakup R1-R5.", ""]
    (OUT / "ringkasan.md").write_text("\n".join(md), encoding="utf-8")
    print(f"kandidat.csv: {len(rows)} baris; ringkasan.md ditulis")
    for usul in ("hapus", "ragu", "label kurang"):
        print(f"  usul {usul}: {sum(1 for r in rows if r['usul'] == usul)} baris")


# ------------------------------------------------------------------ tahap B: terapkan
BACKUP = ROOT / "data" / "pilot-v2-tune" / "sebelum-audit"
DESC_KOSONG = "frame kosong, sudah dicek audit"
KOLOM_DITERAPKAN = ["id", "frame", "split", "lokasi", "sumber_json", "kelas", "bbox", "aturan", "alasan", "cadangan",
                    "shape_sebelum", "shape_sesudah", "status"]


def sha_titik(pts):
    return hashlib.sha1(json.dumps(pts, separators=(",", ":")).encode()).hexdigest()[:16]


def gaya_json(raw):
    """Gaya serialisasi yang mereproduksi byte file persis -> (crlf, ensure_ascii, trailing) atau None."""
    t = raw.decode("utf-8")
    crlf = "\r\n" in t
    body = t.replace("\r\n", "\n")
    d = json.loads(body)
    for ea in (True, False):
        for tr in ("", "\n"):
            if json.dumps(d, indent=2, ensure_ascii=ea) + tr == body:
                return crlf, ea, tr
    return None


def tulis_json(path, d, gaya):
    crlf, ea, tr = gaya
    s = json.dumps(d, indent=2, ensure_ascii=ea) + tr
    path.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode("utf-8"))


def terapkan(csv_path, uji):
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    frames = muat_frame()
    fmap = {f["stem"]: f for f in frames}
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise SystemExit("BERHENTI: ID ganda di csv")
    per_file = defaultdict(list)
    for r in rows:
        stem, idx = r["id"].rsplit("#", 1)
        if not idx.isdigit() or stem not in fmap:
            raise SystemExit(f"BERHENTI: ID tidak dikenal {r['id']}")
        f = fmap[stem]
        if rel(f["json"]) != r["sumber_json"]:
            raise SystemExit(f"BERHENTI: sumber JSON {r['id']} {r['sumber_json']} != {rel(f['json'])}")
        idx = int(idx)
        if idx >= len(f["shapes"]):
            raise SystemExit(f"BERHENTI: indeks di luar jangkauan {r['id']}")
        s = f["shapes"][idx]
        if s["label"] != r["kelas"] or s["label"] in KELAS_PERMUKAAN:
            raise SystemExit(f"BERHENTI: kelas {r['id']} {s['label']} != {r['kelas']}")
        if fmt_bbox(bbox_klip(s["points"], f["w"], f["h"])) != r["bbox"]:
            raise SystemExit(f"BERHENTI: bbox {r['id']} berubah")
        if sha_titik(s["points"]) != r["poin_sha1"]:
            raise SystemExit(f"BERHENTI: titik {r['id']} berubah sejak daftar dibuat")
        per_file[f["json"]].append((idx, r))
    gaya = {}
    for jp in per_file:
        g = gaya_json(jp.read_bytes())
        if g is None:
            raise SystemExit(f"BERHENTI: gaya serialisasi {rel(jp)} tidak bisa direproduksi persis")
        gaya[jp] = g
    print(f"verifikasi OK: {len(rows)} shape di {len(per_file)} JSON (blind: {sum('pilot-v2-blind' in rel(j) for j in per_file)})")
    if uji:
        print("--uji: tidak ada yang ditulis")
        return
    if BACKUP.exists() and any(p.is_file() for p in BACKUP.rglob("*")):
        raise SystemExit(f"BERHENTI: folder cadangan {rel(BACKUP)} sudah berisi file")
    hasil = []
    for jp, items in sorted(per_file.items()):
        dst = BACKUP / jp.parent.name / jp.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(jp, dst)
        if dst.read_bytes() != jp.read_bytes():
            raise SystemExit(f"BERHENTI: cadangan {rel(dst)} tidak identik")
        d = json.loads(jp.read_text(encoding="utf-8"))
        asli = d["shapes"]
        buang = {i for i, _ in items}
        sisa = [s for j, s in enumerate(asli) if j not in buang]
        d["shapes"] = sisa
        kosong = not sisa
        if kosong:
            d["description"] = DESC_KOSONG
        tulis_json(jp, d, gaya[jp])
        cek = json.loads(jp.read_text(encoding="utf-8"))
        assert cek["imageData"] is None and cek["shapes"] == sisa
        for i, r in items:
            hasil.append(dict(id=r["id"], frame=r["frame"], split=r["split"], lokasi=r["lokasi"], sumber_json=r["sumber_json"],
                              kelas=r["kelas"], bbox=r["bbox"], aturan=r["aturan"], alasan=r["alasan"], cadangan=rel(dst),
                              shape_sebelum=len(asli), shape_sesudah=len(sisa),
                              status="dihapus (frame jadi kosong)" if kosong else "dihapus"))
    hasil.sort(key=lambda r: (0 if r["split"] == "val" else 1, r["lokasi"], r["frame"], int(r["id"].rsplit("#", 1)[1])))
    tulis_csv(OUT / "diterapkan.csv", hasil, KOLOM_DITERAPKAN)
    print(f"diterapkan.csv: {len(hasil)} shape dihapus dari {len(per_file)} JSON; cadangan di {rel(BACKUP)}")
    sheet_sebelum_sesudah(hasil)


def sheet_sebelum_sesudah(hasil):
    d = OUT / "sebelum_sesudah"
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.jpg"):
        old.unlink()
    per = defaultdict(list)
    for r in hasil:
        per[r["frame"]].append(r)
    H = 560
    sel = []
    for stem in sorted(per, key=lambda s: (0 if per[s][0]["split"] == "val" else 1, per[s][0]["lokasi"], s)):
        r0 = per[stem][0]
        jp = ROOT / r0["sumber_json"]
        sebelum = json.loads((ROOT / r0["cadangan"]).read_text(encoding="utf-8"))["shapes"]
        sesudah = json.loads(jp.read_text(encoding="utf-8"))["shapes"]
        buang = {int(r["id"].rsplit("#", 1)[1]) for r in per[stem]}
        img = cv2.imread(str(PILOT_IMG / f"{stem}.jpg"))
        a, b = img.copy(), img.copy()
        for j, s in enumerate(sebelum):
            if s["label"] in KELAS_PERMUKAAN:
                continue
            p = np.asarray(s["points"], np.int32)
            cv2.polylines(a, [p], True, (0, 0, 255) if j in buang else (0, 200, 0), 6 if j in buang else 3)
        for s in sesudah:
            if s["label"] in KELAS_PERMUKAAN:
                continue
            cv2.polylines(b, [np.asarray(s["points"], np.int32)], True, (0, 200, 0), 3)
        sc = (H - 40) / img.shape[0]
        kiri, kanan = cv2.resize(a, None, fx=sc, fy=sc), cv2.resize(b, None, fx=sc, fy=sc)
        pair = np.hstack([kiri, np.full((kiri.shape[0], 4, 3), 255, np.uint8), kanan])
        k = np.full((H, pair.shape[1], 3), 255, np.uint8)
        k[40:40 + pair.shape[0], :] = pair
        ats = ",".join(sorted({r["aturan"] for r in per[stem]}))
        cv2.putText(k, f"{stem} | hapus {len(per[stem])} ({ats})", (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
        cv2.putText(k, "SEBELUM (merah = dihapus)", (3, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 160), 1, cv2.LINE_AA)
        cv2.putText(k, "SESUDAH", (kiri.shape[1] + 10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 120, 0), 1, cv2.LINE_AA)
        cv2.rectangle(k, (0, 0), (k.shape[1] - 1, H - 1), (180, 180, 180), 1)
        sel.append(k)
    w = max(t.shape[1] for t in sel)
    sel = [np.pad(t, ((0, 0), (0, w - t.shape[1]), (0, 0)), constant_values=235) for t in sel]
    kosong = np.full_like(sel[0], 235)
    n = 0
    for i in range(0, len(sel), 4):
        n += 1
        blok = sel[i:i + 4] + [kosong] * (4 - len(sel[i:i + 4]))
        cv2.imwrite(str(d / f"{n:02d}.jpg"), np.vstack([np.hstack(blok[:2]), np.hstack(blok[2:])]), [cv2.IMWRITE_JPEG_QUALITY, 82])
    print(f"sebelum_sesudah: {len(sel)} frame -> {n} sheet di {rel(d)}")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aksi", choices=["periksa", "sheet", "petunjuk", "ringkas", "semua"], default="semua")
    ap.add_argument("--terapkan", metavar="CSV", help="TAHAP B: hapus shape ber-ID di csv (mengubah JSON label!)")
    ap.add_argument("--uji", action="store_true", help="dengan --terapkan: hanya verifikasi")
    a = ap.parse_args()
    if a.terapkan:
        terapkan(Path(a.terapkan), a.uji)
        return
    frames = muat_frame()
    inv = inventaris(frames)
    print(f"{len(frames)} frame, {len(inv)} shape kelas kotak (train {sum(f['split'] == 'train' for f in frames)}, "
          f"val {sum(f['split'] == 'val' for f in frames)} frame)")
    cek = None
    if a.aksi in ("periksa", "semua", "ringkas"):
        cek, _ = periksa(frames, inv)
    if a.aksi in ("sheet", "semua"):
        buat_sheet(frames, inv)
    if a.aksi in ("petunjuk", "semua"):
        petunjuk(frames, inv)
    if a.aksi in ("ringkas", "semua"):
        ringkas(frames, inv, cek)


if __name__ == "__main__":
    main()
