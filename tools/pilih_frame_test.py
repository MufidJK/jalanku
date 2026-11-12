"""pilih_frame_test.py - pilih frame test JalanKu (deterministik, hanya dari metadata + ukuran gambar).

Tidak ada model yang dijalankan. Pemilihan tidak melihat hasil model apa pun.

Aturan (lihat data/test-review/LOG.md):
  - Tiap video dapat jatah frame (JATAH). Garis waktu video dibagi n slot sama panjang; pusat slot digeser
    -1/4 slot untuk POV dada dan +1/4 slot untuk POV mata supaya dada dan mata tidak memilih detik yang sama.
  - Pilih n frame berurutan waktu yang lolos (tidak blur, bukan duplikat dari pilihan sebelumnya, jarak >=
    JEDA_MIN detik) dan meminimalkan total |waktu - pusat slot| (DP). Frame terdekat pusat yang ditolak dilaporkan.
  - Blur: variansi Laplacian (gambar 540x960 abu-abu) < RASIO_BLUR x median tetangga (+-5 detik) atau < LANTAI_BLUR.
  - Duplikat: jarak Hamming pHash (64 bit) <= HAMMING_DUP.
  - Tidak ada acak (seed tidak diperlukan): pemilihan DP deterministik, seri diputus ke waktu paling awal.

Mode:
  python tools/pilih_frame_test.py pilih            -> data/test-review/daftar_test.csv + _pilihan/*.jpg
  python tools/pilih_frame_test.py topup <kelas...> -> tidak ada; top-up memakai fungsi calon_topup() dari skrip lain
"""

import csv
import sys
from pathlib import Path

import cv2
import numpy as np

SEED = None   # tidak ada acak: DP deterministik, seri diputus ke frame paling awal
ROOT = Path("data/frame-blur")
OUT = Path("data/test-review")
JEDA_MIN = 3.0
RASIO_BLUR = 0.5
LANTAI_BLUR = 15.0
HAMMING_DUP = 6

# video -> (lokasi, pov, jatah)
JATAH = {
    "selasar-lt11-ubm-tower_2026-10-30_01_dada": 11,
    "selasar-lt11-ubm-tower_2026-10-30_01_mata": 11,
    "pot-lt11-ubm-tower_2026-10-30_01_dada": 12,
    "pot-lt11-ubm-tower_2026-10-30_01_mata": 11,
    "taman-ubm_2026-11-07_01_dada": 23,
    "taman-ubm_2026-11-07_01_mata": 22,
}


def lokasi_pov(video):
    return video.split("_")[0], video.rsplit("_", 1)[1]


def fitur(path):
    g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    g = cv2.resize(g, (540, 960), interpolation=cv2.INTER_AREA)
    lap = float(cv2.Laplacian(g, cv2.CV_64F).var())
    k = cv2.resize(g, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    d = cv2.dct(k)[:8, :8]
    bit = (d > np.median(d[1:, :].ravel())).ravel()
    return lap, bit


def muat_video(video):
    rows = list(csv.DictReader((ROOT / video / "_manifest.csv").open(encoding="utf-8")))
    out = []
    for r in rows:
        lap, bit = fitur(ROOT / video / r["filename"])
        out.append({"video": video, "frame": r["filename"], "t": float(r["timestamp_s"]), "lap": lap, "hash": bit})
    for i, f in enumerate(out):
        tetangga = [g["lap"] for g in out if g is not f and abs(g["t"] - f["t"]) <= 5.0]
        f["lap_tetangga"] = float(np.median(tetangga)) if tetangga else f["lap"]
        f["buram"] = f["lap"] < RASIO_BLUR * f["lap_tetangga"] or f["lap"] < LANTAI_BLUR
    return out


def duplikat(f, o):
    return int((f["hash"] != o["hash"]).sum()) <= HAMMING_DUP


def pilih_video(frames, n, pov, sudah=(), alasan_dasar="slot waktu"):
    """Pilih n frame: urutan waktu naik, jarak >= JEDA_MIN, tidak buram, bukan duplikat dari pilihan sebelumnya
    (dan dari 'sudah'), meminimalkan jumlah |waktu - pusat slot| (DP, deterministik, tanpa acak).
    Return (terpilih, ditolak)."""
    t0, t1 = frames[0]["t"], frames[-1]["t"]
    slot = (t1 - t0) / n
    geser = {"dada": -0.25, "mata": 0.25}[pov] * slot
    pusat = [t0 + (i + 0.5) * slot + geser for i in range(n)]
    tetap = list(sudah)
    cand = [f for f in frames if not f["buram"]
            and all(abs(f["t"] - o["t"]) >= JEDA_MIN and not duplikat(f, o) for o in tetap)]
    m = len(cand)
    INF = float("inf")
    biaya = [[INF] * m for _ in range(n)]
    asal = [[-1] * m for _ in range(n)]
    for j in range(m):
        biaya[0][j] = abs(cand[j]["t"] - pusat[0])
    for i in range(1, n):
        for j in range(m):
            for k in range(j):
                if biaya[i - 1][k] < INF and cand[j]["t"] - cand[k]["t"] >= JEDA_MIN and not duplikat(cand[j], cand[k]):
                    c = biaya[i - 1][k] + abs(cand[j]["t"] - pusat[i])
                    if c < biaya[i][j] - 1e-9:
                        biaya[i][j], asal[i][j] = c, k
    j = min(range(m), key=lambda x: (biaya[n - 1][x], x))
    if biaya[n - 1][j] == INF:
        raise SystemExit(f"Tidak ada pilihan yang memenuhi aturan di {frames[0]['video']}")
    idx = [j]
    for i in range(n - 1, 0, -1):
        idx.append(asal[i][idx[-1]])
    idx = idx[::-1]
    terpilih = []
    for i, j in enumerate(idx):
        f = cand[j]
        f["slot"], f["pusat"], f["alasan"] = i + 1, pusat[i], f"{alasan_dasar} {i + 1}/{n}"
        terpilih.append(f)
    ditolak = []
    for i, f in enumerate(terpilih):
        dekat = min(frames, key=lambda x: (abs(x["t"] - pusat[i]), x["t"]))
        if dekat is f:
            continue
        if dekat["buram"]:
            sebab = f"blur (lap {dekat['lap']:.0f} vs tetangga {dekat['lap_tetangga']:.0f})"
        elif any(duplikat(dekat, o) and o is not dekat for o in terpilih + tetap):
            sebab = "duplikat"
        else:
            sebab = "jarak < 3 s dari pilihan lain"
        ditolak.append((dekat["frame"], dekat["t"], sebab, i + 1, f["frame"]))
    return terpilih, ditolak


def lembar(video, terpilih, tw=180):
    th = int(tw * 1920 / 1080)
    kol = 8
    ubin = []
    for f in terpilih:
        im = cv2.imread(str(ROOT / video / f["frame"]))
        im = cv2.resize(im, (tw, th), interpolation=cv2.INTER_AREA)
        cv2.rectangle(im, (0, 0), (tw, 16), (0, 0, 0), -1)
        cv2.putText(im, f"{f['t']:.0f}s #{f['slot']}", (3, 12), 0, 0.42, (255, 255, 255), 1)
        ubin.append(cv2.copyMakeBorder(im, 0, 3, 0, 3, cv2.BORDER_CONSTANT))
    while len(ubin) % kol:
        ubin.append(np.zeros_like(ubin[0]))
    baris = [np.hstack(ubin[i:i + kol]) for i in range(0, len(ubin), kol)]
    return np.vstack(baris)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_pilihan").mkdir(exist_ok=True)
    daftar, laporan_tolak = [], []
    for video, n in JATAH.items():
        lok, pov = lokasi_pov(video)
        frames = muat_video(video)
        terpilih, ditolak = pilih_video(frames, n, pov)
        print(f"{video}: {len(frames)} frame, {sum(f['buram'] for f in frames)} buram, pilih {len(terpilih)}, "
              f"tolak dilaporkan {len(ditolak)}")
        for f in terpilih:
            daftar.append([f["frame"], video, lok, pov, f"{f['t']:.3f}", f["alasan"], f"{f['lap']:.1f}"])
        for x in ditolak:
            laporan_tolak.append([video, *x])
        cv2.imwrite(str(OUT / "_pilihan" / f"{video}.jpg"), lembar(video, terpilih), [cv2.IMWRITE_JPEG_QUALITY, 85])
    with (OUT / "daftar_test.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "video", "location", "pov", "timestamp_s", "reason_selected", "laplacian_var"])
        w.writerows(daftar)
    with (OUT / "_pilihan" / "ditolak.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["video", "frame_ditolak", "timestamp_s", "alasan", "slot", "pengganti"])
        w.writerows(laporan_tolak)
    print(f"Total {len(daftar)} frame. Ditolak (blur/duplikat) {len(laporan_tolak)}.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "pilih":
        sys.exit("Mode lain belum ada. Pakai: pilih")
    main()
