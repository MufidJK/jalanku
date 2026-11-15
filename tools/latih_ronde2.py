"""latih_ronde2.py - training ronde 2 JalanKu (prompt ronde 2, section 7). Memakai ulang tools/latih_baseline.py.

Pengaturan sama dengan baseline (yolo26n / yolo26n-seg pretrained COCO, seed 0, deterministic, augmentasi default,
optimizer auto, best checkpoint pada val), kecuali yang ditulis di RUNS. latih_baseline.py TIDAK diubah: modul itu
diimpor dan konstanta modulnya (PROJECT, SMOKE, RUNS, BATCH, imgsz) diganti per run sebelum main() dipanggil.

Run (urutan prompt; r2-kotak-v2 diganti r2-kotak-v2bersih, keputusan Jeka A3 14 Nov 2026):
  r2-kotak-v2bersih  gabung-kotak-v2bersih  imgsz 640  100 / 30   efek koreksi label + buang frame bocor saja
  r2-kotak-v3        gabung-kotak-v3        imgsz 640  100 / 30   run utama
  r2-kotak-v3-960    gabung-kotak-v3        imgsz 960  100 / 30   batch dari smoke test (BATCH_960)
  r2-seg-v3          gabung-seg-v3          imgsz 640  300 / 100

Keluaran: runs/ronde2/<run>/ (train.log, meta.json, weights/), smoke: runs/ronde2/_smoke/. Setelah run selesai
best.pt disalin ke models/ronde2/<run>_best.pt. Lanjut setelah terputus: --resume (sama dengan baseline).

  python tools/latih_ronde2.py --run r2-kotak-v3 --smoke --batch 16
  python tools/latih_ronde2.py --run r2-kotak-v3
  python tools/latih_ronde2.py --run r2-kotak-v3 --resume
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import latih_baseline as lb  # noqa: E402

ROOT = lb.ROOT
BATCH_640 = 16
BATCH_960 = 16  # diisi dari smoke test (CHECKPOINT R2)
BATCH_1280 = 8  # smoke ronde 4: b8 138 s/epoch VRAM 5,85 GiB; b10 140 s 7,24 GiB (mepet); b12 946 s 8,71 GiB (meluber)
BATCH_960_S = 6  # yolo26s pada 960, dari smoke test ronde 3: b6 130 s/epoch VRAM 4,65 GiB; b8 266 s/epoch VRAM 6,10 GiB (meluber)

RUNS = {
    "r2-kotak-v2bersih": dict(model="yolo26n.pt", data="data/dataset-gabung-kotak-v2bersih/data.yaml", epochs=100,
                              patience=30, imgsz=640, batch=BATCH_640),
    "r2-kotak-v3": dict(model="yolo26n.pt", data="data/dataset-gabung-kotak-v3/data.yaml", epochs=100, patience=30,
                        imgsz=640, batch=BATCH_640),
    "r2-kotak-v3-960": dict(model="yolo26n.pt", data="data/dataset-gabung-kotak-v3/data.yaml", epochs=100, patience=30,
                            imgsz=960, batch=BATCH_960),
    # ronde 3 (14 Nov 2026): model s, data dan setelan sama dengan r2-kotak-v3-960; batch dari smoke test
    "r3-kotak-v3-960-s": dict(model="yolo26s.pt", data="data/dataset-gabung-kotak-v3/data.yaml", epochs=100, patience=30,
                              imgsz=960, batch=BATCH_960_S),
    # ronde 4 (14 Nov 2026), eksperimen tanpa label baru: setelan sama dengan r2-kotak-v3-960 kecuali yang tertulis
    "r4-kotak-v3-1280": dict(model="yolo26n.pt", data="data/dataset-gabung-kotak-v3/data.yaml", epochs=100, patience=30,
                             imgsz=1280, batch=BATCH_1280),
    "r4-kotak-v3-960-seed1": dict(model="yolo26n.pt", data="data/dataset-gabung-kotak-v3/data.yaml", epochs=100, patience=30,
                                  imgsz=960, batch=BATCH_960, seed=1),
    # ronde 4, training pada dataset v4 (prompt ronde 4 section 7; r4-kotak-v4-1280 hanya kalau aturan imgsz section 8 lolos)
    "r4-kotak-v4-960": dict(model="yolo26n.pt", data="data/dataset-gabung-kotak-v4/data.yaml", epochs=100, patience=30,
                            imgsz=960, batch=BATCH_960),
    "r4-kotak-v4-1280": dict(model="yolo26n.pt", data="data/dataset-gabung-kotak-v4/data.yaml", epochs=100, patience=30,
                             imgsz=1280, batch=BATCH_1280),
    "r4-seg-v4": dict(model="yolo26n-seg.pt", data="data/dataset-gabung-seg-v4/data.yaml", epochs=300, patience=100,
                      imgsz=640, batch=BATCH_640),
    "r2-seg-v3": dict(model="yolo26n-seg.pt", data="data/dataset-gabung-seg-v3/data.yaml", epochs=300, patience=100,
                      imgsz=640, batch=BATCH_640),
}


def main():
    if "--run" not in sys.argv:
        sys.exit(f"Butuh --run ({' | '.join(RUNS)}) atau pakai latih_baseline.py --env.")
    run = sys.argv[sys.argv.index("--run") + 1]
    if run not in RUNS:
        sys.exit(f"run tidak dikenal: {run}")
    cfg = RUNS[run]
    lb.PROJECT = ROOT / "runs" / "ronde2"
    lb.SMOKE = lb.PROJECT / "_smoke"
    lb.FIXED = dict(lb.FIXED, imgsz=cfg["imgsz"], seed=cfg.get("seed", 0))  # seed per run, default tetap 0
    lb.BATCH = cfg["batch"]
    lb.RUNS = {k: {kk: v[kk] for kk in ("model", "data", "epochs", "patience")} for k, v in RUNS.items()}
    try:
        lb.main()
    finally:
        if "--smoke" not in sys.argv:
            rd = lb.PROJECT / run
            mp = rd / "meta.json"
            best = rd / "weights" / "best.pt"
            if mp.exists() and json.loads(mp.read_text(encoding="utf-8")).get("status") == "selesai" and best.exists():
                dst = ROOT / "models" / "ronde2" / f"{run}_best.pt"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(best, dst)
                print(f"best.pt disalin ke {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
