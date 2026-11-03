"""extract_frames.py - ambil frame dari video, buramkan kepala orang, simpan sebagai JPG.

Alur per video:
  sampling ~1 frame/detik -> buang frame mirip (dedup) -> deteksi orang (YOLO)
  -> pixelate area kepala setiap orang -> simpan JPG + _manifest.csv

ATURAN PRIVASI: frame yang BELUM diburamkan TIDAK PERNAH ditulis ke disk.
Pemburaman dilakukan di memori; satu-satunya tempat menulis file (save_jpg)
hanya dipanggil dengan frame yang sudah lewat blur_heads(). Kalau deteksi
gagal di tengah jalan, folder output video itu dihapus (bukan disimpan setengah).

Contoh pemakaian:
  python tools/extract_frames.py data/video-mentah/a.mp4
  python tools/extract_frames.py data/video-mentah --fps 2 --dedup-threshold 6
  python tools/extract_frames.py data/video-mentah --output data/frame-blur --overwrite --device 0
"""

import argparse
import csv
import shutil
import sys
import time
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv"}
HEAD_RATIO = 0.40      # kepala = 40% bagian atas kotak orang
HEAD_PAD = 0.10        # lebarkan 10% kotak di kiri dan kanan
PIXEL_SIZE = 8         # sisi terpanjang area kepala diperkecil jadi ~8 px
JPG_QUALITY = 95


def find_videos(path: Path) -> list[Path]:
    """File tunggal -> [file]. Folder -> semua video di dalamnya (rekursif), terurut."""
    if path.is_file():
        return [path]
    videos = [p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT]
    return sorted(videos)


def sample_frames(cap: cv2.VideoCapture, fps: float, video_fps: float) -> Iterator[tuple[float, np.ndarray]]:
    """Hasilkan (timestamp_detik, frame) kira-kira tiap 1/fps detik.

    Pakai timestamp asli frame (video HP sering variable frame rate), bukan "tiap N frame".
    """
    interval = 1.0 / fps
    next_t = 0.0
    last_ts = -1.0
    index = -1
    while cap.grab():  # grab dulu (murah); retrieve/decode hanya untuk frame yang diambil
        index += 1
        ts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if index > 0 and (ts <= 0 or ts <= last_ts):  # timestamp tidak valid -> hitung dari nomor frame
            ts = index / video_fps
        last_ts = ts
        if ts + 1e-3 >= next_t:
            ok, frame = cap.retrieve()
            if not ok:
                continue
            yield ts, frame
            while next_t <= ts + 1e-3:
                next_t += interval


def small_gray(frame: np.ndarray) -> np.ndarray:
    """Versi kecil (64x64, abu-abu) untuk membandingkan kemiripan frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)


def is_duplicate(small: np.ndarray, last_small: np.ndarray | None, threshold: float) -> tuple[bool, float | None]:
    """Bandingkan dengan frame TERAKHIR YANG DISIMPAN. Return (duplikat?, selisih rata-rata 0-255)."""
    if last_small is None:
        return False, None  # frame pertama selalu disimpan
    diff = float(np.mean(np.abs(small - last_small)))
    return diff < threshold, diff


def pixelate(region: np.ndarray) -> np.ndarray:
    """Pixelate: kecilkan sampai sisi terpanjang ~8 px, besarkan lagi dengan INTER_NEAREST."""
    h, w = region.shape[:2]
    scale = PIXEL_SIZE / max(h, w)
    small_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    small = cv2.resize(region, small_size, interpolation=cv2.INTER_LINEAR)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def blur_heads(frame: np.ndarray, boxes: np.ndarray) -> int:
    """Pixelate area kepala tiap kotak orang (x1,y1,x2,y2) langsung di `frame`. Return jumlah yang diburamkan.

    Sengaja dibuat berlebihan: 40% atas kotak, dilebarkan 10% kiri-kanan,
    jadi orang yang duduk / terpotong di bawah frame tetap tertutup kepalanya.
    """
    img_h, img_w = frame.shape[:2]
    count = 0
    for x1, y1, x2, y2 in boxes:
        bw, bh = x2 - x1, y2 - y1
        left = max(0, int(x1 - HEAD_PAD * bw))
        right = min(img_w, int(np.ceil(x2 + HEAD_PAD * bw)))
        top = max(0, int(y1))
        bottom = min(img_h, int(np.ceil(y1 + HEAD_RATIO * bh)))
        if right <= left or bottom <= top:
            continue  # area kosong (di luar frame)
        frame[top:bottom, left:right] = pixelate(frame[top:bottom, left:right])
        count += 1
    return count


def save_jpg(path: Path, frame: np.ndarray) -> None:
    """Simpan JPG. HANYA boleh dipanggil dengan frame yang sudah diburamkan.

    imencode + write_bytes (bukan cv2.imwrite) supaya aman untuk path Windows non-ASCII.
    """
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPG_QUALITY])
    if not ok:
        raise RuntimeError(f"Gagal meng-encode JPG: {path.name}")
    path.write_bytes(buf.tobytes())


def process_video(video: Path, out_root: Path, model, args) -> dict:
    """Proses satu video. Return statistik. Raise RuntimeError kalau video tidak bisa dibaca."""
    t0 = time.time()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError("video tidak bisa dibuka")
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    if not video_fps or video_fps <= 0:
        video_fps = 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    out_dir = out_root / video.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, last_small, size = [], None, None
    sampled = persons_total = frames_with_person = 0
    try:
        for ts, frame in sample_frames(cap, args.fps, video_fps):
            size = size or (frame.shape[1], frame.shape[0])
            sampled += 1
            small = small_gray(frame)
            dup, diff = is_duplicate(small, last_small, args.dedup_threshold)
            if dup:
                continue
            # Deteksi orang (kelas 0 = person), lalu buramkan kepala SEBELUM menyimpan
            result = model.predict(frame, classes=[0], conf=args.conf, verbose=False,
                                   device=None if args.device == "auto" else args.device)[0]
            n_blur = blur_heads(frame, result.boxes.xyxy.cpu().numpy())
            name = f"{video.stem}_t{round(ts * 1000):07d}.jpg"
            save_jpg(out_dir / name, frame)
            last_small = small
            persons_total += n_blur
            frames_with_person += n_blur > 0
            rows.append([name, f"{ts:.3f}", n_blur, "" if diff is None else f"{diff:.2f}"])
    except Exception:
        shutil.rmtree(out_dir, ignore_errors=True)  # jangan tinggalkan hasil setengah jadi
        raise
    finally:
        cap.release()

    if sampled == 0:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise RuntimeError("video tidak punya frame yang bisa dibaca")

    with open(out_dir / "_manifest.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "timestamp_s", "persons_blurred", "diff_to_last_saved"])
        writer.writerows(rows)

    return {"size": size, "fps": video_fps, "duration": n_frames / video_fps, "sampled": sampled,
            "kept": len(rows), "dups": sampled - len(rows), "persons": persons_total,
            "with_person": frames_with_person, "out_dir": out_dir, "seconds": time.time() - t0}


def load_model(name: str, device: str):
    """Muat model YOLO sekali saja, lalu pemanasan supaya device yang dipakai terlihat."""
    from ultralytics import YOLO
    model = YOLO(name)
    model.predict(np.zeros((64, 64, 3), np.uint8), verbose=False, device=None if device == "auto" else device)
    return model, str(model.predictor.device)


def main() -> None:
    p = argparse.ArgumentParser(description="Ekstrak frame dari video (~1 fps), buang duplikat, "
                                "buramkan kepala orang, simpan sebagai JPG. Frame asli tidak pernah disimpan.")
    p.add_argument("input", metavar="INPUT", help="file video, atau folder berisi video (subfolder ikut diproses)")
    p.add_argument("--output", default="data/frame-blur", help="folder output (default: data/frame-blur)")
    p.add_argument("--fps", type=float, default=1.0, help="jumlah frame per detik yang diambil (default: 1.0)")
    p.add_argument("--dedup-threshold", type=float, default=4.0,
                   help="selisih rata-rata piksel (0-255); di bawah ini dianggap duplikat (default: 4.0)")
    p.add_argument("--model", default="yolo11n.pt", help="bobot YOLO untuk deteksi orang (default: yolo11n.pt)")
    p.add_argument("--conf", type=float, default=0.25, help="confidence minimum deteksi orang (default: 0.25)")
    p.add_argument("--device", default="auto", help="auto, cpu, atau 0 (GPU pertama) (default: auto)")
    p.add_argument("--overwrite", action="store_true",
                   help="hapus & buat ulang subfolder video yang sudah ada (default: video dilewati)")
    args = p.parse_args()

    if args.fps <= 0:
        sys.exit("Error: --fps harus lebih besar dari 0.")
    in_path, out_root = Path(args.input), Path(args.output)
    if not in_path.exists():
        sys.exit(f"Error: path tidak ditemukan: {in_path}")
    videos = find_videos(in_path)
    if not videos:
        sys.exit(f"Error: tidak ada video ({', '.join(sorted(VIDEO_EXT))}) di: {in_path}")

    try:
        model, device = load_model(args.model, args.device)
    except Exception as e:
        sys.exit(f"Error: gagal memuat model '{args.model}': {e}")
    print(f"Model: {args.model} | Device: {device}")
    print(f"{len(videos)} video akan diproses -> {out_root}\n")

    totals = {"kept": 0, "dups": 0, "persons": 0, "with_person": 0}
    skipped, failed = [], []
    for video in videos:
        out_dir = out_root / video.stem
        print(f"== {video.name}")
        if out_dir.is_dir() and any(out_dir.iterdir()):
            if not args.overwrite:
                print(f"   DILEWATI: {out_dir} sudah ada (pakai --overwrite untuk membuat ulang)\n")
                skipped.append(video.name)
                continue
            shutil.rmtree(out_dir)
        try:
            s = process_video(video, out_root, model, args)
        except Exception as e:
            print(f"   GAGAL: {e}\n")
            failed.append(f"{video.name} ({e})")
            continue
        for k in totals:
            totals[k] += s[k]
        print(f"   Resolusi        : {s['size'][0]}x{s['size'][1]} | fps video: {s['fps']:.2f} | durasi: {s['duration']:.1f} detik")
        print(f"   Frame disampel  : {s['sampled']}")
        print(f"   Frame disimpan  : {s['kept']}")
        print(f"   Dilewati (mirip): {s['dups']}")
        print(f"   Orang diburamkan: {s['persons']} (di {s['with_person']} frame)")
        print(f"   Folder output   : {s['out_dir']}")
        print(f"   Waktu           : {s['seconds']:.1f} detik\n")

    if len(videos) > 1:
        print("== TOTAL")
        print(f"   Frame disimpan: {totals['kept']} | duplikat: {totals['dups']} | "
              f"orang diburamkan: {totals['persons']} | frame berisi orang: {totals['with_person']}")
    if skipped:
        print(f"   Dilewati ({len(skipped)}): " + ", ".join(skipped))
    if failed:
        print(f"   Gagal ({len(failed)}): " + "; ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
