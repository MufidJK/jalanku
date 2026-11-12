"""autolabel_v2.py - label otomatis lengkap (10 kelas) frame kampus, output JSON X-AnyLabeling.

Beda dengan autolabel_kampus.py: semua kelas dilabel (termasuk pilar, pohon, tepian), hasilnya
polygon yang bisa direview di X-AnyLabeling, bukan dataset YOLO langsung.

Model (semua lokal):
  SegFormer-B5 ADE20K      : peta permukaan, juga konfirmasi kelas lain
  YOLO11x-seg COCO         : orang, kendaraan, kursi, tanaman_pot
  Grounding DINO base      : kandidat pilar, pohon, tepian, tanaman_pot, tangga, kursi gelap, eskalator
  SAM 2.1 base-plus        : mask dari kotak GDINO, dan perluasan area permukaan

GDINO sendirian tidak bisa dipercaya (staircase nyangkut di zebra cross, tree trunk di kolom
marmer), jadi tiap kelas punya syarat tambahan dari ADE dan bentuk mask. Lihat fungsi saring_*.

Permukaan: lantai dan jalan digabung dulu lalu dibagi per area (SAM), kelasnya ditentukan per area
utuh, bukan per piksel, supaya tidak belang. Di lokasi campuran (LOKASI_CAMPURAN) kelas ditentukan
dari bukti visual:
  jalan_kendaraan : ada kendaraan di atasnya, ada marka, atau ADE road dominan
  jalur_jalan     : ADE bukan road, tidak ada tanda kendaraan, tidak menempel area jalan_kendaraan
  ambigu          : jalan_kendaraan + flag perlu_cek "permukaan ambigu"

Keamanan data:
  - JSON yang sudah ada tidak pernah ditimpa (frame dilewati, jadi aman dijalankan ulang).
  - Lokasi test ditolak, kecuali --izin-test dan --out berada di data/test-review.
  - Gambar di output adalah hard link. data/frame-blur hanya dibaca.

Contoh pemakaian:
  python tools/autolabel_v2.py data/pilot/images --out data/pilot-v2 --device 0
  python tools/autolabel_v2.py --daftar frame.txt --out data/pilot-v2-tune --cache cache_dir
  python tools/autolabel_v2.py --semua-training --out data/auto-kampus-v2 --device 0
"""

import argparse
import csv
import json
import pickle
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from autolabel_kampus import _gabung_lubang, _rapikan, taut  # noqa: E402

KELAS = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan",
         "jalur_jalan", "jalan_kendaraan", "tangga"]
TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
IMG_EXT = {".jpg", ".jpeg", ".png"}
VERSI_XANY = "4.3.1"

M_SEG = "nvidia/segformer-b5-finetuned-ade-640-640"
M_GDINO = "IDEA-Research/grounding-dino-base"
M_SAM = "facebook/sam2.1-hiera-base-plus"

# Lokasi: selain dua daftar ini, semua permukaan jalur_jalan.
LOKASI_SEMUA_JALAN = ("parkiran-motor-b1",)
LOKASI_CAMPURAN = ("dapsut", "samping-ubm", "jalanan-ubm")
LOKASI_TANGGA = ("tangga-naik",)
LOKASI_LUAR = ("dapsut", "samping-ubm", "jalanan-ubm", "halaman-ubm") + ("taman-ubm",)   # taman-ubm: lokasi test (Stage 6), tidak ada di training

PROMPT = {
    "pilar": "pillar. column. pole. lamp post. bollard.",
    "pohon": "tree trunk.",
    "tepian": "curb. step edge.",
    "pot": "potted plant. planter box.",
    "tangga": "staircase.",
    "kursi": "office chair. stool.",
    "eskalator": "escalator.",
    "marka": "zebra crossing. road arrow marking.",
    "orang": "person.",
    "kendaraan": "motorcycle. car. bicycle.",
    "pagarkaca": "glass railing. handrail.",
}
PROMPT_TILE = ("pilar", "pohon", "tepian", "pot", "tangga", "kursi", "orang", "kendaraan")
GDINO_MIN = 0.15                       # disimpan ke cache, disaring lagi per kelas di T
YOLO_MIN = 0.10
TILE_TINGGI, TILE_JUMLAH = 800, 3      # 3 potongan 1080x800, overlap 240 px di frame 1920

# Threshold per kelas (hasil tuning dicatat di LOG.md)
T = {
    "pilar": 0.35, "pilar_tinggi": 0.30, "pilar_besar": 0.24, "pohon": 0.30, "tepian": 0.35, "tepian_dalam": 0.50, "pot": 0.40,
    "tangga": 0.30, "tangga_luar": 0.45, "tangga_lokasi": 0.30,
    "kursi": 0.40, "eskalator": 0.40, "marka": 0.30,
    "yolo_orang": 0.35, "yolo_kendaraan": 0.30, "yolo_kursi": 0.25, "yolo_pot": 0.30,
}
# Batas bawah kandidat. Di antara batas ini dan T + RAGU: tetap masuk JSON sebagai difficult: true.
BATAS_YOLO = {"orang": 0.12, "kendaraan": 0.12, "kursi": 0.15, "tanaman_pot": 0.15}
BATAS_GDINO = {"pilar": 0.25, "pohon": 0.25, "tepian": 0.25, "tepian_dalam": 0.42, "pot": 0.28, "kursi": 0.30,
               "orang": 0.30, "kendaraan": 0.30}
# Lokasi lab: kaki meja dan sekat terbaca pilar/kursi/orang. Dicek ke inventaris_objek.csv (lihat LOG.md).
LOKASI_LAB = ("lab-iota1", "lab1-lt5")
LOKASI_ORANG_KETAT = LOKASI_LAB + ("alfamart",)   # orang lemah wajib didukung ADE person atau kepala pixelate
T_LAB = {"pilar": 0.45, "kursi": 0.60, "orang": 0.42}
ORANG_LEMAH = 0.40                     # di lab dan alfamart: orang di bawah skor ini wajib didukung ADE person atau kepala pixelate
TEKSTUR_BETON = 0.055                  # porsi piksel tepi Canny; paving bata jauh di atas ini
SEGMEN_TEPIAN = 300                    # panjang maksimal satu polygon tepian (px)
DIBUANG = []                           # catatan objek yang dibuang aturan, ditulis ke dibuang_aturan.csv
MAKS_KANDIDAT = 20                     # per kelas per frame, supaya review tidak banjir
RAGU = 0.10                            # skor < T + RAGU diberi difficult: true
MIN_SISI = 96                          # objek biasa: sisi terpendek (px di frame 1080x1920)
TIPIS_PANJANG, TIPIS_PENDEK = 96, 24   # pilar, pohon, tepian: disetujui Jeka, masuk kelas.md v1.5
MIN_LUAS_SURFACE = 0.005
MIN_LUBANG = 0.002
MAX_AREA_SEED = 8

COCO = {"person": "orang", "bicycle": "kendaraan", "car": "kendaraan", "motorcycle": "kendaraan",
        "bus": "kendaraan", "truck": "kendaraan", "chair": "kursi", "bench": "kursi",
        "potted plant": "tanaman_pot"}

ADE = {
    "lantai": {"floor", "sidewalk", "path", "rug", "road"},
    "road": {"road"},
    "tangga": {"stairs", "stairway", "step"},
    "eskalator": {"escalator"},
    "tiang": {"column", "pole"},
    "pohon": {"tree", "palm"},
    "pot": {"pot", "flowerpot", "vase", "plant"},
    "kursi": {"chair", "armchair", "swivel", "bench", "seat", "ottoman", "stool", "sofa"},
    "pagar": {"railing", "fence", "bannister"},
    "larang": {"wall", "sky", "building", "ceiling", "grass", "plant", "tree", "fence", "railing",
               "bannister", "door", "windowpane", "glass", "mountain", "water", "cabinet", "shelf",
               "escalator", "earth", "field", "ashcan", "signboard", "bookcase", "counter"},
    "kaca": {"windowpane", "door", "glass", "mirror", "painting", "poster"},
    "sampah": {"ashcan"},
    "pot_asli": {"pot", "flowerpot", "vase"},
    "orang": {"person"},
    "rumput": {"grass", "field"},
    "dinding": {"wall"},
    "trotoar": {"sidewalk"},
    "cadang": {"base", "stage"},
}

BOBOT_ALASAN = {"outdoor 0 pilar 0 tepian": 5, "lantai balik kaca": 4, "permukaan ambigu": 3, "pohon perlu cek": 3,
                "coco orang": 3, "coco kendaraan": 3, "frame tanpa objek": 3, "lokasi tangga tanpa tangga": 3,
                "tepian kandidat": 2, "trotoar dari ade": 3, "lantai kecil dibuang": 1, "tajuk dipotong": 1}

WARNA = {"pilar": (255, 0, 255), "pohon": (0, 128, 255), "tepian": (0, 255, 255), "orang": (0, 255, 0),
         "tanaman_pot": (255, 255, 0), "kursi": (0, 165, 255), "kendaraan": (255, 80, 80),
         "jalur_jalan": (80, 220, 80), "jalan_kendaraan": (60, 60, 255), "tangga": (255, 160, 0)}


# ---------- tile ----------

def tile_y(h):
    """Batas vertikal tile, overlap merata."""
    if h <= TILE_TINGGI:
        return []
    langkah = (h - TILE_TINGGI) / (TILE_JUMLAH - 1)
    return [(int(i * langkah), int(i * langkah) + TILE_TINGGI) for i in range(TILE_JUMLAH)]


def kena_seam(b, y0, tinggi, h):
    """Kotak menyentuh batas potongan di dalam frame, berarti objeknya mungkin terpotong oleh tile."""
    return (y0 > 0 and b[1] <= y0 + 4) or (y0 + tinggi < h and b[3] >= y0 + tinggi - 4)


# ---------- model ----------

class Model:
    def __init__(self, a):
        import torch
        from transformers import AutoConfig, Sam2Model, Sam2Processor
        self.torch = torch
        self.dev = "cpu" if a.device == "cpu" or not torch.cuda.is_available() else f"cuda:{a.device}"
        self.yolo_dev = "cpu" if self.dev == "cpu" else int(a.device)
        self.a, self.seg = a, None
        self.sam_p = Sam2Processor.from_pretrained(M_SAM)
        self.sam = Sam2Model.from_pretrained(M_SAM).to(self.dev).eval()
        self.id2 = AutoConfig.from_pretrained(M_SEG).id2label

    def _muat(self):
        if self.seg is not None:
            return
        from transformers import (AutoImageProcessor, AutoModelForZeroShotObjectDetection, AutoProcessor,
                                  SegformerForSemanticSegmentation)
        from ultralytics import YOLO
        self.seg_p = AutoImageProcessor.from_pretrained(M_SEG)
        self.seg = SegformerForSemanticSegmentation.from_pretrained(M_SEG).to(self.dev).eval()
        self.gd_p = AutoProcessor.from_pretrained(M_GDINO)
        self.gd = AutoModelForZeroShotObjectDetection.from_pretrained(M_GDINO).to(self.dev).eval()
        self.coco = YOLO(self.a.coco_model)
        self.coco_ids = [i for i, n in self.coco.names.items() if n in COCO]

    def ade(self, rgb):
        self._muat()
        t = self.torch
        h, w = rgb.shape[:2]
        with t.no_grad():
            x = self.seg_p(images=rgb, return_tensors="pt").to(self.dev)
            lg = t.nn.functional.interpolate(self.seg(**x).logits, size=(h, w), mode="bilinear", align_corners=False)
        return lg.argmax(1)[0].cpu().numpy().astype(np.uint8)

    def _yolo1(self, img, dy, tile, h):
        r = self.coco.predict(img, conf=YOLO_MIN, imgsz=1280, classes=self.coco_ids, device=self.yolo_dev,
                              retina_masks=True, verbose=False)[0]
        out = []
        if r.masks is not None:
            for poly, c, sk, b in zip(r.masks.xy, r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
                if len(poly) >= 3:
                    b = [b[0], b[1] + dy, b[2], b[3] + dy]
                    out.append({"kelas": COCO[self.coco.names[int(c)]], "skor": float(sk), "box": b, "tile": tile,
                                "seam": kena_seam(b, dy, img.shape[0], h),
                                "poly": np.asarray(poly, np.float32) + np.array([0, dy], np.float32)})
        return out

    def yolo(self, img):
        self._muat()
        h = img.shape[0]
        out = self._yolo1(img, 0, None, h)
        for i, (y0, y1) in enumerate(tile_y(h)):
            out += self._yolo1(np.ascontiguousarray(img[y0:y1]), y0, i, h)
        return out

    def _gdino1(self, pil, teks):
        t = self.torch
        x = self.gd_p(images=pil, text=teks, return_tensors="pt").to(self.dev)
        with t.no_grad():
            o = self.gd(**x)
        r = self.gd_p.post_process_grounded_object_detection(
            o, x.input_ids, threshold=GDINO_MIN, text_threshold=0.12, target_sizes=[pil.size[::-1]])[0]
        return list(zip(r["boxes"].tolist(), r["scores"].tolist(), r.get("text_labels", r.get("labels"))))

    def gdino(self, pil):
        self._muat()
        h = pil.size[1]
        out = {}
        for k, teks in PROMPT.items():
            out[k] = [{"box": b, "skor": sk, "teks": l, "tile": None, "seam": False} for b, sk, l in self._gdino1(pil, teks)]
        for i, (y0, y1) in enumerate(tile_y(h)):
            c = pil.crop((0, y0, pil.size[0], y1))
            for k in PROMPT_TILE:
                for b, sk, l in self._gdino1(c, PROMPT[k]):
                    b = [b[0], b[1] + y0, b[2], b[3] + y0]
                    out[k].append({"box": b, "skor": sk, "teks": l, "tile": i, "seam": kena_seam(b, y0, y1 - y0, h)})
        return out


class Sam:
    """Encoder SAM dijalankan sekali per gambar, prompt dijalankan berkali-kali."""

    def __init__(self, m: Model, pil):
        self.m, self.pil = m, pil
        px = m.sam_p(images=pil, return_tensors="pt").to(m.dev)
        with m.torch.no_grad():
            self.emb = m.sam.get_image_embeddings(px["pixel_values"])

    def _jalan(self, multi, **prompt):
        m = self.m
        x = m.sam_p(images=self.pil, return_tensors="pt", **prompt).to(m.dev)
        x.pop("pixel_values")
        ukuran = x.pop("original_sizes")
        x.pop("reshaped_input_sizes", None)
        with m.torch.no_grad():
            o = m.sam(image_embeddings=self.emb, multimask_output=multi, **x)
        mk = m.sam_p.post_process_masks(o.pred_masks.cpu(), ukuran.cpu())[0]
        return mk.numpy() > 0, o.iou_scores.float().cpu().numpy().reshape(mk.shape[0], -1)

    def boxes(self, bx):
        out = []
        for i in range(0, len(bx), 8):
            mk, _ = self._jalan(False, input_boxes=[[list(map(float, b)) for b in bx[i:i + 8]]])
            out += [mk[j, 0] for j in range(mk.shape[0])]
        return out

    def titik(self, x, y):
        mk, sc = self._jalan(True, input_points=[[[[float(x), float(y)]]]], input_labels=[[[1]]])
        return mk[0], sc[0]


# ---------- util ----------

def lut(id2, nama):
    l = np.zeros(256, bool)
    for i, n in id2.items():
        if n.strip().lower().replace(";", " ").replace(",", " ").split()[0] in nama:
            l[int(i)] = True
    return l


def box_mask(m):
    ys, xs = np.nonzero(m)
    return None if len(xs) == 0 else [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)]


def iou_box(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    aa, ab = (a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])
    return i / max(1e-6, aa + ab - i), i / max(1e-6, min(aa, ab))


def nms(c, iou=0.5, isi=0.8):
    """c: list dict dengan box, skor. Dipertahankan yang skornya tertinggi."""
    out = []
    for d in sorted(c, key=lambda v: -v["skor"]):
        if all(iou_box(d["box"], o["box"])[0] < iou and iou_box(d["box"], o["box"])[1] < isi for o in out):
            out.append(d)
    return out


def gabung(c, iou=0.5, isi=0.8, rasio_lebar=None, telan=True):
    """Gabung kotak sekelas. Kotak terbesar yang dipertahankan (potongan tile terpotong tidak menang),
    skornya diambil yang tertinggi. rasio_lebar: kotak jauh lebih lebar tidak boleh menelan yang sempit."""
    out = []
    for d in sorted(c, key=lambda v: -(v["box"][2] - v["box"][0]) * (v["box"][3] - v["box"][1])):
        for o in out:
            i, n = iou_box(d["box"], o["box"])
            lebar_o, lebar_d = o["box"][2] - o["box"][0], d["box"][2] - d["box"][0]
            luas_o = lebar_o * (o["box"][3] - o["box"][1])
            luas_d = lebar_d * (d["box"][3] - d["box"][1])
            boleh = telan or d.get("seam") or luas_o <= 2 * luas_d
            if i >= iou or (n >= isi and boleh and not (rasio_lebar and lebar_o > rasio_lebar * lebar_d)):
                o["skor"] = max(o["skor"], d["skor"])
                break
        else:
            out.append(dict(d))
    return out


def luas_box(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def wadah(b, semua):
    """Kotak yang berisi dua kotak sekelas atau lebih yang lebih kecil, misalnya satu kotak menutup dua mobil (13)."""
    return sum(1 for o in semua if o is not b and luas_box(o) <= 0.7 * luas_box(b) and iou_box(b, o)[1] >= 0.7) >= 2


def kepala_blur(gray, box):
    """extract_frames.py mempixelate 40% atas badan, dan YOLO berhenti tepat di bawah blok itu, jadi tinggi
    kepala = 2/3 tinggi kotak. Area itu harus benar-benar pixelate: rata tapi punya tepi blok. Return kotak area."""
    x1, y1, x2, y2 = box
    if y1 < 10:
        return None
    ya, yb, xa, xb = int(max(0, y1 - 0.667 * (y2 - y1))), int(y1) - 2, int(x1), int(x2)
    if yb - ya < 16 or xb - xa < 16:
        return None
    g = gray[ya:yb, xa:xb].astype(np.int16)
    gx, gy = np.abs(g[:, 1:] - g[:, :-1])[:-1], np.abs(g[1:, :] - g[:-1, :])[:, :-1]
    if ((gx <= 2) & (gy <= 2)).mean() >= 0.8 and ((gx > 6) | (gy > 6)).mean() >= 0.02:
        return [float(xa), float(ya), float(xb), float(y1) + 2]
    return None


def pecah_garis(m):
    """Mask tepian panjang dipecah sepanjang sumbu utamanya supaya kotak tiap segmen tetap rapat."""
    ys, xs = np.nonzero(m)
    if len(xs) < 50:
        return []
    p = np.stack([xs, ys], 1).astype(np.float64)
    p -= p.mean(0)
    v = np.linalg.eigh(np.cov(p.T))[1][:, 1]
    t = p @ v
    n = int(np.ceil((t.max() - t.min()) / SEGMEN_TEPIAN))
    if n <= 1:
        return [m]
    batas = np.linspace(t.min(), t.max() + 1e-6, n + 1)
    out = []
    for i in range(n):
        q = np.zeros_like(m)
        sel = (t >= batas[i]) & (t < batas[i + 1])
        q[ys[sel], xs[sel]] = True
        if q.sum() >= 200:
            out.append(q)
    return out


def kerb_di_atas(c, img):
    """Trotoar hanya sah kalau materialnya beda dari jalan (beton halus, bukan paving bata) dan batas atasnya
    kerb cat belang (29). Selain itu tetap ambigu, jadi tetap jalan_kendaraan. Return mask pita kerb atau None."""
    h, w = c.shape
    xs = np.nonzero(c.any(0))[0]
    if len(xs) < 0.5 * w:
        return None
    y = int(np.median(c.argmax(0)[xs]))
    if y < 0.5 * h:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    inti = cv2.erode(c.astype(np.uint8), np.ones((41, 41), np.uint8)) > 0
    if not inti.any() or (cv2.Canny(gray, 50, 150)[inti] > 0).mean() > TEKSTUR_BETON:
        return None
    for yc in range(y - 30, min(h - 30, y + 110), 10):          # zebra di atasnya rata selebar frame, kerb bergantian
        pita = gray[max(0, yc - 15):yc + 15, xs]
        gelap = (pita < 125).mean(0) >= 0.6
        terang = (pita > 200).mean(0) >= 0.6
        if not 0.15 <= gelap.mean() <= 0.7 or terang.mean() < 0.2 or (gelap | terang).mean() < 0.75:
            continue
        ganti = np.flatnonzero(np.diff(gelap.astype(np.int8)))
        if len(ganti) >= 2:
            out = np.zeros((h, w), bool)
            out[max(0, yc - 30):yc + 30, xs] = True
            return out
    return None


def sambung_vertikal(c):
    """Tiang atau batang yang terpotong batas tile disambung lagi."""
    c = [dict(d) for d in c]
    ubah = True
    while ubah:
        ubah = False
        for i in range(len(c)):
            for j in range(i + 1, len(c)):
                a, b = c[i], c[j]
                if not (a.get("seam") or b.get("seam")):
                    continue
                x = min(a["box"][2], b["box"][2]) - max(a["box"][0], b["box"][0])
                lebar = min(a["box"][2] - a["box"][0], b["box"][2] - b["box"][0])
                celah = max(a["box"][1], b["box"][1]) - min(a["box"][3], b["box"][3])
                if x >= 0.5 * lebar and celah < 60:
                    a["box"] = [min(a["box"][0], b["box"][0]), min(a["box"][1], b["box"][1]),
                                max(a["box"][2], b["box"][2]), max(a["box"][3], b["box"][3])]
                    a["skor"] = max(a["skor"], b["skor"])
                    a["seam"] = False
                    del c[j]
                    ubah = True
                    break
            if ubah:
                break
    return c


def isi_box(ade_l, b):
    x1, y1, x2, y2 = (int(max(0, v)) for v in b)
    s = ade_l[y1:y2, x1:x2]
    return float(s.mean()) if s.size else 0.0


def lolos_ukuran(b, tipis):
    w, h = b[2] - b[0], b[3] - b[1]
    if tipis:
        return max(w, h) >= TIPIS_PANJANG and min(w, h) >= TIPIS_PENDEK
    return min(w, h) >= MIN_SISI


def poly_ke_mask(poly, h, w):
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [poly.astype(np.int32)], 1)
    return m > 0


def rapikan_komponen(m, min_luas):
    """Komponen terbesar + semua yang >= min_luas piksel."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    return [lab == i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= min_luas]


def potong_batang(m):
    """Buang tajuk: dari bawah ke atas, simpan baris selama lebarnya masih wajar (<= 1.8x median bawah)."""
    ys = np.nonzero(m.any(1))[0]
    if len(ys) < 10:
        return m, False
    lebar = m[ys].sum(1)
    n3 = max(5, len(ys) // 3)
    acuan = max(8.0, float(np.median(lebar[-n3:])))
    out = m.copy()
    potong = False
    for i in range(len(ys) - 1, -1, -1):
        if lebar[i] > 1.8 * acuan:
            out[: ys[i] + 1] = False
            potong = True
            break
    return out, potong


def rasio_memanjang(m):
    c, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not c:
        return 0.0
    (_, _), (a, b), _ = cv2.minAreaRect(max(c, key=cv2.contourArea))
    return max(a, b) / max(1.0, min(a, b))


# ---------- saring per kelas ----------

def saring_pilar(g, L, orang, W, H):
    out = []
    for d in g["pilar"]:
        b = d["box"]
        w, h = b[2] - b[0], b[3] - b[1]
        besar = h >= 0.5 * H and 0.2 * W <= w <= 0.65 * W       # kolom besar di depan kamera (178, 199)
        if h < 1.3 * w and not besar:
            continue
        if d["skor"] < (T["pilar_besar"] if besar else BATAS_GDINO["pilar"]) or w > 0.65 * W:
            continue
        if any(iou_box(b, o)[1] > 0.5 for o in orang):
            continue
        out.append({**d, "src": "gdino+sam", "besar": besar})
    return out


def umpak(g, orang):
    """Umpak tiang (kasus b): kotak pendek-lebar, dipakai hanya kalau menempel di bawah tiang."""
    return [d for d in g["pilar"] if d["skor"] >= 0.28 and d["tile"] is None
            and (d["box"][3] - d["box"][1]) < 2.2 * (d["box"][2] - d["box"][0])
            and all(iou_box(d["box"], o)[1] < 0.5 for o in orang)]


def kandidat_tiang_ade(L):
    n, _, st, _ = cv2.connectedComponentsWithStats(
        cv2.morphologyEx(L["tiang"].astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)), 8)
    out = []
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        if h >= 1.5 * w and h >= TIPIS_PANJANG and w >= TIPIS_PENDEK:
            out.append({"box": [float(x), float(y), float(x + w), float(y + h)], "skor": T["pilar"], "src": "ade+sam"})
    return out


def kotak_ke_mask(b, h, w):
    m = np.zeros((h, w), bool)
    m[int(max(0, b[1])):int(b[3]), int(max(0, b[0])):int(b[2])] = True
    return m


def kusen(b, L, W, luar):
    """Rangka kaca. ADE membaca rangkanya sebagai wall, jadi yang dilihat sisi kiri-kanannya.
    Di dalam gedung satu sisi kaca sudah cukup (119), di luar harus dua sisi."""
    x1, y1, x2, y2 = (int(v) for v in b)
    if x2 - x1 > 160:
        return False
    sisi = [L["kaca"][y1:y2, max(0, x1 - 50):x1], L["kaca"][y1:y2, x2:min(W, x2 + 50)]]
    sisi = [v.mean() for v in sisi if v.size]
    return len(sisi) > 0 and (min(sisi) if luar else max(sisi)) >= 0.5


def validasi_pilar(m, d, L, W, H):
    """Return mask final. Kalau SAM gagal menutup tiang (stainless memantulkan sekitarnya), pakai kotak
    GDINO sebagai polygon, karena model kotak hanya butuh kotaknya."""
    kb = d["box"]
    if d.get("besar") and d["skor"] < 0.4 and isi_box(L["terang"], kb) >= 0.35:      # panel kaca buram (199)
        return None
    bh = kb[3] - kb[1]
    b = box_mask(m)
    sempit = b is not None and d.get("besar") and (b[2] - b[0]) < 0.5 * (kb[2] - kb[0])
    if b is None or (b[3] - b[1]) < 0.7 * bh or sempit:
        if bh < 3 * (kb[2] - kb[0]) and not d.get("besar"):
            return None
        m = kotak_ke_mask(kb, H, W)
        d["kotak_saja"] = True
        b = box_mask(m)
    if not lolos_ukuran(b, True):
        return None
    w, h = b[2] - b[0], b[3] - b[1]
    if not d.get("besar") and (h < 1.2 * w or w > 0.5 * W):
        return None
    if m.sum() < 0.3 * w * h:
        return None
    for k in ("kaca", "sampah", "pagar"):
        if L[k][m].mean() > 0.4:
            return None
    return m


def saring_tangga(g, L, nama):
    out = []
    lokasi = nama.startswith(LOKASI_TANGGA)
    for d in g["tangga"]:
        ade = isi_box(L["tangga"], d["box"])
        if d["skor"] >= (T["tangga"] if lokasi else T["tangga_luar"]) and ade >= 0.25:
            out.append({**d, "src": "gdino+ade+sam"})
        elif lokasi and d["skor"] >= T["tangga_lokasi"] + 0.15:
            out.append({**d, "src": "gdino+sam"})
    return out


# ---------- polygon & JSON ----------

def mask_ke_shapes(m, min_luas, tutup=7):
    k = np.ones((tutup, tutup), np.uint8)
    u = m.astype(np.uint8)
    u = cv2.morphologyEx(cv2.morphologyEx(u, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)), cv2.MORPH_CLOSE, k)
    c, hier = cv2.findContours(u, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return []
    hier = hier[0]
    luas = m.shape[0] * m.shape[1]
    out = []
    for i, ci in enumerate(c):
        if hier[i][3] != -1 or cv2.contourArea(ci) < min_luas:
            continue
        lub, j = [], hier[i][2]
        while j != -1:
            if cv2.contourArea(c[j]) >= MIN_LUBANG * luas:
                h = _rapikan(c[j])
                if len(h) >= 3:
                    lub.append(h)
            j = hier[j][0]
        l = _rapikan(ci)
        if len(l) >= 3:
            out.append(_gabung_lubang(l, lub))
    return out


def mask_ke_objek(m):
    """Satu polygon per objek. Kontur terbesar; kalau ada fragmen >= 10% luasnya, pakai hull semuanya."""
    u = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    c, _ = cv2.findContours(u, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = sorted(c, key=cv2.contourArea, reverse=True)
    if not c or cv2.contourArea(c[0]) < 200:
        return None
    besar = [x for x in c if cv2.contourArea(x) >= 0.1 * cv2.contourArea(c[0])]
    k = c[0] if len(besar) == 1 else cv2.convexHull(np.vstack(besar))
    r = _rapikan(k)
    return r if len(r) >= 3 else None


def bentuk(label, poly, skor, src, ragu):
    return {"review_status": "pending", "label": label, "score": round(float(skor), 3),
            "points": [[round(float(x), 1), round(float(y), 1)] for x, y in poly], "group_id": None,
            "description": f"auto-v2 {src} {skor:.2f}", "difficult": bool(ragu), "shape_type": "polygon",
            "flags": {}, "attributes": {}, "kie_linking": []}


# ---------- permukaan ----------

def bukti_marka(rgb_hsv, reg, g):
    """Marka kuning (panah, garis) di area, atau GDINO zebra/arrow yang dikonfirmasi cat putih/kuning."""
    hh, ss, vv = rgb_hsv
    kuning = (hh > 18) & (hh < 35) & (ss > 90) & (vv > 110)
    inti = cv2.erode(reg.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0     # tanah di tepi batu bukan marka
    n = int((kuning & inti).sum())
    if n >= 0.002 * reg.size:
        return "marka kuning"
    putih = (ss < 45) & (vv > 170)
    for d in g["marka"]:
        if d["skor"] < T["marka"]:
            continue
        x1, y1, x2, y2 = (int(max(0, v)) for v in d["box"])
        r = reg[y1:y2, x1:x2]
        if min(x2 - x1, y2 - y1) < 80:             # goresan di batu pijakan terbaca road arrow (186)
            continue
        porsi = (putih[y1:y2, x1:x2] & r).sum() / max(1, r.sum())
        if r.size and r.mean() > 0.5 and 0.2 < porsi <= 0.75:
            return "marka putih"
    return None


def bagi_area(lantai, boleh, sam, cadang=None):
    """Bagi permukaan jadi area homogen pakai SAM. Seed di titik terdalam sisa area."""
    h, w = lantai.shape
    luas = h * w
    tertutup = np.zeros_like(lantai)
    area = []
    for _ in range(MAX_AREA_SEED):
        sisa = lantai & ~tertutup
        if sisa.sum() < MIN_LUAS_SURFACE * luas:
            break
        kecil = cv2.resize(sisa.astype(np.uint8), (w // 4, h // 4), interpolation=cv2.INTER_NEAREST)
        d = cv2.distanceTransform(kecil, cv2.DIST_L2, 3)
        yy, xx = np.unravel_index(d.argmax(), d.shape)
        mk, _ = sam.titik(xx * 4, yy * 4)
        pilih = None
        for j in np.argsort([-m.sum() for m in mk]):
            m = mk[j]
            dasar = lantai if cadang is None else (lantai | cadang)
            if m.sum() and (m & dasar).sum() >= 0.6 * m.sum() and (m & ~boleh).sum() <= 0.15 * m.sum():
                pilih = m
                break
        if pilih is None:
            n, lab = cv2.connectedComponents(sisa.astype(np.uint8), connectivity=8)
            pilih = lab == lab[yy * 4, xx * 4] if lab[yy * 4, xx * 4] else sisa
        r = pilih & boleh & ~tertutup
        if r.sum() == 0:
            tertutup |= pilih
            continue
        area.append(r)
        tertutup |= r | pilih
    sisa = lantai & ~tertutup
    if sisa.sum() >= MIN_LUAS_SURFACE * luas:
        area.append(sisa)
    return area


def buang_balik_kaca(m, g, alasan):
    """Kasus f: lantai di dalam kotak pagar kaca (222) adalah lantai level lain."""
    h, w = m.shape
    kaca = [d["box"] for d in g["pagarkaca"] if d["skor"] >= 0.3 and d["box"][2] - d["box"][0] >= 0.4 * w
            and d["box"][3] >= 0.9 * h]
    if not kaca:
        return m
    out = np.zeros_like(m)
    for c in rapikan_komponen(m, 1):
        if any(c[int(b[1]):int(b[3]), int(b[0]):int(b[2])].sum() >= 0.7 * c.sum() for b in kaca):
            alasan.add("lantai balik kaca")
            continue
        out |= c
    return out


def buang_balik_pagar(m, L, alasan):
    """Kasus f: lantai level lain di balik pagar kaca. Komponen yang tidak sampai bagian bawah frame dan
    tepat di bawahnya ada pagar dibuang. Komponen kecil yang mengambang (mobil lewat jendela di 92,
    tembok planter di 51) juga dibuang."""
    h, w = m.shape
    out = np.zeros_like(m)
    for c in rapikan_komponen(m, 1):
        ys, xs = np.nonzero(c)
        y2 = ys.max()
        if y2 < 0.75 * h:
            pita = L["pagar"][y2:min(h, y2 + 60), xs.min():xs.max() + 1]
            if pita.size and pita.mean() > 0.10:
                continue
        if y2 < 0.9 * h and c.sum() < 0.03 * h * w:
            if c.sum() >= MIN_LUAS_SURFACE * h * w:
                alasan.add("lantai kecil dibuang")
            continue
        out |= c
    return out


def pita_hijau(r, hijau, tebal=40):
    """Porsi hijau tepat di atas dan di bawah area, dihitung per kolom. None kalau menyentuh tepi frame."""
    h = r.shape[0]
    xs = np.nonzero(r.any(0))[0]
    if len(xs) == 0:
        return None, None
    atas, bawah, tepi_a, tepi_b = [], [], 0, 0
    for x in xs[:: max(1, len(xs) // 40)]:
        ys = np.nonzero(r[:, x])[0]
        y1, y2 = int(ys.min()), int(ys.max())
        if y1 <= 5:
            tepi_a += 1
        else:
            atas.append(hijau[max(0, y1 - tebal):y1 - 3, x].mean())
        if y2 >= h - 6:
            tepi_b += 1
        else:
            bawah.append(hijau[y2 + 3:y2 + tebal, x].mean())
    a = float(np.mean(atas)) if len(atas) > tepi_a else None
    b = float(np.mean(bawah)) if len(bawah) > tepi_b else None
    return a, b


def permukaan(nama, ade, L, objek, tangga, eskal, g, img, sam, alasan, tepian_baru):
    h, w = ade.shape
    lantai = L["lantai"] & ~objek & ~tangga & ~eskal
    lantai = cv2.morphologyEx(lantai.astype(np.uint8), cv2.MORPH_OPEN, np.ones((9, 9), np.uint8)) > 0
    boleh = ~L["larang"] & ~objek & ~tangga & ~eskal
    area = []
    hv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hijau = (hv[:, :, 0] > 28) & (hv[:, :, 0] < 90) & (hv[:, :, 1] > 40) & (hv[:, :, 2] > 40)
    campuran = nama.startswith(LOKASI_CAMPURAN)
    banyak_rumput = L["rumput"].mean() >= 0.25
    cadang = L["cadang"] & ~objek & ~tangga & ~eskal
    for r in bagi_area(lantai, boleh, sam, cadang):       # strip rumput tipis sering terbaca lantai oleh ADE
        r = r & ~hijau if campuran else r
        u = cv2.morphologyEx(r.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0
        area += rapikan_komponen(u, int(0.002 * h * w))
    trotoar = []
    if campuran:          # trotoar utuh di bawah frame (29): ADE sidewalk murni, tidak ikut area jalan di sebelahnya
        pisah = []
        for r in area:
            t = cv2.morphologyEx((r & L["trotoar"]).astype(np.uint8), cv2.MORPH_OPEN, np.ones((9, 9), np.uint8)) > 0
            cs = []
            for c in rapikan_komponen(t, int(0.05 * h * w)):
                pita = kerb_di_atas(c, img) if np.nonzero(c.any(1))[0].max() >= h - 6 else None
                if pita is not None:
                    cs.append(c)
                    tepian_baru.append(pita & ~objek)
            for c in cs:
                r = r & ~c
            trotoar += cs
            pisah += cs + (rapikan_komponen(r, int(0.002 * h * w)) if cs else [r])
        area = pisah
    jalur, jalan = np.zeros((h, w), bool), np.zeros((h, w), bool)
    if nama.startswith(LOKASI_SEMUA_JALAN):
        for r in area:
            jalan |= r
    elif not nama.startswith(LOKASI_CAMPURAN):
        for r in area:
            jalur |= r
        jalur = buang_balik_pagar(jalur, L, alasan)
        return (jalur if nama.startswith(LOKASI_LUAR) else buang_balik_kaca(jalur, g, alasan)), jalan
    else:
        hsv = cv2.split(cv2.cvtColor(img, cv2.COLOR_BGR2HSV))
        kendaraan = objek.kotak
        status = []
        for r in area:
            bukti = None
            lebar = cv2.dilate(r.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
            for b in kendaraan:
                x1, x2, y2 = int(b[0]), int(b[2]), int(min(h - 1, b[3]))
                y1 = int(max(0, b[3] - 0.15 * (b[3] - b[1])))
                if lebar[y1:y2 + 1, x1:x2].any():
                    bukti = "kendaraan"
                    break
            bukti = bukti or bukti_marka(hsv, r, g)
            adalah_trotoar = any(r is c for c in trotoar)
            if adalah_trotoar and bukti != "kendaraan":
                bukti = None
                alasan.add("trotoar dari ade")
            atas, bawah = pita_hijau(r, hijau)
            # kasus g: rumput di atas dan bawahnya. Di frame yang didominasi rumput (186) celah antarbatu
            # lebih banyak tanah, jadi cukup ada rumput di sisi atas.
            pijakan = (not bukti and r.sum() < 0.2 * h * w and atas is not None
                       and ((atas >= 0.4 and (bawah is None or bawah >= 0.4)) or (atas >= 0.2 and banyak_rumput)))
            pijakan = pijakan or (adalah_trotoar and not bukti)
            status.append([r, bukti, float(L["road"][r].mean()), pijakan])
        pasti_jalan = np.zeros((h, w), bool)
        for r, bukti, road, pijakan in status:
            if bukti or (road >= 0.5 and not pijakan):
                pasti_jalan |= r
        lebar_jalan = cv2.dilate(pasti_jalan.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        for r, bukti, road, pijakan in status:
            if bukti:
                jalan |= r
            elif pijakan:
                jalur |= r
            elif road >= 0.5:
                jalan |= r
                alasan.add("permukaan ambigu")
            elif (r & lebar_jalan).sum() > 200:
                jalan |= r
                alasan.add("permukaan ambigu")
            else:
                jalur |= r
    return buang_balik_pagar(jalur, L, alasan), buang_balik_pagar(jalan, L, alasan)


class Objek(np.ndarray):
    """Mask bool semua objek, plus daftar kotaknya."""
    def __new__(cls, m, kotak):
        o = np.asarray(m).view(cls)
        o.kotak = kotak
        return o

    def __array_finalize__(self, obj):
        self.kotak = getattr(obj, "kotak", [])


# ---------- proses satu frame ----------

def proses(f, img, ade, yolo, g, luts, sam):
    h, w = img.shape[:2]
    nama = f.name
    L = {k: v[ade] for k, v in luts.items()}
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    S = hsv[:, :, 1]
    L["terang"] = (hsv[:, :, 2] > 170) & (S < 30)
    alasan = set()
    shapes = []
    jumlah = Counter()
    kotak = []
    bukti_kendaraan = []
    tak_lolos = Counter()
    objek = np.zeros((h, w), bool)

    def catat(label, skor, b, aturan):
        DIBUANG.append([nama, label, round(float(skor), 3), [int(v) for v in b], aturan])

    lab = nama.startswith(LOKASI_LAB)
    orang_ketat = nama.startswith(LOKASI_ORANG_KETAT)

    def tambah(label, m, skor, src, ragu):
        if lab and skor < T_LAB.get(label, 0):
            catat(label, skor, box_mask(m), "ambang lab")
            return False
        if label in ("kursi", "pilar", "tepian", "tanaman_pot", "pohon") and eskal[m].mean() >= 0.5:
            catat(label, skor, box_mask(m), "di eskalator")
            return False
        poly = mask_ke_objek(m)
        if poly is None:
            return False
        shapes.append(bentuk(label, poly, skor, src, ragu))
        jumlah[label] += 1
        kotak.append((label, box_mask(m)))
        return True

    # eskalator (veto, tidak dilabel)
    eskal = L["eskalator"].copy()
    kand = [d for d in g["eskalator"] if d["skor"] >= T["eskalator"]]
    if kand:
        for m, d in zip(sam.boxes([d["box"] for d in kand]), kand):
            if L["eskalator"][m].mean() > 0.1 or isi_box(L["eskalator"], d["box"]) > 0.1:
                eskal |= m

    # orang, kendaraan, kursi dari YOLO (full + tile)
    orang = []
    gorang = [q for q in g["orang"] if q["skor"] >= 0.3 and not q["seam"]]
    ambang_y = {"orang": T["yolo_orang"], "kendaraan": T["yolo_kendaraan"], "kursi": T["yolo_kursi"]}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    kursi_kuat = np.zeros((h, w), bool)        # kursi yakin (>= 0,5): tidak boleh jadi bagian tangga (bangku kayu di 186)
    for kelas in ("orang", "kendaraan", "kursi"):
        calon = gabung([v for v in yolo if v["kelas"] == kelas and v["skor"] >= BATAS_YOLO[kelas]], telan=False)
        kuat = [v["box"] for v in calon if v["skor"] >= 0.25]
        for d in calon:
            if wadah(d["box"], kuat):
                catat(kelas, d["skor"], d["box"], "wadah")
                continue
            m = poly_ke_mask(d["poly"], h, w)
            if kelas == "orang":
                kepala = None if d.get("seam") else kepala_blur(gray, d["box"])
                if kepala is None and d["skor"] < ORANG_LEMAH and isi_box(L["eskalator"], d["box"]) >= 0.3:
                    catat(kelas, d["skor"], d["box"], "orang di eskalator")      # pegangan eskalator (119)
                    continue
                if orang_ketat and kepala is None and d["skor"] < ORANG_LEMAH and isi_box(L["orang"], d["box"]) < 0.05:
                    catat(kelas, d["skor"], d["box"], "orang lemah")
                    continue
                if kepala is not None:
                    m = m | kotak_ke_mask(kepala, h, w)
                    d = {**d, "box": box_mask(m)}
                # kepala yang dipixelate sering lepas dari kotak YOLO; kotak GDINO person menambalnya
                b0 = d["box"]
                bh0, bw0 = b0[3] - b0[1], b0[2] - b0[0]
                for q in ([] if kepala is not None else gorang):
                    qb = q["box"]
                    if (iou_box(b0, qb)[1] >= 0.7 and qb[1] < b0[1] - 0.05 * bh0 and (qb[3] - qb[1]) < 1.9 * bh0
                            and (qb[2] - qb[0]) < 1.5 * bw0):
                        b1 = [min(b0[0], qb[0]), qb[1], max(b0[2], qb[2]), max(b0[3], qb[3])]
                        m = m | (sam.boxes([b1])[0] & kotak_ke_mask(b1, h, w)) | kotak_ke_mask(
                            [qb[0] + 0.25 * (qb[2] - qb[0]), qb[1], qb[2] - 0.25 * (qb[2] - qb[0]), b0[1] + 5], h, w)
                        d = {**d, "box": box_mask(m)}
                        break
                orang.append(d["box"])
            if d["skor"] >= ambang_y[kelas]:
                objek |= m
            if kelas == "kursi" and (d["box"][2] - d["box"][0]) > 4 * (d["box"][3] - d["box"][1]):
                continue
            if not lolos_ukuran(d["box"], False):
                if kelas != "kursi" and d["skor"] >= 0.25:
                    tak_lolos[kelas] += 1
                continue
            if kelas == "kursi" and d["skor"] >= 0.5:
                kursi_kuat |= m
            sumber = "yolo" if d["tile"] is None else "yolo-tile"
            tambah(kelas, m, d["skor"], sumber, d["skor"] < ambang_y[kelas] + RAGU)
            if kelas == "kendaraan" and d["skor"] >= 0.3:
                bukti_kendaraan.append(d["box"])

    # orang dan kendaraan yang hanya ditemukan GDINO
    for kelas in ("orang", "kendaraan"):
        ada = [b for k, b in kotak if k == kelas]
        c = [d for d in g[kelas] if d["skor"] >= BATAS_GDINO[kelas] and not d["seam"]
             and (d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]) < 0.5 * h * w
             and lolos_ukuran(d["box"], False) and all(iou_box(d["box"], b)[1] < 0.5 for b in ada)]
        c = sorted(gabung(c), key=lambda v: -v["skor"])[:MAKS_KANDIDAT]
        if c:
            for m, d in zip(sam.boxes([q["box"] for q in c]), c):
                b = box_mask(m)
                if b is None or not lolos_ukuran(b, False):
                    continue
                if kelas == "orang" and isi_box(L["eskalator"], b) >= 0.3:
                    catat(kelas, d["skor"], b, "orang di eskalator")
                    continue
                if kelas == "orang" and orang_ketat and d["skor"] < ORANG_LEMAH and isi_box(L["orang"], b) < 0.05:
                    catat(kelas, d["skor"], b, "orang lemah")
                    continue
                tambah(kelas, m, d["skor"], "gdino+sam", True)
                if kelas == "orang":
                    orang.append(b)

    # kursi gelap dari GDINO, wajib didukung ADE dan bukan duplikat YOLO
    kk = [d for d in g["kursi"] if d["skor"] >= BATAS_GDINO["kursi"] and isi_box(L["kursi"], d["box"]) >= 0.2
          and 0.4 <= (d["box"][3] - d["box"][1]) / max(1, d["box"][2] - d["box"][0]) <= 3
          and all(iou_box(d["box"], b)[1] < 0.5 for k, b in kotak if k == "kursi")]
    kk = gabung(kk)
    if kk:
        for m, d in zip(sam.boxes([d["box"] for d in kk]), kk):
            b = box_mask(m)
            if b and lolos_ukuran(b, False):
                ragu = d["skor"] < T["kursi"] + RAGU
                if not ragu:
                    objek |= m
                tambah("kursi", m, d["skor"], "gdino+sam", ragu)

    # tanaman_pot: COCO diperluas dengan kotak GDINO yang memuatnya; GDINO sendiri butuh ADE pot
    pots = [{**v, "src": "yolo+sam"} for v in gabung([v for v in yolo if v["kelas"] == "tanaman_pot"
                                                      and v["skor"] >= BATAS_YOLO["tanaman_pot"]])]
    gp = [d for d in g["pot"] if d["skor"] >= BATAS_GDINO["pot"] and luas_box(d["box"]) < 0.42 * h * w]
    for p in pots:
        for d in gp:
            b = p["box"]
            lintang = (min(b[2], d["box"][2]) - max(b[0], d["box"][0])) / max(1, b[2] - b[0])
            nempel = lintang > 0.5 and b[3] >= d["box"][1] - 30 and b[1] <= d["box"][1] + 30   # tanaman di atas planter
            if iou_box(b, d["box"])[1] > 0.7 or (nempel and d["skor"] >= 0.5):
                p["box"] = [min(b[0], d["box"][0]), min(b[1], d["box"][1]), max(b[2], d["box"][2]), max(b[3], d["box"][3])]
    for d in gp:
        if (all(iou_box(d["box"], p["box"])[1] < 0.5 for p in pots) and isi_box(L["pot"], d["box"]) >= 0.3
                and (d["box"][2] - d["box"][0]) < 0.6 * w):
            pots.append({**d, "src": "gdino+sam"})
    pots = [p for p in gabung(pots) if p["box"][3] > 0.4 * h]       # tanaman gantung ditolak
    if pots:
        for m, d in zip(sam.boxes([p["box"] for p in pots]), pots):
            b = box_mask(m)
            if b and lolos_ukuran(b, False):
                # semak di bedeng terbaca planter: tanpa bukti pot tetap masuk, tapi sebagai ragu
                ragu = d["skor"] < T["pot"] + RAGU or isi_box(L["pot_asli"], d["box"]) < 0.05
                if not ragu:
                    objek |= m
                tambah("tanaman_pot", m, d["skor"], d["src"], ragu)

    # tangga: satu polygon per tangga
    tangga = np.zeros((h, w), bool)
    kt = gabung(saring_tangga({"tangga": [d for d in g["tangga"] if not d["seam"]]}, L, nama), iou=0.3, isi=0.6)
    if kt:
        for m, d in zip(sam.boxes([p["box"] for p in kt]), kt):
            m = m & ~eskal & ~kursi_kuat
            if m.sum() >= 0.015 * h * w:
                tangga |= m
    if tangga.any():
        tangga = cv2.morphologyEx(tangga.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((61, 61), np.uint8)) > 0
        skor = max(d["skor"] for d in kt)
        komp = [c for c in rapikan_komponen(tangga, int(0.015 * h * w)) if lolos_ukuran(box_mask(c), False)]
        ubah = True
        while ubah:                          # potongan yang kotaknya tumpang tindih = satu tangga (orang di tengah, 227)
            ubah = False
            for i in range(len(komp)):
                for j in range(i + 1, len(komp)):
                    bi, bj = box_mask(komp[i]), box_mask(komp[j])
                    if iou_box([bi[0] - 60, bi[1] - 60, bi[2] + 60, bi[3] + 60], bj)[1] > 0:
                        komp[i] = komp[i] | komp[j]
                        del komp[j]
                        ubah = True
                        break
                if ubah:
                    break
        di_luar = not nama.startswith(LOKASI_TANGGA)
        for c in komp:
            ragu = skor < T["tangga"] + RAGU or (di_luar and skor < 0.6)
            tambah("tangga", c, skor, kt[0]["src"], ragu)

    # tepian: kandidat, selalu ditandai ragu
    luar = nama.startswith(LOKASI_LUAR)
    ambang_t = BATAS_GDINO["tepian"] if luar else BATAS_GDINO["tepian_dalam"]
    ke = gabung(sorted([d for d in g["tepian"] if d["skor"] >= ambang_t], key=lambda v: -v["skor"])[:60],
                iou=0.4, isi=0.8)
    ke = sorted(ke, key=lambda v: -v["skor"])[:MAKS_KANDIDAT]
    tepi = np.zeros((h, w), bool)
    grup = 0
    if ke:
        dekat = cv2.dilate(L["lantai"].astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
        for m, d in zip(sam.boxes([p["box"] for p in ke]), ke):
            m = m & ~tangga & ~objek & ~tepi
            b = box_mask(m)
            if b is None or not lolos_ukuran(b, True) or rasio_memanjang(m) < 2.5 or (m & dekat).sum() < 0.1 * m.sum():
                continue
            atas = L["dinding"][max(0, int(b[1]) - 40):max(1, int(b[1])), int(b[0]):int(b[2])]
            if m.sum() > 0.15 * h * w or (atas.size and atas.mean() > 0.5) or L["pot"][m].mean() > 0.7:
                continue
            grup += 1
            n0 = len(shapes)
            for seg in pecah_garis(m):
                tambah("tepian", seg, d["skor"], "gdino+sam", True)
            for sh in shapes[n0:]:
                sh["group_id"] = grup
            if len(shapes) > n0:
                tepi |= m
                alasan.add("tepian kandidat")

    # pilar
    kb0 = [d for d in g["pohon"] if d["skor"] >= T["pohon"] and isi_box(
        L["pohon"], [d["box"][0] - 40, d["box"][1] - 80, d["box"][2] + 40, d["box"][3]]) >= 0.15]

    def kalah_dari_batang(d):
        b = d["box"]
        tinggi_tipis = (b[3] - b[1]) >= 6 * (b[2] - b[0])
        lw = (b[2] - b[0]) / 3
        logam = float(S[int(b[1]):int(b[3]), int(b[0] + lw):int(b[2] - lw) + 1].mean()) < 45
        if tinggi_tipis and logam:                 # stainless: ADE dan GDINO sering membacanya sebagai batang
            return False
        return any(iou_box(b, t["box"])[0] >= 0.5 and t["skor"] > d["skor"] for t in kb0)

    def dekat_kepala(d):
        for o in orang:
            ow, oh = o[2] - o[0], o[3] - o[1]
            if iou_box(d["box"], [o[0] - 0.3 * ow, o[1] - 0.8 * oh, o[2] + 0.3 * ow, o[3]])[1] >= 0.6:
                return True
        return False

    ade_tiang = [d for d in kandidat_tiang_ade(L) if not dekat_kepala(d)]
    kp = sambung_vertikal(saring_pilar(g, L, orang, w, h) + ade_tiang)
    kp = [d for d in gabung(kp, iou=0.5, isi=0.8, rasio_lebar=2) if not kalah_dari_batang(d)]
    kp = sorted(kp, key=lambda d: -d["skor"])[:MAKS_KANDIDAT]
    alas = umpak(g, orang)
    terpakai = set()
    hasil = []
    if kp:
        for m, d in zip(sam.boxes([p["box"] for p in kp]), kp):
            m = validasi_pilar(m & ~tangga, d, L, w, h)
            if m is None or (m & tepi).sum() > 0.3 * m.sum() or kusen(box_mask(m), L, w, luar):
                continue
            b = box_mask(m)
            if any(iou_box(b, o)[1] >= 0.5 for o in orang):
                continue
            hasil.append([m, b, d])
    for i, u in sorted(enumerate(alas), key=lambda v: -v[1]["skor"]):      # kasus b: tiap umpak ikut satu tiang
        ub = u["box"]
        calon = [r for r in hasil if ub[0] <= (r[1][0] + r[1][2]) / 2 <= ub[2]
                 and (abs(ub[1] - r[1][3]) < 0.15 * h or ub[1] < r[1][3] < ub[3]) and (r[1][2] - r[1][0]) < (ub[2] - ub[0])]
        if calon:
            r = min(calon, key=lambda v: abs((v[1][0] + v[1][2]) / 2 - (ub[0] + ub[2]) / 2))
            if id(r) not in terpakai:
                terpakai.add(id(r))
                r[0] = r[0] | kotak_ke_mask(ub, h, w)
                r[1] = box_mask(r[0])
    gabungan = []
    for r in sorted(hasil, key=lambda v: -(v[1][2] - v[1][0]) * (v[1][3] - v[1][1])):    # 52: satu tiang satu kotak
        for o in gabungan:
            i, n = iou_box(r[1], o[1])
            if i >= 0.4 or n >= 0.7:
                o[0] = o[0] | r[0]
                o[1] = box_mask(o[0])
                o[2] = {**o[2], "skor": max(o[2]["skor"], r[2]["skor"])}
                break
        else:
            gabungan.append(r)
    pilar_b = []
    for m, b, d in gabungan:
        objek |= m
        ragu = d.get("kotak_saja") or d.get("besar") or d["skor"] < T["pilar"] + RAGU
        tambah("pilar", m, d["skor"], d["src"] + ("-kotak" if d.get("kotak_saja") else ""), ragu)
        pilar_b.append(b)

    # pohon: batang saja, area ADE tree harus ada di sekitarnya, kasus i: tidak di balik pagar
    kb = [d for d in g["pohon"] if d["skor"] >= BATAS_GDINO["pohon"] and isi_box(
        L["pohon"], [d["box"][0] - 40, d["box"][1] - 80, d["box"][2] + 40, d["box"][3]]) >= 0.15
        and isi_box(L["pagar"], d["box"]) < 0.3]
    kb = gabung(sambung_vertikal(kb), iou=0.4, isi=0.7)
    kb = [d for d in sorted(kb, key=lambda v: -v["skor"])[:MAKS_KANDIDAT] if all(iou_box(d["box"], o)[0] < 0.4 for o in pilar_b)]
    if kb:
        for m, d in zip(sam.boxes([p["box"] for p in kb]), kb):
            m, dipotong = potong_batang(m & ~objek)
            b = box_mask(m)
            if b is None or not lolos_ukuran(b, True):
                continue
            bw, bh = b[2] - b[0], b[3] - b[1]
            ragu = d["skor"] < T["pohon"] + RAGU
            if bh < 1.2 * bw or bw > 0.35 * w:
                alasan.add("pohon perlu cek")
                kb_ = d["box"]
                if (kb_[3] - kb_[1]) < 1.5 * (kb_[2] - kb_[0]) or (kb_[2] - kb_[0]) > 0.35 * w:
                    continue
                m = kotak_ke_mask(kb_, h, w) & ~objek         # SAM gagal, kotak GDINO masih bentuk batang
                ragu = True
            objek |= m
            tambah("pohon", m, d["skor"], "gdino+sam", ragu)
            if dipotong:
                alasan.add("tajuk dipotong")

    # kotak wadah di kelas lain
    for label in ("pilar", "pohon", "tanaman_pot", "kursi", "orang", "kendaraan"):
        sk = [(q, [min(x for x, _ in q["points"]), min(y for _, y in q["points"]),
                   max(x for x, _ in q["points"]), max(y for _, y in q["points"])]) for q in shapes if q["label"] == label]
        bx = [b for _, b in sk]
        for q, b in sk:
            if wadah(b, bx):
                catat(label, q["score"], b, "wadah")
                shapes.remove(q)
                jumlah[label] -= 1

    # permukaan
    ob = Objek(objek, bukti_kendaraan)
    tepian_baru = []
    jalur, jalan = permukaan(nama, ade, L, ob, tangga, eskal, g, img, sam, alasan, tepian_baru)
    for m in tepian_baru:                  # kerb belang yang memisahkan trotoar dari jalan
        grup += 1
        n0 = len(shapes)
        for seg in pecah_garis(m):
            tambah("tepian", seg, 0.30, "kerb-belang", True)
        for sh in shapes[n0:]:
            sh["group_id"] = grup
    for label, m in (("jalur_jalan", jalur), ("jalan_kendaraan", jalan)):
        for poly in mask_ke_shapes(np.asarray(m), MIN_LUAS_SURFACE * h * w):
            shapes.append(bentuk(label, poly, 0.5, "segformer+sam", "permukaan ambigu" in alasan and label == "jalan_kendaraan"))
            jumlah[label] += 1

    # flag frame mencurigakan
    if luar and not jumlah["pilar"] and not jumlah["tepian"]:
        alasan.add("outdoor 0 pilar 0 tepian")
    for k, n in tak_lolos.items():
        alasan.add(f"coco {k} x{n} kena aturan ukuran")
    if nama.startswith(LOKASI_TANGGA) and not jumlah["tangga"]:
        alasan.add("lokasi tangga tanpa tangga")
    if not any(jumlah[k] for k in KELAS if k not in ("jalur_jalan", "jalan_kendaraan")):
        alasan.add("frame tanpa objek")
    return shapes, jumlah, sorted(alasan)


# ---------- lembar cek ----------

def panel(img, shapes, mode, tw):
    h, w = img.shape[:2]
    v = img.copy()
    if mode == "seg":
        ov = img.copy()
        for s in shapes:
            if s["label"] in ("jalur_jalan", "jalan_kendaraan", "tangga"):
                cv2.fillPoly(ov, [np.array(s["points"], np.int32)], WARNA[s["label"]])
        v = cv2.addWeighted(ov, 0.5, img, 0.5, 0)
    elif mode == "kotak":
        for s in shapes:
            if s["label"] in ("jalur_jalan", "jalan_kendaraan"):
                continue
            p = np.array(s["points"], np.int32)
            x1, y1, x2, y2 = p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()
            c = WARNA[s["label"]]
            cv2.polylines(v, [p], True, c, 3)
            cv2.rectangle(v, (x1, y1), (x2, y2), c, 8 if not s["difficult"] else 3)
            cv2.putText(v, f"{s['label']} {s['score']:.2f}", (x1 + 6, max(50, y1 + 50)), 0, 1.5, (0, 0, 0), 9)
            cv2.putText(v, f"{s['label']} {s['score']:.2f}", (x1 + 6, max(50, y1 + 50)), 0, 1.5, c, 4)
    return cv2.resize(v, (tw, int(tw * h / w)), interpolation=cv2.INTER_AREA)


def lembar(out, nomor, alasan, tw=220, kol=3, baris=2):
    folder = out / "_cek"
    folder.mkdir(exist_ok=True)
    js = sorted(out.glob("*.json"))
    per = kol * baris
    for s in range(0, len(js), per):
        tile = []
        for j in js[s:s + per]:
            d = json.loads(j.read_text(encoding="utf-8"))
            img = cv2.imread(str(out / d["imagePath"]))
            p = [panel(img, d["shapes"], m, tw) for m in ("asli", "seg", "kotak")]
            t = np.hstack(p)
            pita = np.zeros((22, t.shape[1], 3), np.uint8)
            alas = alasan.get(d["imagePath"], "")
            cv2.putText(pita, f"{nomor.get(j.stem + '.jpg', '?')} {j.stem[:34]} {alas[:40]}", (4, 16), 0, 0.42, (255, 255, 255), 1)
            tile.append(np.vstack([pita, t]))
        while len(tile) < per:
            tile.append(np.zeros_like(tile[0]))
        rows = [np.hstack([cv2.copyMakeBorder(t, 0, 2, 0, 3, cv2.BORDER_CONSTANT) for t in tile[r * kol:(r + 1) * kol]])
                for r in range(baris)]
        cv2.imwrite(str(folder / f"cek_{s // per + 1:02d}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])


# ---------- main ----------

def kumpulkan(a):
    if a.semua_training:
        root = Path("data/frame-blur")
        return sorted(f for d in root.iterdir() if d.is_dir() and not d.name.startswith(TEST)
                      for f in d.iterdir() if f.suffix.lower() in IMG_EXT)
    files = []
    if a.daftar:
        files += [Path(x.strip()) for x in Path(a.daftar).read_text(encoding="utf-8").splitlines() if x.strip()]
    for p in a.input:
        p = Path(p)
        files += [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.suffix.lower() in IMG_EXT)
    return files


def main():
    ap = argparse.ArgumentParser(description="Label otomatis 10 kelas JalanKu, output JSON X-AnyLabeling.")
    ap.add_argument("input", nargs="*", help="file atau folder gambar")
    ap.add_argument("--daftar", help="file teks berisi path gambar, satu per baris")
    ap.add_argument("--semua-training", action="store_true", help="semua frame di data/frame-blur kecuali lokasi test")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", help="folder cache hasil model (mempercepat tuning)")
    ap.add_argument("--coco-model", default="yolo11x-seg.pt")
    ap.add_argument("--device", default="0")
    ap.add_argument("--izin-test", action="store_true", help="hanya untuk Stage 6, --out wajib di data/test-review")
    a = ap.parse_args()

    out = Path(a.out)
    if "frame-blur" in out.resolve().as_posix():
        sys.exit("BERHENTI: output tidak boleh di data/frame-blur.")
    files = kumpulkan(a)
    if not files:
        sys.exit("Tidak ada gambar.")
    ada_test = [f for f in files if f.name.startswith(TEST)]
    if ada_test and not (a.izin_test and out.resolve().as_posix().endswith("data/test-review")):
        sys.exit(f"BERHENTI: {len(ada_test)} frame lokasi test di input. Data test tidak boleh masuk training.")

    from PIL import Image
    M = Model(a)
    luts = {k: lut(M.id2, v) for k, v in ADE.items()}
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(a.cache) if a.cache else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    ringkas, total, t0, baru = [], Counter(), time.time(), 0
    for f in files:
        js = out / (f.stem + ".json")
        if js.exists():
            continue
        img = cv2.imread(str(f))
        h, w = img.shape[:2]
        pil = Image.open(f).convert("RGB")
        c = cache / (f.stem + ".pkl") if cache else None
        if c and c.exists():
            ade, yolo, g = pickle.loads(c.read_bytes())
        else:
            ade, yolo, g = M.ade(np.array(pil)), M.yolo(img), M.gdino(pil)
            if c:
                c.write_bytes(pickle.dumps((ade, yolo, g)))
        sam = Sam(M, pil)
        shapes, jumlah, alasan = proses(f, img, ade, yolo, g, luts, sam)
        taut(f, out / f.name)
        flags = {"perlu_cek": True} if alasan else {}
        js.write_text(json.dumps({"version": VERSI_XANY, "flags": flags, "checked": False, "shapes": shapes,
                                  "imagePath": f.name, "imageData": None, "imageHeight": h, "imageWidth": w},
                                 indent=2, ensure_ascii=False), encoding="utf-8")
        total += jumlah
        ringkas.append([f.name, "; ".join(alasan)] + [jumlah[k] for k in KELAS])
        baru += 1
        print(f"{baru}/{len(files)} {f.name} {dict(jumlah)} {alasan}", flush=True)

    p = out / "ringkasan_run.csv"
    baru_file = not p.exists()
    with p.open("a", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        if baru_file:
            wr.writerow(["filename", "alasan"] + KELAS)
        wr.writerows(ringkas)
    with p.open(newline="", encoding="utf-8") as fh:
        semua = list(csv.DictReader(fh))
    bobot = lambda r: sum(BOBOT_ALASAN.get(x.split(" x")[0], 1) for x in r["alasan"].split("; ") if x)
    semua.sort(key=lambda r: -bobot(r))
    with (out / "review_list.csv").open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, ["filename", "prioritas", "alasan"] + KELAS, extrasaction="ignore")
        wr.writeheader()
        for r in semua:
            wr.writerow({**r, "prioritas": bobot(r)})
    pb = out / "dibuang_aturan.csv"
    baru_b = not pb.exists()
    with pb.open("a", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        if baru_b:
            wr.writerow(["filename", "kelas", "skor", "kotak", "aturan"])
        wr.writerows(DIBUANG)
    urut = sorted(Path("data/pilot/images").glob("*.jpg"))
    lembar(out, {x.name: i + 1 for i, x in enumerate(urut)}, {r["filename"]: r["alasan"] for r in semua})
    print(f"\n== {baru} frame, {(time.time() - t0) / max(1, baru):.1f} detik/frame | {dict(total)}")


if __name__ == "__main__":
    main()
