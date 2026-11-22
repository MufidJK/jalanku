"""Tahap 5a, Bagian A: akurasi box + seg pada imgsz 320 / 416 (data/prompt-model-hp.md section 3). VAL v2 saja.

Tahap 5b: bagian hp-pt / hp-onnx / hp-laporan (model latih ulang, keluaran ke data/model-hp/5b/). Tahap 5a: empat langkah, masing-masing di venv yang punya paketnya (dijalankan dari root repo):

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
def hitung_cek(sz, kind, pt_name, imgs, names, prefix="", sufiks=""):
    """Jumlah deteksi conf >= 0.25 pada 3 frame: .pt vs ONNX fp32 vs ONNX fp16 (gambar letterbox yang sama)."""
    import cv2
    from ultralytics import YOLO

    pt = YOLO(str(ROOT / pt_name))
    nc = len(names)
    files = {"fp32": ONNX / f"{prefix}{kind}_{sz}{sufiks}.onnx", "fp16": ONNX / f"{prefix}{kind}_{sz}{sufiks}_fp16.onnx"}
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


# ---------------------------------------------------------------- Tahap 5b (model latih ulang, ukuran sendiri)
OUT5B = ROOT / "data" / "model-hp" / "5b"
HP_BOX = "models/hp/hp-kotak-v3-{sz}_best.pt"
HP_SEG = "models/hp/hp-seg-v3-{sz}_best.pt"
LAMA = OUT / "akurasi.json"  # angka 5a (model lama, dilatih 640)


def hp_pt():
    """GPU: box .pt dan seg Ultralytics val pada ukuran latihnya (320 / 416). VAL v2 saja."""
    out = OUT5B / "pt.json"
    if out.exists():
        sys.exit(f"{out} sudah ada, tidak ditimpa.")
    names, imgs, lab_dir = er.cek_val(er.YK)
    er.pasang_imgsz()
    h = dict(sumber="val v2 (er.cek_val(er.YK), 54 frame)", box_pt={}, seg_ultra={})
    for sz in SIZES:
        bp, sp = HP_BOX.format(sz=sz), HP_SEG.format(sz=sz)
        if not (ROOT / bp).exists() or not (ROOT / sp).exists():
            print(f"bobot {sz} belum lengkap, dilewati")
            continue
        nm = f"hp5b-box-{sz}"
        er.MODEL[nm] = ("detect", er.YK, bp, sz)
        print(f"== box .pt (latih ulang) imgsz {sz}", flush=True)
        pred, _ = ev.prediksi(nm, imgs, conf=CONF_MAP)
        h["box_pt"][str(sz)] = ringkas_box(names, imgs, lab_dir, pred)
        print(f"   mAP50 {h['box_pt'][str(sz)]['metrik']['mAP50']:.4f}", flush=True)
        nm = f"hp5b-seg-{sz}"
        er.IMGSZ["nilai"] = sz
        eb.RUNS[nm] = ("segment", er.YS)
        print(f"== seg Ultralytics val (latih ulang) imgsz {sz}", flush=True)
        u = eb.jalankan_val(nm, ROOT / sp, OUT5B / "runs")
        u["imgsz"] = sz
        h["seg_ultra"][str(sz)] = u
        print(f"   mask mAP50 {u['mask']['mAP50']:.4f} R {u['mask']['R']:.3f}", flush=True)
    tulis(out, h)


def hp_onnx():
    """CPU: box ONNX fp32 + fp16 (jalur app.js) pada ukuran latihnya + cek jumlah deteksi .pt vs ONNX (box dan seg)."""
    out = OUT5B / "onnx.json"
    if out.exists():
        sys.exit(f"{out} sudah ada, tidak ditimpa.")
    names, imgs, lab_dir = er.cek_val(er.YK)
    names_s, imgs_s, _ = eb.info_val(er.YS)
    h = dict(sumber="val v2 (er.cek_val(er.YK), 54 frame)", jalur="letterbox app.js + NMS per kelas IoU 0.7 + ensemble_val.metrik",
             box_onnx={}, cek_jumlah={})
    for sz in SIZES:
        for prec in ("fp32", "fp16"):
            f = ONNX / (f"hp_box_{sz}.onnx" if prec == "fp32" else f"hp_box_{sz}_fp16.onnx")
            if not f.exists():
                continue
            print(f"== box ONNX latih ulang {sz} {prec}", flush=True)
            pred, ms = prediksi_onnx(f, sz, imgs, len(names))
            r = ringkas_box(names, imgs, lab_dir, pred)
            r["cpu_ms_median"] = ms
            h["box_onnx"][f"{sz}_{prec}"] = r
            print(f"   mAP50 {r['metrik']['mAP50']:.4f} mAP50-95 {r['metrik']['mAP50_95']:.4f} n_pred {r['metrik']['n_prediksi']}", flush=True)
        for kind, pt_name, nm, im in (("box", HP_BOX.format(sz=sz), names, imgs), ("seg", HP_SEG.format(sz=sz), names_s, imgs_s)):
            if not (ONNX / f"hp_{kind}_{sz}.onnx").exists():
                continue
            print(f"== cek jumlah {kind} {sz}", flush=True)
            h["cek_jumlah"][f"{kind}_{sz}"] = hitung_cek(sz, kind, pt_name, im[:3], nm, prefix="hp_")
    tulis(out, h)


def hp_laporan():
    """Tabel 5b: model lama pada ukuran S (angka 5a) vs latih ulang pada S, plus rujukan 640. Aturan 1 (fp16 resmi) dan 2."""
    for p in (OUT5B / "akurasi.json", OUT5B / "akurasi.md"):
        if p.exists():
            sys.exit(f"{p} sudah ada, tidak ditimpa.")
    pt = json.loads((OUT5B / "pt.json").read_text(encoding="utf-8"))
    ox = json.loads((OUT5B / "onnx.json").read_text(encoding="utf-8"))
    lama = json.loads(LAMA.read_text(encoding="utf-8"))
    ukuran = [str(s) for s in SIZES if str(s) in pt["box_pt"] and f"{s}_fp16" in ox["box_onnx"] and str(s) in pt["seg_ultra"]]
    hasil = dict(aturan=ATURAN, referensi=REF, per_ukuran={})
    md = ["# Tahap 5b, Bagian B: akurasi model latih ulang (val v2, 54 frame)", "",
          "Model lama = r2-kotak-v3 / r2-seg-v3 (dilatih 640), dijalankan pada S (angka 5a, `data/model-hp/akurasi.json`). "
          "Latih ulang = hp-kotak-v3-S / hp-seg-v3-S (data dan pengaturan sama, hanya imgsz). "
          "Angka resmi box = ONNX fp16 pada S (jalur app.js). Seleksi best checkpoint dan evaluasi memakai val yang sama "
          "(optimis, sama dengan ronde sebelumnya).", "",
          "## Box", "",
          "| imgsz | model | jalur | mAP50 | mAP50-95 | F1 | AP50 tangga | AP50 tepian | AP50 orang | AP50 pilar | recall dekat 0.25 | TP/FP/FN 0.25 | n prediksi |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def baris(sz, model, jalur, r):
        m, c = r["metrik"], r["conf025"]
        k = m["kelas"]
        rd = c["recall_dekat"]
        md.append(f"| {sz} | {model} | {jalur} | {f3(m['mAP50'])} | {f3(m['mAP50_95'])} | {f3(m['F1'])} | "
                  + " | ".join(f3(k.get(n, {}).get("AP50")) for n in ("tangga", "tepian", "orang", "pilar"))
                  + f" | {rd['ditemukan']}/{rd['gt']} ({f3(rd['recall'])}) | {c['total']['tp']}/{c['total']['fp']}/{c['total']['fn']} | {m['n_prediksi']} |")

    def dari_lama(r):  # akurasi.json menyimpan metrik + conf025 digabung
        return dict(metrik={k: v for k, v in r.items() if k != "conf025"}, conf025=r["conf025"])

    lama640 = dari_lama(lama["box_onnx"]["640_fp32"])
    baris("640", "lama", "ONNX fp32 (rujukan)", lama640)
    for sz in ukuran:
        baris(sz, "lama", "ONNX fp32", dari_lama(lama["box_onnx"][f"{sz}_fp32"]))
        baris(sz, "lama", "ONNX fp16", dari_lama(lama["box_onnx"][f"{sz}_fp16"]))
        baris(sz, "**latih ulang**", ".pt (pembanding)", pt["box_pt"][sz])
        baris(sz, "**latih ulang**", "ONNX fp32", ox["box_onnx"][f"{sz}_fp32"])
        baris(sz, "**latih ulang**", "ONNX fp16 (resmi)", ox["box_onnx"][f"{sz}_fp16"])
    md += ["", "Rujukan: box .pt lama pada 640 mAP50 0.471; C2 (ensemble laptop, 4 model 960/1280) 0.613, tidak jalan di HP.", "",
           "### AP50 per kelas, box (ONNX fp16)", ""]
    kol = []
    for sz in ukuran:
        kol += [(f"lama {sz}", dari_lama(lama["box_onnx"][f"{sz}_fp16"])), (f"ulang {sz}", ox["box_onnx"][f"{sz}_fp16"])]
    kelas = list(lama640["metrik"]["kelas"])
    md += ["| kelas | n | lama 640 fp32 | " + " | ".join(k for k, _ in kol) + " |", "|---|---|---|" + "---|" * len(kol)]
    for k in kelas:
        n = lama640["metrik"]["kelas"][k]["n"]
        md.append(f"| {'**' + k + '**' if k in PENTING + ('pilar',) else k}{' *' if n < eb.LOW_N else ''} | {n} | "
                  f"{f3(lama640['metrik']['kelas'][k].get('AP50'))} | "
                  + " | ".join(f3(r["metrik"]["kelas"].get(k, {}).get("AP50")) for _, r in kol) + " |")
    md += ["", "\\* n < 20 instance di val: angka kelas ini goyah (tangga hanya 5 instance box).", "",
           "## Seg (Ultralytics val, mask)", "",
           "| imgsz | model | box mAP50 | mask mAP50 | mask mAP50-95 | mask P | mask R | mask mAP50 jalur_jalan | jalan_kendaraan | tangga |",
           "|---|---|---|---|---|---|---|---|---|---|"]

    def baris_seg(sz, model, u):
        mk = {c["nama"]: c for c in u["mask"]["kelas"]}
        md.append(f"| {sz} | {model} | {f3(u['box']['mAP50'])} | {f3(u['mask']['mAP50'])} | {f3(u['mask']['mAP50_95'])} | {f3(u['mask']['P'])} | "
                  f"{f3(u['mask']['R'])} | " + " | ".join(f3(mk.get(n, {}).get("mAP50")) for n in ("jalur_jalan", "jalan_kendaraan", "tangga")) + " |")

    baris_seg("640", "lama (rujukan)", lama["seg_ultra"]["640"])
    for sz in ukuran:
        baris_seg(sz, "lama", lama["seg_ultra"][sz])
        baris_seg(sz, "**latih ulang**", pt["seg_ultra"][sz])
    md += ["", "## Aturan 1 dan 2 (aturan 3, kecepatan bertahan 5 menit, menunggu tes HP)", "",
           "| imgsz | aturan 1: box ONNX fp16 mAP50 >= 0.42 | aturan 2: seg mask mAP50 >= 0.55 | lolos 1 dan 2 |", "|---|---|---|---|"]
    for sz in ukuran:
        b = ox["box_onnx"][f"{sz}_fp16"]["metrik"]["mAP50"]
        b32 = ox["box_onnx"][f"{sz}_fp32"]["metrik"]["mAP50"]
        s_ = pt["seg_ultra"][sz]["mask"]["mAP50"]
        a1, a2 = b >= ATURAN["box_mAP50"], s_ >= ATURAN["seg_mask_mAP50"]
        hasil["per_ukuran"][sz] = dict(box_onnx_fp16_mAP50=b, box_onnx_fp32_mAP50=b32, aturan1=a1, seg_mask_mAP50=s_, aturan2=a2,
                                       lolos_1_2=bool(a1 and a2))
        md.append(f"| {sz} | {b:.3f} {'LOLOS' if a1 else 'GAGAL'} (fp32 {b32:.3f}) | {s_:.3f} {'LOLOS' if a2 else 'GAGAL'} | "
                  f"{'YA' if a1 and a2 else 'TIDAK'} |")
    md += ["", "## Cek jumlah deteksi (conf >= 0.25, 3 frame val pertama, gambar letterbox yang sama)", "",
           "| model | gambar | .pt | ONNX fp32 | ONNX fp16 | sama? |", "|---|---|---|---|---|---|"]
    for key, rows in ox["cek_jumlah"].items():
        for r in rows:
            sama = len(r["pt"]) == len(r.get("fp32", [])) and ("fp16" not in r or len(r["fp16"]) == len(r["fp32"]))
            md.append(f"| {key} | {r['gambar'][:30]} | {len(r['pt'])} | {len(r['fp32']) if 'fp32' in r else '-'} | "
                      f"{len(r['fp16']) if 'fp16' in r else '-'} | {'ya' if sama else 'BEDA'} |")
    md += ["", "Catatan: jalur ONNX memakai cv2.resize INTER_LINEAR; browser (drawImage) bisa sedikit beda interpolasinya. "
           "Val v2 hanya 54 frame; tangga 5 instance box dan 11 instance mask."]
    hasil["box_pt"] = {k: v["metrik"] | dict(conf025=v["conf025"]) for k, v in pt["box_pt"].items()}
    hasil["box_onnx"] = {k: v["metrik"] | dict(conf025=v["conf025"], cpu_ms_median=v["cpu_ms_median"]) for k, v in ox["box_onnx"].items()}
    hasil["seg_ultra"] = {k: dict(box=v["box"], mask=v["mask"]) for k, v in pt["seg_ultra"].items()}
    hasil["cek_jumlah"] = ox["cek_jumlah"]
    tulis(OUT5B / "akurasi.json", hasil)
    (OUT5B / "akurasi.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("tersimpan:", OUT5B / "akurasi.md")


# ---------------------------------------------------------------- Tahap 5c (distilasi, box 416)
OUT5C = ROOT / "data" / "model-hp" / "5c"
DISTIL_PT = "models/hp/hp-kotak-v3-416-distil_best.pt"
ATURAN_5C = dict(box_mAP50=0.460, orang_AP50=0.589, recall_dekat=30)  # ditulis sebelum hasil (data/prompt-distilasi.md 0.3)
# Ronde 2 (--r2): sama persis, hanya nama model/berkas yang bersufiks -r2; berkas ronde 1 tidak disentuh.
SUF5C = ""  # "" atau "-r2"; diatur lewat --r2 di bawah


def _d():
    """(sufiks berkas laporan, bobot .pt, nama onnx tanpa ekstensi, sufiks hitung_cek)."""
    if SUF5C:
        return SUF5C, "models/hp/hp-kotak-v3-416-distil-r2_best.pt", "hp_box_416_distil_r2", "_distil_r2"
    return "", DISTIL_PT, "hp_box_416_distil", "_distil"


def distil_pt():
    """GPU: box .pt hp-kotak-v3-416-distil pada imgsz 416 (pembanding, tidak menentukan). VAL v2 saja."""
    suf, pt_distil, _, _ = _d()
    out = OUT5C / f"pt{suf}.json"
    if out.exists():
        sys.exit(f"{out} sudah ada, tidak ditimpa.")
    names, imgs, lab_dir = er.cek_val(er.YK)
    er.pasang_imgsz()
    nm = "hp5c-box-416"
    er.MODEL[nm] = ("detect", er.YK, pt_distil, 416)
    pred, _ = ev.prediksi(nm, imgs, conf=CONF_MAP)
    h = dict(sumber="val v2 (er.cek_val(er.YK), 54 frame)", box_pt={"416": ringkas_box(names, imgs, lab_dir, pred)})
    print(f"   mAP50 .pt {h['box_pt']['416']['metrik']['mAP50']:.4f}", flush=True)
    tulis(out, h)


def distil_onnx():
    """CPU: box ONNX fp32 + fp16 (jalur app.js) + cek jumlah deteksi .pt vs ONNX."""
    suf, pt_distil, onnx_nama, suf_cek = _d()
    out = OUT5C / f"onnx{suf}.json"
    if out.exists():
        sys.exit(f"{out} sudah ada, tidak ditimpa.")
    names, imgs, lab_dir = er.cek_val(er.YK)
    h = dict(sumber="val v2 (er.cek_val(er.YK), 54 frame)", jalur="letterbox app.js + NMS per kelas IoU 0.7 + ensemble_val.metrik",
             box_onnx={}, cek_jumlah={})
    for prec in ("fp32", "fp16"):
        f = ONNX / (f"{onnx_nama}.onnx" if prec == "fp32" else f"{onnx_nama}_fp16.onnx")
        if not f.exists():
            sys.exit(f"{f} belum ada (ekspor dulu: export_onnx.py --distil [--fp16])")
        print(f"== box ONNX distil 416 {prec}", flush=True)
        pred, ms = prediksi_onnx(f, 416, imgs, len(names))
        r = ringkas_box(names, imgs, lab_dir, pred)
        r["cpu_ms_median"] = ms
        h["box_onnx"][f"416_{prec}"] = r
        print(f"   mAP50 {r['metrik']['mAP50']:.4f} mAP50-95 {r['metrik']['mAP50_95']:.4f} n_pred {r['metrik']['n_prediksi']}", flush=True)
    h["cek_jumlah"]["box_416_distil" + suf.replace("-", "_")] = hitung_cek(416, "box", pt_distil, imgs[:3], names, prefix="hp_",
                                                                         sufiks=suf_cek)
    tulis(out, h)


def distil_laporan():
    """Tabel samping-menyamping dan aturan 0.3 (data/prompt-distilasi.md). Menulis data/model-hp/5c/akurasi.{json,md}."""
    for p in (OUT5C / "akurasi.json", OUT5C / "akurasi.md"):
        if p.exists():
            sys.exit(f"{p} sudah ada, tidak ditimpa.")
    pt = json.loads((OUT5C / "pt.json").read_text(encoding="utf-8"))
    ox = json.loads((OUT5C / "onnx.json").read_text(encoding="utf-8"))
    b5 = json.loads((OUT5B / "onnx.json").read_text(encoding="utf-8"))
    p5 = json.loads((OUT5B / "pt.json").read_text(encoding="utf-8"))
    lama = json.loads(LAMA.read_text(encoding="utf-8"))

    def dari_lama(r):
        return dict(metrik={k: v for k, v in r.items() if k != "conf025"}, conf025=r["conf025"])

    baris_def = [("hp-kotak-v3-416 (sekarang)", "ONNX fp16", b5["box_onnx"]["416_fp16"]),
                 ("**hp-kotak-v3-416-distil**", "ONNX fp16 (resmi)", ox["box_onnx"]["416_fp16"]),
                 ("hp-kotak-v3-416 (sekarang)", ".pt", p5["box_pt"]["416"]),
                 ("**hp-kotak-v3-416-distil**", ".pt", pt["box_pt"]["416"]),
                 ("hp-kotak-v3-416 (sekarang)", "ONNX fp32", b5["box_onnx"]["416_fp32"]),
                 ("**hp-kotak-v3-416-distil**", "ONNX fp32", ox["box_onnx"]["416_fp32"]),
                 ("lama (latih 640), dijalankan 640", "ONNX fp32", dari_lama(lama["box_onnx"]["640_fp32"]))]
    md = ["# Tahap 5c, Bagian B: akurasi hp-kotak-v3-416-distil (val v2, 54 frame)", "",
          "Angka resmi = ONNX fp16 pada 416 lewat jalur app.js. C2 (ensemble laptop) mAP50 0.613, tidak jalan di HP, tidak dievaluasi ulang di sini.", "",
          "| model | jalur | mAP50 | mAP50-95 | F1 | AP50 tangga | AP50 tepian | AP50 orang | AP50 pilar | recall dekat 0.25 | TP/FP/FN 0.25 | n prediksi |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for model, jalur, r in baris_def:
        m, c = r["metrik"], r["conf025"]
        k, rd = m["kelas"], c["recall_dekat"]
        md.append(f"| {model} | {jalur} | {f3(m['mAP50'])} | {f3(m['mAP50_95'])} | {f3(m['F1'])} | "
                  + " | ".join(f3(k.get(n, {}).get("AP50")) for n in ("tangga", "tepian", "orang", "pilar"))
                  + f" | {rd['ditemukan']}/{rd['gt']} ({f3(rd['recall'])}) | {c['total']['tp']}/{c['total']['fp']}/{c['total']['fn']} | {m['n_prediksi']} |")
    kol = [("sekarang 416 fp16", b5["box_onnx"]["416_fp16"]), ("distil 416 fp16", ox["box_onnx"]["416_fp16"]),
           ("lama 640 fp32", dari_lama(lama["box_onnx"]["640_fp32"]))]
    md += ["", "### AP50 per kelas (ONNX)", "", "| kelas | n | " + " | ".join(k for k, _ in kol) + " |", "|---|---|" + "---|" * len(kol)]
    for k, v in kol[2][1]["metrik"]["kelas"].items():
        md.append(f"| {'**' + k + '**' if k in PENTING + ('pilar',) else k}{' *' if v['n'] < eb.LOW_N else ''} | {v['n']} | "
                  + " | ".join(f3(r["metrik"]["kelas"].get(k, {}).get("AP50")) for _, r in kol) + " |")
    md += ["", "\\* n < 20 instance di val: angka kelas ini goyah.", ""]
    d = ox["box_onnx"]["416_fp16"]
    mAP, orang, rec = d["metrik"]["mAP50"], d["metrik"]["kelas"]["orang"]["AP50"], d["conf025"]["recall_dekat"]["ditemukan"]
    a1, a2, a3 = mAP >= ATURAN_5C["box_mAP50"], orang >= ATURAN_5C["orang_AP50"], rec >= ATURAN_5C["recall_dekat"]
    ganti = bool(a1 and a2 and a3)
    md += ["## Aturan 0.3 (ONNX fp16, ditulis sebelum ada hasil)", "",
           "| aturan | batas | distil | hasil |", "|---|---|---|---|",
           f"| 1. mAP50 val v2 | >= 0.460 | {mAP:.4f} | {'LOLOS' if a1 else 'GAGAL'} |",
           f"| 2. AP50 orang | >= 0.589 | {orang:.4f} | {'LOLOS' if a2 else 'GAGAL'} |",
           f"| 3. recall dekat (y2 >= 0.65) conf 0.25 | >= 30/72 | {rec}/72 | {'LOLOS' if a3 else 'GAGAL'} |", "",
           f"**Keputusan: {'GANTI hp-kotak-v3-416 dengan hp-kotak-v3-416-distil' if ganti else 'PERTAHANKAN hp-kotak-v3-416'}.**"]
    tulis(OUT5C / "akurasi.json", dict(aturan=ATURAN_5C, box_onnx=ox["box_onnx"], box_pt=pt["box_pt"], cek_jumlah=ox["cek_jumlah"],
                                       keputusan=dict(aturan1=bool(a1), aturan2=bool(a2), aturan3=bool(a3), ganti=ganti,
                                                      mAP50=mAP, orang_AP50=orang, recall_dekat=rec)))
    (OUT5C / "akurasi.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[-9:]))


def distil_laporan_r2():
    """Ronde 2: tabel 3 arah (sekarang, distil ronde 1, distil r2) + aturan 0.3 yang sama. Menulis akurasi-r2.{json,md}. Hanya baca berkas ronde 1."""
    for p in (OUT5C / "akurasi-r2.json", OUT5C / "akurasi-r2.md"):
        if p.exists():
            sys.exit(f"{p} sudah ada, tidak ditimpa.")
    pt1 = json.loads((OUT5C / "pt.json").read_text(encoding="utf-8"))
    ox1 = json.loads((OUT5C / "onnx.json").read_text(encoding="utf-8"))
    pt2 = json.loads((OUT5C / "pt-r2.json").read_text(encoding="utf-8"))
    ox2 = json.loads((OUT5C / "onnx-r2.json").read_text(encoding="utf-8"))
    b5 = json.loads((OUT5B / "onnx.json").read_text(encoding="utf-8"))
    p5 = json.loads((OUT5B / "pt.json").read_text(encoding="utf-8"))
    lama = json.loads(LAMA.read_text(encoding="utf-8"))

    def dari_lama(r):
        return dict(metrik={k: v for k, v in r.items() if k != "conf025"}, conf025=r["conf025"])

    S, D1, D2 = "hp-kotak-v3-416 (sekarang)", "distil ronde 1 (ambang 0.50)", "**distil ronde 2 (ambang per kelas)**"
    baris_def = [(S, "ONNX fp16 (resmi)", b5["box_onnx"]["416_fp16"]), (D1, "ONNX fp16 (resmi)", ox1["box_onnx"]["416_fp16"]),
                 (D2, "ONNX fp16 (resmi)", ox2["box_onnx"]["416_fp16"]),
                 (S, ".pt", p5["box_pt"]["416"]), (D1, ".pt", pt1["box_pt"]["416"]), (D2, ".pt", pt2["box_pt"]["416"]),
                 (S, "ONNX fp32", b5["box_onnx"]["416_fp32"]), (D1, "ONNX fp32", ox1["box_onnx"]["416_fp32"]),
                 (D2, "ONNX fp32", ox2["box_onnx"]["416_fp32"]),
                 ("lama (latih 640), dijalankan 640", "ONNX fp32", dari_lama(lama["box_onnx"]["640_fp32"]))]
    md = ["# Tahap 5c, ronde 2: akurasi hp-kotak-v3-416-distil-r2 (val v2, 54 frame)", "",
          "Angka resmi = ONNX fp16 pada 416 lewat jalur app.js, sama dengan ronde 1. C2 (ensemble laptop) mAP50 0.613, tidak dievaluasi ulang.", "",
          "| model | jalur | mAP50 | mAP50-95 | F1 | AP50 tangga | AP50 tepian | AP50 orang | AP50 pilar | recall dekat 0.25 | TP/FP/FN 0.25 | n prediksi |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for model, jalur, r in baris_def:
        m, c = r["metrik"], r["conf025"]
        k, rd = m["kelas"], c["recall_dekat"]
        md.append(f"| {model} | {jalur} | {f3(m['mAP50'])} | {f3(m['mAP50_95'])} | {f3(m['F1'])} | "
                  + " | ".join(f3(k.get(n, {}).get("AP50")) for n in ("tangga", "tepian", "orang", "pilar"))
                  + f" | {rd['ditemukan']}/{rd['gt']} ({f3(rd['recall'])}) | {c['total']['tp']}/{c['total']['fp']}/{c['total']['fn']} | {m['n_prediksi']} |")
    kol = [("sekarang 416 fp16", b5["box_onnx"]["416_fp16"]), ("distil r1 fp16", ox1["box_onnx"]["416_fp16"]),
           ("distil r2 fp16", ox2["box_onnx"]["416_fp16"]), ("lama 640 fp32", dari_lama(lama["box_onnx"]["640_fp32"]))]
    md += ["", "### AP50 per kelas (ONNX)", "", "| kelas | n | " + " | ".join(k for k, _ in kol) + " |", "|---|---|" + "---|" * len(kol)]
    for k, v in kol[0][1]["metrik"]["kelas"].items():
        md.append(f"| {'**' + k + '**' if k in PENTING + ('pilar',) else k}{' *' if v['n'] < eb.LOW_N else ''} | {v['n']} | "
                  + " | ".join(f3(r["metrik"]["kelas"].get(k, {}).get("AP50")) for _, r in kol) + " |")
    md += ["", "\\* n < 20 instance di val: angka kelas ini goyah.", ""]
    d = ox2["box_onnx"]["416_fp16"]
    mAP, orang, rec = d["metrik"]["mAP50"], d["metrik"]["kelas"]["orang"]["AP50"], d["conf025"]["recall_dekat"]["ditemukan"]
    a1, a2, a3 = mAP >= ATURAN_5C["box_mAP50"], orang >= ATURAN_5C["orang_AP50"], rec >= ATURAN_5C["recall_dekat"]
    ganti = bool(a1 and a2 and a3)
    md += ["## Aturan 0.3 (ONNX fp16, sama dengan ronde 1, tidak diubah)", "",
           "| aturan | batas | distil r2 | hasil |", "|---|---|---|---|",
           f"| 1. mAP50 val v2 | >= 0.460 | {mAP:.4f} | {'LOLOS' if a1 else 'GAGAL'} |",
           f"| 2. AP50 orang | >= 0.589 | {orang:.4f} | {'LOLOS' if a2 else 'GAGAL'} |",
           f"| 3. recall dekat (y2 >= 0.65) conf 0.25 | >= 30/72 | {rec}/72 | {'LOLOS' if a3 else 'GAGAL'} |", "",
           f"**Keputusan: {'GANTI hp-kotak-v3-416 dengan hp-kotak-v3-416-distil-r2' if ganti else 'PERTAHANKAN hp-kotak-v3-416'}.**"]
    tulis(OUT5C / "akurasi-r2.json", dict(aturan=ATURAN_5C, box_onnx=ox2["box_onnx"], box_pt=pt2["box_pt"], cek_jumlah=ox2["cek_jumlah"],
                                          keputusan=dict(aturan1=bool(a1), aturan2=bool(a2), aturan3=bool(a3), ganti=ganti,
                                                         mAP50=mAP, orang_AP50=orang, recall_dekat=rec)))
    (OUT5C / "akurasi-r2.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[-9:]))


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
    ap.add_argument("--bagian", choices=["pt", "onnx", "laporan", "hp-pt", "hp-onnx", "hp-laporan",
                                         "distil-pt", "distil-onnx", "distil-laporan", "distil-laporan-r2"], required=True)
    ap.add_argument("--r2", action="store_true", help="ronde 2: bagian distil-pt/distil-onnx memakai hp-kotak-v3-416-distil-r2")
    arg = ap.parse_args()
    b = arg.bagian
    if arg.r2:
        SUF5C = "-r2"
    {"pt": bagian_pt, "onnx": bagian_onnx, "laporan": bagian_laporan,
     "hp-pt": hp_pt, "hp-onnx": hp_onnx, "hp-laporan": hp_laporan,
     "distil-pt": distil_pt, "distil-onnx": distil_onnx, "distil-laporan": distil_laporan,
     "distil-laporan-r2": distil_laporan_r2}[b]()
