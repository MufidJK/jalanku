"""autolabel_kampus.py - label otomatis frame kampus untuk dua model JalanKu, sekali jalan.

Dua model dipakai bersamaan:
  - SegFormer ADE20K (segmentasi semantik 150 kelas: lantai, jalan, tangga, kolom, tiang, pot, pohon, ...)
  - YOLO segmentasi COCO (orang, kendaraan, kursi, pot tanaman)

Hasil 1, dataset SEGMENTASI (polygon, kelas: 0 jalur_jalan, 1 jalan_kendaraan, 2 tangga)
  jalur_jalan     <- ADE floor, sidewalk, path, rug
  jalan_kendaraan <- ADE road (di parkiran-motor-b1 semua permukaan jadi jalan_kendaraan)
  tangga          <- ADE stairs, stairway
  Objek di atas lantai dijadikan lubang (tidak ikut dilabel). Eskalator, rumput, tanah tidak dilabel.

Hasil 2, dataset KOTAK (kelas: 0 pilar, 1 pohon, 2 tepian, 3 orang, 4 tanaman_pot, 5 kursi,
6 kendaraan, 7 tangga)
  orang, kendaraan, kursi <- COCO
  tanaman_pot             <- COCO potted plant, kotaknya diperluas mencakup pot dari ADE
  pilar                   <- ADE column dan pole
  tangga                  <- ADE stairs dan stairway
  pohon dan tepian TIDAK bisa diotomasi (ADE melabel pohon utuh dengan daun, tepian tidak dikenal).
  Supaya model tidak belajar "batang pohon = bukan objek", frame dengan pohon (ADE tree >= 3% luas
  gambar) dikeluarkan dari dataset kotak dan dicatat di kotak/dikeluarkan.txt.

Ini PSEUDO-LABEL untuk training baseline, bukan untuk evaluasi. Label test tetap dicek manusia.
Lokasi test (selasar-lt11, pot-lt11, taman-ubm) ditolak.

Output:
  <out>/seg/images, <out>/seg/labels, <out>/seg/data.yaml
  <out>/kotak/images, <out>/kotak/labels, <out>/kotak/data.yaml, <out>/kotak/dikeluarkan.txt
  <out>/preview/preview_XX.jpg   (kiri: segmentasi, kanan: kotak)
  <out>/ringkasan.csv
Gambar di images/ dibuat sebagai hard link ke data/frame-blur (tidak makan storage dobel).
Frame yang sudah ada label-nya dilewati, jadi aman dijalankan ulang.

Contoh pemakaian:
  python tools/autolabel_kampus.py data/pilot/images --out data/auto-pilot --device 0
  python tools/autolabel_kampus.py --semua-training --out data/auto-kampus --device 0
"""

import argparse
import csv
import os
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

KELAS_SEG = ["jalur_jalan", "jalan_kendaraan", "tangga"]
KELAS_KOTAK = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"]

ADE_SEG = {"floor": 0, "sidewalk": 0, "path": 0, "rug": 0, "road": 1, "stairs": 2, "stairway": 2}
ADE_PILAR = {"column", "pole"}
ADE_TANGGA = {"stairs", "stairway"}
ADE_POT = {"pot"}
ADE_POHON = {"tree"}
COCO_KOTAK = {"person": 3, "bicycle": 6, "car": 6, "motorcycle": 6, "bus": 6, "truck": 6,
              "chair": 5, "bench": 5, "potted plant": 4}

TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
LOKASI_JALAN_KENDARAAN = ("parkiran-motor-b1",)
IMG_EXT = {".jpg", ".jpeg", ".png"}
MIN_LUAS = 0.01        # polygon segmentasi < 1% luas gambar dibuang
MIN_LUBANG = 0.002     # objek di atas lantai >= 0.2% luas gambar jadi lubang
MIN_SISI_640 = 32      # aturan objek terlalu kecil di docs/kelas.md (sisi terpendek di gambar 640)
BATAS_POHON = 0.03     # frame dengan pohon >= 3% luas gambar dikeluarkan dari dataset kotak
WARNA_SEG = [(80, 220, 80), (60, 60, 255), (255, 160, 0)]
WARNA_KOTAK = [(255, 0, 255), (0, 128, 255), (0, 255, 255), (0, 255, 0), (255, 255, 0),
               (0, 165, 255), (255, 80, 80), (255, 160, 0)]


# ---------- input ----------

def kumpulkan(a) -> list[Path]:
    if a.semua_training:
        root = Path("data/frame-blur")
        return sorted(f for d in root.iterdir() if d.is_dir() and not d.name.startswith(TEST)
                      for f in d.iterdir() if f.suffix.lower() in IMG_EXT)
    files = []
    for p in a.input:
        p = Path(p)
        files += [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.suffix.lower() in IMG_EXT)
    return files


def id_ade(id2label: dict, nama: set) -> list[int]:
    out = []
    for i, n in id2label.items():
        kata = n.strip().lower().replace(";", " ").replace(",", " ").split()[0]
        if kata in nama:
            out.append(int(i))
    return out


# ---------- polygon segmentasi ----------

def _rapikan(c: np.ndarray) -> np.ndarray:
    c = cv2.approxPolyDP(c, max(2.0, 0.003 * cv2.arcLength(c, True)), True)
    return c.reshape(-1, 2)


def _gabung_lubang(luar: np.ndarray, lubang: list[np.ndarray]) -> np.ndarray:
    """Format YOLO tidak punya lubang, jadi tiap lubang disambung ke tepi luar lewat celah
    selebar nol (titik terdekat). Saat polygon diubah jadi mask, area lubang tetap kosong."""
    p = luar.astype(np.float64)
    for h in lubang:
        h = h.astype(np.float64)
        d = ((p[:, None, :] - h[None, :, :]) ** 2).sum(-1)
        i, j = np.unravel_index(d.argmin(), d.shape)
        h = np.roll(h, -j, axis=0)
        p = np.vstack([p[: i + 1], h, h[:1], p[i:]])
    return p


def mask_ke_polygon(mask: np.ndarray) -> list[np.ndarray]:
    k = np.ones((7, 7), np.uint8)
    m = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
    cnts, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return []
    hier = hier[0]
    luas_img = mask.shape[0] * mask.shape[1]
    out = []
    for i, c in enumerate(cnts):
        if hier[i][3] != -1 or cv2.contourArea(c) < MIN_LUAS * luas_img:
            continue
        lubang, j = [], hier[i][2]
        while j != -1:
            if cv2.contourArea(cnts[j]) >= MIN_LUBANG * luas_img:
                h = _rapikan(cnts[j])
                if len(h) >= 3:
                    lubang.append(h)
            j = hier[j][0]
        luar = _rapikan(c)
        if len(luar) >= 3:
            out.append(_gabung_lubang(luar, lubang))
    return out


# ---------- kotak ----------

def kotak_dari_mask(mask: np.ndarray, min_sisi: float) -> list[list[float]]:
    """Satu kotak per komponen terhubung."""
    m = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        if min(w, h) >= min_sisi:
            out.append([float(x), float(y), float(x + w), float(y + h)])
    return out


def perluas_pot(box: list[float], pot_mask: np.ndarray) -> list[float]:
    """COCO 'potted plant' sering hanya tanamannya. Cari pot (ADE) di bawah/sekitar kotak lalu gabungkan."""
    x1, y1, x2, y2 = box
    h_img, w_img = pot_mask.shape
    bw, bh = x2 - x1, y2 - y1
    ax1, ax2 = int(max(0, x1 - 0.2 * bw)), int(min(w_img, x2 + 0.2 * bw))
    ay1, ay2 = int(max(0, y1)), int(min(h_img, y2 + 1.0 * bh))
    sub = pot_mask[ay1:ay2, ax1:ax2]
    if sub.sum() < 50:
        return box
    ys, xs = np.nonzero(sub)
    return [min(x1, ax1 + xs.min()), min(y1, ay1 + ys.min()), max(x2, ax1 + xs.max()), max(y2, ay1 + ys.max())]


def taut(src: Path, dst: Path):
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def preview(img, seg_teks, kotak_baris, w, h):
    seg = img.copy()
    for t in seg_teks:
        v = t.split()
        p = (np.array(v[1:], float).reshape(-1, 2) * [w, h]).astype(np.int32)
        lap = np.zeros((h, w), np.uint8)
        cv2.fillPoly(lap, [p], 1)
        seg[lap > 0] = WARNA_SEG[int(v[0])]
    seg = cv2.addWeighted(seg, 0.45, img, 0.55, 0)
    kt = img.copy()
    for k, b in kotak_baris:
        x1, y1, x2, y2 = map(int, b)
        cv2.rectangle(kt, (x1, y1), (x2, y2), WARNA_KOTAK[k], 8)
        cv2.putText(kt, KELAS_KOTAK[k], (x1 + 6, y1 + 50), cv2.FONT_HERSHEY_SIMPLEX, 1.6, WARNA_KOTAK[k], 4)
    tw = 220
    th = int(tw * h / w)
    return np.hstack([cv2.resize(seg, (tw, th)), cv2.resize(kt, (tw, th))])


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="Pseudo-label frame kampus: segmentasi (jalur, jalan, tangga) dan kotak.")
    ap.add_argument("input", nargs="*", help="file atau folder gambar")
    ap.add_argument("--semua-training", action="store_true", help="semua frame di data/frame-blur kecuali lokasi test")
    ap.add_argument("--out", required=True, help="folder output")
    ap.add_argument("--seg-model", default="nvidia/segformer-b5-finetuned-ade-640-640")
    ap.add_argument("--coco-model", default="yolo11x-seg.pt")
    ap.add_argument("--conf", type=float, default=0.35, help="confidence minimum COCO (default 0.35)")
    ap.add_argument("--device", default="0", help="0 untuk GPU, cpu untuk CPU")
    ap.add_argument("--preview", type=int, default=60)
    a = ap.parse_args()

    files = kumpulkan(a)
    if not files:
        print("Tidak ada gambar.")
        return 1
    if any(f.name.startswith(TEST) for f in files):
        print("BERHENTI: ada gambar lokasi test di input. Data test tidak boleh dipakai training.")
        return 1

    import torch
    from transformers import AutoImageProcessor, SegformerForSemanticSegmentation
    from ultralytics import YOLO
    dev = "cpu" if a.device == "cpu" or not torch.cuda.is_available() else f"cuda:{a.device}"
    proc = AutoImageProcessor.from_pretrained(a.seg_model)
    segm = SegformerForSemanticSegmentation.from_pretrained(a.seg_model).to(dev).eval()
    id2 = segm.config.id2label
    n_ade = len(id2)

    lut_seg = np.full(n_ade, 255, np.uint8)
    print("Pemetaan ADE20K:")
    for nama, k in ADE_SEG.items():
        for i in id_ade(id2, {nama}):
            lut_seg[i] = k
            print(f"   {i:3d} {id2[i]!r:26s} -> seg {KELAS_SEG[k]}")
    def lut_dari(nama):
        l = np.zeros(n_ade, bool)
        ids = id_ade(id2, nama)
        l[ids] = True
        print(f"   {ids} {[id2[i] for i in ids]} -> {sorted(nama)}")
        return l
    lut_pilar, lut_tangga, lut_pot, lut_pohon = (lut_dari(ADE_PILAR), lut_dari(ADE_TANGGA),
                                                 lut_dari(ADE_POT), lut_dari(ADE_POHON))

    coco = YOLO(a.coco_model)
    target = [i for i, n in coco.names.items() if n in COCO_KOTAK]
    yolo_dev = "cpu" if dev == "cpu" else int(a.device)
    print(f"Device: {dev} | {len(files)} gambar -> {a.out}")

    out = Path(a.out)
    for sub in ("seg/images", "seg/labels", "kotak/images", "kotak/labels", "preview"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    tiap = max(1, len(files) // max(1, a.preview))
    contoh, baris, dikeluarkan, baru = [], [], [], 0
    hitung = np.zeros(len(KELAS_KOTAK), int)

    for n, f in enumerate(files):
        lbl_seg = out / "seg" / "labels" / (f.stem + ".txt")
        if lbl_seg.exists():
            continue
        img = cv2.imread(str(f))
        h, w = img.shape[:2]
        min_sisi = MIN_SISI_640 * max(h, w) / 640

        # SegFormer
        with torch.no_grad():
            x = proc(images=cv2.cvtColor(img, cv2.COLOR_BGR2RGB), return_tensors="pt").to(dev)
            lg = torch.nn.functional.interpolate(segm(**x).logits, size=(h, w), mode="bilinear", align_corners=False)
            ade = lg.argmax(1)[0].cpu().numpy().astype(np.int32)

        # COCO
        r = coco.predict(str(f), conf=a.conf, imgsz=1280, classes=target, device=yolo_dev,
                         retina_masks=True, verbose=False)[0]
        coco_box, coco_mask = [], np.zeros((h, w), np.uint8)
        if r.boxes is not None and len(r.boxes):
            for i, (c, b) in enumerate(zip(r.boxes.cls.tolist(), r.boxes.xyxy.tolist())):
                coco_box.append((COCO_KOTAK[coco.names[int(c)]], b))
            if r.masks is not None:
                coco_mask = (r.masks.data.cpu().numpy().max(0) > 0.5).astype(np.uint8)
                if coco_mask.shape != (h, w):
                    coco_mask = cv2.resize(coco_mask, (w, h), interpolation=cv2.INTER_NEAREST)

        # --- segmentasi ---
        kelas = lut_seg[ade]
        kelas[coco_mask > 0] = 255          # orang/kendaraan/kursi/pot COCO juga jadi lubang
        if f.name.startswith(LOKASI_JALAN_KENDARAAN):
            kelas[kelas == 0] = 1
        seg_teks, luas = [], []
        for k in range(len(KELAS_SEG)):
            m = (kelas == k).astype(np.uint8)
            luas.append(round(100 * m.mean(), 1))
            for poly in mask_ke_polygon(m):
                seg_teks.append(f"{k} " + " ".join(f"{px / w:.5f} {py / h:.5f}" for px, py in poly))
        taut(f, out / "seg" / "images" / f.name)
        lbl_seg.write_text("\n".join(seg_teks) + ("\n" if seg_teks else ""), encoding="utf-8")

        # --- kotak ---
        pot_mask = lut_pot[ade].astype(np.uint8)
        kotak = []
        for k, b in coco_box:
            if k == 4:
                b = perluas_pot(b, pot_mask)
            if min(b[2] - b[0], b[3] - b[1]) >= min_sisi:
                kotak.append((k, b))
        for b in kotak_dari_mask(lut_pilar[ade].astype(np.uint8), min_sisi):
            kotak.append((0, b))
        for b in kotak_dari_mask(lut_tangga[ade].astype(np.uint8), min_sisi):
            kotak.append((7, b))
        persen_pohon = round(100 * lut_pohon[ade].mean(), 1)
        masuk_kotak = persen_pohon < 100 * BATAS_POHON
        if masuk_kotak:
            taut(f, out / "kotak" / "images" / f.name)
            teks = [f"{k} {(b[0] + b[2]) / 2 / w:.5f} {(b[1] + b[3]) / 2 / h:.5f} {(b[2] - b[0]) / w:.5f} {(b[3] - b[1]) / h:.5f}"
                    for k, b in kotak]
            (out / "kotak" / "labels" / (f.stem + ".txt")).write_text("\n".join(teks) + ("\n" if teks else ""), encoding="utf-8")
            for k, _ in kotak:
                hitung[k] += 1
        else:
            dikeluarkan.append(f"{f.name}\tpohon {persen_pohon}%")

        baris.append([f.name, *luas, persen_pohon, len(seg_teks), len(kotak), int(masuk_kotak)])
        baru += 1
        if n % tiap == 0 and len(contoh) < a.preview:
            v = preview(img, seg_teks, kotak, w, h)
            cv2.putText(v, f.stem[:34], (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
            contoh.append(v)
        if baru % 100 == 0:
            print(f"   {baru} gambar selesai")

    if contoh:
        hmax = max(c.shape[0] for c in contoh)
        contoh = [cv2.copyMakeBorder(c, 0, hmax - c.shape[0], 0, 4, cv2.BORDER_CONSTANT) for c in contoh]
        for s in range(0, len(contoh), 5):
            row = contoh[s:s + 5] + [np.zeros_like(contoh[0])] * (5 - len(contoh[s:s + 5]))
            cv2.imwrite(str(out / "preview" / f"preview_{s // 5 + 1:02d}.jpg"), np.hstack(row))

    ring = out / "ringkasan.csv"
    baru_file = not ring.exists()
    with ring.open("a", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        if baru_file:
            wr.writerow(["filename", "persen_jalur_jalan", "persen_jalan_kendaraan", "persen_tangga",
                         "persen_pohon", "polygon_seg", "kotak", "masuk_dataset_kotak"])
        wr.writerows(baris)
    with (out / "kotak" / "dikeluarkan.txt").open("a", encoding="utf-8") as fh:
        fh.writelines(x + "\n" for x in dikeluarkan)
    for sub, kls in (("seg", KELAS_SEG), ("kotak", KELAS_KOTAK)):
        (out / sub / "data.yaml").write_text(
            f"path: {(out / sub).resolve().as_posix()}\ntrain: images\nval: images\nnames:\n"
            + "".join(f"  {i}: {k}\n" for i, k in enumerate(kls)), encoding="utf-8")

    print(f"\n== SELESAI: {baru} gambar baru")
    print(f"   Dataset kotak: {baru - len(dikeluarkan)} gambar, {len(dikeluarkan)} dikeluarkan karena ada pohon")
    print("   Jumlah kotak per kelas (run ini):")
    for k, nama in enumerate(KELAS_KOTAK):
        print(f"     {nama:12s}: {hitung[k]}" + ("   (tidak diotomasi, dari dataset publik)" if nama in ("pohon", "tepian") else ""))
    print(f"   Cek preview di {out / 'preview'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
