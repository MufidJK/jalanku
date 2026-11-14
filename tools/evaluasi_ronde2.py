"""evaluasi_ronde2.py - evaluasi ronde 2 pada VAL v2 kampus (54 frame). TIDAK PERNAH test (prompt ronde 2, section 8).

Memakai ulang fungsi tools/evaluasi_baseline.py (jalankan_val, prediksi_semua, analisis, buat_sheet, ukur_kecepatan),
jadi jalur kodenya sama dengan runs/baseline/eval-v2/v2. evaluasi_baseline.py tidak diubah. Satu-satunya beda: imgsz
untuk model 960 (fungsi baseline menulis imgsz=640 secara harfiah, di sini Model.val / Model.predict dibungkus supaya
imgsz diganti per model). Ukuran objek untuk "recall per ukuran" tetap dihitung pada skala 640 untuk semua model.

Model yang dievaluasi (semua pada val v2 yang sama; val v2bersih/v3 byte-identik dengan v2):
  baseline-kotak      models/baseline/kotak-gabung_best.pt         640  data/dataset-gabung-kotak-v2
  r2-kotak-v2bersih   models/ronde2/r2-kotak-v2bersih_best.pt      640
  r2-kotak-v3         models/ronde2/r2-kotak-v3_best.pt            640
  r2-kotak-v3-960     models/ronde2/r2-kotak-v3-960_best.pt        960
  baseline-seg        models/baseline/seg-kampus_best.pt           640  data/dataset-gabung-seg-v2
  r2-seg-v3           models/ronde2/r2-seg-v3_best.pt              640

Keluaran runs/ronde2/eval/ (tidak menimpa): <model>/metrik.json, galat.json, kontak_*.jpg; <model>-val/ (plot conf 0.001);
<model>-val-conf025/ (confusion matrix conf 0.25); kecepatan.json; banding.json + tabel.md.

  python tools/evaluasi_ronde2.py --aksi val                    # metrik + galat + kontak + cm025, model yang belum ada
  python tools/evaluasi_ronde2.py --aksi kecepatan              # GPU dan CPU (1 thread, semua core fisik), saat idle
  python tools/evaluasi_ronde2.py --aksi tabel
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import evaluasi_baseline as eb  # noqa: E402

ROOT = eb.ROOT
OUT = ROOT / "runs" / "ronde2" / "eval"
YK = ROOT / "data/dataset-gabung-kotak-v2/data.yaml"
YS = ROOT / "data/dataset-gabung-seg-v2/data.yaml"
TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
LOKASI_VAL = ("dapsut", "perpus-lt9-ubm-tower", "tangga-naik-lt9-lt10-ubm-tower")
MODEL = {
    "baseline-kotak": ("detect", YK, "models/baseline/kotak-gabung_best.pt", 640),
    "r2-kotak-v2bersih": ("detect", YK, "models/ronde2/r2-kotak-v2bersih_best.pt", 640),
    "r2-kotak-v3": ("detect", YK, "models/ronde2/r2-kotak-v3_best.pt", 640),
    "r2-kotak-v3-960": ("detect", YK, "models/ronde2/r2-kotak-v3-960_best.pt", 960),
    "baseline-seg": ("segment", YS, "models/baseline/seg-kampus_best.pt", 640),
    "r2-seg-v3": ("segment", YS, "models/ronde2/r2-seg-v3_best.pt", 640),
}
IMGSZ = {"nilai": 640}


def pasang_imgsz():
    """Bungkus Model.val / Model.predict: imgsz=640 harfiah di evaluasi_baseline diganti IMGSZ['nilai']."""
    from ultralytics.engine.model import Model

    if getattr(Model, "_r2_dibungkus", False):
        return
    val_asli, pred_asli = Model.val, Model.predict

    def val(self, *a, **k):
        k["imgsz"] = IMGSZ["nilai"]
        return val_asli(self, *a, **k)

    def predict(self, *a, **k):
        k["imgsz"] = IMGSZ["nilai"]
        return pred_asli(self, *a, **k)

    Model.val, Model.predict, Model._r2_dibungkus = val, predict, True


def cek_val(yaml_path):
    names, imgs, lab_dir = eb.info_val(yaml_path)
    assert len(imgs) == 54, len(imgs)
    for p in imgs:
        lok = p.stem.split("_20")[0]
        assert lok in LOKASI_VAL and not lok.startswith(TEST), f"bukan frame val: {p.name}"
    return names, imgs, lab_dir


def aksi_val(daftar):
    from ultralytics import YOLO

    pasang_imgsz()
    for nama in daftar:
        tugas, yp, bobot, imgsz = MODEL[nama]
        bobot = ROOT / bobot
        if (OUT / nama / "metrik.json").exists():
            print(f"-- {nama}: sudah ada, dilewati")
            continue
        if not bobot.exists():
            print(f"-- {nama}: bobot belum ada ({bobot}), dilewati")
            continue
        for sub in (nama, f"{nama}-val", f"{nama}-val-conf025"):
            if (OUT / sub).exists():
                sys.exit(f"{OUT / sub} sudah ada tapi metrik.json tidak lengkap. Tidak ditimpa; periksa dulu.")
        names, imgs, lab_dir = cek_val(yp)
        IMGSZ["nilai"] = imgsz
        eb.RUNS[nama] = (tugas, yp)
        print(f"== val {nama} imgsz {imgsz}", flush=True)
        h = eb.jalankan_val(nama, bobot, OUT)
        h["imgsz"] = imgsz
        h["data"] = eb.rel(yp)
        print(f"== galat + kontak {nama}", flush=True)
        pred = eb.prediksi_semua(YOLO(str(bobot)), imgs)
        rekap, per = eb.analisis(nama, names, imgs, lab_dir, tugas, pred)
        rekap["per_gambar"] = per
        print(f"== confusion matrix conf {eb.CONF} {nama}", flush=True)
        YOLO(str(bobot)).val(data=str(yp), split="val", imgsz=imgsz, batch=16, workers=2, device=0, plots=True, seed=0,
                             conf=eb.CONF, project=str(OUT), name=f"{nama}-val-conf025", exist_ok=False, verbose=False)
        (OUT / nama).mkdir(exist_ok=True)
        (OUT / nama / "galat.json").write_text(json.dumps(rekap, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
        bagus, buruk = eb.pilih(per)
        eb.buat_sheet(nama, tugas, names, imgs, lab_dir, pred, per, bagus + buruk, 4, 240, 427, OUT / nama / "kontak_16.jpg", "")
        eb.buat_sheet(nama, tugas, names, imgs, lab_dir, pred, per, buruk, 2, 380, 676, OUT / nama / "kontak_terburuk.jpg", "terburuk")
        (OUT / nama / "kontak_pilihan.json").write_text(json.dumps(dict(bagus=bagus, terburuk=buruk), indent=2), encoding="utf-8")
        # metrik.json ditulis TERAKHIR: adanya berkas ini = model ini selesai dievaluasi
        (OUT / nama / "metrik.json").write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")
        b = h["box"]
        print(f"   {nama}: box mAP50 {b['mAP50']:.4f} mAP50-95 {b['mAP50_95']:.4f} P {b['P']:.3f} R {b['R']:.3f} F1 {b['F1']:.3f}", flush=True)


def aksi_kecepatan(daftar):
    import os

    import psutil
    import torch

    pasang_imgsz()
    kf = OUT / "kecepatan.json"
    sp = json.loads(kf.read_text(encoding="utf-8")) if kf.exists() else dict(
        catatan="Kecepatan LAPTOP ini, fp32, PyTorch tanpa ekspor, batch 1, imgsz = sisi panjang (640 atau 960), conf 0.25, "
                "warm-up 10, median atas 54 frame val. Bukan kecepatan HP.",
        cpu=eb.cpu_nama(), gpu=torch.cuda.get_device_name(0), omp_num_threads_env=os.environ.get("OMP_NUM_THREADS"),
        cpu_core_fisik=psutil.cpu_count(logical=False), hasil={})
    for nama in daftar:
        tugas, yp, bobot, imgsz = MODEL[nama]
        bobot = ROOT / bobot
        if nama in sp["hasil"] or not bobot.exists():
            print(f"-- {nama}: {'sudah ada' if nama in sp['hasil'] else 'bobot belum ada'}, dilewati")
            continue
        _, imgs, _ = cek_val(yp)
        IMGSZ["nilai"] = imgsz
        d = dict(imgsz=imgsz)
        print(f"== kecepatan {nama} GPU", flush=True)
        d["GPU"] = eb.ukur_kecepatan(bobot, imgs, 0)
        for th in sorted({1, psutil.cpu_count(logical=False)}):
            print(f"== kecepatan {nama} CPU {th} thread", flush=True)
            d[f"CPU ({th} thread)"] = eb.ukur_kecepatan(bobot, imgs, "cpu", threads=th)
        sp["hasil"][nama] = d
        kf.write_text(json.dumps(sp, indent=2, ensure_ascii=False), encoding="utf-8")


def f3(x):
    return "-" if x is None else f"{x:.3f}"


def aksi_tabel():
    hs = {n: json.loads((OUT / n / "metrik.json").read_text(encoding="utf-8")) for n in MODEL if (OUT / n / "metrik.json").exists()}
    gs = {n: json.loads((OUT / n / "galat.json").read_text(encoding="utf-8")) for n in hs}
    md = []
    banding = {}
    for tugas, jenis, acuan in (("detect", "box", "baseline-kotak"), ("segment", "mask", "baseline-seg")):
        ms = [n for n in hs if MODEL[n][0] == tugas]
        if not ms:
            continue
        md += [f"## {'Kotak' if tugas == 'detect' else 'Segmentasi (mask)'}: val v2, 54 frame", "",
               "| Model | imgsz | mAP50 | mAP50-95 | P | R | F1 | conf F1 terbaik | d mAP50 | d mAP50-95 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for n in ms:
            d = hs[n][jenis]
            a = hs[acuan][jenis] if acuan in hs else None
            banding[n] = {k: d[k] for k in ("mAP50", "mAP50_95", "P", "R", "F1", "conf_F1_terbaik")}
            md.append(f"| {n} | {MODEL[n][3]} | {f3(d['mAP50'])} | {f3(d['mAP50_95'])} | {f3(d['P'])} | {f3(d['R'])} | {f3(d['F1'])} | "
                      f"{f3(d['conf_F1_terbaik'])} | " + (f"{d['mAP50'] - a['mAP50']:+.3f} | {d['mAP50_95'] - a['mAP50_95']:+.3f} |" if a and n != acuan else "- | - |"))
        for metrik in ("mAP50", "P", "R"):
            md += ["", f"Per kelas, {metrik} ({jenis}):", "", "| Kelas | n val | " + " | ".join(ms) + " |", "|---|---|" + "---|" * len(ms)]
            for c in hs[ms[0]][jenis]["kelas"]:
                sel = []
                for n in ms:
                    x = next((k for k in hs[n][jenis]["kelas"] if k["nama"] == c["nama"]), None)
                    sel.append(f3(x[metrik]) if x else "-")
                md.append(f"| {c['nama']}{' *' if c['rendah'] else ''} | {c['n_instance']} | " + " | ".join(sel) + " |")
        md += ["", f"\\* n < {eb.LOW_N}: angka kurang bisa dipercaya.", ""]
        if tugas == "detect":
            md += [f"Galat conf >= {eb.CONF}, IoU >= {eb.IOU} (TP / FP / FN):", "", "| Kelas | " + " | ".join(ms) + " |", "|---|" + "---|" * len(ms)]
            for k in gs[ms[0]]["per_kelas"]:
                md.append(f"| {k} | " + " | ".join("{tp} / {fp} / {fn}".format(**gs[n]["per_kelas"][k]) for n in ms) + " |")
            tot = {n: [sum(v[x] for v in gs[n]["per_kelas"].values()) for x in ("tp", "fp", "fn")] for n in ms}
            md.append("| **semua** | " + " | ".join(f"{t[0]} / {t[1]} / {t[2]}" for t in tot.values()) + " |")
            md += ["", "Recall per ukuran objek (akar luas kotak, px pada skala 640), ditemukan / GT (recall):", "",
                   "| Ukuran | " + " | ".join(ms) + " |", "|---|" + "---|" * len(ms)]
            for b in gs[ms[0]]["recall_per_ukuran_px640"]:
                md.append(f"| {b} | " + " | ".join("{ditemukan} / {gt} ({r})".format(r=f3(gs[n]["recall_per_ukuran_px640"][b]["recall"]),
                                                                                   **gs[n]["recall_per_ukuran_px640"][b]) for n in ms) + " |")
            for n in ms:
                banding[n]["galat_conf025"] = dict(zip(("tp", "fp", "fn"), tot[n]))
                banding[n]["recall_kecil_lt32"] = gs[n]["recall_per_ukuran_px640"]["<32"]
        else:
            md += [f"IoU piksel agregat, conf >= {eb.CONF}:", "", "| Kelas | " + " | ".join(ms) + " |", "|---|" + "---|" * len(ms)]
            for k in gs[ms[0]]["iou_piksel_per_kelas"]:
                md.append(f"| {k} | " + " | ".join(f3(gs[n]["iou_piksel_per_kelas"][k]) for n in ms) + " |")
            for n in ms:
                banding[n]["iou_piksel"] = gs[n]["iou_piksel_per_kelas"]
        md.append("")
    kf = OUT / "kecepatan.json"
    if kf.exists():
        sp = json.loads(kf.read_text(encoding="utf-8"))
        md += ["## Kecepatan", "", sp["catatan"], f"CPU: {sp['cpu']} ({sp['cpu_core_fisik']} core fisik); GPU: {sp['gpu']}", "",
               "| Model | imgsz | Perangkat | Preprocess (ms) | Inference (ms) | Postprocess (ms) | Total (ms) | FPS | p95 total (ms) |", "|---|---|---|---|---|---|---|---|---|"]
        for n, d in sp["hasil"].items():
            for dev, v in d.items():
                if dev == "imgsz":
                    continue
                md.append(f"| {n} | {d['imgsz']} | {dev} | {v['preprocess_ms']:.1f} | {v['inference_ms']:.1f} | {v['postprocess_ms']:.1f} | "
                          f"{v['total_ms']:.1f} | {v['fps']:.1f} | {v['total_ms_p95']:.1f} |")
        md.append("")
    (OUT / "banding.json").write_text(json.dumps(banding, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "tabel.md").write_text("\n".join(md), encoding="utf-8")
    print(f"tabel: {OUT / 'tabel.md'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aksi", choices=["val", "kecepatan", "tabel"], required=True)
    ap.add_argument("--model", choices=list(MODEL), action="append", help="default: semua yang bobotnya ada")
    args = ap.parse_args()
    for _, yp, _, _ in MODEL.values():
        assert not any(t in str(yp) for t in TEST) and "test" not in str(yp).lower(), yp
    OUT.mkdir(parents=True, exist_ok=True)
    daftar = args.model or list(MODEL)
    if args.aksi == "val":
        aksi_val(daftar)
        aksi_tabel()
    elif args.aksi == "kecepatan":
        aksi_kecepatan(daftar)
        aksi_tabel()
    else:
        aksi_tabel()


if __name__ == "__main__":
    main()
