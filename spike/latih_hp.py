"""latih_hp.py - Tahap 5b: latih ulang box + seg pada imgsz HP (320 dan 416). Prompt: data/prompt-model-hp-5b.md.

Sama persis dengan tools/latih_ronde2.py (r2-kotak-v3 / r2-seg-v3), hanya imgsz yang berbeda: modul tools/latih_baseline.py
diimpor, konstanta modulnya diganti per run, lalu main() dipanggil. Tidak ada yang di tools/ diubah.
Data, epoch, patience, batch, seed 0, deterministic, augmentasi default, optimizer auto, best checkpoint pada val: sama.

Run:
  hp-kotak-v3-320   yolo26n.pt      gabung-kotak-v3  imgsz 320  100 / 30  batch 16
  hp-kotak-v3-416   yolo26n.pt      gabung-kotak-v3  imgsz 416  100 / 30  batch 16
  hp-seg-v3-320     yolo26n-seg.pt  gabung-seg-v3    imgsz 320  300 / 100 batch 16
  hp-seg-v3-416     yolo26n-seg.pt  gabung-seg-v3    imgsz 416  300 / 100 batch 16

Keluaran: runs/hp/<run>/ (train.log, meta.json, weights/); smoke: runs/hp/_smoke/. Setelah selesai best.pt disalin ke
models/hp/<run>_best.pt (tidak menimpa) dan meta.json diberi epoch terbaik. Lanjut setelah terputus: --resume.
Folder run yang sudah ada tidak ditimpa (dicek di latih_baseline). Laptop harus dicolok (dicek di latih_baseline).

  venv\\Scripts\\python spike\\latih_hp.py --run hp-kotak-v3-320 --smoke
  venv\\Scripts\\python spike\\latih_hp.py --run hp-kotak-v3-320
  venv\\Scripts\\python spike\\latih_hp.py --run hp-kotak-v3-320 --resume
  venv\\Scripts\\python spike\\latih_hp.py --semua           # 4 run berurutan (tiap run proses sendiri)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import latih_baseline as lb  # noqa: E402

BATCH = 16  # sama dengan r2-kotak-v3 / r2-seg-v3
KOTAK, SEG = "data/dataset-gabung-kotak-v3/data.yaml", "data/dataset-gabung-seg-v3/data.yaml"

RUNS = {
    "hp-kotak-v3-320": dict(model="yolo26n.pt", data=KOTAK, epochs=100, patience=30, imgsz=320, batch=BATCH),
    "hp-kotak-v3-416": dict(model="yolo26n.pt", data=KOTAK, epochs=100, patience=30, imgsz=416, batch=BATCH),
    # Tahap 5c (data/prompt-distilasi.md): sama dengan hp-kotak-v3-416, data = gabung-kotak-v3 + pseudo-label teacher C2
    "hp-kotak-v3-416-distil": dict(model="yolo26n.pt", data="data/dataset-distil-kotak-v3/data.yaml", epochs=100, patience=30,
                                   imgsz=416, batch=BATCH),
    # Tahap 5c ronde 2: sama, pseudo-label dengan ambang per kelas = conf_kelas aplikasi (data/dataset-distil-kotak-v3-r2)
    "hp-kotak-v3-416-distil-r2": dict(model="yolo26n.pt", data="data/dataset-distil-kotak-v3-r2/data.yaml", epochs=100, patience=30,
                                      imgsz=416, batch=BATCH),
    # Tahap 5c ronde 3 (data/prompt-distilasi.md, putaran 3): self-training dua tahap, seed 0 dan 1. Aturan dikunci sebelum hasil.
    #   t1: init dari hp-kotak-v3-416_best.pt, latih di dataset r2 (manusia + pseudo per kelas), TEPAT 30 epoch, patience 0 (mati).
    #   t2: init dari last.pt t1, latih di data manusia saja (gabung-kotak-v3), TEPAT 15 epoch, lr0 0.001, warmup 0, patience 0.
    #   Yang dievaluasi hanya last.pt tahap 2 (tidak ada pemilihan epoch/best.pt berdasarkan val).
    #   t2 memakai optimizer AdamW eksplisit: dengan optimizer=auto, Ultralytics mengabaikan lr0 (memilih lr sendiri 0.000833).
    "hp-kotak-v3-416-distil-r3-s0-t1": dict(model=str(ROOT / "models/hp/hp-kotak-v3-416_best.pt"),
                                              data="data/dataset-distil-kotak-v3-r2/data.yaml", epochs=30, patience=0, imgsz=416,
                                              batch=BATCH, seed=0, simpan="last"),
    "hp-kotak-v3-416-distil-r3-s0-t2": dict(model=str(ROOT / "runs/hp/hp-kotak-v3-416-distil-r3-s0-t1/weights/last.pt"),
                                              data=KOTAK, epochs=15, patience=0, imgsz=416, batch=BATCH, seed=0, simpan="last",
                                              extra=dict(optimizer="AdamW", lr0=0.001, momentum=0.9, warmup_epochs=0)),
    "hp-kotak-v3-416-distil-r3-s1-t1": dict(model=str(ROOT / "models/hp/hp-kotak-v3-416_best.pt"),
                                              data="data/dataset-distil-kotak-v3-r2/data.yaml", epochs=30, patience=0, imgsz=416,
                                              batch=BATCH, seed=1, simpan="last"),
    "hp-kotak-v3-416-distil-r3-s1-t2": dict(model=str(ROOT / "runs/hp/hp-kotak-v3-416-distil-r3-s1-t1/weights/last.pt"),
                                              data=KOTAK, epochs=15, patience=0, imgsz=416, batch=BATCH, seed=1, simpan="last",
                                              extra=dict(optimizer="AdamW", lr0=0.001, momentum=0.9, warmup_epochs=0)),
    "hp-seg-v3-320": dict(model="yolo26n-seg.pt", data=SEG, epochs=300, patience=100, imgsz=320, batch=BATCH),
    "hp-seg-v3-416": dict(model="yolo26n-seg.pt", data=SEG, epochs=300, patience=100, imgsz=416, batch=BATCH),
}
ORDE = ["hp-kotak-v3-320", "hp-kotak-v3-416", "hp-seg-v3-320", "hp-seg-v3-416"]
SMOKE_FRAKSI = {"kotak": 0.15, "seg": 1.0}  # seg hanya 249 gambar latih, jadi satu epoch penuh


def tambah_meta_hp(run, rd):
    """Isi meta.json: imgsz, epoch terbaik (dari checkpoint best.pt), ringkasan waktu dan VRAM."""
    mp = rd / "meta.json"
    meta = json.loads(mp.read_text(encoding="utf-8"))
    best = rd / "weights" / "best.pt"
    best_epoch = None
    try:  # best.pt akhir sudah di-strip (epoch -1), jadi hitung dari results.csv: fitness Ultralytics = 0.1 mAP50 + 0.9 mAP50-95
        import csv

        with open(rd / "results.csv", newline="", encoding="utf-8") as f:
            rows = [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(f)]
        def fit(r):
            return sum(0.1 * float(r[f"metrics/mAP50({t})"]) + 0.9 * float(r[f"metrics/mAP50-95({t})"])
                       for t in ("B", "M") if f"metrics/mAP50({t})" in r)
        best_epoch = int(rows[max(range(len(rows)), key=lambda i: fit(rows[i]))]["epoch"])
    except Exception as e:  # tidak fatal
        print("epoch terbaik tidak terbaca:", e)
    kunci_be = "epoch_terbaik_val_hanya_informasi" if RUNS[run].get("simpan") == "last" else "epoch_terbaik"  # ronde 3: tidak dipakai memilih
    meta["hp"] = dict(imgsz=RUNS[run]["imgsz"], **{kunci_be: best_epoch}, epoch_dijalankan=meta.get("epoch_terakhir"),
                      total_detik_latih=meta.get("total_detik_latih"), vram_puncak_gib=meta.get("vram_puncak_gib"),
                      catatan="sama dengan r2-kotak-v3 / r2-seg-v3, hanya imgsz yang beda")
    lb.tulis_meta(mp, meta)
    return best_epoch


def satu_run():
    run = sys.argv[sys.argv.index("--run") + 1] if "--run" in sys.argv else None
    if run not in RUNS:
        sys.exit(f"Butuh --run ({' | '.join(RUNS)}) atau --semua.")
    smoke = "--smoke" in sys.argv
    if smoke and "--fraction" not in sys.argv:
        sys.argv += ["--fraction", str(SMOKE_FRAKSI["seg" if "seg" in run else "kotak"])]
    if smoke and "--batch" not in sys.argv:
        sys.argv += ["--batch", str(BATCH)]
    cfg = RUNS[run]
    lb.PROJECT = ROOT / "runs" / "hp"
    lb.SMOKE = lb.PROJECT / "_smoke"
    lb.FIXED = dict(lb.FIXED, imgsz=cfg["imgsz"], seed=cfg.get("seed", 0), **cfg.get("extra", {}))
    lb.BATCH = cfg["batch"]
    lb.RUNS = {k: {kk: v[kk] for kk in ("model", "data", "epochs", "patience")} for k, v in RUNS.items()}
    simpan_last = cfg.get("simpan") == "last"  # ronde 3: bobot yang dipakai = last.pt, tidak pernah best.pt
    dst = ROOT / "models" / "hp" / (f"{run}_last.pt" if simpan_last else f"{run}_best.pt")
    if not smoke and not ("--resume" in sys.argv) and dst.exists():
        sys.exit(f"{dst} sudah ada, tidak ditimpa.")
    try:
        lb.main()
    finally:
        if not smoke:
            rd = lb.PROJECT / run
            mp = rd / "meta.json"
            best = rd / "weights" / "best.pt"
            src = rd / "weights" / ("last.pt" if simpan_last else "best.pt")
            if mp.exists() and json.loads(mp.read_text(encoding="utf-8")).get("status") == "selesai" and src.exists():
                be = tambah_meta_hp(run, rd)
                if dst.exists():
                    print(f"{dst.relative_to(ROOT)} sudah ada, tidak ditimpa")
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    print(f"{src.name}" + ("" if simpan_last else f" (epoch {be})") + f" disalin ke {dst.relative_to(ROOT)}")


def semua():
    gagal = []
    for run in ORDE:
        if (ROOT / "runs" / "hp" / run).exists():
            print(f"== {run}: folder sudah ada, dilewati (pakai --run {run} --resume kalau terputus)")
            continue
        print(f"== mulai {run}", flush=True)
        r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--run", run])
        if r.returncode != 0:
            gagal.append(run)
            print(f"== {run} GAGAL (kode {r.returncode}). Lanjut ke run berikutnya hanya kalau penyebabnya khusus run ini; "
                  "periksa train.log.", flush=True)
            break  # prompt: lapor dulu, jangan lanjut otomatis
    print("selesai. gagal:", gagal or "tidak ada")


if __name__ == "__main__":  # wajib di Windows: dataloader workers memakai spawn
    if "--semua" in sys.argv:
        semua()
    else:
        satu_run()
