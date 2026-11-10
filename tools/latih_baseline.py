"""latih_baseline.py - latih baseline JalanKu (kotak + segmentasi) dengan pengaturan tetap per run.

Dijalankan dari root repo. Satu perintah = satu run yang bisa diulang persis.

Run (pengaturan tetap di RUNS di bawah):
  kotak-gabung  yolo26n.pt      data/dataset-gabung-kotak/data.yaml   100 epoch, patience 30
  kotak-kampus  yolo26n.pt      data/dataset-kampus-kotak/data.yaml   300 epoch, patience 100  (ablasi: hanya data kampus)
  seg-kampus    yolo26n-seg.pt  data/dataset-gabung-seg/data.yaml     300 epoch, patience 100  (isinya kampus saja)

Pengaturan yang sama untuk semua run: seed=0, deterministic=True, imgsz=640, augmentasi dan hyperparameter
default Ultralytics (ini baseline; tuning nanti). batch, workers, cache ditetapkan sekali di konstanta
BATCH / WORKERS / CACHE di bawah (hasil smoke test, Checkpoint T0) dan tidak bisa diganti dari CLI
kecuali dengan --smoke, supaya run akhir tidak bisa beda diam-diam.

Keluaran: runs/baseline/<run>/ (weights/best.pt, last.pt, results.csv, plot, train.log, meta.json).
Smoke test: runs/baseline/_smoke/<run>*/ . Tidak pernah menimpa: kalau folder run sudah ada dan tidak
pakai --resume, skrip berhenti (Ultralytics sendiri akan diam-diam membuat <run>2, jadi dicek di sini).

Contoh:
  python tools/latih_baseline.py --env                                  # laporan environment (GPU, versi, RAM, disk)
  python tools/latih_baseline.py --run kotak-gabung --smoke --batch 16  # 1 epoch, cek GPU/VRAM/waktu
  python tools/latih_baseline.py --run kotak-gabung                     # run penuh
  python tools/latih_baseline.py --run kotak-gabung --resume            # lanjut dari last.pt setelah terputus
  python tools/latih_baseline.py --run seg-kampus > NUL                 # (log tetap masuk runs/baseline/seg-kampus/train.log)

Pantau: Get-Content runs\\baseline\\<run>\\train.log -Tail 20 -Wait   atau   Get-Content runs\\baseline\\<run>\\results.csv -Tail 3
"""
import argparse
import datetime as dt
import functools
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "runs" / "baseline"
SMOKE = PROJECT / "_smoke"
PRETRAINED = ROOT / "models" / "pretrained"
TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")

# --- Pengaturan tetap run akhir (diisi setelah smoke test, Checkpoint T0) ---
BATCH = 16
WORKERS = 4
CACHE = False  # False / "ram" / "disk"

# --- Pengaturan tetap semua run ---
FIXED = dict(imgsz=640, seed=0, deterministic=True, device=0, plots=True)

RUNS = {
    "kotak-gabung": dict(model="yolo26n.pt", data="data/dataset-gabung-kotak/data.yaml", epochs=100, patience=30),
    # 300/100: data kampus kecil (195 gambar) -> langkah optimizer per epoch jauh lebih sedikit; epoch dinaikkan
    # (keputusan Jeka, 10 Nov 2026) supaya ablasi tidak tercampur undertraining. Jumlah langkah dicatat di meta.json.
    "kotak-kampus": dict(model="yolo26n.pt", data="data/dataset-kampus-kotak/data.yaml", epochs=300, patience=100),
    "seg-kampus": dict(model="yolo26n-seg.pt", data="data/dataset-gabung-seg/data.yaml", epochs=300, patience=100),
}


def info_env():
    """Kumpulkan info environment untuk laporan (tanpa rahasia)."""
    import psutil
    import torch
    import ultralytics

    gpu = {}
    try:
        q = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip().split(",")
        gpu = dict(nama=q[0].strip(), vram_total_mib=int(q[1]), vram_terpakai_mib=int(q[2]), driver=q[3].strip())
    except Exception as e:  # nvidia-smi tidak ada / gagal
        gpu = dict(error=str(e))
    vm = psutil.virtual_memory()
    du = shutil.disk_usage(ROOT)
    bat = psutil.sensors_battery()
    return dict(
        python=platform.python_version(),
        os=platform.platform(),
        torch=torch.__version__,
        cuda_torch=torch.version.cuda,
        cudnn=torch.backends.cudnn.version(),
        cuda_tersedia=torch.cuda.is_available(),
        gpu_torch=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        ultralytics=ultralytics.__version__,
        gpu=gpu,
        ram_total_gb=round(vm.total / 1e9, 1),
        ram_bebas_gb=round(vm.available / 1e9, 1),
        disk_bebas_gb=round(du.free / 1e9, 1),
        baterai=None if bat is None else dict(persen=round(bat.percent), dicolok=bat.power_plugged),
        git_commit=_git_commit(),
    )


def _git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except Exception:
        return None


def hitung_gambar(data_yaml):
    """Jumlah gambar train/val dari data.yaml (hanya membaca daftar file)."""
    import yaml

    cfg = yaml.safe_load(Path(data_yaml).read_text(encoding="utf-8"))
    base = Path(cfg["path"])
    out = {}
    for k in ("train", "val"):
        d = base / cfg[k]
        out[k] = sum(1 for p in d.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}) if d.exists() else None
    return out


class _Tee:
    """Teruskan stdout/stderr ke konsol dan ke train.log (baris progress tqdm diringkas ke keadaan akhir)."""

    def __init__(self, stream):
        self.stream = stream
        self.file = None
        self.sisa = ""
        self.antri = []

    def attach(self, fobj):
        self.file = fobj
        for s in self.antri:
            self._tulis_file(s)
        self.antri = []

    def _tulis_file(self, s):
        self.sisa += s
        while "\n" in self.sisa:
            baris, self.sisa = self.sisa.split("\n", 1)
            self.file.write(baris.split("\r")[-1] + "\n")
        self.file.flush()

    def write(self, s):
        try:
            self.stream.write(s)
        except Exception:
            pass
        if self.file is not None:
            self._tulis_file(s)
        else:
            self.antri.append(s)
        return len(s)

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass

    def isatty(self):
        return False

    def __getattr__(self, name):
        return getattr(self.stream, name)


def tulis_meta(path, meta):
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def parse():
    ap = argparse.ArgumentParser(description="Latih baseline JalanKu dengan pengaturan tetap per run.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--run", choices=sorted(RUNS))
    ap.add_argument("--resume", action="store_true", help="lanjutkan run yang terputus dari last.pt")
    ap.add_argument("--env", action="store_true", help="cetak laporan environment lalu selesai")
    ap.add_argument("--smoke", action="store_true", help="1 epoch ke runs/baseline/_smoke/ untuk cek GPU/VRAM/waktu")
    ap.add_argument("--batch", type=int, help="hanya dengan --smoke (boleh -1 = auto)")
    ap.add_argument("--workers", type=int, help="hanya dengan --smoke")
    ap.add_argument("--cache", choices=["false", "ram", "disk"], help="hanya dengan --smoke")
    ap.add_argument("--fraction", type=float, default=1.0, help="hanya dengan --smoke: porsi data latih")
    ap.add_argument("--epochs", type=int, help="hanya dengan --smoke: jumlah epoch (default 1)")
    ap.add_argument("--izinkan-baterai", action="store_true", help="jangan berhenti walau laptop tidak dicolok")
    return ap.parse_args()


def main():
    args = parse()
    if args.env:
        print(json.dumps(info_env(), indent=2, ensure_ascii=False))
        return
    if not args.run:
        sys.exit("Butuh --run (kotak-gabung | kotak-kampus | seg-kampus) atau --env.")
    if not args.smoke and (args.batch is not None or args.workers is not None or args.cache or args.fraction != 1.0
                           or args.epochs is not None):
        sys.exit("--batch/--workers/--cache/--fraction/--epochs hanya untuk --smoke. Run akhir memakai BATCH/WORKERS/CACHE di skrip.")
    if args.smoke and args.resume:
        sys.exit("--smoke dan --resume tidak bisa digabung.")

    cfg = RUNS[args.run]
    data = ROOT / cfg["data"]
    if any(t in str(data) for t in TEST):
        sys.exit("Data mengandung lokasi test. Ditolak.")
    if not data.exists():
        sys.exit(f"data.yaml tidak ada: {data}")
    pretrained = PRETRAINED / cfg["model"]
    if not pretrained.exists():
        sys.exit(f"Bobot pretrained tidak ada: {pretrained}")

    import torch

    if not torch.cuda.is_available():
        sys.exit("CUDA tidak tersedia di torch. Berhenti (training di CPU tidak dimaksudkan).")
    env = info_env()
    if env["baterai"] and not env["baterai"]["dicolok"] and not args.izinkan_baterai:
        sys.exit("Laptop tidak dicolok ke listrik. Colok dulu (atau --izinkan-baterai).")

    proj = SMOKE if args.smoke else PROJECT
    if args.smoke:  # nama memuat pengaturan yang dicoba, mis. kotak-gabung-b16-w4
        nama = (f"{args.run}-b{args.batch if args.batch is not None else BATCH}"
                f"-w{args.workers if args.workers is not None else WORKERS}-e{args.epochs or 1}")
    else:
        nama = args.run
    run_dir = proj / nama
    if args.resume:
        last = run_dir / "weights" / "last.pt"
        if not last.exists():
            sys.exit(f"Tidak ada yang bisa dilanjutkan: {last}")
    elif run_dir.exists():
        sys.exit(f"{run_dir} sudah ada. Tidak ditimpa. (Lanjutkan dengan --resume, atau pindahkan folder itu sendiri.)")

    if args.smoke:
        batch = args.batch if args.batch is not None else BATCH
        workers = args.workers if args.workers is not None else WORKERS
        cache = {"false": False, "ram": "ram", "disk": "disk", None: CACHE}[args.cache]
        epochs, patience, fraction = args.epochs or 1, 100, args.fraction
    else:
        batch, workers, cache = BATCH, WORKERS, CACHE
        epochs, patience, fraction = cfg["epochs"], cfg["patience"], 1.0

    train_kw = dict(data=str(data), epochs=epochs, patience=patience, batch=batch, workers=workers, cache=cache,
                    fraction=fraction, project=str(proj), name=nama, exist_ok=False, **FIXED)

    from ultralytics import YOLO
    from ultralytics.utils import LOGGER

    tee_out, tee_err = _Tee(sys.stdout), _Tee(sys.stderr)
    sys.stdout, sys.stderr = tee_out, tee_err

    state = dict(meta_path=None, meta=None, t_seg=None, t_epoch=None, peak_alloc=0, peak_reserved=0, epoch_sec=[],
                 file_handler=None, steps=0, batches=0)

    def on_pretrain_start(tr):
        sd = Path(tr.save_dir)
        f = open(sd / "train.log", "a", encoding="utf-8")
        tee_out.attach(f)
        tee_err.attach(f)
        state["file_handler"] = logging.FileHandler(sd / "train.log", encoding="utf-8")
        LOGGER.addHandler(state["file_handler"])
        mp = sd / "meta.json"
        meta = json.loads(mp.read_text(encoding="utf-8")) if (args.resume and mp.exists()) else dict(
            run=args.run, smoke=args.smoke, perintah=" ".join([Path(sys.executable).name] + sys.argv),
            pengaturan=train_kw, model_awal=str(pretrained.relative_to(ROOT)), jumlah_gambar=hitung_gambar(data),
            environment=env, segmen=[])
        meta["segmen"].append(dict(mulai=dt.datetime.now().isoformat(timespec="seconds"), selesai=None,
                                   resume=args.resume, detik=None, perintah=" ".join(sys.argv),
                                   ram_bebas_gb_awal=env["ram_bebas_gb"]))
        meta["status"] = "berjalan"
        state.update(meta_path=mp, meta=meta, t_seg=time.time())
        tulis_meta(mp, meta)

    def on_train_start(tr):
        # hitung langkah optimizer yang benar-benar terjadi (langkah yang dilewati GradScaler karena inf tidak terhitung)
        asli = tr.optimizer.step

        @functools.wraps(asli)  # pertahankan atribut yang dipakai lr_scheduler
        def terhitung(*a, **k):
            state["steps"] += 1
            return asli(*a, **k)

        tr.optimizer.step = terhitung

    def on_batch_end(tr):
        state["batches"] += 1

    def on_epoch_start(tr):
        state["t_epoch"] = time.time()
        torch.cuda.reset_peak_memory_stats(0)

    def on_fit_epoch_end(tr):
        if state["t_epoch"] is None:  # panggilan dari validasi akhir best.pt, bukan epoch latih
            return
        dur = time.time() - state["t_epoch"]
        state["t_epoch"] = None
        state["epoch_sec"].append(round(dur, 1))
        state["peak_alloc"] = max(state["peak_alloc"], torch.cuda.max_memory_allocated(0))
        state["peak_reserved"] = max(state["peak_reserved"], torch.cuda.max_memory_reserved(0))
        m = {k: round(float(v), 4) for k, v in tr.metrics.items() if "mAP" in k}
        LOGGER.info(f"[baseline] {args.run} epoch {tr.epoch + 1}/{tr.epochs} {dur:.0f}s "
                    f"vram_puncak={state['peak_reserved'] / 2**30:.2f}GiB {m}")

    def simpan_akhir(status, tr=None):
        meta, mp = state["meta"], state["meta_path"]
        if meta is None:
            return
        seg = meta["segmen"][-1]
        seg["selesai"] = dt.datetime.now().isoformat(timespec="seconds")
        seg["detik"] = round(time.time() - state["t_seg"], 1)
        seg["detik_per_epoch"] = state["epoch_sec"]
        seg["langkah_optimizer"] = state["steps"]
        seg["batch_diproses"] = state["batches"]
        meta["status"] = status
        meta["total_detik_latih"] = round(sum(s["detik"] or 0 for s in meta["segmen"]), 1)
        # total langkah optimizer = jumlah semua segmen (kalau di-resume, epoch yang terulang dari last.pt ikut terhitung)
        meta["total_langkah_optimizer"] = sum(s.get("langkah_optimizer") or 0 for s in meta["segmen"])
        meta["total_batch_diproses"] = sum(s.get("batch_diproses") or 0 for s in meta["segmen"])
        meta["vram_puncak_gib"] = dict(
            allocated=round(max(state["peak_alloc"], meta.get("vram_puncak_gib", {}).get("allocated", 0) * 2**30) / 2**30, 2),
            reserved=round(max(state["peak_reserved"], meta.get("vram_puncak_gib", {}).get("reserved", 0) * 2**30) / 2**30, 2))
        if tr is not None:
            meta["optimizer"] = type(tr.optimizer).__name__
            meta["batch_efektif"] = dict(batch=tr.batch_size, nbs=tr.args.nbs, accumulate=tr.accumulate)
            meta["epoch_terakhir"] = tr.epoch + 1
            meta["best_pt"] = str(Path(tr.best).relative_to(ROOT)) if Path(tr.best).exists() else None
            meta["last_pt"] = str(Path(tr.last).relative_to(ROOT)) if Path(tr.last).exists() else None
            meta["metrik_terakhir"] = {k: round(float(v), 5) for k, v in tr.metrics.items()}
        meta["versi"] = dict(python=env["python"], torch=env["torch"], cuda=env["cuda_torch"],
                             ultralytics=env["ultralytics"], gpu=env["gpu"].get("nama"), driver=env["gpu"].get("driver"))
        tulis_meta(mp, meta)

    holder = {}

    def on_train_end(tr):
        holder["tr"] = tr

    model = YOLO(str(run_dir / "weights" / "last.pt") if args.resume else str(pretrained))
    model.add_callback("on_pretrain_routine_start", on_pretrain_start)
    model.add_callback("on_train_start", on_train_start)
    model.add_callback("on_train_batch_end", on_batch_end)
    model.add_callback("on_train_epoch_start", on_epoch_start)
    model.add_callback("on_fit_epoch_end", on_fit_epoch_end)
    model.add_callback("on_train_end", on_train_end)

    status = "gagal"
    try:
        if args.resume:
            model.train(resume=True)
        else:
            model.train(**train_kw)
        status = "selesai"
    except KeyboardInterrupt:
        status = "terhenti (Ctrl+C), lanjutkan dengan --resume"
        raise
    finally:
        simpan_akhir(status, holder.get("tr") or getattr(model, "trainer", None))
        if state["file_handler"]:
            LOGGER.removeHandler(state["file_handler"])
            state["file_handler"].close()


if __name__ == "__main__":  # wajib di Windows: dataloader workers memakai spawn
    main()
