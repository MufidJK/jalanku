"""Tahap 5a, Bagian A: akurasi box + seg pada imgsz 320 / 416 (data/prompt-model-hp.md section 3). VAL v2 saja.

Empat langkah, masing-masing di venv yang punya paketnya (dijalankan dari root repo):

  venv\\Scripts\\python spike\\eval_hp.py --bagian pt         # GPU: box .pt 640/416/320 (jalur t1_val), seg Ultralytics val 640/416/320
  venv-export\\Scripts\\python spike\\export_onnx.py --fp16   # (opsional) {box,seg}_{320,416}_fp16.onnx
  venv-export\\Scripts\\python spike\\eval_hp.py --bagian onnx # CPU: box ONNX (jalur app.js) + cek jumlah deteksi ONNX vs .pt, fp16 vs fp32
  venv-export\\Scripts\\python spike\\eval_hp.py --bagian laporan  # -> data/model-hp/akurasi.json + akurasi.md

Jalur box ONNX ("angka resmi", seperti HP): letterbox persegi pad 114 persis app.js (offset Math.round(x - 0.1)), RGB 0..1 NCHW,
decode output0 [1, 4+nc, N] (skor max kelas, conf >= 0.001), NMS per kelas IoU 0.7 (greedy, sama dengan app.js; tanpa batas
max_det seperti app.js), kotak dipetakan balik ke koordinat gambar asli (dipotong ke tepi gambar), lalu ensemble_val.metrik()
(sama dengan t1_val) dan ensemble_val.conf025() (TP/FP/FN + recall dekat y2 >= 0.65 pada conf 0.25).
Jalur box .pt (pembanding): ensemble_val.prediksi() (conf 0.001, max_det 300) dengan imgsz diganti, lalu metrik yang sama.
Seg: evaluasi_baseline.jalankan_val (jalur yang sama dengan angka 0.647) pada imgsz 640/416/320.

Tidak menyentuh test set. Tidak mengubah tools/. Menolak menimpa berkas keluaran di data/model-hp/.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ensemble_val as ev  # noqa: E402
import evaluasi_baseline as eb  # noqa: E402
import evaluasi_ronde2 as er  # noqa: E402

OUT = ROOT / "data" / "model-hp"
ONNX = ROOT / "models" / "onnx"
BOX_PT = "models/ronde2/r2-kotak-v3_best.pt"
SEG_PT = "models/ronde2/r2-seg-v3_best.pt"
SIZES = (320, 416)
CONF_MAP, IOU_NMS, CONF_CEK = 0.001, 0.7, 0.25
PENTING = ("tangga", "tepian", "orang")
ATURAN = dict(box_mAP50=0.42, seg_mask_mAP50=0.55, fps=3.0)
REF = dict(box_pt_640_mAP50=0.471, seg_mask_640_mAP50=0.647, C2_mAP50=0.613)


def tulis(path, obj):
    if path.exists():
        sys.exit(f"{path} sudah ada, tidak ditimpa. Hapus/ganti nama dulu kalau memang mau mengulang.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    print("tersimpan:", path, flush=True)


def ringkas_box(names, imgs, lab_dir, pred):
    m = ev.metrik(names, imgs, lab_dir, pred)
    c = ev.conf025(names, imgs, lab_dir, pred)
    return dict(metrik=m, conf025=dict(total=c["total"], F1_mikro=c["F1_mikro"], fp_per_frame=c["fp_per_frame"],
                                       recall_dekat=c["recall_dekat"], recall_jauh=c["recall_jauh"], per_kelas=c["per_kelas"]))


# ---------------------------------------------------------------- letterbox + decode seperti app.js
def jsround(x):
    return int(math.floor(x + 0.5))  # Math.round


def letterbox_js(im_bgr, sz):
    import cv2

    h, w = im_bgr.shape[:2]
    r = min(sz / h, sz / w)
    nw, nh = jsround(w * r), jsround(h * r)
    left, top = jsround((sz - nw) / 2 - 0.1), jsround((sz - nh) / 2 - 0.1)
    out = np.full((sz, sz, 3), 114, np.uint8)
    out[top:top + nh, left:left + nw] = cv2.resize(im_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x = np.ascontiguousarray(out[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
    return x, out, dict(r=r, left=left, top=top, w=w, h=h)


def decode_nms(o0, nc, conf_min):
    """o0: [4+nc(+32), N] -> xyxy (input px), conf, cls setelah NMS per kelas (greedy, IoU > 0.7 dibuang)."""
    import torch
    import torchvision

    bx, sc = o0[:4].T, o0[4:4 + nc].T
    conf, cl = sc.max(1), sc.argmax(1)
    k = conf >= conf_min
    bx, conf, cl = bx[k], conf[k], cl[k]
    xyxy = np.c_[bx[:, 0] - bx[:, 2] / 2, bx[:, 1] - bx[:, 3] / 2, bx[:, 0] + bx[:, 2] / 2, bx[:, 1] + bx[:, 3] / 2]
    keep = torchvision.ops.batched_nms(torch.tensor(xyxy, dtype=torch.float32), torch.tensor(conf, dtype=torch.float32),
                                       torch.tensor(cl), IOU_NMS).numpy()
    return xyxy[keep], conf[keep], cl[keep]


def sesi(path):
    import onnxruntime as ort

    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def prediksi_onnx(path, sz, imgs, nc):
    import cv2

    s = sesi(path)
    out, t = {}, []
    for p in imgs:
        x, _, g = letterbox_js(cv2.imread(str(p)), sz)
        a = time.perf_counter()
        o0 = s.run(None, {"images": x})[0][0]
        t.append((time.perf_counter() - a) * 1000)
        xyxy, conf, cl = decode_nms(o0, nc, CONF_MAP)
        xyxy = (xyxy - [g["left"], g["top"], g["left"], g["top"]]) / g["r"]
        xyxy = np.clip(xyxy, 0, [g["w"], g["h"], g["w"], g["h"]])
        out[p.name] = dict(w=g["w"], h=g["h"], cls=cl.astype(int), conf=conf.astype(float), xyxy=xyxy.astype(float), poly=None)
    return out, float(np.median(t))


# ---------------------------------------------------------------- bagian pt (GPU, venv utama)
def bagian_pt():
    out = OUT / "pt.json"
    if out.exists():
        sys.exit(f"{out} sudah ada, tidak ditimpa.")
    names, imgs, lab_dir = er.cek_val(er.YK)
    er.pasang_imgsz()
    h = dict(sumber="val v2 (er.cek_val(er.YK), 54 frame)", box_pt={}, seg_ultra={})
    for sz in (640,) + SIZES:
        nm = f"hp-box-{sz}"
        er.MODEL[nm] = ("detect", er.YK, BOX_PT, sz)
        print(f"== box .pt imgsz {sz}", flush=True)
        pred, _ = ev.prediksi(nm, imgs, conf=CONF_MAP)
        h["box_pt"][str(sz)] = ringkas_box(names, imgs, lab_dir, pred)
        print(f"   mAP50 {h['box_pt'][str(sz)]['metrik']['mAP50']:.4f}", flush=True)
    m640 = h["box_pt"]["640"]["metrik"]["mAP50"]
    h["sanity_640"] = dict(mAP50=m640, target=REF["box_pt_640_mAP50"], lolos=abs(m640 - REF["box_pt_640_mAP50"]) <= 0.005)
    runs = OUT / "runs"
    for sz in (640,) + SIZES:
        nm = f"hp-seg-{sz}"
        er.IMGSZ["nilai"] = sz
        eb.RUNS[nm] = ("segment", er.YS)
        print(f"== seg Ultralytics val imgsz {sz}", flush=True)
        u = eb.jalankan_val(nm, ROOT / SEG_PT, runs)
        u["imgsz"] = sz
        h["seg_ultra"][str(sz)] = u
        print(f"   mask mAP50 {u['mask']['mAP50']:.4f} R {u['mask']['R']:.3f}", flush=True)
    tulis(out, h)
    print(f"Sanity box .pt 640: mAP50 {m640:.4f} (target {REF['box_pt_640_mAP50']}) -> {'OK' if h['sanity_640']['lolos'] else 'TIDAK COCOK'}")


# ---------------------------------------------------------------- bagian onnx (CPU, venv-export)
def hitung_cek(sz, kind, pt_name, imgs, names):
    """Jumlah deteksi conf >= 0.25 pada 3 frame: .pt vs ONNX fp32 vs ONNX fp16 (gambar letterbox yang sama)."""
    import cv2
    from ultralytics import YOLO

    pt = YOLO(str(ROOT / pt_name))
    nc = len(names)
    files = {"fp32": ONNX / f"{kind}_{sz}.onnx", "fp16": ONNX / f"{kind}_{sz}_fp16.onnx"}
    sess = {k: sesi(v) for k, v in files.items() if v.exists()}
    rows = []
    for p in imgs:
        x, lb, _ = letterbox_js(cv2.imread(str(p)), sz)
        r = dict(gambar=p.name, pt=sorted(names[int(c)] for c in pt.predict(lb, imgsz=sz, conf=CONF_CEK, iou=IOU_NMS, device="cpu",
                                                                            verbose=False)[0].boxes.cls.numpy()))
        for k, s in sess.items():
            _, _, cl = decode_nms(s.run(None, {"images": x})[0][0], nc, CONF_CEK)
            r[k] = sorted(names[int(c)] for c in cl)
        rows.append(r)
    return rows


def bagian_onnx():
    out = OUT / "onnx.json"
    if out.exists():
        sys.exit(f"{out} sudah ada, tidak ditimpa.")
    names, imgs, lab_dir = er.cek_val(er.YK)
    names_s, imgs_s, _ = eb.info_val(er.YS)
    h = dict(sumber="val v2 (er.cek_val(er.YK), 54 frame)", jalur="letterbox app.js + NMS per kelas IoU 0.7 + ensemble_val.metrik",
             box_onnx={}, cek_jumlah={}, ada_fp16={})
    for sz in (640,) + SIZES:
        for prec in ("fp32", "fp16"):
            f = ONNX / (f"box_{sz}.onnx" if prec == "fp32" else f"box_{sz}_fp16.onnx")
            if not f.exists():
                continue
            print(f"== box ONNX {sz} {prec}", flush=True)
            pred, ms = prediksi_onnx(f, sz, imgs, len(names))
            r = ringkas_box(names, imgs, lab_dir, pred)
            r["cpu_ms_median"] = ms
            h["box_onnx"][f"{sz}_{prec}"] = r
            print(f"   mAP50 {r['metrik']['mAP50']:.4f} mAP50-95 {r['metrik']['mAP50_95']:.4f} n_pred {r['metrik']['n_prediksi']}", flush=True)
    for sz in SIZES:
        for kind, pt_name, nm, im in (("box", BOX_PT, names, imgs), ("seg", SEG_PT, names_s, imgs_s)):
            h["ada_fp16"][f"{kind}_{sz}"] = (ONNX / f"{kind}_{sz}_fp16.onnx").exists()
            print(f"== cek jumlah {kind} {sz}", flush=True)
            h["cek_jumlah"][f"{kind}_{sz}"] = hitung_cek(sz, kind, pt_name, im[:3], nm)
    tulis(out, h)


# ---------------------------------------------------------------- laporan
def f3(x):
    return "-" if x is None else f"{x:.3f}"


def bagian_laporan():
    for p in (OUT / "akurasi.json", OUT / "akurasi.md"):
        if p.exists():
            sys.exit(f"{p} sudah ada, tidak ditimpa.")
    pt =json.loads((OUT / "pt.json").read_text(encoding="utf-8"))
    ox = json.loads((OUT / "onnx.json").read_text(encoding="utf-8"))
    hasil = dict(aturan=ATURAN, referensi=REF, sanity_640=pt["sanity_640"], per_ukuran={})
    md = ["# Tahap 5a, Bagian A: akurasi (val v2, 54 frame)", "",
          f"Sanity: box .pt imgsz 640 lewat jalur t1_val: mAP50 {pt['sanity_640']['mAP50']:.4f} (target 0.471, toleransi 0.005): "
          f"{'cocok' if pt['sanity_640']['lolos'] else 'TIDAK cocok'}.", "",
          "## Box (r2-kotak-v3, dilatih 640)", "",
          "| imgsz | jalur | mAP50 | mAP50-95 | F1 | AP50 tangga | AP50 tepian | AP50 orang | recall dekat 0.25 | TP/FP/FN 0.25 | n prediksi |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]

    def baris(sz, jalur, r):
        m, c = r["metrik"], r["conf025"]
        k = m["kelas"]
        rd = c["recall_dekat"]
        md.append(f"| {sz} | {jalur} | {f3(m['mAP50'])} | {f3(m['mAP50_95'])} | {f3(m['F1'])} | "
                  + " | ".join(f3(k.get(n, {}).get("AP50")) for n in PENTING)
                  + f" | {rd['ditemukan']}/{rd['gt']} ({f3(rd['recall'])}) | {c['total']['tp']}/{c['total']['fp']}/{c['total']['fn']} | {m['n_prediksi']} |")

    for sz in ("640",) + tuple(str(s) for s in SIZES):
        baris(sz, ".pt (pembanding)", pt["box_pt"][sz])
        for prec in ("fp32", "fp16"):
            if f"{sz}_{prec}" in ox["box_onnx"]:
                baris(sz, f"ONNX {prec}" + (" (resmi)" if prec == "fp32" and sz != "640" else ""), ox["box_onnx"][f"{sz}_{prec}"])
    md += ["", "C2 (ensemble laptop, 4 model 960/1280): mAP50 0.613. Tidak jalan di HP.", "",
           "### AP50 per kelas, box", ""]
    kol = []
    for sz in ("640",) + tuple(str(s) for s in SIZES):
        kol.append((f".pt {sz}", pt["box_pt"][sz]))
        for prec in ("fp32", "fp16"):
            if f"{sz}_{prec}" in ox["box_onnx"]:
                kol.append((f"ONNX {sz} {prec}", ox["box_onnx"][f"{sz}_{prec}"]))
    kelas = list(pt["box_pt"]["640"]["metrik"]["kelas"])
    md += ["| kelas | n | " + " | ".join(k for k, _ in kol) + " |", "|---|---|" + "---|" * len(kol)]
    for k in kelas:
        n = pt["box_pt"]["640"]["metrik"]["kelas"][k]["n"]
        md.append(f"| {'**' + k + '**' if k in PENTING else k}{' *' if n < eb.LOW_N else ''} | {n} | "
                  + " | ".join(f3(r["metrik"]["kelas"].get(k, {}).get("AP50")) for _, r in kol) + " |")
    md += ["", "\\* n < 20 instance di val: angka kelas ini goyah.", "",
           "## Seg (r2-seg-v3, dilatih 640), Ultralytics val", "",
           "| imgsz | box mAP50 | mask mAP50 | mask mAP50-95 | mask P | mask R | mask mAP50 jalur_jalan | jalan_kendaraan | tangga |",
           "|---|---|---|---|---|---|---|---|---|"]
    for sz in ("640",) + tuple(str(s) for s in SIZES):
        u = pt["seg_ultra"][sz]
        mk = {c["nama"]: c for c in u["mask"]["kelas"]}
        md.append(f"| {sz} | {f3(u['box']['mAP50'])} | {f3(u['mask']['mAP50'])} | {f3(u['mask']['mAP50_95'])} | {f3(u['mask']['P'])} | "
                  f"{f3(u['mask']['R'])} | " + " | ".join(f3(mk.get(n, {}).get("mAP50")) for n in ("jalur_jalan", "jalan_kendaraan", "tangga")) + " |")
    md += ["", "## Aturan 1 dan 2 (aturan 3, kecepatan, menunggu tes HP)", "",
           "| imgsz | aturan 1: box ONNX fp32 mAP50 >= 0.42 | aturan 2: seg mask mAP50 >= 0.55 |", "|---|---|---|"]
    for sz in SIZES:
        b = ox["box_onnx"][f"{sz}_fp32"]["metrik"]["mAP50"]
        s = pt["seg_ultra"][str(sz)]["mask"]["mAP50"]
        a1, a2 = b >= ATURAN["box_mAP50"], s >= ATURAN["seg_mask_mAP50"]
        hasil["per_ukuran"][str(sz)] = dict(box_onnx_fp32_mAP50=b, aturan1=a1, seg_mask_mAP50=s, aturan2=a2,
                                            box_onnx_fp16_mAP50=ox["box_onnx"].get(f"{sz}_fp16", {}).get("metrik", {}).get("mAP50"))
        md.append(f"| {sz} | {b:.3f} {'LOLOS' if a1 else 'GAGAL'} | {s:.3f} {'LOLOS' if a2 else 'GAGAL'} |")
    md += ["", "## Cek jumlah deteksi (conf >= 0.25, 3 frame val pertama, gambar letterbox yang sama)", "",
           "| model | gambar | .pt | ONNX fp32 | ONNX fp16 | sama? |", "|---|---|---|---|---|---|"]
    for key, rows in ox["cek_jumlah"].items():
        for r in rows:
            sama = len(r["pt"]) == len(r.get("fp32", [])) and ("fp16" not in r or len(r["fp16"]) == len(r["fp32"]))
            md.append(f"| {key} | {r['gambar'][:30]} | {len(r['pt'])} | {len(r.get('fp32', [])) if 'fp32' in r else '-'} | "
                      f"{len(r['fp16']) if 'fp16' in r else '-'} | {'ya' if sama else 'BEDA'} |")
    md += ["", "Catatan: jalur ONNX memakai cv2.resize INTER_LINEAR; browser (drawImage) bisa sedikit beda interpolasinya. "
           "Jalur ONNX tidak membatasi jumlah prediksi (seperti app.js); jalur .pt memakai max_det 300 dan letterbox persegi panjang Ultralytics."]
    hasil["box_pt"] = {k: v["metrik"] | dict(conf025=v["conf025"]) for k, v in pt["box_pt"].items()}
    hasil["box_onnx"] = {k: v["metrik"] | dict(conf025=v["conf025"], cpu_ms_median=v["cpu_ms_median"]) for k, v in ox["box_onnx"].items()}
    hasil["seg_ultra"] = {k: dict(box=v["box"], mask=v["mask"]) for k, v in pt["seg_ultra"].items()}
    hasil["cek_jumlah"] = ox["cek_jumlah"]
    tulis(OUT / "akurasi.json", hasil)
    p = OUT / "akurasi.md"
    if p.exists():
        sys.exit(f"{p} sudah ada, tidak ditimpa.")
    p.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("tersimpan:", p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bagian", choices=["pt", "onnx", "laporan"], required=True)
    b = ap.parse_args().bagian
    {"pt": bagian_pt, "onnx": bagian_onnx, "laporan": bagian_laporan}[b]()
