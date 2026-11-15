"""ensemble_val.py - pemeriksaan TTA dan ensemble WBF di VAL v2 saja (aturan [ENS-ATURAN] di data/test-final/LOG.md).

  r2 = r2-kotak-v3-960 sendiri
  C1 = r2-kotak-v3-960 dengan Ultralytics augment=True (imgsz 960)
  C2 = WBF per kelas dari 4 model: r2-kotak-v3-960, r4-kotak-v3-960-seed1, r4-kotak-v4-960 (960), r4-kotak-v3-1280 (1280)

Satu jalur kode untuk ketiganya: prediksi conf 0,001 -> pencocokan per kelas IoU 0,50:0,95 (logika match_predictions
Ultralytics) -> ultralytics.utils.metrics.ap_per_class (mAP50, mAP50-95, AP50 per kelas, F1 pada satu conf global terbaik).
Recall dekat dan FP per frame pada conf 0,25 lewat test_final.hitung. Kecepatan GPU: batch 1, warm-up 10, median 54 frame.

  python tools/ensemble_val.py --aksi banding     # -> data/test-final/ens_banding_val.json (+ val_pred_ens_*.pkl)

Hanya VAL v2 (er.cek_val: 54 frame). Menolak menimpa berkas keluaran. Tidak menyentuh test. Tidak memasang paket.
"""
import argparse
import json
import pickle
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import evaluasi_baseline as eb  # noqa: E402
import evaluasi_ronde2 as er  # noqa: E402
import test_final as tf  # noqa: E402

ROOT = eb.ROOT
DT = tf.DT
R2 = "r2-kotak-v3-960"
ANGGOTA = ("r2-kotak-v3-960", "r4-kotak-v3-960-seed1", "r4-kotak-v4-960", "r4-kotak-v3-1280")
WBF_IOU = 0.55
CONF_MAP = 0.001
CONF_KEC = 0.05
IOUV = np.linspace(0.5, 0.95, 10)


def muat(nama):
    from ultralytics import YOLO

    er.pasang_imgsz()
    _, _, bobot, imgsz = er.MODEL[nama]
    return YOLO(str(ROOT / bobot)), imgsz


def prediksi(nama, imgs, conf=CONF_MAP, augment=False):
    m, imgsz = muat(nama)
    er.IMGSZ["nilai"] = imgsz
    out = {}
    hs = m.predict([str(p) for p in imgs], conf=conf, imgsz=imgsz, device=0, verbose=False, batch=8, augment=augment, max_det=300)
    for p, r in zip(imgs, hs):
        h, w = r.orig_shape
        out[p.name] = dict(w=w, h=h, cls=r.boxes.cls.cpu().numpy().astype(int), conf=r.boxes.conf.cpu().numpy().astype(float),
                           xyxy=r.boxes.xyxy.cpu().numpy().astype(float), poly=None)
    return out, bool(getattr(m.model, "end2end", False))


def iou_matriks(a, b):
    """a (n,4), b (m,4) -> (n,m)."""
    if not len(a) or not len(b):
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    la = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    lb = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(la[:, None] + lb[None, :] - inter, 1e-9)


def wbf_kelas(kotak, conf, mdl, n_model, thr=WBF_IOU):
    """Satu kelas, satu gambar. kotak (n,4), conf (n,), mdl (n,) indeks model. -> kotak gabungan (k,4), conf (k,)."""
    urut = np.argsort(-conf, kind="stable")
    gab = np.zeros((0, 4))
    sw, sxy, mx = [], [], []  # jumlah bobot, jumlah bobot*kotak, conf tertinggi per model
    for i in urut:
        k = -1
        if len(gab):
            v = iou_matriks(kotak[i][None], gab)[0]
            j = int(v.argmax())
            if v[j] > thr:
                k = j
        if k < 0:
            sw.append(0.0)
            sxy.append(np.zeros(4))
            mx.append(np.zeros(n_model))
            gab = np.vstack([gab, kotak[i][None]])
            k = len(sw) - 1
        sw[k] += conf[i]
        sxy[k] = sxy[k] + conf[i] * kotak[i]
        mx[k][mdl[i]] = max(mx[k][mdl[i]], conf[i])
        gab[k] = sxy[k] / sw[k]
    return gab, np.array([m.sum() / n_model for m in mx])


def wbf_gambar(daftar, thr=WBF_IOU):
    """daftar: prediksi satu gambar dari tiap model (dict cls/conf/xyxy). -> dict format prediksi."""
    n = len(daftar)
    cls = np.concatenate([d["cls"] for d in daftar])
    conf = np.concatenate([d["conf"] for d in daftar])
    xy = np.concatenate([d["xyxy"].reshape(-1, 4) for d in daftar])
    mdl = np.concatenate([np.full(len(d["cls"]), i) for i, d in enumerate(daftar)]).astype(int)
    oc, of, ox = [], [], []
    for c in np.unique(cls):
        s = cls == c
        g, f = wbf_kelas(xy[s], conf[s], mdl[s], n, thr)
        oc.append(np.full(len(f), c))
        of.append(f)
        ox.append(g)
    return dict(w=daftar[0]["w"], h=daftar[0]["h"], cls=np.concatenate(oc).astype(int) if oc else np.zeros(0, int),
                conf=np.concatenate(of) if of else np.zeros(0), xyxy=np.concatenate(ox) if ox else np.zeros((0, 4)), poly=None)


def metrik(names, imgs, lab_dir, pred):
    """Jalur bersama: mAP50, mAP50-95, AP50 per kelas, F1 pada satu conf global terbaik."""
    from ultralytics.utils.metrics import ap_per_class, smooth

    tps, confs, pcs, tcs = [], [], [], []
    for p in imgs:
        pr = pred[p.name]
        gt = eb.baca_gt(lab_dir / (p.stem + ".txt"), pr["w"], pr["h"], "detect")
        gc = np.array([c for c, _, _ in gt], dtype=int)
        gb = np.array([bx for _, bx, _ in gt]).reshape(-1, 4)
        benar = np.zeros((len(pr["cls"]), len(IOUV)), dtype=bool)
        if len(gc) and len(pr["cls"]):
            iou = iou_matriks(gb, pr["xyxy"]) * (gc[:, None] == pr["cls"][None, :])
            for i, t in enumerate(IOUV):
                mt = np.array(np.nonzero(iou >= t)).T
                if mt.shape[0]:
                    if mt.shape[0] > 1:
                        mt = mt[iou[mt[:, 0], mt[:, 1]].argsort()[::-1]]
                        mt = mt[np.unique(mt[:, 1], return_index=True)[1]]
                        mt = mt[np.unique(mt[:, 0], return_index=True)[1]]
                    benar[mt[:, 1].astype(int), i] = True
        tps.append(benar)
        confs.append(pr["conf"])
        pcs.append(pr["cls"])
        tcs.append(gc)
    tp, conf, pc, tc = np.concatenate(tps), np.concatenate(confs), np.concatenate(pcs), np.concatenate(tcs)
    _, _, p, r, f1, ap, kls, _, _, f1_curve, x, _ = ap_per_class(tp, conf, pc, tc, plot=False, names=names)
    conf_f1 = float(x[smooth(f1_curve.mean(0), 0.1).argmax()])
    nt = np.bincount(tc, minlength=len(names))
    return dict(mAP50=float(ap[:, 0].mean()), mAP50_95=float(ap.mean()), P=float(p.mean()), R=float(r.mean()), F1=float(f1.mean()),
                conf_F1_terbaik=conf_f1, n_prediksi=int(len(conf)),
                kelas={names[int(c)]: dict(n=int(nt[int(c)]), AP50=float(ap[i, 0]), AP50_95=float(ap[i].mean()), P=float(p[i]), R=float(r[i]),
                                           F1=float(f1[i])) for i, c in enumerate(kls)})


def conf025(names, imgs, lab_dir, pred):
    st, _, gts, _ = tf.hitung(names, imgs, lab_dir, pred, 0.25)
    tot = {k: sum(v[k] for v in st.values()) for k in ("tp", "fp", "fn")}
    rd = tf.recall_dekat(names, gts)
    return dict(total=tot, F1_mikro=tf.prf(tot)[2], fp_per_frame=tot["fp"] / len(imgs), recall_dekat=rd["dekat"], recall_jauh=rd["jauh"],
                per_kelas={names[k]: v for k, v in st.items()})


def kecepatan(daftar, imgs, augment=False, gabung=False):
    """GPU, batch 1, warm-up 10. Per frame: jumlah (pre + inferensi + post) semua model + waktu WBF. -> median, p95, rincian."""
    mods = [muat(n) for n in daftar]
    for m, s in mods:
        er.IMGSZ["nilai"] = s
        for _ in range(11):
            m.predict(str(imgs[0]), imgsz=s, conf=CONF_KEC, device=0, verbose=False, augment=augment)
    tot, t_wbf, t_mod = [], [], []
    for p in imgs:
        t, ps = 0.0, []
        for m, s in mods:
            er.IMGSZ["nilai"] = s
            r = m.predict(str(p), imgsz=s, conf=CONF_KEC, device=0, verbose=False, augment=augment)[0]
            t += sum(r.speed[k] for k in ("preprocess", "inference", "postprocess"))
            h, w = r.orig_shape
            ps.append(dict(w=w, h=h, cls=r.boxes.cls.cpu().numpy().astype(int), conf=r.boxes.conf.cpu().numpy().astype(float),
                           xyxy=r.boxes.xyxy.cpu().numpy().astype(float)))
        t_mod.append(t)
        tw = 0.0
        if gabung:
            a = time.perf_counter()
            wbf_gambar(ps)
            tw = (time.perf_counter() - a) * 1000
        t_wbf.append(tw)
        tot.append(t + tw)
    return dict(total_ms=statistics.median(tot), total_ms_p95=sorted(tot)[int(0.95 * len(tot)) - 1], model_ms=statistics.median(t_mod),
                wbf_ms=statistics.median(t_wbf), conf=CONF_KEC, n_gambar=len(imgs), model=list(daftar), augment=augment)


def aksi_kecepatan_protokol():
    """[ENS-KEC-PROTOKOL]: satu kali, mengikat. Menunggu 300 detik, lalu r2, tiap anggota, dan C2 ujung ke ujung."""
    import subprocess

    out = DT / "ens_kecepatan_protokol.json"
    if out.exists():
        sys.exit(f"{out} sudah ada. Pengukuran ini hanya SATU KALI dan mengikat; tidak diulang.")
    _, imgs, _ = er.cek_val(er.YK)

    def ps(cmd):
        return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60).stdout.strip()

    kondisi = dict(skema_daya=ps("powercfg /getactivescheme"), status_baterai=ps("(Get-CimInstance Win32_Battery).BatteryStatus"),
                   jendela_terbuka=ps("(Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -ExpandProperty ProcessName | Sort-Object -Unique) -join ', '"))
    print(json.dumps(kondisi, indent=2, ensure_ascii=False), flush=True)
    # penanda ditulis SEBELUM mengukur: sekali mulai, tidak bisa diulang diam-diam
    out.write_text(json.dumps(dict(status="mulai", kondisi=kondisi), indent=2, ensure_ascii=False), encoding="utf-8")
    print("Menunggu 300 detik (laptop diam). Jangan sentuh laptop.", flush=True)
    time.sleep(300)
    er.pasang_imgsz()
    h = dict(status="selesai", mulai_ukur=time.strftime("%Y-%m-%d %H:%M:%S"), kondisi=kondisi, sendiri={})
    for n in ANGGOTA:
        er.IMGSZ["nilai"] = er.MODEL[n][3]
        h["sendiri"][n] = eb.ukur_kecepatan(ROOT / er.MODEL[n][2], imgs, 0)
        print(f"{n}: {h['sendiri'][n]['total_ms']:.1f} ms", flush=True)
    h["C2"] = kecepatan(ANGGOTA, imgs, gabung=True)
    h["lolos_60ms"] = bool(h["C2"]["total_ms"] <= 60)
    out.write_text(json.dumps(h, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    print(f"C2 ujung ke ujung: {h['C2']['total_ms']:.1f} ms (model {h['C2']['model_ms']:.1f} + WBF {h['C2']['wbf_ms']:.1f}), p95 {h['C2']['total_ms_p95']:.1f}; "
          f"r2 sendiri {h['sendiri'][R2]['total_ms']:.1f} ms -> {'LOLOS' if h['lolos_60ms'] else 'GAGAL'} batas 60 ms", flush=True)


def aksi_t0_ens():
    """T0 untuk C2 (akhiran _ens): aturan T0 yang sama ([R3-3]: tepian recall >= 0,5), prediksi = val_pred_ens_C2.pkl."""
    names, imgs, lab_dir = er.cek_val(er.YK)
    pred = pickle.loads((DT / "val_pred_ens_C2.pkl").read_bytes())
    lama = json.loads((DT / "ens_banding_val.json").read_text(encoding="utf-8"))["hasil"]["C2"]["conf025"]["total"]
    st = tf.hitung(names, imgs, lab_dir, pred, 0.25)[0]
    baru = {k: sum(v[k] for v in st.values()) for k in ("tp", "fp", "fn")}
    assert baru == lama, (baru, lama)
    km = ["model_kotak: ensemble_wbf  # C2: 4 model, digabung per kelas dengan WBF (tools/ensemble_val.py wbf_gambar)",
          "ensemble_kotak:"] + [f"  - {{bobot: {er.MODEL[n][2]}, imgsz: {er.MODEL[n][3]}}}" for n in ANGGOTA] + [
          f"wbf_iou: {WBF_IOU}", "wbf_conf: rata-rata atas 4 model (conf tertinggi tiap model di klaster; model yang tidak ada = 0)",
          f"conf_prediksi_kotak: {CONF_MAP}  # conf predict() tiap anggota; sesudah WBF saring per kelas dengan conf_kelas"]
    tf.aksi_t0("C2-ens", "_ens", {"tepian": 0.5}, pred=pred, konfig_model=km)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aksi", choices=["banding", "kecepatan-protokol", "t0-ens"], required=True)
    aksi = ap.parse_args().aksi
    if aksi == "kecepatan-protokol":
        return aksi_kecepatan_protokol()
    if aksi == "t0-ens":
        return aksi_t0_ens()
    out = DT / "ens_banding_val.json"
    pk = {k: DT / f"val_pred_ens_{k}.pkl" for k in ("r2", "C1", "C2")}
    ada = [str(p) for p in [out, *pk.values()] if p.exists()]
    if ada:
        sys.exit("Sudah ada, tidak ditimpa:\n  " + "\n  ".join(ada))
    names, imgs, lab_dir = er.cek_val(er.YK)

    per_model = {}
    for n in ANGGOTA:
        print(f"== prediksi {n}", flush=True)
        per_model[n], _ = prediksi(n, imgs)
    print("== prediksi C1 (augment=True)", flush=True)
    p_c1, e2e = prediksi(R2, imgs, augment=True)
    p_r2 = per_model[R2]
    sama = all(len(p_r2[k]["conf"]) == len(p_c1[k]["conf"]) and np.allclose(p_r2[k]["conf"], p_c1[k]["conf"], atol=1e-6)
               and np.allclose(p_r2[k]["xyxy"], p_c1[k]["xyxy"], atol=1e-3) for k in p_r2)
    print("== WBF", flush=True)
    p_c2 = {p.name: wbf_gambar([per_model[n][p.name] for n in ANGGOTA]) for p in imgs}
    preds = dict(r2=p_r2, C1=p_c1, C2=p_c2)
    for k, v in preds.items():
        pk[k].write_bytes(pickle.dumps(v))

    h = dict(sumber="val v2, 54 frame", wbf=dict(iou=WBF_IOU, anggota=list(ANGGOTA), conf_masukan=CONF_MAP),
             c1=dict(model_end2end=e2e, prediksi_identik_dengan_r2=bool(sama)), hasil={}, anggota_sendiri={})
    for k, v in preds.items():
        h["hasil"][k] = dict(metrik=metrik(names, imgs, lab_dir, v), conf025=conf025(names, imgs, lab_dir, v))
    for n in ANGGOTA[1:]:
        h["anggota_sendiri"][n] = dict(metrik=metrik(names, imgs, lab_dir, per_model[n]), conf025=conf025(names, imgs, lab_dir, per_model[n]))
    print("== kecepatan", flush=True)
    h["hasil"]["r2"]["kecepatan"] = kecepatan([R2], imgs)
    h["hasil"]["C1"]["kecepatan"] = kecepatan([R2], imgs, augment=True)
    h["hasil"]["C2"]["kecepatan"] = kecepatan(ANGGOTA, imgs, gabung=True)
    out.write_text(json.dumps(h, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    print(f"C1: end2end={e2e}, prediksi identik dengan r2={sama}")
    for k, d in {**h["hasil"], **h["anggota_sendiri"]}.items():
        m, c = d["metrik"], d["conf025"]
        print(f"{k}: mAP50 {m['mAP50']:.4f} mAP50-95 {m['mAP50_95']:.4f} P {m['P']:.3f} R {m['R']:.3f} F1 {m['F1']:.4f} (conf {m['conf_F1_terbaik']:.3f}); "
              f"conf 0,25 TP/FP/FN {c['total']['tp']}/{c['total']['fp']}/{c['total']['fn']} FP/frame {c['fp_per_frame']:.2f} "
              f"dekat {c['recall_dekat']['ditemukan']}/{c['recall_dekat']['gt']}"
              + (f"; GPU {d['kecepatan']['total_ms']:.1f} ms (WBF {d['kecepatan']['wbf_ms']:.1f})" if "kecepatan" in d else ""), flush=True)
        print("   AP50: " + ", ".join(f"{n} {v['AP50']:.3f}" for n, v in m["kelas"].items()), flush=True)


if __name__ == "__main__":
    main()
