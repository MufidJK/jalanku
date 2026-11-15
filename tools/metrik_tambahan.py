"""metrik_tambahan.py - dua metrik tambahan ronde 4 (prompt ronde 4 section 9), dihitung di VAL v2 sekarang dan dipakai ulang di T1 nanti.

  1. Deteksi class-agnostic: semua 8 kelas kotak dianggap satu kelas "rintangan". Ultralytics val dengan single_cls=True
     (label dan prediksi dijadikan kelas 0, NMS agnostik): mAP50, mAP50-95, P, R, F1. Sebagai pemeriksa silang dihitung juga
     TP/FP/FN class-agnostic pada conf 0,25 lewat jalur kode sendiri (eb.cocokkan_kotak dengan semua kelas = 0).
  2. Peringatan tingkat frame: frame GT-positif kalau ada kotak GT (kelas apa pun) dengan y2 >= 0,65 x tinggi DAN yang
     tumpang tindih dengan pita tengah x 0,33-0,67 lebar; prediksi-positif dengan aturan sama pada prediksi (kelas apa pun)
     setelah disaring ambang per kelas. TP/FP/FN/TN, precision, recall. Dihitung dengan (a) ambang per kelas TERKUNCI model
     final (file ambang_val*.json) dan (b) conf 0,25 seragam, supaya model pembanding (baseline) tidak dinilai dengan ambang
     yang disetel untuk model lain tanpa pembanding netral.

  python tools/metrik_tambahan.py --aksi val --model baseline-kotak --model r2-kotak-v3-960 --model <final> \\
         --ambang data/test-final/ambang_val_r4.json --keluaran data/test-final/metrik_tambahan_val.json

Hanya VAL v2 (cek_val: 54 frame, semua lokasi val). Menolak menimpa berkas keluaran. Tidak menyentuh test.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import evaluasi_baseline as eb  # noqa: E402
import evaluasi_ronde2 as er  # noqa: E402
import test_final as tf  # noqa: E402

ROOT = eb.ROOT
X_PITA = (0.33, 0.67)
Y_DEKAT = 0.65


def zona(bx, w, h):
    """kotak xyxy: tepi bawah >= 0,65 tinggi dan tumpang tindih dengan pita tengah."""
    return bool(bx[3] >= Y_DEKAT * h and bx[2] > X_PITA[0] * w and bx[0] < X_PITA[1] * w)


def level_frame(imgs, lab_dir, pred, amb):
    tp = fp = fn = tn = 0
    per = {}
    for p in imgs:
        pr = tf.saring(pred[p.name], amb)
        w, h = pr["w"], pr["h"]
        gt = any(zona(bx, w, h) for _, bx, _ in eb.baca_gt(lab_dir / (p.stem + ".txt"), w, h, "detect"))
        pd = any(zona(bx, w, h) for bx in pr["xyxy"])
        per[p.name] = dict(gt=gt, pred=pd)
        tp += gt and pd
        fn += gt and not pd
        fp += pd and not gt
        tn += (not gt) and (not pd)
    return dict(TP=int(tp), FP=int(fp), FN=int(fn), TN=int(tn), n_frame=len(imgs), n_gt_positif=int(tp + fn),
                precision=tp / (tp + fp) if tp + fp else None, recall=tp / (tp + fn) if tp + fn else None), per


def agnostik_silang(imgs, lab_dir, pred, conf=0.25):
    """TP/FP/FN class-agnostic pada conf (IoU 0,5) lewat jalur kode sendiri (semua kelas = 0)."""
    import numpy as np

    tp = fp = fn = 0
    for p in imgs:
        pr = tf.saring(pred[p.name], conf)
        pr["cls"] = np.zeros_like(pr["cls"])
        gt = [(0, bx, po) for _, bx, po in eb.baca_gt(lab_dir / (p.stem + ".txt"), pr["w"], pr["h"], "detect")]
        a, b, c = eb.cocokkan_kotak(gt, pr)
        tp += len(a)
        fp += len(b)
        fn += len(c)
    pp, rr, ff = tf.prf(dict(tp=tp, fp=fp, fn=fn))
    return dict(conf=conf, tp=tp, fp=fp, fn=fn, P=pp, R=rr, F1=ff)


def agnostik_val(nama, yaml_path, split="val", proyek=None, tag=""):
    """Ultralytics val dengan single_cls=True. Keluaran: mAP50, mAP50-95, P, R, F1 (kelas tunggal)."""
    from ultralytics import YOLO

    er.pasang_imgsz()
    _, _, bobot, imgsz = er.MODEL[nama]
    er.IMGSZ["nilai"] = imgsz
    proyek = proyek or ROOT / "runs" / "ronde4" / "extra"
    m = YOLO(str(ROOT / bobot)).val(data=str(yaml_path), split=split, imgsz=imgsz, batch=16, workers=2, device=0, plots=False, seed=0,
                                    single_cls=True, project=str(proyek), name=f"{nama}-agnostik{tag}", exist_ok=False, verbose=False)
    b = m.box
    return dict(mAP50=float(b.map50), mAP50_95=float(b.map), P=float(b.mp), R=float(b.mr), F1=float(b.f1.mean()),
                catatan="P/R/F1 pada conf F1 terbaik (definisi tabel Ultralytics); NMS agnostik karena single_cls")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aksi", choices=["val"], required=True)
    ap.add_argument("--model", action="append", required=True, choices=[n for n, v in er.MODEL.items() if v[0] == "detect"])
    ap.add_argument("--ambang", required=True, help="ambang_val*.json model final (conf_kelas) = ambang terkunci")
    ap.add_argument("--keluaran", required=True)
    a = ap.parse_args()
    out = Path(a.keluaran)
    if out.exists():
        sys.exit(f"{out} sudah ada, tidak ditimpa.")
    names, imgs, lab_dir = er.cek_val(er.YK)
    conf_kelas = json.loads(Path(a.ambang).read_text(encoding="utf-8"))["conf_kelas"]
    amb = {k: conf_kelas[nm] for k, nm in names.items()}
    hasil = dict(sumber="val v2, 54 frame", ambang_terkunci=conf_kelas, pita_x=X_PITA, y_dekat=Y_DEKAT, model={})
    for m in a.model:
        print(f"== {m}", flush=True)
        pred = tf.prediksi(m, imgs, tf.CONF_PRED)
        h = dict(agnostik=agnostik_val(m, er.YK), agnostik_silang_conf025=agnostik_silang(imgs, lab_dir, pred))
        h["frame_ambang_terkunci"], per_a = level_frame(imgs, lab_dir, pred, amb)
        h["frame_conf025"], _ = level_frame(imgs, lab_dir, pred, 0.25)
        h["frame_per_gambar_ambang_terkunci"] = per_a
        hasil["model"][m] = h
        g, f = h["agnostik"], h["frame_ambang_terkunci"]
        print(f"   agnostik mAP50 {g['mAP50']:.3f} mAP50-95 {g['mAP50_95']:.3f} P {g['P']:.3f} R {g['R']:.3f} F1 {g['F1']:.3f}; "
              f"frame (ambang terkunci) TP {f['TP']} FP {f['FP']} FN {f['FN']} TN {f['TN']} P {f['precision']} R {f['recall']}", flush=True)
    out.write_text(json.dumps(hasil, indent=2, ensure_ascii=False, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
