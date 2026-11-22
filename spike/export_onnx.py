"""Ekspor model JalanKu ke ONNX untuk spike HP (Stage 2).

Jalankan dengan venv TERPISAH (bukan venv/ milik v1), dari root repo:
    venv-export\\Scripts\\python spike\\export_onnx.py

Baca  : models/ronde2/r2-kotak-v3_best.pt  dan  r2-seg-v3_best.pt
Tulis : models/onnx/{box,seg}_{640,416,320}.onnx   (folder ini tidak masuk Git)
Opsi  : fp32, dynamic=False, simplify=True, opset default Ultralytics (18).
Hasil : output MENTAH (bukan end-to-end), jadi NMS dikerjakan di JS.
        box: output0 [1, 4+8, N];  seg: output0 [1, 4+3+32, N] + output1 [1, 32, S/4, S/4].
File yang sudah ada TIDAK ditimpa kecuali pakai --force.
"""
import argparse
import shutil
import tempfile
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "models" / "ronde2"
MODELS = [("box", "r2-kotak-v3_best.pt"), ("seg", "r2-seg-v3_best.pt")]
SIZES = (640, 416, 320)


def ekspor_hp(a):
    """Pengaturan ekspor sama dengan 5a: opset default, dynamic=False, simplify=True, quantize=16 untuk fp16."""
    src = ROOT / "models" / "hp"
    suffix = "_fp16" if a.fp16 else ""
    with tempfile.TemporaryDirectory() as tmp:
        for short, kind in (("box", "kotak"), ("seg", "seg")):
            for sz in (320, 416):
                pt_src = src / f"hp-{kind}-v3-{sz}_best.pt"
                dst = a.out / f"hp_{short}_{sz}{suffix}.onnx"
                if dst.exists():
                    print("sudah ada, lewati:", dst)
                    continue
                if not pt_src.exists():
                    print("bobot belum ada, lewati:", pt_src)
                    continue
                pt = Path(tmp) / pt_src.name
                shutil.copy(pt_src, pt)
                kw = dict(quantize=16) if a.fp16 else dict(half=False)
                p = YOLO(str(pt)).export(format="onnx", imgsz=sz, dynamic=False, simplify=True, device="cpu", **kw)
                shutil.move(p, dst)
                print("tersimpan:", dst, f"{dst.stat().st_size / 1e6:.2f} MB")


def ekspor_distil(a):
    """Tahap 5c: hp-kotak-v3-416-distil_best.pt -> models/onnx/hp_box_416_distil[_fp16].onnx. Pengaturan sama dengan 5b. Tidak menimpa."""
    r2 = "-r2" if a.r2 else ""  # ronde 2: hp-kotak-v3-416-distil-r2_best.pt -> hp_box_416_distil_r2[_fp16].onnx
    pt_src = ROOT / "models" / "hp" / f"hp-kotak-v3-416-distil{r2}_best.pt"
    dst = a.out / f"hp_box_416_distil{r2.replace('-', '_')}{'_fp16' if a.fp16 else ''}.onnx"
    if dst.exists():
        print("sudah ada, lewati:", dst)
        return
    with tempfile.TemporaryDirectory() as tmp:
        pt = Path(tmp) / pt_src.name
        shutil.copy(pt_src, pt)
        kw = dict(quantize=16) if a.fp16 else dict(half=False)
        p = YOLO(str(pt)).export(format="onnx", imgsz=416, dynamic=False, simplify=True, device="cpu", **kw)
        shutil.move(p, dst)
        print("tersimpan:", dst, f"{dst.stat().st_size / 1e6:.2f} MB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "onnx")
    ap.add_argument("--force", action="store_true", help="timpa file .onnx yang sudah ada")
    ap.add_argument("--fp16", action="store_true",
                    help="Tahap 5a: ekspor fp16 (quantize=16, pengganti half=True) ke {box,seg}_{320,416}_fp16.onnx. "
                         "Di CPU Ultralytics mengonversi lewat onnxruntime float16 (keep_io_types: input/output tetap float32). "
                         "File yang sudah ada TIDAK pernah ditimpa di mode ini.")
    ap.add_argument("--hp", action="store_true",
                    help="Tahap 5b: ekspor bobot latih ulang models/hp/hp-{kotak,seg}-v3-{320,416}_best.pt ke "
                         "models/onnx/hp_{box,seg}_{320,416}[_fp16].onnx (fp32, atau fp16 bersama --fp16). Tidak pernah menimpa.")
    ap.add_argument("--distil", action="store_true",
                    help="Tahap 5c: ekspor models/hp/hp-kotak-v3-416-distil_best.pt ke models/onnx/hp_box_416_distil[_fp16].onnx. Tidak pernah menimpa.")
    ap.add_argument("--r2", action="store_true", help="bersama --distil: ronde 2 (hp-kotak-v3-416-distil-r2)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.distil:
        return ekspor_distil(a)
    if a.hp:
        return ekspor_hp(a)
    sizes = (416, 320) if a.fp16 else SIZES
    suffix = "_fp16" if a.fp16 else ""

    with tempfile.TemporaryDirectory() as tmp:  # ekspor di folder sementara, bukan di models/ronde2
        for short, pt_name in MODELS:
            pt = Path(tmp) / pt_name
            shutil.copy(SRC / pt_name, pt)
            for sz in sizes:
                dst = a.out / f"{short}_{sz}{suffix}.onnx"
                if dst.exists() and (a.fp16 or not a.force):
                    print("sudah ada, lewati:", dst)
                    continue
                m = YOLO(str(pt))
                kw = dict(quantize=16) if a.fp16 else dict(half=False)
                p = m.export(format="onnx", imgsz=sz, dynamic=False, simplify=True, device="cpu", **kw)
                shutil.move(p, dst)
                print("tersimpan:", dst, f"{dst.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
