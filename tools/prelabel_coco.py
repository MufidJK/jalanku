"""prelabel_coco.py - bikin draf label polygon untuk X-AnyLabeling pakai YOLO segmentasi COCO.

Model COCO hanya kenal sebagian kelas JalanKu. Yang dipetakan:
  person -> orang
  bicycle, car, motorcycle, bus, truck -> kendaraan
  chair, bench -> kursi
  potted plant -> tanaman_pot
Kelas lain (pilar, pohon, tepian, jalur_jalan, jalan_kendaraan, tangga) tetap dilabel manual pakai SAM.

Hasilnya file .json di sebelah tiap gambar (format X-AnyLabeling), jadi tinggal buka folder
gambarnya di X-AnyLabeling lalu koreksi. Semua shape hasil script ini diberi description
"prelabel-coco" supaya bisa dibedakan dari label manual.

Gambar yang sudah punya .json DILEWATI (label manual tidak tertimpa), kecuali pakai --overwrite.

Objek yang terlalu kecil dibuang mengikuti docs/kelas.md: sisi terpendek kotaknya kurang dari
32 piksel kalau gambar diperkecil jadi 640 (untuk frame 1080x1920 artinya kurang dari 96 piksel).

Contoh pemakaian:
  python tools/prelabel_coco.py data/pilot/images --device 0
  python tools/prelabel_coco.py data/pilot/images --model yolo11x-seg.pt --conf 0.4
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

COCO_KE_JALANKU = {
    "person": "orang",
    "bicycle": "kendaraan",
    "car": "kendaraan",
    "motorcycle": "kendaraan",
    "bus": "kendaraan",
    "truck": "kendaraan",
    "chair": "kursi",
    "bench": "kursi",
    "potted plant": "tanaman_pot",
}
IMG_EXT = {".jpg", ".jpeg", ".png"}
MIN_SISI_640 = 32        # aturan objek terlalu kecil di docs/kelas.md
VERSI_XANY = "4.3.1"


def sederhanakan(poly: np.ndarray) -> list[list[float]]:
    """Kurangi jumlah titik polygon supaya gampang diedit, bentuk tetap mengikuti objek."""
    c = poly.reshape(-1, 1, 2).astype(np.float32)
    eps = max(1.0, 0.004 * cv2.arcLength(c, True))
    s = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
    if len(s) < 3:
        s = poly
    return [[round(float(x), 1), round(float(y), 1)] for x, y in s]


def shape(label: str, points: list, score: float) -> dict:
    return {
        "review_status": "pending",
        "label": label,
        "score": round(score, 3),
        "points": points,
        "group_id": None,
        "description": "prelabel-coco",
        "difficult": False,
        "shape_type": "polygon",
        "flags": {},
        "attributes": {},
        "kie_linking": [],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Draf label polygon (orang, kendaraan, kursi, tanaman_pot) untuk X-AnyLabeling.")
    p.add_argument("folder", help="folder berisi gambar")
    p.add_argument("--model", default="yolo11x-seg.pt", help="bobot YOLO segmentasi COCO (default: yolo11x-seg.pt, otomatis di-download)")
    p.add_argument("--conf", type=float, default=0.35, help="confidence minimum (default: 0.35)")
    p.add_argument("--imgsz", type=int, default=1280, help="ukuran input model (default: 1280)")
    p.add_argument("--device", default=None, help="0 untuk GPU pertama, cpu untuk CPU (default: otomatis)")
    p.add_argument("--overwrite", action="store_true", help="timpa .json yang sudah ada (HATI-HATI: label manual hilang)")
    a = p.parse_args()

    folder = Path(a.folder)
    gambar = sorted(f for f in folder.iterdir() if f.suffix.lower() in IMG_EXT)
    if not gambar:
        print(f"Tidak ada gambar di {folder}")
        return 1

    from ultralytics import YOLO
    model = YOLO(a.model)
    nama = model.names
    target = [i for i, n in nama.items() if n in COCO_KE_JALANKU]

    hitung, dilewati, kecil, ditulis = Counter(), 0, 0, 0
    for f in gambar:
        out = f.with_suffix(".json")
        if out.exists() and not a.overwrite:
            dilewati += 1
            continue
        r = model.predict(str(f), conf=a.conf, imgsz=a.imgsz, classes=target, device=a.device,
                          retina_masks=True, verbose=False)[0]
        h, w = r.orig_shape
        min_sisi = MIN_SISI_640 * max(h, w) / 640
        shapes = []
        if r.masks is not None:
            for poly, cls, conf, box in zip(r.masks.xy, r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
                if len(poly) < 3:
                    continue
                if min(box[2] - box[0], box[3] - box[1]) < min_sisi:
                    kecil += 1
                    continue
                label = COCO_KE_JALANKU[nama[int(cls)]]
                shapes.append(shape(label, sederhanakan(poly), conf))
                hitung[label] += 1
        data = {"version": VERSI_XANY, "flags": {}, "checked": False, "shapes": shapes,
                "imagePath": f.name, "imageData": None, "imageHeight": h, "imageWidth": w}
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        ditulis += 1
        print(f"{f.name}: {len(shapes)} objek")

    print("\n== TOTAL")
    print(f"   JSON ditulis      : {ditulis}")
    print(f"   Dilewati (ada JSON): {dilewati}")
    print(f"   Objek terlalu kecil: {kecil} (dibuang)")
    for k in ("orang", "kendaraan", "kursi", "tanaman_pot"):
        print(f"   {k:12s}: {hitung[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
