"""evaluasi_baseline.py - evaluasi baseline JalanKu pada VAL KAMPUS saja (54 frame). Tidak menyentuh lokasi test.

Dijalankan dari root repo setelah `tools/latih_baseline.py` selesai. Memakai weights/best.pt tiap run.

Keluaran di runs/baseline/eval/ (tidak menimpa; kalau folder sudah ada, berhenti):
  <run>-val/        plot bawaan Ultralytics: confusion_matrix.png, confusion_matrix_normalized.png,
                    BoxPR_curve.png, BoxF1_curve.png (+ MaskPR/MaskF1 untuk seg)
  <run>/metrik.json metrik keseluruhan dan per kelas (dengan jumlah instance val), conf terbaik F1
  <run>/galat.json  analisis galat pada conf >= 0.25 (TP/FP/FN per kelas, pasangan tertukar, recall per ukuran objek)
  <run>/kontak_*.jpg  contact sheet 16 frame val (GT di kiri, prediksi di kanan): bagus + terburuk
  kecepatan.json    latensi/FPS: GPU dan CPU, batch 1, imgsz 640, warm-up, median (preprocess/inference/postprocess)
  tabel.md          semua tabel dalam Markdown (disalin ke docs/hasil-baseline.md)

Catatan metrik: P, R, F1 adalah nilai pada conf yang memaksimalkan F1 rata-rata kelas (cara Ultralytics);
mAP dihitung pada conf 0.001. Analisis galat dan contact sheet memakai conf 0.25 dan IoU 0.5.
Kecepatan adalah kecepatan LAPTOP ini (fp32), bukan kecepatan HP.

Opsi --versi-data=-v2 atau --versi-data=-v2-noR4 (pakai tanda sama dengan): evaluasi bobot YANG SAMA pada val versi data lain (setelah audit label kampus).
  Folder keluaran default menjadi runs/baseline/eval<versi>/ ... lebih aman beri --out sendiri (mis. runs/baseline/eval-v2/v2).
  kotak-gabung dievaluasi pada val dataset-gabung-kotak<versi> (val = kampus val); kalau folder itu tidak ada (mis. -v2-noR4,
  yang hanya membangun dataset kampus) dipakai dataset-kampus-kotak<versi>, yang val-nya identik menurut konstruksi.
  seg-kampus tidak dievaluasi ulang untuk versi baru (label seg tidak berubah; lihat docs/hasil-audit.md).

Contoh:
  python tools/evaluasi_baseline.py                       # semua run, semua langkah
  python tools/evaluasi_baseline.py --run kotak-gabung --aksi val
  python tools/evaluasi_baseline.py --aksi kecepatan      # sebaiknya saat GPU dan CPU idle
"""
import argparse
import json
import platform
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "runs" / "baseline"
RUNS = {
    "kotak-gabung": ("detect", ROOT / "data/dataset-gabung-kotak/data.yaml"),
    "kotak-kampus": ("detect", ROOT / "data/dataset-kampus-kotak/data.yaml"),
    "seg-kampus": ("segment", ROOT / "data/dataset-gabung-seg/data.yaml"),
}
LOW_N = 20  # kelas dengan instance val < 20 = angka kurang bisa dipercaya
CONF = 0.25
IOU = 0.5
IMG_EXT = {".jpg", ".jpeg", ".png"}
PALET = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40), (148, 103, 189),
         (140, 86, 75), (227, 119, 194), (23, 190, 207), (188, 189, 34), (127, 127, 127)]  # RGB


# ---------------------------------------------------------------- data val
def info_val(yaml_path):
    import yaml

    cfg = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    base = Path(cfg["path"])
    img_dir = base / cfg["val"]
    lab_dir = base / "labels" / Path(cfg["val"]).name
    imgs = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXT)
    return cfg["names"], imgs, lab_dir


def baca_gt(lab_file, w, h, tugas):
    """-> list (kelas, xyxy piksel, poligon piksel atau None)."""
    import numpy as np

    out = []
    if not lab_file.exists():
        return out
    for ln in lab_file.read_text().splitlines():
        v = ln.split()
        if len(v) < 5:
            continue
        c = int(v[0])
        a = [float(x) for x in v[1:]]
        if tugas == "detect" and len(a) == 4:
            xc, yc, bw, bh = a
            out.append((c, np.array([(xc - bw / 2) * w, (yc - bh / 2) * h, (xc + bw / 2) * w, (yc + bh / 2) * h]), None))
        elif len(a) >= 6:
            pts = np.array(a).reshape(-1, 2) * [w, h]
            out.append((c, np.array([pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()]), pts))
    return out


def iou_xyxy(a, b):
    import numpy as np

    x1, y1 = np.maximum(a[0], b[:, 0]), np.maximum(a[1], b[:, 1])
    x2, y2 = np.minimum(a[2], b[:, 2]), np.minimum(a[3], b[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) - inter
    return inter / np.maximum(ua, 1e-9)


# ---------------------------------------------------------------- 1. metrik Ultralytics
def rel(p):
    """Path relatif ke root repo; di luar repo (uji coba) pakai path penuh."""
    try:
        return str(Path(p).relative_to(ROOT))
    except ValueError:
        return str(p)


def jalankan_val(run, bobot, out):
    from ultralytics import YOLO
    import numpy as np
    from ultralytics.utils.metrics import smooth

    tugas, yaml_path = RUNS[run]
    model = YOLO(str(bobot))
    m = model.val(data=str(yaml_path), split="val", imgsz=640, batch=16, workers=2, device=0, plots=True, seed=0,
                  project=str(out), name=f"{run}-val", exist_ok=False, verbose=False)
    names = m.names
    nt = getattr(m, "nt_per_class", None)
    if nt is None:
        nt = getattr(m.box, "nt_per_class", None)
    jenis = {"box": m.box}
    if tugas == "segment":
        jenis["mask"] = m.seg
    hasil = dict(run=run, tugas=tugas, bobot=rel(bobot), plot_dir=rel(m.save_dir))
    for nama, mm in jenis.items():
        px = np.linspace(0, 1, mm.f1_curve.shape[1]) if hasattr(mm, "f1_curve") and mm.f1_curve.size else None
        conf_terbaik = float(px[smooth(mm.f1_curve.mean(0), 0.1).argmax()]) if px is not None else None
        kelas = []
        for i, ci in enumerate(mm.ap_class_index):
            p, r, ap50, ap = mm.class_result(i)
            n = int(nt[ci]) if nt is not None else None
            kelas.append(dict(id=int(ci), nama=names[int(ci)], n_instance=n, P=float(p), R=float(r), F1=float(mm.f1[i]),
                              mAP50=float(ap50), mAP50_95=float(ap), rendah=(n is not None and n < LOW_N)))
        hasil[nama] = dict(
            conf_F1_terbaik=conf_terbaik, P=float(mm.mp), R=float(mm.mr), F1=float(mm.f1.mean()), mAP50=float(mm.map50),
            mAP50_95=float(mm.map), kelas=kelas)
    hasil["n_instance_total"] = int(sum(nt)) if nt is not None else None
    hasil["plot"] = sorted(rel(p) for p in Path(m.save_dir).glob("*.png"))
    return hasil


# ---------------------------------------------------------------- 2. prediksi + galat
def prediksi_semua(model, imgs):
    import cv2

    out = {}
    hs = model.predict([str(p) for p in imgs], conf=CONF, imgsz=640, device=0, verbose=False, batch=8)
    for p, r in zip(imgs, hs):
        h, w = r.orig_shape
        d = dict(w=w, h=h, cls=r.boxes.cls.cpu().numpy().astype(int), conf=r.boxes.conf.cpu().numpy(),
                 xyxy=r.boxes.xyxy.cpu().numpy(), poly=None)
        if r.masks is not None:
            d["poly"] = [x for x in r.masks.xy]
        out[p.name] = d
    return out


def cocokkan_kotak(gt, pr):
    """Greedy per gambar. -> tp, fp(list), fn(list). fp: (idx, tertukar_dengan_kelas_atau_None); fn: (idx, tertukar_dengan_atau_None)."""
    import numpy as np

    order = np.argsort(-pr["conf"])
    pakai = set()
    tp = []
    fp = []
    for j in order:
        best, bi = 0.0, -1
        for i, (c, bx, _) in enumerate(gt):
            if i in pakai or c != pr["cls"][j]:
                continue
            v = iou_xyxy(pr["xyxy"][j], bx[None])[0]
            if v > best:
                best, bi = v, i
        if best >= IOU:
            pakai.add(bi)
            tp.append((bi, j))
        else:
            tuker = None
            for c, bx, _ in gt:
                if c != pr["cls"][j] and iou_xyxy(pr["xyxy"][j], bx[None])[0] >= IOU:
                    tuker = c
                    break
            fp.append((j, tuker))
    fn = []
    for i, (c, bx, _) in enumerate(gt):
        if i in pakai:
            continue
        tuker = None
        for j in range(len(pr["cls"])):
            if pr["cls"][j] != c and iou_xyxy(pr["xyxy"][j], bx[None])[0] >= IOU:
                tuker = int(pr["cls"][j])
                break
        fn.append((i, tuker))
    return tp, fp, fn


def raster(polys, w, h, s=0.25):
    import cv2
    import numpy as np

    m = np.zeros((int(h * s) + 1, int(w * s) + 1), np.uint8)
    for p in polys:
        if len(p) >= 3:
            cv2.fillPoly(m, [np.round(np.asarray(p) * s).astype(np.int32)], 1)
    return m.astype(bool)


def analisis(run, names, imgs, lab_dir, tugas, pred):
    """Hitung skor per gambar + statistik galat. -> (rekap, per_gambar)."""
    import cv2
    import numpy as np

    nc = len(names)
    per = {}
    st = {k: dict(tp=0, fp=0, fn=0, tuker_fp={}, tuker_fn={}) for k in range(nc)}
    bucket = {b: [0, 0] for b in ("<32", "32-64", "64-128", ">=128")}  # [GT, ditemukan] per ukuran @640
    fp_daftar = []
    fn_daftar = []
    iou_acc = {k: [0, 0] for k in range(nc)}  # seg: inter, union piksel
    for p in imgs:
        im = cv2.imread(str(p))
        h, w = im.shape[:2]
        gt = baca_gt(lab_dir / (p.stem + ".txt"), w, h, tugas)
        pr = pred[p.name]
        lokasi = p.stem.split("_20")[0]
        if tugas == "detect":
            tp, fp, fn = cocokkan_kotak(gt, pr)
            for i, j in tp:
                st[gt[i][0]]["tp"] += 1
            for j, tk in fp:
                c = int(pr["cls"][j])
                st[c]["fp"] += 1
                if tk is not None:
                    st[c]["tuker_fp"][names[tk]] = st[c]["tuker_fp"].get(names[tk], 0) + 1
                fp_daftar.append(dict(gambar=p.name, kelas=names[c], conf=round(float(pr["conf"][j]), 2),
                                      tertukar_dengan=names[tk] if tk is not None else None,
                                      xyxy=[round(float(v)) for v in pr["xyxy"][j]]))
            for i, tk in fn:
                c = gt[i][0]
                st[c]["fn"] += 1
                if tk is not None:
                    st[c]["tuker_fn"][names[tk]] = st[c]["tuker_fn"].get(names[tk], 0) + 1
                fn_daftar.append(dict(gambar=p.name, kelas=names[c], tertukar_dengan=names[tk] if tk is not None else None,
                                      xyxy=[round(float(v)) for v in gt[i][1]]))
            ketemu = {i for i, _ in tp}
            sk = 640.0 / max(w, h)
            for i, (c, bx, _) in enumerate(gt):
                ukuran = float(np.sqrt((bx[2] - bx[0]) * (bx[3] - bx[1]))) * sk
                b = "<32" if ukuran < 32 else "32-64" if ukuran < 64 else "64-128" if ukuran < 128 else ">=128"
                bucket[b][0] += 1
                bucket[b][1] += int(i in ketemu)
            ntp, nfp, nfn = len(tp), len(fp), len(fn)
            f1 = 2 * ntp / max(2 * ntp + nfp + nfn, 1) if (len(gt) or len(pr["cls"])) else None
            per[p.name] = dict(lokasi=lokasi, skor=f1, n_gt=len(gt), tp=ntp, fp=nfp, fn=nfn)
        else:
            ious = []
            for c in range(nc):
                g = raster([x[2] for x in gt if x[0] == c], w, h)
                q = raster([pr["poly"][j] for j in range(len(pr["cls"])) if pr["cls"][j] == c] if pr["poly"] else [], w, h)
                u = int((g | q).sum())
                if u:
                    it = int((g & q).sum())
                    ious.append(it / u)
                    iou_acc[c][0] += it
                    iou_acc[c][1] += u
            per[p.name] = dict(lokasi=lokasi, skor=float(np.mean(ious)) if ious else None, n_gt=len(gt),
                               n_pred=len(pr["cls"]))
    rekap = dict(conf=CONF, iou=IOU)
    if tugas == "detect":
        rekap["per_kelas"] = {names[k]: dict(tp=v["tp"], fp=v["fp"], fn=v["fn"], fp_tertukar_dengan=v["tuker_fp"],
                                             fn_tertukar_dengan=v["tuker_fn"]) for k, v in st.items()}
        rekap["recall_per_ukuran_px640"] = {b: dict(gt=a, ditemukan=d, recall=(d / a if a else None)) for b, (a, d) in bucket.items()}
        rekap["fp_daftar"] = sorted(fp_daftar, key=lambda x: -x["conf"])
        rekap["fn_daftar"] = fn_daftar
    else:
        rekap["iou_piksel_per_kelas"] = {names[k]: (v[0] / v[1] if v[1] else None) for k, v in iou_acc.items()}
    return rekap, per


# ---------------------------------------------------------------- 3. contact sheet
def gambar_panel(im, items, tugas, names, ch, cw, judul=None):
    """items: list (kelas, xyxy, poligon atau None, conf atau None)."""
    import cv2
    import numpy as np

    h, w = im.shape[:2]
    cv = im.copy()
    tebal = max(2, int(round(max(h, w) / 400)))
    fs = max(0.5, max(h, w) / 900)
    if tugas == "segment":
        lay = cv.copy()
        for c, bx, poly, cf in items:
            if poly is not None and len(poly) >= 3:
                cv2.fillPoly(lay, [np.round(np.asarray(poly)).astype(np.int32)], PALET[c % 10][::-1])
        cv = cv2.addWeighted(lay, 0.45, cv, 0.55, 0)
    for c, bx, poly, cf in items:
        col = PALET[c % 10][::-1]
        if tugas == "segment" and poly is not None and len(poly) >= 3:
            cv2.polylines(cv, [np.round(np.asarray(poly)).astype(np.int32)], True, col, tebal)
            x, y = int(np.asarray(poly)[:, 0].mean()), int(np.asarray(poly)[:, 1].mean())
        else:
            x1, y1, x2, y2 = [int(v) for v in bx]
            cv2.rectangle(cv, (x1, y1), (x2, y2), col, tebal)
            x, y = x1, max(y1 - 4, 12)
        txt = names[c] + (f" {cf:.2f}" if cf is not None else "")
        cv2.putText(cv, txt, (x, y), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), tebal + 2, cv2.LINE_AA)
        cv2.putText(cv, txt, (x, y), cv2.FONT_HERSHEY_SIMPLEX, fs, col, tebal, cv2.LINE_AA)
    s = min(cw / w, ch / h)
    cv = cv2.resize(cv, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    kanvas = np.full((ch, cw, 3), 245, np.uint8)
    kanvas[: cv.shape[0], : cv.shape[1]] = cv
    return kanvas


def pilih(per, n_bagus=8, n_buruk=8):
    """Campuran: n frame terbaik (min 3 objek GT) dan n terburuk, bergantian antar lokasi supaya beragam."""
    def rr(urut, n):
        grup = {}
        for nm in urut:
            grup.setdefault(per[nm]["lokasi"], []).append(nm)
        hasil = []
        while len(hasil) < n and any(grup.values()):
            for k in list(grup):
                if grup[k] and len(hasil) < n:
                    hasil.append(grup[k].pop(0))
        return hasil

    ada = [k for k, v in per.items() if v["skor"] is not None]
    bagus = sorted([k for k in ada if per[k]["n_gt"] >= 3], key=lambda k: (-per[k]["skor"], -per[k]["n_gt"], k))
    bagus = rr(bagus, n_bagus)
    buruk = rr(sorted([k for k in ada if k not in bagus], key=lambda k: (per[k]["skor"], -per[k]["n_gt"], k)), n_buruk)
    return bagus, buruk


def buat_sheet(run, tugas, names, imgs, lab_dir, pred, per, pilihan, kolom, cw, ch, path, jenis):
    import cv2
    import numpy as np

    peta = {p.name: p for p in imgs}
    pasang = []
    for nm in pilihan:
        im = cv2.imread(str(peta[nm]))
        h, w = im.shape[:2]
        gt = [(c, bx, poly, None) for c, bx, poly in baca_gt(lab_dir / (peta[nm].stem + ".txt"), w, h, tugas)]
        pr = pred[nm]
        pit = [(int(pr["cls"][j]), pr["xyxy"][j], pr["poly"][j] if pr["poly"] is not None else None, float(pr["conf"][j]))
               for j in range(len(pr["cls"]))]
        g = gambar_panel(im, gt, tugas, names, ch, cw)
        q = gambar_panel(im, pit, tugas, names, ch, cw)
        v = per[nm]
        ket = (f"{jenis} | {v['lokasi'][:22]} | skor {v['skor']:.2f} | "
               + (f"TP{v['tp']} FP{v['fp']} FN{v['fn']}" if tugas == "detect" else f"GT{v['n_gt']} pred{v['n_pred']}"))
        atas = np.full((22, cw * 2 + 4, 3), 255, np.uint8)
        cv2.putText(atas, ket, (3, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        pasang.append(np.vstack([atas, np.hstack([g, np.full((ch, 4, 3), 255, np.uint8), q])]))
    baris = []
    for i in range(0, len(pasang), kolom):
        r = pasang[i:i + kolom]
        while len(r) < kolom:
            r.append(np.full_like(pasang[0], 255))
        baris.append(np.hstack([np.hstack([x, np.full((x.shape[0], 10, 3), 255, np.uint8)]) for x in r]))
    cv2.imwrite(str(path), np.vstack(baris), [cv2.IMWRITE_JPEG_QUALITY, 88])


# ---------------------------------------------------------------- 4. kecepatan
def cpu_nama():
    try:
        o = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                           capture_output=True, text=True, timeout=30).stdout.strip()
        return o or platform.processor()
    except Exception:
        return platform.processor()


def ukur_kecepatan(bobot, imgs, device, threads=None):
    import torch
    from ultralytics import YOLO

    model = YOLO(str(bobot))
    model.predict(str(imgs[0]), imgsz=640, conf=CONF, device=device, verbose=False)  # setup; select_device('cpu') MERESET thread ke 8
    if threads:
        torch.set_num_threads(threads)  # harus SETELAH setup di atas, kalau tidak ditimpa Ultralytics
    for _ in range(10):  # warm-up
        model.predict(str(imgs[0]), imgsz=640, conf=CONF, device=device, verbose=False)
    pre, inf, pos, tot = [], [], [], []
    for p in imgs:
        r = model.predict(str(p), imgsz=640, conf=CONF, device=device, verbose=False)[0]
        s = r.speed
        pre.append(s["preprocess"]); inf.append(s["inference"]); pos.append(s["postprocess"])
        tot.append(s["preprocess"] + s["inference"] + s["postprocess"])
    med = statistics.median
    aktual = torch.get_num_threads()
    if threads and aktual != threads:
        raise RuntimeError(f"thread torch aktual {aktual} != diminta {threads}")
    return dict(device=str(device), torch_threads=aktual, n_gambar=len(imgs), preprocess_ms=med(pre), inference_ms=med(inf), postprocess_ms=med(pos),
                total_ms=med(tot), fps=1000 / med(tot), total_ms_p95=sorted(tot)[int(0.95 * len(tot)) - 1])


# ---------------------------------------------------------------- tabel Markdown
def f3(x):
    return "-" if x is None else f"{x:.3f}"


def tabel_overall(h):
    ks = ["box"] + (["mask"] if "mask" in h else [])
    baris = ["| Jenis | mAP50 | mAP50-95 | P | R | F1 | conf F1 terbaik |", "|---|---|---|---|---|---|---|"]
    for k in ks:
        d = h[k]
        baris.append(f"| {k} | {f3(d['mAP50'])} | {f3(d['mAP50_95'])} | {f3(d['P'])} | {f3(d['R'])} | {f3(d['F1'])} | {f3(d['conf_F1_terbaik'])} |")
    return "\n".join(baris)


def tabel_kelas(h, k):
    baris = [f"| Kelas | n val | mAP50 | mAP50-95 | P | R | F1 | Catatan |", "|---|---|---|---|---|---|---|---|"]
    for c in h[k]["kelas"]:
        cat = f"n < {LOW_N}: angka kurang bisa dipercaya" if c["rendah"] else ""
        baris.append(f"| {c['nama']} | {c['n_instance']} | {f3(c['mAP50'])} | {f3(c['mAP50_95'])} | {f3(c['P'])} | {f3(c['R'])} | {f3(c['F1'])} | {cat} |")
    return "\n".join(baris)


def tabel_banding(a, b):
    ka, kb = {c["nama"]: c for c in a["box"]["kelas"]}, {c["nama"]: c for c in b["box"]["kelas"]}
    baris = ["| Kelas | n val | mAP50 gabung | mAP50 kampus | Selisih | mAP50-95 gabung | mAP50-95 kampus | Selisih | F1 gabung | F1 kampus | Catatan |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in ka:
        x, y = ka[n], kb.get(n)
        if y is None:
            continue
        cat = f"n < {LOW_N}" if x["rendah"] else ""
        baris.append(f"| {n} | {x['n_instance']} | {f3(x['mAP50'])} | {f3(y['mAP50'])} | {x['mAP50'] - y['mAP50']:+.3f} | "
                     f"{f3(x['mAP50_95'])} | {f3(y['mAP50_95'])} | {x['mAP50_95'] - y['mAP50_95']:+.3f} | {f3(x['F1'])} | {f3(y['F1'])} | {cat} |")
    A, B = a["box"], b["box"]
    baris.append(f"| **semua** | {a['n_instance_total']} | {f3(A['mAP50'])} | {f3(B['mAP50'])} | {A['mAP50'] - B['mAP50']:+.3f} | "
                 f"{f3(A['mAP50_95'])} | {f3(B['mAP50_95'])} | {A['mAP50_95'] - B['mAP50_95']:+.3f} | {f3(A['F1'])} | {f3(B['F1'])} | |")
    return "\n".join(baris)


def tabel_kecepatan(sp):
    baris = ["| Model | Perangkat | Preprocess (ms) | Inference (ms) | Postprocess (ms) | Total (ms) | FPS | p95 total (ms) |", "|---|---|---|---|---|---|---|---|"]
    for run, d in sp["hasil"].items():
        for dev, v in d.items():
            baris.append(f"| {run} | {dev} | {v['preprocess_ms']:.1f} | {v['inference_ms']:.1f} | {v['postprocess_ms']:.1f} | {v['total_ms']:.1f} | {v['fps']:.1f} | {v['total_ms_p95']:.1f} |")
    return "\n".join(baris)


def tabel_galat(g, names):
    if "per_kelas" not in g:
        baris = ["| Kelas | IoU piksel (conf 0.25) |", "|---|---|"]
        for k, v in g["iou_piksel_per_kelas"].items():
            baris.append(f"| {k} | {f3(v)} |")
        return "\n".join(baris)
    baris = ["| Kelas | TP | FP | FN | FP yang sebenarnya kelas lain | FN yang diprediksi kelas lain |", "|---|---|---|---|---|---|"]
    for k, v in g["per_kelas"].items():
        baris.append(f"| {k} | {v['tp']} | {v['fp']} | {v['fn']} | {v['fp_tertukar_dengan'] or '-'} | {v['fn_tertukar_dengan'] or '-'} |")
    baris += ["", "| Ukuran objek (akar luas, px pada gambar 640) | GT | Ditemukan | Recall |", "|---|---|---|---|"]
    for b, v in g["recall_per_ukuran_px640"].items():
        baris.append(f"| {b} | {v['gt']} | {v['ditemukan']} | {f3(v['recall'])} |")
    return "\n".join(baris)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", choices=sorted(RUNS), action="append", help="default: semua")
    ap.add_argument("--aksi", choices=["val", "galat", "kecepatan", "cm025", "semua"], default="semua")
    ap.add_argument("--out", default=str(BASE / "eval"), help="folder keluaran (tidak boleh sudah ada isinya yang sama)")
    ap.add_argument("--bobot-dir", help="ganti sumber weights (uji coba): <dir>/<run>/weights/best.pt")
    ap.add_argument("--versi-data", default="", help="akhiran versi dataset, mis. -v2 atau -v2-noR4 (default: kosong = data lama)")
    args = ap.parse_args()
    if args.versi_data:
        if args.run is None:
            args.run = [r for r in sorted(RUNS) if RUNS[r][0] == "detect"]
        for r in list(RUNS):
            tugas, yp = RUNS[r]
            if tugas != "detect":
                continue
            yp2 = Path(str(yp).replace("dataset-gabung-kotak", f"dataset-gabung-kotak{args.versi_data}")
                       .replace("dataset-kampus-kotak", f"dataset-kampus-kotak{args.versi_data}"))
            if not yp2.exists() and "gabung" in str(yp2):
                yp2 = Path(str(yp2).replace(f"dataset-gabung-kotak{args.versi_data}", f"dataset-kampus-kotak{args.versi_data}"))
            if not yp2.exists():
                sys.exit(f"Tidak ada: {yp2}")
            RUNS[r] = (tugas, yp2)
        if args.run and any(RUNS[r][0] != "detect" for r in args.run):
            sys.exit("--versi-data hanya untuk run kotak (detect)")

    runs = args.run or sorted(RUNS)
    out = Path(args.out).resolve()  # harus absolut: Ultralytics menafsirkan project relatif di bawah runs/detect
    out.mkdir(parents=True, exist_ok=True)
    bobot = {r: Path(args.bobot_dir or BASE) / r / "weights" / "best.pt" for r in runs}
    for r, b in bobot.items():
        if not b.exists():
            sys.exit(f"Tidak ada: {b}")
    for r in runs:
        for sub in ([f"{r}-val", r] if args.aksi in ("val", "semua") else []):
            if (out / sub).exists():
                sys.exit(f"{out / sub} sudah ada. Tidak ditimpa.")
    if args.aksi in ("kecepatan", "semua") and (out / "kecepatan.json").exists():
        sys.exit(f"{out / 'kecepatan.json'} sudah ada. Tidak ditimpa.")

    from ultralytics import YOLO

    semua = {}
    if args.aksi in ("val", "semua", "galat"):
        for r in runs:
            tugas, yaml_path = RUNS[r]
            names, imgs, lab_dir = info_val(yaml_path)
            (out / r).mkdir(exist_ok=True)
            h = None
            if args.aksi in ("val", "semua"):
                print(f"== val {r}", flush=True)
                h = jalankan_val(r, bobot[r], out)
                (out / r / "metrik.json").write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")
                semua[r] = h
            print(f"== galat + kontak {r}", flush=True)
            model = YOLO(str(bobot[r]))
            pred = prediksi_semua(model, imgs)
            rekap, per = analisis(r, names, imgs, lab_dir, tugas, pred)
            rekap["per_gambar"] = per
            (out / r / "galat.json").write_text(json.dumps(rekap, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
            bagus, buruk = pilih(per)
            jenis_skor = "F1" if tugas == "detect" else "mIoU"
            buat_sheet(r, tugas, names, imgs, lab_dir, pred, per, bagus + buruk, 4, 240, 427, out / r / "kontak_16.jpg", "")
            buat_sheet(r, tugas, names, imgs, lab_dir, pred, per, bagus, 2, 380, 676, out / r / "kontak_bagus.jpg", "bagus")
            buat_sheet(r, tugas, names, imgs, lab_dir, pred, per, buruk, 2, 380, 676, out / r / "kontak_terburuk.jpg", "terburuk")
            (out / r / "kontak_pilihan.json").write_text(json.dumps(dict(skor=jenis_skor, bagus=bagus, terburuk=buruk), indent=2),
                                                         encoding="utf-8")
            print(f"   kontak: {out / r}", flush=True)

    if args.aksi in ("cm025", "semua"):
        # confusion matrix di conf 0.25 (titik operasi). Plot bawaan val memakai conf 0.001, jadi kolom background membengkak.
        for r in runs:
            if (out / f"{r}-val-conf025").exists():
                sys.exit(f"{out / f'{r}-val-conf025'} sudah ada. Tidak ditimpa.")
            print(f"== confusion matrix conf {CONF} {r}", flush=True)
            YOLO(str(bobot[r])).val(data=str(RUNS[r][1]), split="val", imgsz=640, batch=16, workers=2, device=0, plots=True,
                                    seed=0, conf=CONF, project=str(out), name=f"{r}-val-conf025", exist_ok=False, verbose=False)

    if args.aksi in ("kecepatan", "semua"):
        sp = dict(catatan="Kecepatan LAPTOP ini, fp32, batch 1, imgsz 640 (sisi panjang), conf 0.25, warm-up 10, median atas val kampus. Bukan kecepatan HP.",
                  cpu=cpu_nama(), gpu=None, hasil={})
        import torch

        import os
        import psutil

        sp["gpu"] = torch.cuda.get_device_name(0)
        sp["torch_threads_awal"] = torch.get_num_threads()
        sp["omp_num_threads_env"] = os.environ.get("OMP_NUM_THREADS")
        sp["cpu_core_fisik"] = psutil.cpu_count(logical=False)
        sp["cpu_thread_diuji"] = sorted({1, psutil.cpu_count(logical=False)})
        for r in runs:
            names, imgs, lab_dir = info_val(RUNS[r][1])
            sp["hasil"][r] = {}
            print(f"== kecepatan {r} GPU", flush=True)
            sp["hasil"][r]["GPU"] = ukur_kecepatan(bobot[r], imgs, 0)
            for th in sp["cpu_thread_diuji"]:  # OMP_NUM_THREADS=1 di environment ini -> ukur 1 thread dan semua core fisik
                print(f"== kecepatan {r} CPU {th} thread", flush=True)
                sp["hasil"][r][f"CPU ({th} thread)"] = ukur_kecepatan(bobot[r], imgs, "cpu", threads=th)
        (out / "kecepatan.json").write_text(json.dumps(sp, indent=2, ensure_ascii=False), encoding="utf-8")
        semua["_kecepatan"] = sp

    # tabel.md dari file yang ada
    md = []
    hs = {}
    for r in sorted(RUNS):
        f = out / r / "metrik.json"
        if f.exists():
            hs[r] = json.loads(f.read_text(encoding="utf-8"))
    for r, h in hs.items():
        md += [f"## {r}", "", f"Bobot: `{h['bobot']}`; plot: `{h['plot_dir']}`", "", tabel_overall(h), "",
               "Per kelas (box):", "", tabel_kelas(h, "box"), ""]
        if "mask" in h:
            md += ["Per kelas (mask):", "", tabel_kelas(h, "mask"), ""]
        g = out / r / "galat.json"
        if g.exists():
            md += [f"Galat pada conf >= {CONF}, IoU >= {IOU}:", "", tabel_galat(json.loads(g.read_text(encoding='utf-8')), None), ""]
    if "kotak-gabung" in hs and "kotak-kampus" in hs:
        md += ["## Perbandingan kotak-gabung vs kotak-kampus", "", tabel_banding(hs["kotak-gabung"], hs["kotak-kampus"]), ""]
    kf = out / "kecepatan.json"
    if kf.exists():
        sp = json.loads(kf.read_text(encoding="utf-8"))
        md += ["## Kecepatan", "", sp["catatan"], f"CPU: {sp['cpu']} ({sp['cpu_core_fisik']} core fisik); GPU: {sp['gpu']}; OMP_NUM_THREADS di environment: {sp['omp_num_threads_env']} (torch awal {sp['torch_threads_awal']} thread; jumlah thread tiap baris diverifikasi setelah pengukuran)", "",
               tabel_kecepatan(sp), ""]
    if md:
        (out / "tabel.md").write_text("\n".join(md), encoding="utf-8")
        print(f"tabel: {out / 'tabel.md'}")


if __name__ == "__main__":
    main()
