"""distil_label.py - Tahap 5c, Bagian A: pseudo-label dari teacher C2 + lembar cek. Prompt: data/prompt-distilasi.md.

Kolam frame: data/frame-blur/<video>/*.jpg (baca saja), tanpa lokasi val (dapsut_, perpus-lt9-ubm-tower_,
tangga-naik-lt9-lt10-ubm-tower_), tanpa lokasi test (selasar-lt11-ubm-tower_, pot-lt11-ubm-tower_, taman-ubm_),
tanpa frame yang sudah punya label manusia di dataset-gabung-kotak-v3 (cocok lewat nama dasar tanpa __rN).
Tidak memakai data/rekam/ dan data/analisis-rekaman/.

Teacher = C2 persis seperti server (src/server/deteksi.py): 4 anggota dari src/server/config.yaml, imgsz masing-masing,
predict(conf=conf_prediksi_kotak, half=False, device=0) pada gambar BGR numpy, WBF IoU 0.55 (src/server/ensemble.py).
Kotak gabungan disimpan kalau conf >= 0.50 (orang >= 0.60). Frame tanpa kotak tetap jadi frame latar (tanpa baris label),
kecuali jumlahnya > 40% kolam: lalu hanya 40% acak (seed 0) dari frame kosong yang disimpan.

Keluaran: data/dataset-distil-kotak-v3[-t<nilai>]/ (menolak kalau sudah ada), laporan di data/model-hp/5c/.
Gambar dan label dataset asli ditautkan keras (hardlink) atau disalin; dataset asli tidak diubah.

  venv\\Scripts\\python spike\\distil_label.py                 # ambang 0.50 -> data/dataset-distil-kotak-v3
  venv\\Scripts\\python spike\\distil_label.py --ambang 0.60   # -> data/dataset-distil-kotak-v3-t0.6
"""
import argparse
import csv
import json
import os
import random
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "server"))
import yaml  # noqa: E402
from ensemble import WBF_IOU, wbf_gambar  # noqa: E402

FRAME = ROOT / "data" / "frame-blur"
SUMBER = ROOT / "data" / "dataset-gabung-kotak-v3"
OUTDIR = ROOT / "data" / "model-hp" / "5c"
EXCL_VAL = ("dapsut_", "perpus-lt9-ubm-tower_", "tangga-naik-lt9-lt10-ubm-tower_")
EXCL_TEST = ("selasar-lt11-ubm-tower_", "pot-lt11-ubm-tower_", "taman-ubm_")
EXCL_DILARANG = ("selasar-lt11", "pot-lt11", "taman-ubm", "dapsut", "perpus-lt9", "tangga-naik-lt9-lt10")
AMBANG_ORANG = 0.60
MAKS_KOSONG = 0.40
SEED = 0


def nama_dasar(stem):
    return stem.split("__r")[0]


def bangun_kolam():
    """-> (kolam [(folder, Path)], hitungan per folder, jumlah dikecualikan val/test/berlabel)."""
    berlabel = {nama_dasar(p.stem) for p in (SUMBER / "images" / "train").iterdir() if p.suffix.lower() == ".jpg"}
    berlabel |= {nama_dasar(p.stem) for p in (SUMBER / "images" / "val").iterdir() if p.suffix.lower() == ".jpg"}
    kolam, per, ex = [], {}, dict(val=0, test=0, berlabel=0)
    for d in sorted(p for p in FRAME.iterdir() if p.is_dir()):
        fr = sorted(d.glob("*.jpg"))
        if d.name.startswith(EXCL_VAL):
            ex["val"] += len(fr)
            continue
        if d.name.startswith(EXCL_TEST):
            ex["test"] += len(fr)
            continue
        ada = 0
        for p in fr:
            if nama_dasar(p.stem) in berlabel:
                ex["berlabel"] += 1
                ada += 1
            else:
                kolam.append((d.name, p))
        per[d.name] = dict(total=len(fr), berlabel=ada, kolam=len(fr) - ada)
    return kolam, per, ex


def muat_teacher():
    import torch
    from ultralytics import YOLO

    cfg = yaml.safe_load((ROOT / "src" / "server" / "config.yaml").read_text(encoding="utf-8"))
    anggota = cfg["ensemble_kotak"]
    assert len(anggota) == 4 and float(cfg["wbf_iou"]) == WBF_IOU and cfg.get("half", False) is False
    mdl = [(YOLO(str(ROOT / a["bobot"])), int(a["imgsz"])) for a in anggota]
    for m, _ in mdl[1:]:
        assert m.names == mdl[0][0].names
    return dict(cfg=cfg, model=mdl, names=mdl[0][0].names, conf=float(cfg["conf_prediksi_kotak"]),
                device=0 if torch.cuda.is_available() else "cpu", anggota=anggota)


def teacher_prediksi(t, gambar):
    """Sama dengan MesinDeteksi._prediksi_anggota + wbf_gambar (tanpa saring conf_kelas, disaring di pemanggil)."""
    daftar = []
    for model, imgsz in t["model"]:
        h = model.predict(source=gambar, imgsz=imgsz, conf=t["conf"], device=t["device"], verbose=False)[0]
        th, lb = h.orig_shape
        daftar.append(dict(w=lb, h=th, cls=h.boxes.cls.cpu().numpy().astype(int), conf=h.boxes.conf.cpu().numpy().astype(float),
                           xyxy=h.boxes.xyxy.cpu().numpy().astype(float)))
    return wbf_gambar(daftar, WBF_IOU)


def simpan_label(path, pred, names, ambang):
    ids = {n: i for i, n in names.items()}
    baris, kotak = [], []
    for c, f, (x1, y1, x2, y2) in zip(pred["cls"], pred["conf"], pred["xyxy"]):
        batas = AMBANG_ORANG if names[int(c)] == "orang" else ambang
        if f < batas - 1e-9:
            continue
        w, h = pred["w"], pred["h"]
        x1, x2, y1, y2 = min(max(x1, 0), w), min(max(x2, 0), w), min(max(y1, 0), h), min(max(y2, 0), h)
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue
        baris.append(f"{int(c)} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
        kotak.append((int(c), float(f), (float(x1), float(y1), float(x2), float(y2))))
    return baris, kotak


def tautkan(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def salin_dataset(out):
    """train asli (gambar + label) dan val identik, tautan keras (atau salinan)."""
    n = Counter()
    for sp in ("train", "val"):
        for sub in ("images", "labels"):
            (out / sub / sp).mkdir(parents=True, exist_ok=True)
        for p in sorted((SUMBER / "images" / sp).iterdir()):
            if p.suffix.lower() == ".jpg":
                tautkan(p, out / "images" / sp / p.name)
                n[sp] += 1
        for p in sorted((SUMBER / "labels" / sp).iterdir()):
            if p.suffix == ".txt":
                tautkan(p, out / "labels" / sp / p.name)
    return n


def kotak_manusia():
    c = Counter()
    for p in (SUMBER / "labels" / "train").glob("*.txt"):
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                c[int(ln.split()[0])] += 1
    return c


def lembar_cek(sel, names, path, kolom=6, lebar=360, tinggi=480):
    import cv2

    cat = [(0, 165, 255), (0, 200, 0), (255, 120, 0), (0, 0, 255), (200, 0, 200), (200, 200, 0), (0, 255, 255), (255, 0, 120)]
    sel_img = []
    for folder, p, kotak in sel:
        im = cv2.imread(str(p))
        h, w = im.shape[:2]
        s = min(lebar / w, tinggi / h)
        im = cv2.resize(im, (int(w * s), int(h * s)))
        for c, f, (x1, y1, x2, y2) in kotak:
            col = cat[c % len(cat)]
            a, b = (int(x1 * s), int(y1 * s)), (int(x2 * s), int(y2 * s))
            cv2.rectangle(im, a, b, col, 2)
            tek = f"{names[c]} {f:.2f}"
            (tw, th), _ = cv2.getTextSize(tek, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            y0 = max(b[1] - 0, a[1])
            ya = a[1] - th - 4 if a[1] - th - 4 >= 0 else a[1]
            cv2.rectangle(im, (a[0], ya), (a[0] + tw + 4, ya + th + 4), col, -1)
            cv2.putText(im, tek, (a[0] + 2, ya + th + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)
        sel_img.append((im, folder, p.stem, len(kotak)))
    baris = (len(sel_img) + kolom - 1) // kolom
    kanvas = np.full((baris * (tinggi + 28), kolom * lebar, 3), 255, np.uint8)
    for i, (im, folder, stem, nk) in enumerate(sel_img):
        r, c = divmod(i, kolom)
        y0, x0 = r * (tinggi + 28), c * lebar
        kanvas[y0 + 28:y0 + 28 + im.shape[0], x0:x0 + im.shape[1]] = im
        cv2.putText(kanvas, f"#{i + 1} {folder[:22]} {stem[-9:]} n={nk}", (x0 + 3, y0 + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (0, 0, 0), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), kanvas, [cv2.IMWRITE_JPEG_QUALITY, 88])


def pilih_lembar(simpan, names, n=30):
    """30 frame seed 0, tersebar antar folder; minimal 3 berisi orang dan 3 berisi tangga/tepian kalau ada."""
    rng = random.Random(SEED)
    oleh = defaultdict(list)
    for item in simpan:
        oleh[item[0]].append(item)
    for v in oleh.values():
        rng.shuffle(v)
    pilih, ada = [], set()

    def ambil(syarat, minimal):
        calon = [it for v in oleh.values() for it in v if syarat(it) and id(it) not in ada]
        rng.shuffle(calon)
        calon.sort(key=lambda it: sum(1 for q in pilih if q[0] == it[0]))  # utamakan folder yang belum terpilih
        k = 0
        for it in calon:
            if k >= minimal:
                break
            pilih.append(it)
            ada.add(id(it))
            k += 1
        return k

    n_orang = ambil(lambda it: any(names[c] == "orang" for c, _, _ in it[2]), 3)
    n_tt = ambil(lambda it: any(names[c] in ("tangga", "tepian") for c, _, _ in it[2]), 3)
    folder = sorted(oleh)
    rng.shuffle(folder)
    i = 0
    while len(pilih) < n and any(len(oleh[f]) for f in folder):
        f = folder[i % len(folder)]
        i += 1
        for it in oleh[f]:
            if id(it) not in ada:
                pilih.append(it)
                ada.add(id(it))
                break
        else:
            oleh[f] = []
    return pilih[:n], n_orang, n_tt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ambang", type=float, default=0.50)
    a = ap.parse_args()
    suf = "" if abs(a.ambang - 0.50) < 1e-9 else f"-t{a.ambang:g}"
    out = ROOT / "data" / f"dataset-distil-kotak-v3{suf}"
    if out.exists():
        sys.exit(f"{out} sudah ada, tidak ditimpa.")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    lap_json = OUTDIR / f"label_palsu{suf}.json"
    lembar = OUTDIR / f"cek_label_palsu{suf}.jpg"
    for p in (lap_json, lembar):
        if p.exists():
            sys.exit(f"{p} sudah ada, tidak ditimpa.")

    kolam, per, ex = bangun_kolam()
    print(f"kolam: {len(kolam)} frame; dikecualikan val {ex['val']}, test {ex['test']}, sudah berlabel {ex['berlabel']}", flush=True)
    assert len(kolam) > 0
    assert not any(f.startswith(EXCL_VAL + EXCL_TEST) for f, _ in kolam)
    assert not any(any(x in str(p) for x in ("rekam", "analisis-rekaman")) for _, p in kolam)

    import cv2

    t = muat_teacher()
    names = t["names"]
    print("teacher:", [(Path(x["bobot"]).name, x["imgsz"]) for x in t["anggota"]], "kelas:", names, flush=True)
    teacher_prediksi(t, np.zeros((640, 480, 3), np.uint8))  # pemanasan
    hasil, t0 = [], time.perf_counter()
    for i, (folder, p) in enumerate(kolam):
        pred = teacher_prediksi(t, cv2.imread(str(p)))
        baris, kotak = simpan_label(p, pred, names, a.ambang)
        hasil.append((folder, p, kotak, baris))
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(kolam)}  {time.perf_counter() - t0:.0f}s", flush=True)
    detik = time.perf_counter() - t0

    kosong = [h for h in hasil if not h[2]]
    isi = [h for h in hasil if h[2]]
    batas_kosong = len(kolam) * MAKS_KOSONG
    kosong_dipotong = len(kosong) > batas_kosong
    if kosong_dipotong:
        rng = random.Random(SEED)
        keep = set(rng.sample(range(len(kosong)), int(round(len(kosong) * MAKS_KOSONG))))
        kosong_simpan = [k for i, k in enumerate(kosong) if i in keep]
    else:
        kosong_simpan = kosong
    simpan = sorted(isi + kosong_simpan, key=lambda h: (h[0], h[1].name))

    # tulis dataset baru (di folder sementara dulu, lalu ganti nama, supaya tidak ada folder setengah jadi)
    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        sys.exit(f"{tmp} sisa jalan sebelumnya; hapus manual dulu.")
    n_asli = salin_dataset(tmp)
    for folder, p, kotak, baris in simpan:
        tautkan(p, tmp / "images" / "train" / f"pseudo_{p.name}")
        (tmp / "labels" / "train" / f"pseudo_{p.stem}.txt").write_text("\n".join(baris) + ("\n" if baris else ""), encoding="utf-8")
    ycfg = yaml.safe_load((SUMBER / "data.yaml").read_text(encoding="utf-8"))
    (tmp / "data.yaml").write_text(
        f"path: {out.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {k}: {v}\n" for k, v in ycfg["names"].items()), encoding="utf-8")
    assert {int(k): v for k, v in ycfg["names"].items()} == {int(k): v for k, v in names.items()}, "kelas data.yaml beda dengan teacher"
    tmp.rename(out)

    # laporan
    pseudo_box = Counter(c for _, _, kotak, _ in simpan for c, _, _ in kotak)
    manusia = kotak_manusia()
    per_folder = Counter(f for f, _, _, _ in simpan)
    assert not any(f.startswith(EXCL_VAL + EXCL_TEST) for f in per_folder)
    assert not any(any(x in p.name for x in EXCL_DILARANG) for _, p, _, _ in simpan)
    md = [f"# Tahap 5c, Bagian A: pseudo-label (ambang {a.ambang:g}, orang {AMBANG_ORANG:g})", "",
          f"Kolam: {len(kolam)} frame. Dikecualikan: val {ex['val']}, test {ex['test']}, sudah berlabel manusia {ex['berlabel']}.",
          f"Teacher C2: {len(kolam)} frame dalam {detik:.0f} s ({detik / len(kolam):.2f} s/frame, 4 model, GPU). "
          f"Frame tanpa kotak: {len(kosong)} ({100 * len(kosong) / len(kolam):.1f}% kolam), disimpan {len(kosong_simpan)}"
          + (f" (dipotong ke 40% acak, seed 0, karena > 40% kolam)" if kosong_dipotong else " (tidak dipotong, tidak > 40% kolam)") + ".",
          f"Frame pseudo disimpan: {len(simpan)} (berisi kotak {len(isi)}, latar {len(kosong_simpan)}). "
          f"Dataset asli: train {n_asli['train']} gambar, val {n_asli['val']} gambar. Dataset baru train = {n_asli['train'] + len(simpan)}.", "",
          "## Per folder", "", "| folder | total | berlabel manusia | kolam | pseudo disimpan |", "|---|---|---|---|---|"]
    for f, v in per.items():
        md.append(f"| {f} | {v['total']} | {v['berlabel']} | {v['kolam']} | {per_folder.get(f, 0)} |")
    md += ["", "## Kotak per kelas", "", "| kelas | pseudo (kotak) | manusia train (kotak, termasuk salinan oversampling dan data publik) |", "|---|---|---|"]
    for i in sorted(names):
        md.append(f"| {names[i]} | {pseudo_box.get(i, 0)} | {manusia.get(i, 0)} |")
    md += ["", f"Total kotak pseudo: {sum(pseudo_box.values())}; manusia: {sum(manusia.values())}."]
    (OUTDIR / f"laporan_label_palsu{suf}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    lap_json.write_text(json.dumps(dict(ambang=a.ambang, kolam=len(kolam), dikecualikan=ex, per_folder=per, detik_teacher=detik,
                                         kosong=len(kosong), kosong_simpan=len(kosong_simpan), kosong_dipotong=kosong_dipotong,
                                         pseudo=len(simpan), pseudo_per_kelas={names[k]: v for k, v in pseudo_box.items()},
                                         manusia_per_kelas={names[k]: v for k, v in manusia.items()}), indent=1, ensure_ascii=False),
                        encoding="utf-8")
    print("\n".join(md))

    sel, n_or, n_tt = pilih_lembar([(f, p, kotak) for f, p, kotak, _ in simpan], names)
    lembar_cek([(f, p, kotak) for f, p, kotak in sel], names, lembar)
    print(f"lembar cek: {lembar} (30 frame; berisi orang >= {n_or} dipaksa, tangga/tepian >= {n_tt} dipaksa)")
    print("dataset:", out)


if __name__ == "__main__":
    main()
