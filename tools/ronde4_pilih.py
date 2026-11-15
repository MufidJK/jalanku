"""ronde4_pilih.py - ronde 4 JalanKu, CHECKPOINT R4-0: pool, cache prediksi (model final ronde 2), studi sumber draft (val), pilih 150 frame.

Dijalankan dari root repo. Semua keluaran di data/ronde4/. Tidak mengubah tools/ronde2_pilih.py (fungsi bantu diimpor),
dataset lama, label, atau data/frame-blur.

  python tools/ronde4_pilih.py pool     # pool + prediksi kotak (imgsz 960) / seg (imgsz 640) -> data/ronde4/pred-cache/
  python tools/ronde4_pilih.py studi    # studi sumber draft di VAL (pengukuran saja) -> data/ronde4/sumber_draft.csv
  python tools/ronde4_pilih.py pilih    # pilih 150 frame (seed 20261114) -> data/ronde4/pilihan.csv + pilihan_*.png
  python tools/ronde4_pilih.py pilih --ganti data/ronde4/ganti.json   # sama, dengan frame yang dibuang setelah cek visual

Aturan keras (dicek di kode, berhenti kalau dilanggar):
  - Frame baru hanya dari lokasi TRAINING. Lokasi TEST tidak pernah dibaca, model tidak pernah dijalankan di sana.
  - Lokasi VAL hanya dipakai di `studi` untuk pengukuran; tidak ada yang ditulis ke label val.
  - Frame bocor (data/ronde2/bocor/dikeluarkan.csv, data/ronde2/dikeluarkan/) dan rentang waktu BOCOR tidak masuk pool.
Embedding / pHash / Laplacian / luminansi dipakai ulang dari data/ronde2/pred-cache/ (fitur gambar, tidak bergantung model final).
"""
import argparse
import csv
import json
import pickle
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import ronde2_pilih as r2  # noqa: E402
from ronde2_pilih import (FB, KOTAK, LUAR, ROOT, SEG, baca_manifest, baca_yolo, cek_train, cocok, daftar_video, ham, iou1,  # noqa: E402
                          jenis_lokasi, kotak_auto, lokasi_dari, poly_auto, r4_lolos, raster)

OUT = ROOT / "data/ronde4"
CACHE = OUT / "pred-cache"
CACHE_R2 = ROOT / "data/ronde2/pred-cache"
M_KOTAK = ROOT / "models/ronde2/r2-kotak-v3-960_best.pt"
M_SEG = ROOT / "models/ronde2/r2-seg-v3_best.pt"
IMGSZ_KOTAK, IMGSZ_SEG = 960, 640
LABEL_DIRS = [ROOT / "data/pilot-v2", ROOT / "data/pilot-v2-blind", ROOT / "data/ronde2-review", ROOT / "data/ronde2/dikeluarkan"]
DIKELUARKAN_CSV = ROOT / "data/ronde2/bocor/dikeluarkan.csv"
# Rentang bocor taman-ubm (video diawali nama ini, t dalam detik, inklusif). Sumber: data/ronde2/bocor/ + cek visual 14 Nov 2026 (LOG R4-0.1).
BOCOR = [
    ("tangga-naik-alfa-lt2", 0.0, 15.999),                      # depan Maxx Coffee (A1 ronde 2)
    ("jalanan-ubm_2026-11-07_01_mata", 0.0, 24.999),            # plaza drop-off, kanopi + planter palem
    ("jalanan-ubm_2026-11-07_01_dada", 85.0, 1e9),              # tangga naik ke plaza drop-off sampai akhir video
    ("lorong-lt3-eskalator-alfa-tower", 200.0, 1e9),            # lobi bawah, taman-ubm terlihat lewat kaca
]
SEED = 20261114
TARGET = 142            # LOG R4-0.7: frame luar yang lolos dedupe hanya 57; 57/142 = 40%, masih dalam rentang 140-160
JARAK_LABEL = 3.0
JARAK_PILIH = 3.0
MAKS_VIDEO = 8
MAKS_VIDEO_LUAR = 18       # LOG R4-0.6/0.7: 6 video luar; halaman/jalanan mentok di dedupe, hanya samping-ubm yang bisa sampai 18 supaya luar >= 40%
LUAR_MIN = 0.40
KUOTA = {"E": 10, "N": 35, "O": 30, "U": 50, "G": 15, "W": 10}
URUTAN = ["E", "N", "O", "U", "G", "W"]
BOBOT_N = {"tepian": 2.0, "kendaraan": 2.0, "pilar": 1.5, "pohon": 1.5, "tanaman_pot": 1.0}
BOBOT_U = {"pilar": 1.5, "tepian": 1.5, "pohon": 1.5, "kendaraan": 1.0, "tanaman_pot": 1.0}
BOBOT_LAIN = 0.3
Y2_DEKAT = 0.65
CELAH_O, CELAH_G = 10.0, 20.0
COS_DUP, PHASH_DUP = 0.85, 6
BLUR_REL, BLUR_ABS = 0.5, 15.0
BLUR_GANTI = 1.25          # pengganti (cek visual): Laplacian >= 1,25 x median video


def log(baris):
    with (OUT / "LOG.md").open("a", encoding="utf-8") as f:
        f.write(baris.rstrip() + "\n")
    print(baris, flush=True)


def di_bocor(video, t):
    return any(video.startswith(v) and a <= t <= b for v, a, b in BOCOR)


def stem_berlabel():
    s = set()
    for d in LABEL_DIRS:
        s |= {p.stem for p in d.glob("*.json")}
    with DIKELUARKAN_CSV.open(encoding="utf-8") as f:
        s |= {r["stem"] for r in csv.DictReader(f)}
    return s


def bangun_pool():
    """-> (pool, lab_train, ringkasan). lab_train = semua frame lokasi training yang sudah berlabel ATAU dikeluarkan."""
    berlabel = stem_berlabel()
    pool, lab, ring = [], [], Counter()
    for d, lok, jenis in daftar_video():
        if jenis != "train":
            continue  # TEST dan VAL tidak dibaca sama sekali
        cek_train(lok)
        man = baca_manifest(d)
        imgs = sorted(p for p in d.iterdir() if p.suffix.lower() == ".jpg")
        t_lab = [man[p.stem] for p in imgs if p.stem in berlabel]
        pov = d.name.split("_")[-1]
        for p in imgs:
            ring["train_total"] += 1
            t = man[p.stem]
            rec = dict(stem=p.stem, path=p, video=d.name, lokasi=lok, pov=pov, t=t)
            if p.stem in berlabel:
                ring["berlabel"] += 1
                lab.append(rec)
                continue
            if di_bocor(d.name, t):
                ring["bocor"] += 1
                continue
            dmin = min((abs(t - x) for x in t_lab), default=1e9)
            rec["jarak_label"] = dmin
            if dmin < JARAK_LABEL:
                ring["dekat_label"] += 1
                continue
            pool.append(rec)
    ring["pool"] = len(pool)
    return pool, lab, ring


def cmd_pool(a):
    from ultralytics import YOLO

    CACHE.mkdir(parents=True, exist_ok=True)
    pool, lab, ring = bangun_pool()
    for r in pool + lab:
        cek_train(r["lokasi"])
        assert (CACHE_R2 / f"{r['stem']}.pkl").exists(), f"cache ronde 2 tidak ada: {r['stem']}"
    for r in pool:
        assert not di_bocor(r["video"], r["t"])
    log(f"- [R4-0.2] Pool: lokasi training {ring['train_total']} frame; berlabel/dikeluarkan {ring['berlabel']} "
        f"(pilot-v2 + blind + 66 ronde 2 + 16 dikeluarkan); rentang bocor {ring['bocor']}; < {JARAK_LABEL:g} s dari frame berlabel "
        f"{ring['dekat_label']}; POOL {ring['pool']} (luar {sum(r['lokasi'] in LUAR for r in pool)}).")
    mk, ms = YOLO(str(M_KOTAK)), YOLO(str(M_SEG))
    todo = [r for r in pool if not (CACHE / f"{r['stem']}.pkl").exists()]
    print(f"cache ada {len(pool) - len(todo)}, perlu {len(todo)}", flush=True)
    waktu = Counter()
    B = 16
    for i in range(0, len(todo), B):
        grp = todo[i:i + B]
        paths = [str(r["path"]) for r in grp]
        t0 = time.perf_counter()
        rk = mk.predict(paths, imgsz=IMGSZ_KOTAK, conf=0.05, device=0, verbose=False, batch=B)
        t1 = time.perf_counter()
        rs = ms.predict(paths, imgsz=IMGSZ_SEG, conf=0.05, device=0, verbose=False, batch=B, retina_masks=False)
        t2 = time.perf_counter()
        waktu["kotak"] += t1 - t0
        waktu["seg"] += t2 - t1
        waktu["n"] += len(grp)
        for r, a1, a2 in zip(grp, rk, rs):
            rec = dict(
                stem=r["stem"], h=a1.orig_shape[0], w=a1.orig_shape[1],
                kotak=dict(cls=a1.boxes.cls.cpu().numpy().astype(np.int16), conf=a1.boxes.conf.cpu().numpy().astype(np.float32),
                           xyxy=a1.boxes.xyxy.cpu().numpy().astype(np.float32)),
                seg=dict(cls=a2.boxes.cls.cpu().numpy().astype(np.int16), conf=a2.boxes.conf.cpu().numpy().astype(np.float32),
                         xyxy=a2.boxes.xyxy.cpu().numpy().astype(np.float32),
                         poly=[x.astype(np.float32) for x in a2.masks.xy] if a2.masks is not None else []),
            )
            (CACHE / f"{r['stem']}.pkl").write_bytes(pickle.dumps(rec))
        print(f"{min(i + B, len(todo))}/{len(todo)}", flush=True)
    if waktu["n"]:
        n = waktu["n"]
        info = dict(n=n, kotak_ms=1000 * waktu["kotak"] / n, seg_ms=1000 * waktu["seg"] / n,
                    catatan="batch 16, GPU, kotak imgsz 960, seg imgsz 640, conf 0,05, termasuk baca gambar")
        (OUT / "waktu_prediksi.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        log(f"- [R4-0.3] Prediksi di {n} frame pool: kotak r2-kotak-v3-960 (imgsz 960) {info['kotak_ms']:.1f} ms/frame, "
            f"seg r2-seg-v3 (imgsz 640) {info['seg_ms']:.1f} ms/frame (GPU, batch 16, conf 0,05). Cache: data/ronde4/pred-cache/. "
            f"Embedding/pHash/Laplacian dipakai ulang dari data/ronde2/pred-cache/.")
    with (OUT / "pool.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["stem", "video", "lokasi", "pov", "t", "jarak_label_s", "berlabel"])
        for r in lab:
            wr.writerow([r["stem"], r["video"], r["lokasi"], r["pov"], f"{r['t']:.3f}", "0", 1])
        for r in pool:
            wr.writerow([r["stem"], r["video"], r["lokasi"], r["pov"], f"{r['t']:.3f}", f"{r['jarak_label']:.1f}", 0])


def muat_cache(stem, pred=True):
    c = pickle.loads((CACHE_R2 / f"{stem}.pkl").read_bytes())
    out = {k: c[k] for k in ("stem", "h", "w", "embed", "lap", "lum", "phash")}
    if pred:
        p = pickle.loads((CACHE / f"{stem}.pkl").read_bytes())
        out["kotak"], out["seg"] = p["kotak"], p["seg"]
    return out


# ------------------------------------------------------------------ studi (VAL, pengukuran saja)
def cmd_studi(a):
    from ultralytics import YOLO

    vk = ROOT / "data/dataset-kampus-kotak-v2"
    vs = ROOT / "data/dataset-kampus-seg-v2"
    imgs = sorted((vk / "images/val").glob("*.jpg"))
    assert len(imgs) == 54, len(imgs)
    for p in imgs:
        if jenis_lokasi(lokasi_dari(p.stem)) != "val":
            sys.exit(f"BERHENTI: {p.name} bukan lokasi val")
    mk, ms = YOLO(str(M_KOTAK)), YOLO(str(M_SEG))
    CONFS = (0.15, 0.25, 0.35)
    st = defaultdict(Counter)
    piks = defaultdict(Counter)
    for p in imgs:
        rk = mk.predict(str(p), imgsz=IMGSZ_KOTAK, conf=0.05, device=0, verbose=False)[0]
        rs = ms.predict(str(p), imgsz=IMGSZ_SEG, conf=0.05, device=0, verbose=False)[0]
        h, w = rk.orig_shape
        gt = baca_yolo(vk / "labels/val" / f"{p.stem}.txt", w, h, False)
        auto = kotak_auto(ROOT / "data/pilot-v2-auto-backup" / f"{p.stem}.json")
        auto = {k: [(b, s) for b, s in v if r4_lolos(k, *b)] for k, v in auto.items()}
        model_all = defaultdict(list)
        for c, cf, b in zip(rk.boxes.cls.cpu().numpy(), rk.boxes.conf.cpu().numpy(), rk.boxes.xyxy.cpu().numpy()):
            k = KOTAK[int(c)]
            if r4_lolos(k, *b):
                model_all[k].append((b, float(cf)))
        for k in KOTAK:
            srcs = {}
            for cf in CONFS:
                srcs[f"model@{cf:.2f}"] = [x for x in model_all[k] if x[1] >= cf]
            srcs["auto"] = auto.get(k, [])
            for cf in CONFS:
                m = srcs[f"model@{cf:.2f}"]
                srcs[f"union@{cf:.2f}"] = list(m) + [x for x in srcs["auto"] if not any(iou1(x[0], [y[0]])[0] > 0.5 for y in m)]
            for nm, pr in srcs.items():
                ious, fp, fn = cocok(gt.get(k, []), pr)
                c = st[(nm, k)]
                c["n_gt"] += len(gt.get(k, []))
                c["n_draft"] += len(pr)
                c["tp"] += len(ious)
                c["tp_low"] += sum(1 for v in ious if v < 0.7)
                c["fp"] += fp
                c["fn"] += fn
        gs = baca_yolo(vs / "labels/val" / f"{p.stem}.txt", w, h, True)
        pa = poly_auto(ROOT / "data/pilot-v2-auto-backup" / f"{p.stem}.json")
        mpoly = defaultdict(lambda: defaultdict(list))
        if rs.masks is not None:
            for c, cf, poly in zip(rs.boxes.cls.cpu().numpy(), rs.boxes.conf.cpu().numpy(), rs.masks.xy):
                for t in (0.25, 0.50):
                    if cf >= t:
                        mpoly[f"model@{t:.2f}"][SEG[int(c)]].append(poly)
        for k in SEG:
            G = raster(gs.get(k, []), w, h)
            for nm, polys in [("auto", pa.get(k, []))] + [(n, mpoly[n][k]) for n in ("model@0.25", "model@0.50")]:
                P = raster(polys, w, h)
                c = piks[(nm, k)]
                c["inter"] += int((G & P).sum())
                c["union"] += int((G | P).sum())
                c["pred"] += int(P.sum())
                c["gt"] += int(G.sum())
                c["n_poly"] += len(polys)
                c["n_gt_poly"] += len(gs.get(k, []))
    baris = []
    for (nm, k), c in sorted(st.items(), key=lambda x: (KOTAK.index(x[0][1]), x[0][0])):
        biaya = 5 * c["fn"] + 2 * c["fp"] + 3 * c["tp_low"]
        baris.append(dict(jenis="kotak", kelas=k, sumber=nm, n_gt=c["n_gt"], n_draft=c["n_draft"], tp=c["tp"], tp_iou_lt07=c["tp_low"],
                          fp=c["fp"], fn=c["fn"], P=round(c["tp"] / max(c["tp"] + c["fp"], 1), 3), R=round(c["tp"] / max(c["n_gt"], 1), 3),
                          biaya=biaya, iou_piksel="", P_piksel="", R_piksel=""))
    for (nm, k), c in sorted(piks.items(), key=lambda x: (SEG.index(x[0][1]), x[0][0])):
        baris.append(dict(jenis="permukaan", kelas=k, sumber=nm, n_gt=c["n_gt_poly"], n_draft=c["n_poly"], tp="", tp_iou_lt07="", fp="", fn="",
                          P="", R="", biaya="", iou_piksel=round(c["inter"] / max(c["union"], 1), 3),
                          P_piksel=round(c["inter"] / max(c["pred"], 1), 3), R_piksel=round(c["inter"] / max(c["gt"], 1), 3)))
    pil = {}
    for k in KOTAK:
        cand = [b for b in baris if b["jenis"] == "kotak" and b["kelas"] == k]
        pil[k] = min(cand, key=lambda b: (b["biaya"], b["sumber"]))["sumber"]
    for k in SEG:
        cand = [b for b in baris if b["jenis"] == "permukaan" and b["kelas"] == k]
        pil["seg:" + k] = max(cand, key=lambda b: (b["iou_piksel"], b["sumber"]))["sumber"]
    for b in baris:
        key = b["kelas"] if b["jenis"] == "kotak" else "seg:" + b["kelas"]
        b["dipilih"] = int(pil[key] == b["sumber"])
    with (OUT / "sumber_draft.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, list(baris[0].keys()))
        wr.writeheader()
        wr.writerows(baris)
    (OUT / "sumber_draft_pilihan.json").write_text(json.dumps(pil, indent=2), encoding="utf-8")
    log(f"- [R4-0.4] Studi sumber draft di 54 frame val (pengukuran saja, tidak ada yang ditulis ke val; model r2-kotak-v3-960 imgsz 960, "
        f"r2-seg-v3 imgsz 640): data/ronde4/sumber_draft.csv. Pilihan termurah: {pil}")


# ------------------------------------------------------------------ pilih
def cmd_pilih(a):
    rng = random.Random(SEED)
    pool, lab, ring = bangun_pool()
    for r in pool + lab:
        cek_train(r["lokasi"])
    ganti = json.loads(Path(a.ganti).read_text(encoding="utf-8")) if a.ganti else {}
    C = {r["stem"]: muat_cache(r["stem"]) for r in pool}
    C.update({r["stem"]: muat_cache(r["stem"], pred=False) for r in lab})
    stems_all = [r["stem"] for r in lab + pool]
    E = np.stack([C[s]["embed"] for s in stems_all])
    En = E - E.mean(0)
    En /= np.linalg.norm(En, axis=1, keepdims=True) + 1e-9
    idx = {s: i for i, s in enumerate(stems_all)}

    per_video = defaultdict(list)
    for r in pool + lab:
        per_video[r["video"]].append(r)
    # median Laplacian memakai SEMUA frame video yang ada di cache ronde 2 (termasuk yang dekat frame berlabel)
    lap_video = defaultdict(list)
    man_cache = {}
    for p in CACHE_R2.glob("*.pkl"):
        v = p.stem.rsplit("_t", 1)[0]
        if jenis_lokasi(lokasi_dari(v)) != "train":
            continue
        if v not in man_cache:
            man_cache[v] = baca_manifest(FB / v)
        lap_video[v].append((man_cache[v][p.stem], pickle.loads(p.read_bytes())["lap"]))
    med_video = {v: float(np.median([x[1] for x in xs])) for v, xs in lap_video.items()}
    blur = {}
    for r in pool:
        tet = [lp for t, lp in lap_video[r["video"]] if abs(t - r["t"]) <= 5.0]
        lp = C[r["stem"]]["lap"]
        blur[r["stem"]] = lp < BLUR_REL * float(np.median(tet)) or lp < BLUR_ABS
    n_blur = sum(blur.values())

    def preds(s):
        k = C[s]["kotak"]
        for c, cf, b in zip(k["cls"], k["conf"], k["xyxy"]):
            yield KOTAK[int(c)], float(cf), b

    skor = {}
    for r in pool:
        s = r["stem"]
        h = C[s]["h"]
        n, u, o = Counter(), Counter(), Counter()
        for k, cf, b in preds(s):
            if not r4_lolos(k, *b):
                continue
            if 0.15 <= cf <= 0.60 and b[3] >= Y2_DEKAT * h:
                n[k] += 1
            if 0.15 <= cf <= 0.50:
                u[k] += 1
            if cf >= 0.15 and k in ("pohon", "tepian", "kendaraan"):
                o[k] += 1
        tg_box = max([cf for k, cf, b in preds(s) if k == "tangga"], default=0.0)
        sg = C[s]["seg"]
        tg_seg = max([float(cf) for c, cf in zip(sg["cls"], sg["conf"]) if SEG[int(c)] == "tangga"], default=0.0)
        skor[s] = dict(N=sum(BOBOT_N.get(k, BOBOT_LAIN) * v for k, v in n.items()), N_detail=dict(n),
                       U=sum(BOBOT_U.get(k, BOBOT_LAIN) * v for k, v in u.items()), U_detail=dict(u),
                       O=sum(o.values()), O_detail=dict(o), E=max(tg_box, tg_seg), E_box=tg_box, E_seg=tg_seg,
                       lum=C[s]["lum"], lap=C[s]["lap"])

    terpilih, tol = [], {}
    pov_n, vid_n = Counter(), Counter()
    luar_target = int(np.ceil(LUAR_MIN * TARGET))
    t_lab = defaultdict(list)
    for r in lab:
        t_lab[r["video"]].append(r["t"])

    def celah(r):
        """jarak waktu ke frame berlabel ATAU terpilih terdekat di video yang sama."""
        ts = t_lab[r["video"]] + [x["t"] for x in terpilih if x["video"] == r["video"]]
        return min((abs(r["t"] - t) for t in ts), default=1e9)

    def n_luar():
        return sum(x["lokasi"] in LUAR for x in terpilih)

    def boleh(r, lap_min=0.0):  # noqa: F811 (lap_min dibaca saat dipanggil)
        if r["stem"] in ganti:
            return "dibuang cek visual"
        if blur[r["stem"]]:
            return "buram"
        if lap_min and C[r["stem"]]["lap"] < lap_min * med_video[r["video"]]:
            return "kurang tajam (pengganti)"
        if any(x["stem"] == r["stem"] for x in terpilih):
            return "sudah"
        if vid_n[r["video"]] >= (MAKS_VIDEO_LUAR if r["lokasi"] in LUAR else MAKS_VIDEO):
            return "maks per video"
        for x in terpilih:
            if x["video"] == r["video"] and abs(x["t"] - r["t"]) < JARAK_PILIH:
                return "< 3 s dari terpilih"
        i, ph = idx[r["stem"]], C[r["stem"]]["phash"]
        for x in lab + terpilih:
            if x["lokasi"] != r["lokasi"]:
                continue
            cs = float(En[i] @ En[idx[x["stem"]]])
            if cs >= COS_DUP:
                return f"duplikat cos {cs:.2f} vs {x['stem']}"
            hd = ham(ph, C[x["stem"]]["phash"])
            if hd <= PHASH_DUP:
                return f"duplikat phash {hd} vs {x['stem']}"
        return None

    def ambil(r, bucket, alasan):
        r = dict(r)
        r["bucket"], r["alasan"] = bucket, (("pengganti cek visual; " if ganti and lap_min else "") + alasan)
        terpilih.append(r)
        pov_n[r["pov"]] += 1
        vid_n[r["video"]] += 1

    def pov_ok(r):
        return pov_n[r["pov"]] - pov_n["mata" if r["pov"] == "dada" else "dada"] < 3

    jit = {r["stem"]: rng.random() * 1e-6 for r in pool}
    lap_min = BLUR_GANTI if ganti else 0.0   # setelah cek visual: semua pilihan baru harus >= 1,25 x median video

    def alasan_dari(bucket, r):
        sk = skor[r["stem"]]
        det = lambda d: ", ".join(f"{k} {n}" for k, n in sorted(d.items(), key=lambda x: -x[1]))  # noqa: E731
        if bucket == "E":
            return f"tangga di eskalator? box {sk['E_box']:.2f} seg {sk['E_seg']:.2f}"
        if bucket == "N":
            return "ragu dekat: " + det(sk["N_detail"])
        if bucket == "O":
            return f"luar, celah {celah(r):.0f} s; " + det(sk["O_detail"])
        if bucket == "U":
            return "ragu: " + det(sk["U_detail"])
        return f"celah {celah(r):.0f} s dari frame berlabel/terpilih"

    def isi(bucket, q, lama=None):
        """lama: dict stem -> bucket dari pilihan sebelum cek visual (dipertahankan dulu supaya penggantian minimal)."""
        n0 = len(terpilih)
        if bucket == "W":
            kand = list(pool)
            Ef = En[[idx[r["stem"]] for r in kand]]
            maxcos = (Ef @ En[[idx[x["stem"]] for x in lab + terpilih]].T).max(1)
            while len(terpilih) - n0 < q:
                order = np.argsort(-(1 - maxcos))
                pil = None
                for tahap in ((True, True), (True, False), (False, False)):
                    for i in order:
                        r = kand[i]
                        if tahap[0] and n_luar() < luar_target and r["lokasi"] not in LUAR:
                            continue
                        if tahap[1] and not pov_ok(r):
                            continue
                        al = boleh(r, lap_min)
                        if al is None:
                            pil = i
                            break
                        tol.setdefault(r["stem"], al)
                    if pil is not None:
                        break
                if pil is None:
                    break
                ambil(kand[pil], "W", f"terjauh dari berlabel+terpilih (1-cos {1 - maxcos[pil]:.2f})")
                maxcos = np.maximum(maxcos, Ef @ En[idx[kand[pil]["stem"]]])
            return len(terpilih) - n0
        elig = {
            "E": lambda r: r["lokasi"] == "lorong-lt3-eskalator-alfa-tower" and skor[r["stem"]]["E"] >= 0.25,
            "N": lambda r: skor[r["stem"]]["N"] > 0,
            "O": lambda r: r["lokasi"] in LUAR and celah(r) >= CELAH_O,
            "U": lambda r: skor[r["stem"]]["U"] > 0,
            "G": lambda r: celah(r) >= CELAH_G,
        }[bucket]
        kunci = {
            "E": lambda r: -(skor[r["stem"]]["E"] + jit[r["stem"]]),
            "N": lambda r: -(skor[r["stem"]]["N"] + jit[r["stem"]]),
            "O": lambda r: (-skor[r["stem"]]["O"], -(skor[r["stem"]]["U"] + jit[r["stem"]])),
            "U": lambda r: -(skor[r["stem"]]["U"] + jit[r["stem"]]),
            "G": lambda r: -(celah(r) + jit[r["stem"]]),
        }[bucket]
        if bucket in ("N", "U", "G"):
            sisa_slot = TARGET - len(terpilih)
            luar_b = int(np.ceil(q * max(0, luar_target - n_luar()) / max(1, sisa_slot)))
        else:
            luar_b = 0
        for tahap in ("luar", "pov", "bebas"):
            while len(terpilih) - n0 < q:
                # celah berubah tiap kali ada frame terpilih -> kandidat O/G dihitung ulang tiap langkah
                kand = sorted((r for r in pool if elig(r)), key=kunci)
                dapat = False
                for r in kand:
                    if tahap == "luar" and (r["lokasi"] not in LUAR or sum(x["lokasi"] in LUAR for x in terpilih[n0:]) >= luar_b):
                        continue
                    if tahap in ("luar", "pov") and not pov_ok(r):
                        continue
                    al = boleh(r, lap_min)
                    if al:
                        tol.setdefault(r["stem"], al)
                        continue
                    ambil(r, bucket, alasan_dari(bucket, r))
                    dapat = True
                    break
                if not dapat:
                    break
        return len(terpilih) - n0

    kurang = 0
    hasil = {}
    kuota = dict(KUOTA)
    if ganti:
        # pertahankan pilihan sebelum cek visual (pilihan_awal.csv); hanya frame di ganti.json yang diganti, per bucket
        P = {r["stem"]: r for r in pool}
        lap_min_simpan, lap_min = lap_min, 0.0
        kuota = {k: 0 for k in KUOTA}
        with Path(a.awal).open(encoding="utf-8") as f:
            for x in csv.DictReader(f):
                if x["stem"] in ganti:
                    kuota[x["bucket"]] += 1
                else:
                    ambil(P[x["stem"]], x["bucket"], x["alasan"])
        lap_min = lap_min_simpan
    for b in URUTAN:
        q = kuota[b] + (kurang if b == "U" else 0)
        n = isi(b, q)
        hasil[b] = n
        if b == "U":
            kurang = 0
        kurang += q - n if b != "U" else max(0, q - n)
    if len(terpilih) < TARGET:   # kekurangan G/W (setelah U) juga mengalir ke U
        hasil["U"] += isi("U", TARGET - len(terpilih))
    if a.hanya_u:
        pass
    elif len(terpilih) < TARGET:   # U habis (kandidat ragu tersisa hanya di video yang sudah penuh): sisanya diisi W (LOG R4-0.6)
        hasil["W"] += isi("W", TARGET - len(terpilih))
    if len(terpilih) < TARGET and lap_min and not a.hanya_u:   # pengganti setajam 1,25 x median habis: sisa memakai aturan buram biasa (dicek visual lagi)
        lap_min = 0.0
        hasil["U"] += isi("U", TARGET - len(terpilih))
        hasil["W"] += isi("W", TARGET - len(terpilih))

    luar = n_luar()
    with (OUT / "pilihan.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["stem", "video", "lokasi", "pov", "t", "bucket", "skor_N", "N_detail", "skor_U", "U_detail", "skor_O", "jarak_label_s",
                     "tangga_box", "tangga_seg", "luminansi", "laplacian", "lap_median_video", "luar", "alasan"])
        for r in terpilih:
            sk = skor[r["stem"]]
            wr.writerow([r["stem"], r["video"], r["lokasi"], r["pov"], f"{r['t']:.3f}", r["bucket"], f"{sk['N']:.1f}", json.dumps(sk["N_detail"]),
                         f"{sk['U']:.1f}", json.dumps(sk["U_detail"]), sk["O"], f"{r['jarak_label']:.1f}", f"{sk['E_box']:.2f}",
                         f"{sk['E_seg']:.2f}", f"{sk['lum']:.0f}", f"{sk['lap']:.0f}", f"{med_video[r['video']]:.0f}",
                         int(r["lokasi"] in LUAR), r["alasan"]])
    info = dict(n=len(terpilih), per_bucket=Counter(r["bucket"] for r in terpilih), per_lokasi=Counter(r["lokasi"] for r in terpilih),
                per_video=Counter(r["video"] for r in terpilih), pov=Counter(r["pov"] for r in terpilih), luar=luar,
                luar_porsi=round(luar / max(1, len(terpilih)), 3), buram_pool=n_blur, pool=len(pool),
                dibuang_cek_visual=len(ganti), maks_video=MAKS_VIDEO, maks_video_luar=MAKS_VIDEO_LUAR,
                tolak=Counter(v.split(" ")[0] for v in tol.values()))
    (OUT / "pilihan_info.json").write_text(json.dumps(info, indent=2, default=dict), encoding="utf-8")
    print(json.dumps(info, indent=2, default=dict))
    for r in terpilih:
        cek_train(r["lokasi"])
        assert not di_bocor(r["video"], r["t"])
    sheets(terpilih, C)
    log(f"- [R4-0.5] Pilihan {len(terpilih)} frame (seed {SEED}{', ganti ' + str(len(ganti)) + ' frame setelah cek visual' if ganti else ''}): "
        f"{dict(info['per_bucket'])}, luar {luar} ({100 * luar / max(1, len(terpilih)):.0f}%), pov {dict(info['pov'])}. "
        f"Buram di pool {n_blur}. Berkas: data/ronde4/pilihan.csv, pilihan_*.png, pilihan_info.json.")


def sheets(terpilih, C):
    for f in OUT.glob("pilihan_*.png"):
        f.unlink()  # sheet lama buatan skrip ini sendiri
    for b in URUTAN:
        rs = [r for r in terpilih if r["bucket"] == b]
        per = 30
        for n, i0 in enumerate(range(0, len(rs), per)):
            ths = []
            for j, r in enumerate(rs[i0:i0 + per]):
                r = dict(r)
                r["alasan"] = f"#{i0 + j + 1} " + r["alasan"]
                if "pengganti" in r["alasan"] or "isi akhir" in r["alasan"]:
                    r["lokasi"] = "*GANTI* " + r["lokasi"]
                ths.append(r2.thumb(r, C[r["stem"]]))
            kol = 10
            hmax = max(t.shape[0] for t in ths)
            ths = [np.vstack([t, np.full((hmax - t.shape[0], t.shape[1], 3), 255, np.uint8)]) for t in ths]
            while len(ths) % kol:
                ths.append(np.full_like(ths[0], 255))
            rows = [np.hstack([np.hstack([t, np.full((hmax, 6, 3), 255, np.uint8)]) for t in ths[i:i + kol]]) for i in range(0, len(ths), kol)]
            cv2.imwrite(str(OUT / (f"pilihan_{b}.png" if len(rs) <= per else f"pilihan_{b}_{n + 1}.png")), np.vstack(rows))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("aksi", choices=["pool", "studi", "pilih"])
    ap.add_argument("--awal", default=str(OUT / "pilihan_awal.csv"), help="pilihan yang dipertahankan pada mode --ganti")
    ap.add_argument("--target", type=int, help="ganti TARGET (keputusan Jeka R4-0: 150)")
    ap.add_argument("--lap-ganti", type=float, help="ganti BLUR_GANTI (0 = aturan buram biasa untuk slot baru)")
    ap.add_argument("--hanya-u", action="store_true", help="slot tambahan hanya dari U (tanpa isi akhir W)")
    ap.add_argument("--ganti", help="JSON {stem: alasan} frame yang dibuang setelah cek visual (diganti otomatis)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    global TARGET, BLUR_GANTI
    if a.target:
        TARGET = a.target
    if a.lap_ganti is not None:
        BLUR_GANTI = a.lap_ganti
    {"pool": cmd_pool, "studi": cmd_studi, "pilih": cmd_pilih}[a.aksi](a)


if __name__ == "__main__":
    main()
