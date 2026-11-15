"""test_final.py - evaluasi TEST FINAL JalanKu (prompt data/prompt-test-final.md).

Model final dikunci sebelum ada angka test: kotak r2-kotak-v3-960 (imgsz 960), seg r2-seg-v3 (imgsz 640).
Jalur kode sama dengan tabel val: fungsi tools/evaluasi_baseline.py (jalankan_val, prediksi_semua, cocokkan_kotak,
analisis) lewat pembungkus imgsz tools/evaluasi_ronde2.py. Kedua berkas itu tidak diubah.

  python tools/test_final.py --aksi t0     # HANYA val v2: ambang per kelas, FP tangga, recall objek dekat, config_saran.yaml
  python tools/test_final.py --aksi t1     # test, SEKALI per model (menolak kalau hasil sudah ada)
  python tools/test_final.py --aksi sheet  # contact sheet test, hanya sesudah semua angka t1 tersimpan
  python tools/test_final.py --aksi tabel  # tabel Markdown dari berkas hasil

Definisi (ditetapkan di T0, sebelum test):
  - cocok = kelas sama, IoU >= 0,5, greedy urut conf (eb.cocokkan_kotak).
  - grid ambang 0,05 ... 0,80 langkah 0,05. Ambang kelas = F1 tertinggi di val (seri: yang paling dekat 0,25).
    n val < 20 -> 0,25. "Datar" = F1 terbaik - F1 pada 0,25 < 0,02 -> 0,25.
    Kelas bahaya (tangga, tepian, kendaraan): kalau recall pada ambang terpilih < 0,6, pakai ambang TERTINGGI di grid
    yang recall-nya >= 0,6; kalau tidak ada satu pun, ambang tidak diubah dan ditandai.
  - "dekat" = tepi bawah kotak GT y2 >= 0,65 x tinggi gambar. Ukuran = akar luas kotak, px pada skala 640.
"""
import argparse
import csv
import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import evaluasi_baseline as eb  # noqa: E402
import evaluasi_ronde2 as er  # noqa: E402

ROOT = eb.ROOT
DT = ROOT / "data" / "test-final"
RT = ROOT / "runs" / "test-final"
FINAL_KOTAK, FINAL_SEG = "r2-kotak-v3-960", "r2-seg-v3"
GRID = [round(0.05 * i, 2) for i in range(1, 17)]
BAHAYA = ("tangga", "tepian", "kendaraan")
R_MIN = 0.6
DATAR = 0.02
Y_DEKAT = 0.65
CONF_PRED = 0.05
UKURAN = ("<32", "32-64", "64-128", ">=128")


def log(teks):
    with open(DT / "LOG.md", "a", encoding="utf-8") as f:
        f.write(f"- {teks}\n")
    print(teks, flush=True)


def prediksi(nama, imgs, conf):
    """Prediksi satu model (bobot + imgsz dari er.MODEL) pada conf rendah; jalur eb.prediksi_semua."""
    from ultralytics import YOLO

    er.pasang_imgsz()
    _, _, bobot, imgsz = er.MODEL[nama]
    er.IMGSZ["nilai"] = imgsz
    lama = eb.CONF
    eb.CONF = conf
    try:
        return eb.prediksi_semua(YOLO(str(ROOT / bobot)), imgs)
    finally:
        eb.CONF = lama


def saring(pr, amb):
    """amb: float atau {id kelas: ambang}."""
    import numpy as np

    if isinstance(amb, dict):
        batas = np.array([amb[int(c)] for c in pr["cls"]], dtype=float) if len(pr["cls"]) else np.zeros(0)
    else:
        batas = np.full(len(pr["cls"]), amb, dtype=float)
    m = pr["conf"] >= batas - 1e-9
    return dict(w=pr["w"], h=pr["h"], cls=pr["cls"][m], conf=pr["conf"][m], xyxy=pr["xyxy"][m], poly=None)


def ember(bx, w, h):
    import numpy as np

    u = float(np.sqrt((bx[2] - bx[0]) * (bx[3] - bx[1]))) * 640.0 / max(w, h)
    return "<32" if u < 32 else "32-64" if u < 64 else "64-128" if u < 128 else ">=128"


def hitung(names, imgs, lab_dir, pred, amb):
    """-> st {kelas: tp/fp/fn}, fp (list dict), gt (list dict dengan 'ketemu', 'dekat', 'ukuran'), per gambar."""
    st = {k: dict(tp=0, fp=0, fn=0) for k in names}
    fps, gts, per = [], [], {}
    for p in imgs:
        pr = saring(pred[p.name], amb)
        w, h = pr["w"], pr["h"]
        gt = eb.baca_gt(lab_dir / (p.stem + ".txt"), w, h, "detect")
        tp, fp, fn = eb.cocokkan_kotak(gt, pr)
        ketemu = {i for i, _ in tp}
        for i, (c, bx, _) in enumerate(gt):
            st[c]["tp" if i in ketemu else "fn"] += 1
            gts.append(dict(gambar=p.name, kelas=c, xyxy=[float(v) for v in bx], ketemu=i in ketemu,
                            dekat=bool(bx[3] >= Y_DEKAT * h), ukuran=ember(bx, w, h)))
        for j, tk in fp:
            c = int(pr["cls"][j])
            st[c]["fp"] += 1
            fps.append(dict(gambar=p.name, kelas=c, conf=float(pr["conf"][j]), xyxy=[float(v) for v in pr["xyxy"][j]],
                            tertukar_dengan=None if tk is None else names[tk]))
        per[p.name] = dict(n_gt=len(gt), tp=len(tp), fp=len(fp), fn=len(fn))
    return st, fps, gts, per


def prf(v):
    tp, fp, fn = v["tp"], v["fp"], v["fn"]
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return p, r, f


def rasio(lst):
    n, k = len(lst), sum(1 for g in lst if g["ketemu"])
    return dict(gt=n, ditemukan=k, recall=(k / n if n else None))


def recall_dekat(names, gts):
    """Recall zona dekat vs sisanya, per ukuran, dan per kelas di zona dekat."""
    d = dict(dekat=rasio([g for g in gts if g["dekat"]]), jauh=rasio([g for g in gts if not g["dekat"]]),
             per_ukuran={b: rasio([g for g in gts if g["ukuran"] == b]) for b in UKURAN},
             per_ukuran_dekat={b: rasio([g for g in gts if g["ukuran"] == b and g["dekat"]]) for b in UKURAN},
             per_kelas={})
    for k, nm in names.items():
        d["per_kelas"][nm] = dict(dekat=rasio([g for g in gts if g["kelas"] == k and g["dekat"]]),
                                  jauh=rasio([g for g in gts if g["kelas"] == k and not g["dekat"]]))
    return d


def sheet_fp(daftar, peta, names, gt_dir, path, kolom=4, cw=300, ch=533):
    """Satu sel per FP: frame utuh, kotak FP merah, GT kelas yang sama hijau."""
    import cv2
    import numpy as np

    sel = []
    for n, f in enumerate(daftar, 1):
        im = cv2.imread(str(peta[f["gambar"]]))
        h, w = im.shape[:2]
        t = max(3, round(max(h, w) / 300))
        for c, bx, _ in eb.baca_gt(gt_dir / (Path(f["gambar"]).stem + ".txt"), w, h, "detect"):
            if c == f["kelas"]:
                cv2.rectangle(im, (int(bx[0]), int(bx[1])), (int(bx[2]), int(bx[3])), (0, 200, 0), t)
        x1, y1, x2, y2 = [int(v) for v in f["xyxy"]]
        cv2.rectangle(im, (x1, y1), (x2, y2), (0, 0, 255), t)
        s = min(cw / w, ch / h)
        im = cv2.resize(im, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        kan = np.full((ch + 40, cw, 3), 255, np.uint8)
        kan[40:40 + im.shape[0], :im.shape[1]] = im
        nm = f["gambar"].split("_20")[0][:24] + " " + f["gambar"].rsplit("_", 2)[-2] + " " + Path(f["gambar"]).stem.rsplit("_t", 1)[-1]
        cv2.putText(kan, f"#{n} {names[f['kelas']]} {f['conf']:.2f}", (3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
        cv2.putText(kan, nm, (3, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1, cv2.LINE_AA)
        sel.append(kan)
    if not sel:
        sel = [np.full((ch + 40, cw, 3), 255, np.uint8)]
        cv2.putText(sel[0], "tidak ada FP", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    baris = []
    for i in range(0, len(sel), kolom):
        r = sel[i:i + kolom]
        while len(r) < kolom:
            r.append(np.full_like(sel[0], 255))
        baris.append(np.hstack([np.hstack([x, np.full((x.shape[0], 8, 3), 255, np.uint8)]) for x in r]))
    cv2.imwrite(str(path), np.vstack(baris))


# ---------------------------------------------------------------- T0: val saja
def aksi_t0(model=FINAL_KOTAK, akh="", r_min=None, pred=None, konfig_model=None):
    """akh: akhiran nama berkas (ronde 3: '_final'); r_min: {kelas bahaya: recall minimum} pengganti R_MIN.
    pred + konfig_model (ensemble, tools/ensemble_val.py): prediksi val siap pakai dan baris model untuk config; default tidak berubah."""
    r_min = r_min or {}
    DT.mkdir(parents=True, exist_ok=True)
    keluaran = [DT / n for n in (f"ambang_val{akh}.json", f"ambang_kurva_val{akh}.csv", f"val_fp_tangga{akh}.png", f"val_fp_tangga{akh}.csv",
                                 f"val_recall_dekat{akh}.json", f"config_saran{akh}.yaml", f"val_pred_{model}{akh}.pkl" if akh else "val_pred_final.pkl")]
    ada = [str(p) for p in keluaran if p.exists()]
    if ada:
        sys.exit("Sudah ada, tidak ditimpa:\n  " + "\n  ".join(ada))
    names, imgs, lab_dir = er.cek_val(er.YK)  # assert 54 frame, semua lokasi val, bukan test
    siap = pred is not None
    pred = pred if siap else prediksi(model, imgs, CONF_PRED)
    keluaran[-1].write_bytes(pickle.dumps(pred))
    T = f"T0{akh}"

    # cek jalur: pada conf 0,25 harus sama dengan runs/ronde2/eval/r2-kotak-v3-960/galat.json
    st25, fp25, gt25, _ = hitung(names, imgs, lab_dir, pred, 0.25)
    lama = {names[k]: v for k, v in st25.items()} if siap else json.loads((er.OUT / model / "galat.json").read_text(encoding="utf-8"))["per_kelas"]
    beda = {names[k]: (v, {x: lama[names[k]][x] for x in ("tp", "fp", "fn")}) for k, v in st25.items()
            if any(v[x] != lama[names[k]][x] for x in ("tp", "fp", "fn"))}
    if siap:
        log(f"[{T}-1] Prediksi siap pakai ({model}); cek jalur conf 0,25 dilakukan pemanggil.")
    elif beda:
        log(f"[{T}-1] PERINGATAN: TP/FP/FN conf 0,25 berbeda dari galat.json ronde 2: {beda}")
    else:
        log(f"[{T}-1] Cek jalur: TP/FP/FN conf 0,25 (prediksi conf 0,05 lalu disaring) identik dengan runs/ronde2/eval/{model}/galat.json.")

    kurva = {t: hitung(names, imgs, lab_dir, pred, t)[0] for t in GRID}
    with open(DT / f"ambang_kurva_val{akh}.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["kelas", "n_val", "ambang", "tp", "fp", "fn", "P", "R", "F1"])
        for k, nm in names.items():
            for t in GRID:
                v = kurva[t][k]
                wr.writerow([nm, v["tp"] + v["fn"], t, v["tp"], v["fp"], v["fn"]] + ["" if x is None else f"{x:.4f}" for x in prf(v)])

    amb, rinci = {}, {}
    for k, nm in names.items():
        n = st25[k]["tp"] + st25[k]["fn"]
        f1 = {t: (prf(kurva[t][k])[2] or 0.0) for t in GRID}
        rc = {t: (prf(kurva[t][k])[1] or 0.0) for t in GRID}
        fmax = max(f1.values())
        t_f1 = min((t for t in GRID if abs(f1[t] - fmax) < 1e-12), key=lambda t: (abs(t - 0.25), t))
        cat = []
        if n < eb.LOW_N:
            t = 0.25
            cat.append(f"n val {n} < {eb.LOW_N}: pakai 0,25 (F1 terbaik di grid {fmax:.3f} pada {t_f1})")
        elif fmax - f1[0.25] < DATAR:
            t = 0.25
            cat.append(f"kurva datar (F1 terbaik {fmax:.3f} pada {t_f1} vs {f1[0.25]:.3f} pada 0,25, selisih < {DATAR}): pakai 0,25")
        else:
            t = t_f1
            cat.append(f"F1 terbaik {fmax:.3f} pada {t_f1}")
        R_MIN = r_min.get(nm, globals()["R_MIN"])
        if nm in BAHAYA and n >= eb.LOW_N and rc[t] < R_MIN:
            ok = [x for x in GRID if rc[x] >= R_MIN]
            if ok:
                cat.append(f"kelas bahaya: recall {rc[t]:.3f} pada {t} < {R_MIN}, diturunkan ke ambang tertinggi dengan recall >= {R_MIN}")
                t = max(ok)
            else:
                tmax = max(GRID, key=lambda x: (rc[x], x))
                cat.append(f"kelas bahaya: recall {rc[t]:.3f} pada {t} < {R_MIN} dan TIDAK ADA ambang di grid yang mencapai {R_MIN} "
                           f"(recall tertinggi {rc[tmax]:.3f} pada {tmax}); ambang tidak diubah, perlu keputusan")
        elif nm in BAHAYA and n < eb.LOW_N:
            cat.append(f"kelas bahaya tetapi n < {eb.LOW_N}: aturan recall tidak diterapkan (recall val pada 0,25 = {rc[0.25]:.3f})")
        amb[k] = t
        p_, r_, f_ = prf(kurva[t][k])
        p25, r25, f25 = prf(kurva[0.25][k])
        rinci[nm] = dict(ambang=t, n_val=n, ambang_F1_terbaik=t_f1, F1_terbaik=fmax, P=p_, R=r_, F1=f_, **kurva[t][k],
                         pada_025=dict(P=p25, R=r25, F1=f25, **kurva[0.25][k]), bahaya=nm in BAHAYA, catatan="; ".join(cat))
    conf_kelas = {names[k]: amb[k] for k in names}
    (DT / f"ambang_val{akh}.json").write_text(json.dumps(dict(
        sumber=f"val v2 (54 frame), {model} imgsz {'lihat config' if siap else er.MODEL[model][3]}, cocok IoU>=0,5 kelas sama",
        aturan=dict(grid=GRID, n_min=eb.LOW_N, datar=DATAR, kelas_bahaya=BAHAYA, recall_min_bahaya=globals()["R_MIN"],
                    recall_min_khusus=r_min),
        conf_kelas=conf_kelas, rinci=rinci), indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"[{T}-2] Ambang per kelas dari val: {conf_kelas} -> data/test-final/ambang_val{akh}.json (+ ambang_kurva_val{akh}.csv).")

    # FP tangga
    tg = next(k for k, nm in names.items() if nm == "tangga")
    stA, fpA, gtA, perA = hitung(names, imgs, lab_dir, pred, amb)
    fp_t25 = sorted([f for f in fp25 if f["kelas"] == tg], key=lambda f: -f["conf"])
    fp_tA = [f for f in fpA if f["kelas"] == tg]
    peta = {p.name: p for p in imgs}
    sheet_fp(fp_t25, peta, names, lab_dir, DT / f"val_fp_tangga{akh}.png")
    with open(DT / f"val_fp_tangga{akh}.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["no", "gambar", "conf", "x1", "y1", "x2", "y2", "fp_pada_025", "fp_pada_ambang_app", "isi (diisi setelah dilihat)"])
        for n, x in enumerate(fp_t25, 1):
            wr.writerow([n, x["gambar"], f"{x['conf']:.3f}"] + [round(v) for v in x["xyxy"]] + [1, int(x["conf"] >= amb[tg] - 1e-9), ""])
    log(f"[{T}-3] FP tangga di val: {len(fp_t25)} pada conf 0,25, {len(fp_tA)} pada ambang app ({amb[tg]}). Sheet: data/test-final/val_fp_tangga{akh}.png, daftar val_fp_tangga{akh}.csv.")

    # recall objek dekat
    rd = dict(definisi=f"dekat = y2 GT >= {Y_DEKAT} x tinggi gambar; ukuran = akar luas kotak, px skala 640",
              conf_025=recall_dekat(names, gt25), ambang_app=recall_dekat(names, gtA),
              galat_ambang_app={names[k]: v for k, v in stA.items()},
              fp_per_frame_ambang_app=sum(v["fp"] for v in stA.values()) / len(imgs),
              fp_per_frame_conf_025=sum(v["fp"] for v in st25.values()) / len(imgs))
    (DT / f"val_recall_dekat{akh}.json").write_text(json.dumps(rd, indent=2, ensure_ascii=False), encoding="utf-8")
    a, b = rd["conf_025"], rd["ambang_app"]
    log(f"[{T}-4] Recall val conf 0,25: dekat {a['dekat']['ditemukan']}/{a['dekat']['gt']}, sisanya {a['jauh']['ditemukan']}/{a['jauh']['gt']}; "
        f"ambang app: dekat {b['dekat']['ditemukan']}/{b['dekat']['gt']}, sisanya {b['jauh']['ditemukan']}/{b['jauh']['gt']}. -> val_recall_dekat{akh}.json")

    baris = ["# Saran pengaturan server aplikasi JalanKu. Dibuat tools/test_final.py --aksi t0 dari VAL v2 saja (54 frame),",
             "# sebelum test set disentuh. Ambang per kelas: lihat data/test-final/ambang_val" + akh + ".json untuk alasannya.",
             *(konfig_model or [f"model_kotak: {er.MODEL[model][2]}", f"imgsz_kotak: {er.MODEL[model][3]}"]),
             "model_seg: models/ronde2/r2-seg-v3_best.pt", "imgsz_seg: 640",
             *([] if konfig_model else [f"conf_prediksi_kotak: {min(conf_kelas.values())}  # conf untuk predict(); sesudahnya saring per kelas dengan conf_kelas"]),
             "conf_seg: 0.25  # tidak disetel; sama dengan tabel val", "conf_kelas:"]
    baris += [f"  {nm}: {t}" for nm, t in conf_kelas.items()]
    (DT / f"config_saran{akh}.yaml").write_text("\n".join(baris) + "\n", encoding="utf-8")
    log(f"[{T}-5] data/test-final/config_saran{akh}.yaml ditulis.")


# ---------------------------------------------------------------- ronde 3: banding kandidat final di val
KANDIDAT = ("r2-kotak-v3-960", "r3-kotak-v3-960-s")


def aksi_banding_val(kandidat=None, nama_out="r3_banding_val.json", tag="R3-banding"):
    """Val v2 saja. Angka tabel (mAP, P/R/F1 Ultralytics) dibaca dari runs/ronde2/eval/<model>/metrik.json;
    recall dekat dan FP per frame dihitung di sini pada conf 0,25 dengan jalur yang sama dengan T0."""
    out = DT / nama_out
    if out.exists():
        sys.exit(f"{out} sudah ada, tidak ditimpa.")
    names, imgs, lab_dir = er.cek_val(er.YK)
    kc = json.loads((er.OUT / "kecepatan.json").read_text(encoding="utf-8"))["hasil"]
    h = {}
    for m in (kandidat or KANDIDAT):
        mt = json.loads((er.OUT / m / "metrik.json").read_text(encoding="utf-8"))["box"]
        st, fps, gts, _ = hitung(names, imgs, lab_dir, prediksi(m, imgs, 0.25), 0.25)
        tot = {x: sum(v[x] for v in st.values()) for x in ("tp", "fp", "fn")}
        h[m] = dict(tabel={k: mt[k] for k in ("mAP50", "mAP50_95", "P", "R", "F1", "conf_F1_terbaik")},
                    kelas_tabel={c["nama"]: {k: c[k] for k in ("n_instance", "mAP50", "P", "R", "F1")} for c in mt["kelas"]},
                    conf025=dict(total=tot, F1_mikro=prf(tot)[2], P_mikro=prf(tot)[0], R_mikro=prf(tot)[1],
                                 per_kelas={names[k]: dict(v, **dict(zip(("P", "R", "F1"), prf(v)))) for k, v in st.items()},
                                 fp_per_frame=tot["fp"] / len(imgs), recall=recall_dekat(names, gts)),
                    kecepatan={k: v["total_ms"] for k, v in kc[m].items() if k != "imgsz"})
    out.write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")
    for m, d in h.items():
        r = d["conf025"]["recall"]
        log(f"[{tag}] {m}: tabel mAP50 {d['tabel']['mAP50']:.3f} mAP50-95 {d['tabel']['mAP50_95']:.3f} P {d['tabel']['P']:.3f} R {d['tabel']['R']:.3f} "
            f"F1 {d['tabel']['F1']:.3f}; conf 0,25: TP/FP/FN {d['conf025']['total']['tp']}/{d['conf025']['total']['fp']}/{d['conf025']['total']['fn']}, "
            f"F1 mikro {d['conf025']['F1_mikro']:.3f}, FP/frame {d['conf025']['fp_per_frame']:.2f}, recall dekat {r['dekat']['ditemukan']}/{r['dekat']['gt']}, "
            f"sisanya {r['jauh']['ditemukan']}/{r['jauh']['gt']}; ms/frame {d['kecepatan']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aksi", choices=["t0", "banding-val"], required=True)
    ap.add_argument("--model", default=FINAL_KOTAK, choices=[n for n, v in er.MODEL.items() if v[0] == "detect"])
    ap.add_argument("--akhiran", default="")
    ap.add_argument("--kandidat", action="append", help="banding-val: model kotak (default KANDIDAT ronde 3)")
    ap.add_argument("--keluaran", default="r3_banding_val.json")
    ap.add_argument("--tag", default="R3-banding")
    ap.add_argument("--rmin", action="append", default=[], help="kelas=recall, mis. tepian=0.5")
    args = ap.parse_args()
    if args.aksi == "t0":
        aksi_t0(args.model, args.akhiran, {a.split("=")[0]: float(a.split("=")[1]) for a in args.rmin})
    else:
        aksi_banding_val(args.kandidat, args.keluaran, args.tag)


if __name__ == "__main__":
    main()
