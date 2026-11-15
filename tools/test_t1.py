"""test_t1.py - T1: evaluasi TEST FINAL JalanKu, SEKALI per model (data/prompt-test-final.md section 3 + [ENS-8]).

Tidak mengubah model, ambang, label, atau config. Semua pengaturan di bawah ditetapkan SEBELUM test disentuh dan jalur
kodenya diuji dulu di VAL v2 (--data val), yang angkanya sudah diketahui dari T0 / [ENS-1] / [ENS-4].

Model kotak (10): baseline-kotak, r2-kotak-v2bersih, r2-kotak-v3, r2-kotak-v3-960, r3-kotak-v3-960-s, r4-kotak-v3-960-seed1,
  r4-kotak-v3-1280, r4-kotak-v4-960, C1 (r2-kotak-v3-960 + augment=True), C2 (WBF 4 model = FINAL).
Model seg (3): baseline-seg, r2-seg-v3 (FINAL), r4-seg-v4.

Untuk tiap model kotak, per subset (semua, kelompok lokasi, POV):
  - "jalur sendiri" (ensemble_val.metrik; SATU jalur untuk model tunggal, C1, C2): prediksi conf 0,001 (C2: conf anggota
    0,001 lalu WBF) -> mAP50, mAP50-95, AP50 per kelas, P/R/F1 pada satu conf global terbaik.
  - class-agnostic lewat jalur yang sama: kelas GT dan kelas prediksi akhir dijadikan 0 (C2: WBF per kelas dulu, lalu kelas diabaikan).
  - metrik berambang dari prediksi conf 0,05 = pengaturan app (C2: conf anggota 0,05 lalu WBF, [ENS-8]): TP/FP/FN per kelas,
    P/R/F1 mikro, FP per frame, recall dekat (y2 >= 0,65) dan per ukuran, class-agnostic TP/FP/FN, peringatan tingkat frame;
    pada conf 0,25 seragam untuk SEMUA model, dan pada ambang per kelas TERKUNCI untuk C2 (ambang_val_ens.json) dan
    r2-kotak-v3-960 (ambang_val_final.json, T0 model itu sendiri).
Hanya untuk model tunggal, subset semua: tabel Ultralytics val (eb.jalankan_val, sama dengan tabel val) dan Ultralytics
  single_cls (metrik_tambahan.agnostik_val). C1 dan C2 tidak punya tabel Ultralytics (val() tidak bisa WBF); pembanding
  antar semua model = jalur sendiri.
Seg: eb.jalankan_val (mask mAP, P, R) + eb.prediksi_semua conf 0,25 + eb.analisis (IoU piksel per kelas), per subset.

  python tools/test_t1.py --data val    # uji jalur + angka val jalur-sama -> data/test-final/t1_val/, runs/test-final/val-ulang/
  python tools/test_t1.py --data test   # SEKALI -> data/test-final/t1/, runs/test-final/
  python tools/test_t1.py --aksi tabel  # tabel Markdown -> data/test-final/t1/tabel.md
  python tools/test_t1.py --aksi sheet  # contact sheet test model final, hanya sesudah semua angka tersimpan

Model yang <model>.json-nya sudah ada TIDAK dijalankan ulang.
"""
import argparse
import hashlib
import json
import pickle
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import ensemble_val as ev  # noqa: E402
import evaluasi_baseline as eb  # noqa: E402
import evaluasi_ronde2 as er  # noqa: E402
import metrik_tambahan as mt  # noqa: E402
import test_final as tf  # noqa: E402

ROOT = eb.ROOT
DT = tf.DT
TUNGGAL = ("baseline-kotak", "r2-kotak-v2bersih", "r2-kotak-v3", "r2-kotak-v3-960", "r3-kotak-v3-960-s", "r4-kotak-v3-960-seed1",
           "r4-kotak-v3-1280", "r4-kotak-v4-960")
KOTAK = TUNGGAL + ("C1", "C2")
SEG = ("baseline-seg", "r2-seg-v3", "r4-seg-v4")
FINAL_KOTAK, FINAL_SEG = "C2", "r2-seg-v3"
AMBANG = {"C2": "ambang_val_ens.json", "r2-kotak-v3-960": "ambang_val_final.json"}
SET = {
    "test": dict(yk=ROOT / "data/dataset-test-kotak/data.yaml", ys=ROOT / "data/dataset-test-seg/data.yaml", dt=DT / "t1",
                 rt=ROOT / "runs" / "test-final", n=91),
    "val": dict(yk=er.YK, ys=er.YS, dt=DT / "t1_val", rt=ROOT / "runs" / "test-final" / "val-ulang", n=54),
}


def muat_data(data, yaml_path):
    names, imgs, lab_dir = eb.info_val(yaml_path)  # yaml test: val = images/test (folder yang sama)
    assert len(imgs) == SET[data]["n"], len(imgs)
    for p in imgs:
        lok = p.stem.split("_20")[0]
        if data == "test":
            assert lok.startswith(er.TEST), p.name
        else:
            assert lok in er.LOKASI_VAL, p.name
    return names, imgs, lab_dir


def subset(data, imgs):
    s = {"semua": list(imgs)}
    for p in imgs:
        lok = p.stem.split("_20")[0]
        g = ("lantai11" if lok.startswith(("selasar-lt11", "pot-lt11")) else "taman-ubm") if data == "test" else lok
        s.setdefault(g, []).append(p)
        s.setdefault("dada" if "_dada_" in p.name else "mata", []).append(p)
    assert all(("_dada_" in p.name) != ("_mata_" in p.name) for p in imgs)
    return s


def sidik(*dirs):
    h = hashlib.sha256()
    n = 0
    for d in dirs:
        for p in sorted(Path(d).iterdir()):
            if p.suffix.lower() in (".txt", ".jpg", ".jpeg", ".png"):
                h.update(p.name.encode())
                h.update(p.read_bytes())
                n += 1
    return f"{n} berkas sha256 {h.hexdigest()[:16]}"


@contextmanager
def gt_satu_kelas():
    asli = eb.baca_gt
    eb.baca_gt = lambda *a, **k: [(0, bx, po) for _, bx, po in asli(*a, **k)]
    try:
        yield
    finally:
        eb.baca_gt = asli


def nol_kelas(pred):
    return {k: dict(v, cls=np.zeros_like(v["cls"])) for k, v in pred.items()}


def metrik_aman(names, imgs, lab_dir, pred):
    """ev.metrik; subset tanpa GT atau tanpa prediksi -> None (dicatat), bukan galat."""
    n_gt = sum(len(eb.baca_gt(lab_dir / (p.stem + ".txt"), pred[p.name]["w"], pred[p.name]["h"], "detect")) for p in imgs)
    n_pr = sum(len(pred[p.name]["cls"]) for p in imgs)
    if not n_gt or not n_pr:
        return dict(kosong=True, n_gt=n_gt, n_prediksi=n_pr)
    return ev.metrik(names, imgs, lab_dir, pred)


def berambang(names, imgs, lab_dir, pred, amb):
    st, fps, gts, per = tf.hitung(names, imgs, lab_dir, pred, amb)
    tot = {k: sum(v[k] for v in st.values()) for k in ("tp", "fp", "fn")}
    p, r, f = tf.prf(tot)
    tukar = {}
    for x in fps:
        if x["tertukar_dengan"]:
            k = f"{names[x['kelas']]} (prediksi) di atas GT {x['tertukar_dengan']}"
            tukar[k] = tukar.get(k, 0) + 1
    frame, _ = mt.level_frame(imgs, lab_dir, pred, amb)
    # class-agnostic pada ambang yang sama: saring dulu per kelas, baru kelas diabaikan
    sar = {q.name: tf.saring(pred[q.name], amb) for q in imgs}
    agn = mt.agnostik_silang(imgs, lab_dir, sar, conf=0.0)
    return dict(total=tot, P_mikro=p, R_mikro=r, F1_mikro=f, fp_per_frame=tot["fp"] / len(imgs), n_frame=len(imgs),
                per_kelas={names[k]: dict(v, n=v["tp"] + v["fn"], **dict(zip(("P", "R", "F1"), tf.prf(v)))) for k, v in st.items()},
                recall=tf.recall_dekat(names, gts), fp_tertukar=tukar, frame=frame,
                agnostik={k: agn[k] for k in ("tp", "fp", "fn", "P", "R", "F1")}, per_gambar=per)


def nilai_kotak(nama, data, names, imgs, lab_dir, p001, p005, dt):
    amb_file = AMBANG.get(nama)
    amb = None
    if amb_file:
        ck = json.loads((DT / amb_file).read_text(encoding="utf-8"))["conf_kelas"]
        amb = {k: ck[nm] for k, nm in names.items()}
    h = dict(model=nama, data=data, ambang_terkunci=({names[k]: v for k, v in amb.items()} if amb else None), ambang_dari=amb_file, subset={})
    for sn, S in subset(data, imgs).items():
        d = dict(n_frame=len(S), jalur_sendiri=metrik_aman(names, S, lab_dir, p001))
        with gt_satu_kelas():
            d["agnostik_jalur_sendiri"] = metrik_aman({0: "rintangan"}, S, lab_dir, nol_kelas(p001))
        d["conf025"] = berambang(names, S, lab_dir, p005, 0.25)
        if amb:
            d["ambang_terkunci"] = berambang(names, S, lab_dir, p005, amb)
        if sn != "semua":
            for k in ("conf025", "ambang_terkunci"):
                d.get(k, {}).pop("per_gambar", None)
        h["subset"][sn] = d
    return h


def aksi_jalan(data):
    from ultralytics import YOLO

    cfg = SET[data]
    dt, rt = cfg["dt"], cfg["rt"]
    dt.mkdir(parents=True, exist_ok=True)
    rt.mkdir(parents=True, exist_ok=True)
    catat = tf.log if data == "test" else (lambda t: print(t, flush=True))
    names, imgs, lab_dir = muat_data(data, cfg["yk"])
    names_s, imgs_s, lab_s = muat_data(data, cfg["ys"])
    sebelum = sidik(imgs[0].parent, lab_dir, imgs_s[0].parent, lab_s)
    catat(f"[T1-0] ({data}) mulai tools/test_t1.py: {len(imgs)} frame kotak, {len(imgs_s)} frame seg; isi gambar+label sebelum: {sebelum}.")
    er.pasang_imgsz()
    cache = {}

    def pred(nama, augment=False):
        """prediksi conf 0,001 dan 0,05 satu model; disimpan supaya anggota C2 tidak diprediksi ulang."""
        kunci = (nama, augment)
        pk = dt / f"pred_{nama}{'_tta' if augment else ''}.pkl"
        if kunci not in cache:
            if pk.exists():
                cache[kunci] = pickle.loads(pk.read_bytes())
            else:
                cache[kunci] = dict(c001=ev.prediksi(nama, imgs, conf=0.001, augment=augment)[0],
                                    c005=ev.prediksi(nama, imgs, conf=0.05, augment=augment)[0])
                pk.write_bytes(pickle.dumps(cache[kunci]))
        return cache[kunci]

    for nama in KOTAK:
        out = dt / f"{nama}.json"
        if out.exists():
            print(f"-- {nama}: sudah ada, TIDAK dijalankan ulang", flush=True)
            continue
        print(f"== {nama}", flush=True)
        if nama == "C1":
            pr = pred(ev.R2, augment=True)
            p001, p005 = pr["c001"], pr["c005"]
        elif nama == "C2":
            ps = [pred(n) for n in ev.ANGGOTA]
            p001 = {p.name: ev.wbf_gambar([x["c001"][p.name] for x in ps]) for p in imgs}
            p005 = {p.name: ev.wbf_gambar([x["c005"][p.name] for x in ps]) for p in imgs}
            (dt / "pred_C2.pkl").write_bytes(pickle.dumps(dict(c001=p001, c005=p005)))
        else:
            pr = pred(nama)
            p001, p005 = pr["c001"], pr["c005"]
        h = nilai_kotak(nama, data, names, imgs, lab_dir, p001, p005, dt)
        if nama in TUNGGAL:
            _, _, bobot, imgsz = er.MODEL[nama]
            er.IMGSZ["nilai"] = imgsz
            eb.RUNS[nama] = ("detect", cfg["yk"])
            u = eb.jalankan_val(nama, ROOT / bobot, rt)
            u["imgsz"] = imgsz
            h["ultralytics"] = u
            h["ultralytics_agnostik"] = mt.agnostik_val(nama, cfg["yk"], proyek=rt / "agnostik")
        out.write_text(json.dumps(h, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
        s = h["subset"]["semua"]
        j, c = s["jalur_sendiri"], s["conf025"]
        a = s.get("ambang_terkunci")
        catat(f"[T1-kotak] ({data}) {nama}: jalur sendiri mAP50 {j['mAP50']:.3f} mAP50-95 {j['mAP50_95']:.3f} F1 {j['F1']:.3f}"
              + (f"; tabel Ultralytics mAP50 {h['ultralytics']['box']['mAP50']:.3f} mAP50-95 {h['ultralytics']['box']['mAP50_95']:.3f} "
                 f"P {h['ultralytics']['box']['P']:.3f} R {h['ultralytics']['box']['R']:.3f} F1 {h['ultralytics']['box']['F1']:.3f}" if "ultralytics" in h else "")
              + f"; conf 0,25 TP/FP/FN {c['total']['tp']}/{c['total']['fp']}/{c['total']['fn']} FP/frame {c['fp_per_frame']:.2f} "
                f"dekat {c['recall']['dekat']['ditemukan']}/{c['recall']['dekat']['gt']}"
              + (f"; ambang terkunci TP/FP/FN {a['total']['tp']}/{a['total']['fp']}/{a['total']['fn']} FP/frame {a['fp_per_frame']:.2f} "
                 f"dekat {a['recall']['dekat']['ditemukan']}/{a['recall']['dekat']['gt']} frame TP{a['frame']['TP']} FP{a['frame']['FP']} "
                 f"FN{a['frame']['FN']} TN{a['frame']['TN']}" if a else ""))

    for nama in SEG:
        out = dt / f"{nama}.json"
        if out.exists():
            print(f"-- {nama}: sudah ada, TIDAK dijalankan ulang", flush=True)
            continue
        print(f"== {nama}", flush=True)
        _, _, bobot, imgsz = er.MODEL[nama]
        er.IMGSZ["nilai"] = imgsz
        eb.RUNS[nama] = ("segment", cfg["ys"])
        h = dict(model=nama, data=data, ultralytics=eb.jalankan_val(nama, ROOT / bobot, rt), subset={})
        pr = eb.prediksi_semua(YOLO(str(ROOT / bobot)), imgs_s)
        (dt / f"pred_{nama}.pkl").write_bytes(pickle.dumps(pr))
        for sn, S in subset(data, imgs_s).items():
            rekap, per = eb.analisis(nama, names_s, S, lab_s, "segment", pr)
            h["subset"][sn] = dict(n_frame=len(S), iou_piksel_per_kelas=rekap["iou_piksel_per_kelas"], **(dict(per_gambar=per) if sn == "semua" else {}))
        out.write_text(json.dumps(h, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
        m = h["ultralytics"]["mask"]
        catat(f"[T1-seg] ({data}) {nama}: mask mAP50 {m['mAP50']:.3f} mAP50-95 {m['mAP50_95']:.3f} P {m['P']:.3f} R {m['R']:.3f}; "
              f"IoU piksel {({k: (None if v is None else round(v, 3)) for k, v in h['subset']['semua']['iou_piksel_per_kelas'].items()})}")
    sesudah = sidik(imgs[0].parent, lab_dir, imgs_s[0].parent, lab_s)
    catat(f"[T1-9] ({data}) selesai. Isi gambar+label sesudah: {sesudah} ({'SAMA' if sesudah == sebelum else 'BERBEDA!'}).")


# ---------------------------------------------------------------- tabel
def f3(x):
    return "-" if x is None else f"{x:.3f}"


def rk(d):
    return f"{d['ditemukan']}/{d['gt']}" + (f" ({d['recall']:.2f})" if d["gt"] else "")


def muat_hasil(data):
    dt = SET[data]["dt"]
    return {n: json.loads((dt / f"{n}.json").read_text(encoding="utf-8")) for n in KOTAK + SEG if (dt / f"{n}.json").exists()}


def tabel(data):
    H = muat_hasil(data)
    K = [n for n in KOTAK if n in H]
    md = [f"# Tabel T1 ({data})", ""]
    md += ["## Kotak, semua frame", "",
           "| Model | mAP50 | mAP50-95 | F1 | mAP50 (Ultra) | mAP50-95 (Ultra) | P (Ultra) | R (Ultra) | F1 (Ultra) | TP/FP/FN 0,25 | P/R/F1 mikro 0,25 | FP/frame | dekat | jauh |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in K:
        s = H[n]["subset"]["semua"]
        j, c, u = s["jalur_sendiri"], s["conf025"], H[n].get("ultralytics", {}).get("box")
        md.append(f"| {n} | {f3(j['mAP50'])} | {f3(j['mAP50_95'])} | {f3(j['F1'])} | " + (" | ".join(f3(u[k]) for k in ("mAP50", "mAP50_95", "P", "R", "F1")) if u else "- | - | - | - | -")
                  + f" | {c['total']['tp']}/{c['total']['fp']}/{c['total']['fn']} | {f3(c['P_mikro'])}/{f3(c['R_mikro'])}/{f3(c['F1_mikro'])} | {c['fp_per_frame']:.2f} | "
                    f"{rk(c['recall']['dekat'])} | {rk(c['recall']['jauh'])} |")
    md += ["", "## Kotak, ambang per kelas terkunci (pengaturan app)", "",
           "| Model | subset | TP/FP/FN | P/R/F1 mikro | FP/frame | dekat | jauh | frame TP/FP/FN/TN | frame P | frame R | agnostik TP/FP/FN |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in K:
        for sn, s in H[n]["subset"].items():
            a = s.get("ambang_terkunci")
            if a:
                fr, g = a["frame"], a["agnostik"]
                md.append(f"| {n} | {sn} ({s['n_frame']}) | {a['total']['tp']}/{a['total']['fp']}/{a['total']['fn']} | {f3(a['P_mikro'])}/{f3(a['R_mikro'])}/{f3(a['F1_mikro'])} | "
                          f"{a['fp_per_frame']:.2f} | {rk(a['recall']['dekat'])} | {rk(a['recall']['jauh'])} | {fr['TP']}/{fr['FP']}/{fr['FN']}/{fr['TN']} | {f3(fr['precision'])} | "
                          f"{f3(fr['recall'])} | {g['tp']}/{g['fp']}/{g['fn']} |")
    md += ["", "## Kotak, dua metrik tambahan (semua frame)", "",
           "| Model | agn mAP50 | agn mAP50-95 | agn F1 | agn mAP50 (Ultra single_cls) | agn F1 (Ultra) | agn TP/FP/FN 0,25 | agn P/R 0,25 | frame TP/FP/FN/TN 0,25 | frame P | frame R |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in K:
        s = H[n]["subset"]["semua"]
        g, c, u = s["agnostik_jalur_sendiri"], s["conf025"], H[n].get("ultralytics_agnostik")
        fr, a = c["frame"], c["agnostik"]
        md.append(f"| {n} | {f3(g['mAP50'])} | {f3(g['mAP50_95'])} | {f3(g['F1'])} | {f3(u['mAP50']) if u else '-'} | {f3(u['F1']) if u else '-'} | {a['tp']}/{a['fp']}/{a['fn']} | "
                  f"{f3(a['P'])}/{f3(a['R'])} | {fr['TP']}/{fr['FP']}/{fr['FN']}/{fr['TN']} | {f3(fr['precision'])} | {f3(fr['recall'])} |")
    subs = [k for k in H[K[0]]["subset"] if k != "semua"]
    md += ["", "## Kotak per subset (jalur sendiri mAP50 / mAP50-95; conf 0,25 TP/FP/FN, FP per frame, recall dekat, frame TP/FP/FN/TN)", ""]
    for sn in subs:
        md += [f"### {sn} ({H[K[0]]['subset'][sn]['n_frame']} frame)", "",
               "| Model | mAP50 | mAP50-95 | F1 | TP/FP/FN | P/R/F1 mikro | FP/frame | dekat | frame TP/FP/FN/TN | agn mAP50 | agn TP/FP/FN |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for n in K:
            s = H[n]["subset"][sn]
            j, c, g = s["jalur_sendiri"], s["conf025"], s["agnostik_jalur_sendiri"]
            fr = c["frame"]
            md.append(f"| {n} | {f3(j.get('mAP50'))} | {f3(j.get('mAP50_95'))} | {f3(j.get('F1'))} | {c['total']['tp']}/{c['total']['fp']}/{c['total']['fn']} | "
                      f"{f3(c['P_mikro'])}/{f3(c['R_mikro'])}/{f3(c['F1_mikro'])} | {c['fp_per_frame']:.2f} | {rk(c['recall']['dekat'])} | "
                      f"{fr['TP']}/{fr['FP']}/{fr['FN']}/{fr['TN']} | {f3(g.get('mAP50'))} | {c['agnostik']['tp']}/{c['agnostik']['fp']}/{c['agnostik']['fn']} |")
        md.append("")
    kelas = list(H[K[0]]["subset"]["semua"]["conf025"]["per_kelas"])
    md += ["## Kotak per kelas, AP50 (jalur sendiri)", "", "| Kelas | n | " + " | ".join(K) + " |", "|---|---|" + "---|" * len(K)]
    for k in kelas:
        n_k = H[K[0]]["subset"]["semua"]["conf025"]["per_kelas"][k]["n"]
        md.append(f"| {k}{' *' if n_k < eb.LOW_N else ''} | {n_k} | " + " | ".join(f3(H[n]["subset"]["semua"]["jalur_sendiri"]["kelas"].get(k, {}).get("AP50")) for n in K) + " |")
    md += ["", "## Kotak per kelas, TP/FP/FN conf 0,25", "", "| Kelas | n | " + " | ".join(K) + " |", "|---|---|" + "---|" * len(K)]
    for k in kelas:
        md.append(f"| {k} | {H[K[0]]['subset']['semua']['conf025']['per_kelas'][k]['n']} | "
                  + " | ".join("{tp}/{fp}/{fn}".format(**H[n]["subset"]["semua"]["conf025"]["per_kelas"][k]) for n in K) + " |")
    for n in K:
        a = H[n]["subset"]["semua"].get("ambang_terkunci")
        if not a:
            continue
        md += ["", f"## {n}: per kelas pada ambang terkunci", "", "| Kelas | ambang | n | TP | FP | FN | P | R | F1 | dekat | jauh |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, v in a["per_kelas"].items():
            r = a["recall"]["per_kelas"][k]
            md.append(f"| {k} | {H[n]['ambang_terkunci'][k]} | {v['n']} | {v['tp']} | {v['fp']} | {v['fn']} | {f3(v['P'])} | {f3(v['R'])} | {f3(v['F1'])} | {rk(r['dekat'])} | {rk(r['jauh'])} |")
        md += ["", "Recall per ukuran (px skala 640): " + ", ".join(f"{b} {rk(v)}" for b, v in a["recall"]["per_ukuran"].items()),
               "", "FP yang menimpa GT kelas lain: " + (", ".join(f"{k}: {v}" for k, v in sorted(a["fp_tertukar"].items(), key=lambda x: -x[1])) or "tidak ada")]
    S = [n for n in SEG if n in H]
    if S:
        md += ["", "## Segmentasi (mask)", "", "| Model | mAP50 | mAP50-95 | P | R | F1 | " + " | ".join(f"IoU {k}" for k in H[S[0]]["subset"]["semua"]["iou_piksel_per_kelas"]) + " |",
               "|---|---|---|---|---|---|" + "---|" * len(H[S[0]]["subset"]["semua"]["iou_piksel_per_kelas"])]
        for n in S:
            m = H[n]["ultralytics"]["mask"]
            md.append(f"| {n} | {f3(m['mAP50'])} | {f3(m['mAP50_95'])} | {f3(m['P'])} | {f3(m['R'])} | {f3(m['F1'])} | " + " | ".join(f3(v) for v in H[n]["subset"]["semua"]["iou_piksel_per_kelas"].values()) + " |")
        md += ["", "Per kelas (mask): " + "; ".join(f"{n}: " + ", ".join(f"{c['nama']} n={c['n_instance']} mAP50 {f3(c['mAP50'])} P {f3(c['P'])} R {f3(c['R'])}" for c in H[n]["ultralytics"]["mask"]["kelas"]) for n in S),
               "", "IoU piksel per subset:", "", "| Model | subset | " + " | ".join(H[S[0]]["subset"]["semua"]["iou_piksel_per_kelas"]) + " |", "|---|---|---|---|---|"]
        for n in S:
            for sn, s in H[n]["subset"].items():
                md.append(f"| {n} | {sn} ({s['n_frame']}) | " + " | ".join(f3(v) for v in s["iou_piksel_per_kelas"].values()) + " |")
    out = SET[data]["dt"] / "tabel.md"
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(out)


def aksi_sheet():
    """Contact sheet test model final. Hanya sesudah SEMUA angka test tersimpan."""
    cfg = SET["test"]
    kurang = [n for n in KOTAK + SEG if not (cfg["dt"] / f"{n}.json").exists()]
    if kurang:
        sys.exit(f"Angka test belum lengkap ({kurang}); sheet tidak dibuat.")
    names, imgs, lab_dir = muat_data("test", cfg["yk"])
    ck = json.loads((DT / AMBANG["C2"]).read_text(encoding="utf-8"))["conf_kelas"]
    amb = {k: ck[nm] for k, nm in names.items()}
    p005 = pickle.loads((cfg["dt"] / "pred_C2.pkl").read_bytes())["c005"]
    pred = {p.name: tf.saring(p005[p.name], amb) for p in imgs}
    _, per = eb.analisis("C2", names, imgs, lab_dir, "detect", pred)
    bagus, buruk = eb.pilih(per)
    for nm, pil, kol, cw, ch, jenis in (("kontak_16", bagus + buruk, 4, 240, 427, ""), ("kontak_terburuk", buruk, 2, 380, 676, "terburuk")):
        out = cfg["rt"] / f"C2_{nm}.jpg"
        assert not out.exists(), out
        eb.buat_sheet("C2", "detect", names, imgs, lab_dir, pred, per, pil, kol, cw, ch, out, jenis)
        print(out)
    names_s, imgs_s, lab_s = muat_data("test", cfg["ys"])
    ps = pickle.loads((cfg["dt"] / f"pred_{FINAL_SEG}.pkl").read_bytes())
    per = json.loads((cfg["dt"] / f"{FINAL_SEG}.json").read_text(encoding="utf-8"))["subset"]["semua"]["per_gambar"]
    bagus, buruk = eb.pilih(per)
    out = cfg["rt"] / f"{FINAL_SEG}_kontak_16.jpg"
    assert not out.exists(), out
    eb.buat_sheet(FINAL_SEG, "segment", names_s, imgs_s, lab_s, ps, per, bagus + buruk, 4, 240, 427, out, "")
    print(out)
    (cfg["rt"] / "kontak_pilihan.json").write_text(json.dumps(dict(seg=dict(bagus=bagus, terburuk=buruk)), indent=1), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aksi", choices=["jalan", "tabel", "sheet"], default="jalan")
    ap.add_argument("--data", choices=["val", "test"], default=None)
    a = ap.parse_args()
    if a.aksi == "sheet":
        aksi_sheet()
    elif a.data is None:
        sys.exit("--data val atau --data test wajib")
    elif a.aksi == "tabel":
        tabel(a.data)
    else:
        aksi_jalan(a.data)
