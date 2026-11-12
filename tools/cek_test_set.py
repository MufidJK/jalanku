"""cek_test_set.py - cek programatik JSON X-AnyLabeling di satu folder (default data/test-review).

Tidak mengubah apa pun. Aturan sama dengan tools/audit_label_kampus.py:
  R4 ukuran (frame 1080x1920): kelas biasa sisi pendek >= 96; tipis (pilar, pohon, tepian) sisi panjang >= 96 dan
     sisi pendek >= 24; tangga: kotak gabungan semua shape tangga di frame.
  R6 duplikat: kelas sama, IoU kotak > 0.9.
  titik di luar gambar (toleransi 1 px), label tidak ada di classes.txt, shape < 3 titik.
Hitungan instance per kelas dilakukan SETELAH R4 (shape di bawah ambang tidak dihitung).

Pakai:
  python tools/cek_test_set.py [--folder data/test-review] [--csv keluaran.csv]
  python tools/cek_test_set.py --buang-r4 r4_dibuang.csv --cadangan data/test-review-aux/_sebelum-r4
     -> HANYA atas izin: menyalin dulu tiap JSON yang berubah ke --cadangan, lalu membuang shape pelanggar R4
        (bukan pelanggaran lain), format JSON X-AnyLabeling (CRLF, indent 2) dipertahankan, dan menulis CSV shape yang dibuang.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

KELAS = Path("data/pilot/classes.txt").read_text().split()
KOTAK = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"]
PERMUKAAN = ["jalur_jalan", "jalan_kendaraan", "tangga"]
TIPIS = ("pilar", "pohon", "tepian")
MIN_SISI, MIN_TIPIS, IOU_DUP = 96.0, 24.0, 0.9


def bbox(pts, w, h):
    p = np.asarray(pts, float)
    x1, y1 = np.clip(p.min(0), 0.0, [w, h])
    x2, y2 = np.clip(p.max(0), 0.0, [w, h])
    return float(x1), float(y1), float(x2), float(y2)


def iou(a, b):
    iw, ih = max(0.0, min(a[2], b[2]) - max(a[0], b[0])), max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = iw * ih
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def lolos_r4(kelas, b):
    bw, bh = b[2] - b[0], b[3] - b[1]
    pendek, panjang = min(bw, bh), max(bw, bh)
    if kelas in TIPIS:
        return panjang >= MIN_SISI and pendek >= MIN_TIPIS
    return pendek >= MIN_SISI


def periksa(folder):
    """-> (pelanggaran list[dict], hitung_kotak Counter, hitung_permukaan Counter, hitung_per_frame dict, info)"""
    pel, kotak, perm = [], Counter(), Counter()
    per_frame = {}
    n = 0
    for j in sorted(Path(folder).glob("*.json")):
        d = json.loads(j.read_text(encoding="utf-8"))
        n += 1
        w, h = float(d["imageWidth"]), float(d["imageHeight"])
        stem = j.stem
        fr = Counter()
        tangga_pts = []
        valid = []
        for i, s in enumerate(d["shapes"]):
            lab, pts = s["label"], s["points"]
            sid = f"{stem}#{i}"
            if lab not in KELAS:
                pel.append(dict(frame=stem, idx=i, kelas=lab, aturan="label", alasan="label tidak ada di classes.txt"))
                continue
            if len(pts) < 3:
                pel.append(dict(frame=stem, idx=i, kelas=lab, aturan="titik", alasan=f"{len(pts)} titik"))
                continue
            p = np.asarray(pts, float)
            if p.min() < -1 or p[:, 0].max() > w + 1 or p[:, 1].max() > h + 1:
                pel.append(dict(frame=stem, idx=i, kelas=lab, aturan="luar", alasan="titik di luar gambar"))
            b = bbox(pts, w, h)
            if lab in PERMUKAAN:
                perm[lab] += 1
                fr[lab] += 1
            if lab == "tangga":
                tangga_pts.append(p)
                continue
            if lab in KOTAK:
                if not lolos_r4(lab, b):
                    pel.append(dict(frame=stem, idx=i, kelas=lab, aturan="R4",
                                    alasan=f"kotak {b[2]-b[0]:.0f}x{b[3]-b[1]:.0f}"))
                    continue
                valid.append((i, lab, b, s.get("score", 0)))
                kotak[lab] += 1
                fr[lab] += 1
        if tangga_pts:
            b = bbox(np.vstack(tangga_pts), w, h)
            if lolos_r4("tangga", b):
                kotak["tangga"] += 1
                fr["tangga_kotak"] += 1
            else:
                pel.append(dict(frame=stem, idx="+".join(map(str, range(len(tangga_pts)))), kelas="tangga", aturan="R4",
                                alasan=f"kotak gabungan {b[2]-b[0]:.0f}x{b[3]-b[1]:.0f}"))
        for a in range(len(valid)):
            for c in range(a + 1, len(valid)):
                if valid[a][1] == valid[c][1] and iou(valid[a][2], valid[c][2]) > IOU_DUP:
                    pel.append(dict(frame=stem, idx=valid[c][0], kelas=valid[c][1], aturan="R6",
                                    alasan=f"duplikat dengan #{valid[a][0]} (IoU {iou(valid[a][2], valid[c][2]):.2f})"))
        per_frame[stem] = fr
    return pel, kotak, perm, per_frame, n


def dump_xal(d):
    """Format X-AnyLabeling di Windows: indent 2, CRLF, tanpa newline akhir, non-ASCII apa adanya."""
    return json.dumps(d, indent=2, ensure_ascii=False).replace(chr(10), chr(13) + chr(10)).encode("utf-8")


def buang_r4(folder, pel, csv_out, cadangan):
    """Buang shape pelanggar R4 dari JSON. Mengembalikan Counter per kelas."""
    import shutil
    folder, cadangan = Path(folder), Path(cadangan)
    per_file = defaultdict(set)
    for p in pel:
        if p["aturan"] == "R4":
            for i in str(p["idx"]).split("+"):
                per_file[p["frame"]].add(int(i))
    cadangan.mkdir(parents=True, exist_ok=True)
    if any(cadangan.iterdir()):
        raise SystemExit(f"{cadangan} tidak kosong, berhenti")
    jumlah, baris = Counter(), []
    for stem, idxs in sorted(per_file.items()):
        f = folder / f"{stem}.json"
        raw = f.read_bytes()
        d = json.loads(raw)
        if dump_xal(d) != raw:
            raise SystemExit(f"{f.name}: format tidak bisa dipertahankan byte demi byte, berhenti")
        shutil.copy2(f, cadangan / f.name)
        for i in sorted(idxs):
            s = d["shapes"][i]
            b = bbox(s["points"], d["imageWidth"], d["imageHeight"])
            baris.append(dict(frame=stem, idx=i, kelas=s["label"], bbox=f"{b[0]:.0f},{b[1]:.0f},{b[2]:.0f},{b[3]:.0f}",
                              ukuran=f"{b[2]-b[0]:.0f}x{b[3]-b[1]:.0f}", description=s.get("description", "")))
            jumlah[s["label"]] += 1
        d["shapes"] = [s for i, s in enumerate(d["shapes"]) if i not in idxs]
        f.write_bytes(dump_xal(d))
    with open(csv_out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["frame", "idx", "kelas", "bbox", "ukuran", "description"])
        w.writeheader()
        w.writerows(baris)
    return jumlah, len(per_file)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buang-r4")
    ap.add_argument("--cadangan")
    ap.add_argument("--folder", default="data/test-review")
    ap.add_argument("--csv")
    a = ap.parse_args()
    pel, kotak, perm, per_frame, n = periksa(a.folder)
    print(f"{n} JSON di {a.folder}")
    print("kotak (setelah R4):", {k: kotak[k] for k in KOTAK})
    print("permukaan (jumlah shape):", {k: perm[k] for k in PERMUKAAN})
    c = Counter(p["aturan"] for p in pel)
    print("pelanggaran:", dict(c))
    for p in pel[:40]:
        print("  ", p)
    if a.buang_r4:
        if not a.cadangan:
            raise SystemExit("--buang-r4 butuh --cadangan")
        jumlah, nf = buang_r4(a.folder, pel, a.buang_r4, a.cadangan)
        print(f"R4: {sum(jumlah.values())} shape dibuang dari {nf} file:", dict(jumlah))
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, ["frame", "idx", "kelas", "aturan", "alasan"])
            w.writeheader()
            w.writerows(pel)


if __name__ == "__main__":
    main()
