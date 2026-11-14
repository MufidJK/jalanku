"""ronde2_pilih.py - ronde 2 JalanKu, CHECKPOINT R0: pool kandidat, cache prediksi, studi sumber draft (val), pilih frame.

Dijalankan dari root repo. Semua keluaran di data/ronde2/ (tidak menyentuh dataset lama, label, atau data/frame-blur).

Langkah:
  python tools/ronde2_pilih.py pool     # pool kandidat + prediksi kotak/seg + embedding + blur/pHash/luminansi -> data/ronde2/pred-cache/
  python tools/ronde2_pilih.py studi    # studi sumber draft di VAL (pengukuran saja) -> data/ronde2/sumber_draft.csv
  python tools/ronde2_pilih.py pilih    # pilih ~70 frame (seed 20261113) -> data/ronde2/pilihan.csv + pilihan_*.png

Aturan keras (dicek di kode, berhenti kalau dilanggar):
  - Frame baru hanya dari lokasi TRAINING. Lokasi TEST tidak pernah dibaca, model tidak pernah dijalankan di sana.
  - Lokasi VAL hanya dipakai di `studi` untuk pengukuran; tidak ada yang ditulis ke label val.
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

ROOT = Path(__file__).resolve().parent.parent
FB = ROOT / "data/frame-blur"
OUT = ROOT / "data/ronde2"
CACHE = OUT / "pred-cache"
M_KOTAK = ROOT / "models/baseline/kotak-gabung_best.pt"
M_SEG = ROOT / "models/baseline/seg-kampus_best.pt"
LABEL_DIRS = [ROOT / "data/pilot-v2", ROOT / "data/pilot-v2-blind"]

TEST = ("selasar-lt11", "pot-lt11", "taman-ubm")
VAL = ("dapsut", "perpus-lt9-ubm-tower", "tangga-naik-lt9-lt10-ubm-tower")
LUAR = ("jalanan-ubm", "samping-ubm", "halaman-ubm")
KOTAK = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"]
SEG = ["jalur_jalan", "jalan_kendaraan", "tangga"]
TIPIS = {"pilar", "pohon", "tepian"}
SEED = 20261113
JARAK_LABEL = 3.0      # pool: buang frame < 3 s dari frame berlabel di video yang sama
JARAK_PILIH = 3.0      # antar frame terpilih di video yang sama
MAKS_VIDEO = 5
BOBOT_U = {"pilar": 1.5, "tepian": 1.5, "pohon": 1.2, "tanaman_pot": 1.0}
BOBOT_LAIN = 0.3
KUOTA = [("U", 35), ("G", 12), ("E", 8), ("D", 7), ("W", 8)]
# urutan pengisian: bucket langka dulu (kandidat E/D/G hanya ada di sedikit video; kalau U duluan, jatah 5/video habis)
URUTAN = ["E", "D", "G", "U", "W"]
COS_DUP = 0.85
PHASH_DUP = 6
BLUR_REL, BLUR_ABS = 0.5, 15.0   # sama dengan test set: < 0,5 x median tetangga (+-5 s) atau < 15
CELAH_G = 25.0


def lokasi_dari(nama):
    return nama.split("_")[0]


def jenis_lokasi(lok):
    if lok.startswith(TEST):
        return "test"
    if lok in VAL:
        return "val"
    return "train"


def cek_train(lok):
    """Berhenti keras kalau lokasi bukan training."""
    if lok.startswith(TEST) or lok in VAL or jenis_lokasi(lok) != "train":
        sys.exit(f"BERHENTI: lokasi {lok} bukan lokasi training")


def r4_lolos(kelas, x1, y1, x2, y2):
    w, h = x2 - x1, y2 - y1
    pendek, panjang = min(w, h), max(w, h)
    if kelas in TIPIS:
        return panjang >= 96 and pendek >= 24
    return pendek >= 96


def log(baris):
    with (OUT / "LOG.md").open("a", encoding="utf-8") as f:
        f.write(baris.rstrip() + "\n")
    print(baris, flush=True)


# ------------------------------------------------------------------ pool
def daftar_video():
    out = []
    for d in sorted(FB.iterdir()):
        if not d.is_dir():
            continue
        lok = lokasi_dari(d.name)
        out.append((d, lok, jenis_lokasi(lok)))
    return out


def baca_manifest(d):
    t = {}
    with (d / "_manifest.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t[Path(r["filename"]).stem] = float(r["timestamp_s"])
    return t


def stem_berlabel():
    s = set()
    for d in LABEL_DIRS:
        s |= {p.stem for p in d.glob("*.json")}
    return s


def bangun_pool():
    """-> (pool list of dict, labeled-train list of dict, ringkasan)."""
    berlabel = stem_berlabel()
    pool, lab_train, ring = [], [], Counter()
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
                lab_train.append(rec)
                continue
            dmin = min((abs(t - x) for x in t_lab), default=1e9)
            rec["jarak_label"] = dmin
            if dmin < JARAK_LABEL:
                ring["dekat_label"] += 1
                continue
            pool.append(rec)
    ring["pool"] = len(pool)
    return pool, lab_train, ring


def phash(gray):
    g = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    d = cv2.dct(g)[:8, :8].flatten()
    return np.packbits(d > np.median(d))


def ham(a, b):
    return int(np.unpackbits(np.bitwise_xor(a, b)).sum())


def cmd_pool(a):
    from ultralytics import YOLO

    CACHE.mkdir(parents=True, exist_ok=True)
    pool, lab_train, ring = bangun_pool()
    semua = lab_train + pool
    for r in semua:
        cek_train(r["lokasi"])
    log(f"- [R0-1] Pool: lokasi training {ring['train_total']} frame, berlabel {ring['berlabel']}, "
        f"dibuang < {JARAK_LABEL:g} s dari frame berlabel {ring['dekat_label']}, pool {ring['pool']}.")
    mk, ms = YOLO(str(M_KOTAK)), YOLO(str(M_SEG))
    waktu = Counter()
    todo = [r for r in semua if not (CACHE / f"{r['stem']}.pkl").exists()]
    print(f"cache ada {len(semua) - len(todo)}, perlu {len(todo)}", flush=True)
    B = 16
    for i in range(0, len(todo), B):
        grp = todo[i:i + B]
        paths = [str(r["path"]) for r in grp]
        t0 = time.perf_counter()
        rk = mk.predict(paths, imgsz=640, conf=0.05, device=0, verbose=False, batch=B)
        t1 = time.perf_counter()
        rs = ms.predict(paths, imgsz=640, conf=0.05, device=0, verbose=False, batch=B, retina_masks=False)
        t2 = time.perf_counter()
        em = mk.embed(paths, imgsz=640, device=0, verbose=False, batch=B)
        t3 = time.perf_counter()
        waktu["kotak"] += t1 - t0
        waktu["seg"] += t2 - t1
        waktu["embed"] += t3 - t2
        waktu["n"] += len(grp)
        for r, a1, a2, e in zip(grp, rk, rs, em):
            img = cv2.imread(str(r["path"]))
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            g540 = cv2.resize(gray, (540, 960), interpolation=cv2.INTER_AREA)
            rec = dict(
                stem=r["stem"], h=a1.orig_shape[0], w=a1.orig_shape[1],
                kotak=dict(cls=a1.boxes.cls.cpu().numpy().astype(np.int16), conf=a1.boxes.conf.cpu().numpy().astype(np.float32),
                           xyxy=a1.boxes.xyxy.cpu().numpy().astype(np.float32)),
                seg=dict(cls=a2.boxes.cls.cpu().numpy().astype(np.int16), conf=a2.boxes.conf.cpu().numpy().astype(np.float32),
                         xyxy=a2.boxes.xyxy.cpu().numpy().astype(np.float32),
                         poly=[x.astype(np.float32) for x in a2.masks.xy] if a2.masks is not None else []),
                embed=e.cpu().numpy().astype(np.float32).ravel(),
                lap=float(cv2.Laplacian(g540, cv2.CV_64F).var()), lum=float(gray.mean()), phash=phash(gray),
            )
            (CACHE / f"{r['stem']}.pkl").write_bytes(pickle.dumps(rec))
        print(f"{min(i + B, len(todo))}/{len(todo)}", flush=True)
    if waktu["n"]:
        n = waktu["n"]
        info = dict(n=n, kotak_ms=1000 * waktu["kotak"] / n, seg_ms=1000 * waktu["seg"] / n, embed_ms=1000 * waktu["embed"] / n,
                    catatan="batch 16, GPU, imgsz 640, termasuk baca gambar; tanpa fitur blur/pHash")
        (OUT / "waktu_prediksi.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        log(f"- [R0-2] Prediksi di {n} frame (pool + {len(lab_train)} frame train berlabel untuk referensi embedding/pHash): "
            f"kotak {info['kotak_ms']:.1f} ms/frame, seg {info['seg_ms']:.1f} ms/frame, embedding {info['embed_ms']:.1f} ms/frame "
            f"(GPU, batch 16, imgsz 640, conf 0,05). Cache: data/ronde2/pred-cache/ ({len(semua)} pkl).")
    # tabel pool
    with (OUT / "pool.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["stem", "video", "lokasi", "pov", "t", "jarak_label_s", "berlabel"])
        for r in lab_train:
            wr.writerow([r["stem"], r["video"], r["lokasi"], r["pov"], f"{r['t']:.3f}", "0", 1])
        for r in pool:
            wr.writerow([r["stem"], r["video"], r["lokasi"], r["pov"], f"{r['t']:.3f}", f"{r['jarak_label']:.1f}", 0])


def muat_cache(stem):
    return pickle.loads((CACHE / f"{stem}.pkl").read_bytes())


# ------------------------------------------------------------------ studi (VAL, pengukuran saja)
def iou1(a, B):
    if len(B) == 0:
        return np.zeros(0)
    B = np.asarray(B, float)
    x1, y1 = np.maximum(a[0], B[:, 0]), np.maximum(a[1], B[:, 1])
    x2, y2 = np.minimum(a[2], B[:, 2]), np.minimum(a[3], B[:, 3])
    it = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    return it / np.maximum((a[2] - a[0]) * (a[3] - a[1]) + (B[:, 2] - B[:, 0]) * (B[:, 3] - B[:, 1]) - it, 1e-9)


def cocok(gt, pr):
    """gt: list xyxy; pr: list (xyxy, skor). Greedy per skor, IoU >= 0,5. -> tp_iou(list), fp, fn."""
    pakai, ious, fp = set(), [], 0
    for j in sorted(range(len(pr)), key=lambda j: -pr[j][1]):
        v = iou1(pr[j][0], gt)
        for i in pakai:
            v[i] = 0
        if len(v) and v.max() >= 0.5:
            i = int(v.argmax())
            pakai.add(i)
            ious.append(float(v[i]))
        else:
            fp += 1
    return ious, fp, len(gt) - len(pakai)


def kotak_auto(js):
    """JSON X-AnyLabeling -> {kelas: [(xyxy, skor)]}, tangga satu kotak per frame (seperti builder)."""
    d = json.loads(Path(js).read_text(encoding="utf-8"))
    out, tg, tgs = defaultdict(list), [], []
    for s in d["shapes"]:
        lab = s["label"]
        if lab not in KOTAK:
            continue
        p = np.asarray(s["points"], float)
        if len(p) < 3:
            continue
        sk = float(s.get("score") or 0.5)
        if lab == "tangga":
            tg.append(p)
            tgs.append(sk)
            continue
        out[lab].append((np.r_[p.min(0), p.max(0)], sk))
    if tg:
        p = np.vstack(tg)
        out["tangga"].append((np.r_[p.min(0), p.max(0)], max(tgs)))
    return out


def poly_auto(js):
    d = json.loads(Path(js).read_text(encoding="utf-8"))
    out = defaultdict(list)
    for s in d["shapes"]:
        if s["label"] in SEG and len(s["points"]) >= 3:
            out[s["label"]].append(np.asarray(s["points"], float))
    return out


def raster(polys, w, h, s=0.25):
    m = np.zeros((int(h * s) + 1, int(w * s) + 1), np.uint8)
    for p in polys:
        if len(p) >= 3:
            cv2.fillPoly(m, [np.round(np.asarray(p) * s).astype(np.int32)], 1)
    return m.astype(bool)


def baca_yolo(txt, w, h, seg):
    out = defaultdict(list)
    if not txt.exists():
        return out
    for ln in txt.read_text().splitlines():
        v = ln.split()
        if not v:
            continue
        c, a = int(v[0]), np.array([float(x) for x in v[1:]])
        if seg:
            out[SEG[c]].append(a.reshape(-1, 2) * [w, h])
        else:
            xc, yc, bw, bh = a
            out[KOTAK[c]].append(np.array([(xc - bw / 2) * w, (yc - bh / 2) * h, (xc + bw / 2) * w, (yc + bh / 2) * h]))
    return out


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
    st = defaultdict(lambda: Counter())   # (sumber, kelas) -> tp, tp_low, fp, fn, n_draft
    piks = defaultdict(lambda: Counter())  # (sumber, kelas) -> inter, union, pred, gt
    for p in imgs:
        rk = mk.predict(str(p), imgsz=640, conf=0.05, device=0, verbose=False)[0]
        rs = ms.predict(str(p), imgsz=640, conf=0.05, device=0, verbose=False)[0]
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
                u = list(m) + [x for x in srcs["auto"] if not any(iou1(x[0], [y[0]])[0] > 0.5 for y in m)]
                srcs[f"union@{cf:.2f}"] = u
            for nm, pr in srcs.items():
                ious, fp, fn = cocok(gt.get(k, []), pr)
                c = st[(nm, k)]
                c["n_gt"] += len(gt.get(k, []))
                c["n_draft"] += len(pr)
                c["tp"] += len(ious)
                c["tp_low"] += sum(1 for v in ious if v < 0.7)
                c["fp"] += fp
                c["fn"] += fn
        # permukaan
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
        P = c["tp"] / max(c["tp"] + c["fp"], 1)
        R = c["tp"] / max(c["n_gt"], 1)
        baris.append(dict(jenis="kotak", kelas=k, sumber=nm, n_gt=c["n_gt"], n_draft=c["n_draft"], tp=c["tp"], tp_iou_lt07=c["tp_low"],
                          fp=c["fp"], fn=c["fn"], P=round(P, 3), R=round(R, 3), biaya=biaya, iou_piksel="", P_piksel="", R_piksel=""))
    for (nm, k), c in sorted(piks.items(), key=lambda x: (SEG.index(x[0][1]), x[0][0])):
        baris.append(dict(jenis="permukaan", kelas=k, sumber=nm, n_gt=c["n_gt_poly"], n_draft=c["n_poly"], tp="", tp_iou_lt07="", fp="", fn="",
                          P="", R="", biaya="", iou_piksel=round(c["inter"] / max(c["union"], 1), 3),
                          P_piksel=round(c["inter"] / max(c["pred"], 1), 3), R_piksel=round(c["inter"] / max(c["gt"], 1), 3)))
    # pilihan per kelas
    pil = {}
    for k in KOTAK:
        cand = [b for b in baris if b["jenis"] == "kotak" and b["kelas"] == k]
        best = min(cand, key=lambda b: (b["biaya"], b["sumber"]))
        pil[k] = best["sumber"]
    for k in SEG:
        cand = [b for b in baris if b["jenis"] == "permukaan" and b["kelas"] == k]
        best = max(cand, key=lambda b: (b["iou_piksel"], b["sumber"]))
        pil["seg:" + k] = best["sumber"]
    for b in baris:
        key = b["kelas"] if b["jenis"] == "kotak" else "seg:" + b["kelas"]
        b["dipilih"] = int(pil[key] == b["sumber"])
    with (OUT / "sumber_draft.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, list(baris[0].keys()))
        wr.writeheader()
        wr.writerows(baris)
    (OUT / "sumber_draft_pilihan.json").write_text(json.dumps(pil, indent=2), encoding="utf-8")
    log(f"- [R0-3] Studi sumber draft di 54 frame val (pengukuran saja, tidak ada yang ditulis ke val): data/ronde2/sumber_draft.csv. "
        f"Pilihan termurah: {pil}")


# ------------------------------------------------------------------ pilih
def cmd_pilih(a):
    rng = random.Random(SEED)
    pool, lab_train, ring = bangun_pool()
    for r in pool + lab_train:
        cek_train(r["lokasi"])
    C = {r["stem"]: muat_cache(r["stem"]) for r in pool + lab_train}
    # embedding: dipusatkan (fitur pasca-aktivasi semuanya positif, cosine mentah ~ 1 untuk semua frame)
    stems_all = [r["stem"] for r in lab_train + pool]
    E = np.stack([C[s]["embed"] for s in stems_all])
    mu = E.mean(0)
    En = E - mu
    En /= np.linalg.norm(En, axis=1, keepdims=True) + 1e-9
    idx = {s: i for i, s in enumerate(stems_all)}
    raw = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
    # info distribusi cosine (dipusatkan) antar frame berurutan dan acak
    sampel = rng.sample(range(len(stems_all)), min(400, len(stems_all)))
    cs_acak = [float(En[i] @ En[j]) for i, j in zip(sampel[::2], sampel[1::2])]
    cs_raw = [float(raw[i] @ raw[j]) for i, j in zip(sampel[::2], sampel[1::2])]

    # blur: per video, median tetangga +-5 s
    per_video = defaultdict(list)
    for r in pool + lab_train:
        per_video[r["video"]].append(r)
    blur = {}
    for v, rs in per_video.items():
        for r in rs:
            tet = [C[x["stem"]]["lap"] for x in rs if abs(x["t"] - r["t"]) <= 5.0]
            med = float(np.median(tet))
            lp = C[r["stem"]]["lap"]
            blur[r["stem"]] = (lp < BLUR_REL * med) or (lp < BLUR_ABS)
    n_blur = sum(blur[r["stem"]] for r in pool)

    lab_by_video = defaultdict(list)
    for r in lab_train:
        lab_by_video[r["video"]].append(r["t"])

    def preds(s, conf_min=0.0):
        k = C[s]["kotak"]
        for c, cf, b in zip(k["cls"], k["conf"], k["xyxy"]):
            if cf >= conf_min:
                yield KOTAK[int(c)], float(cf), b

    # skor per bucket
    skor = {}
    for r in pool:
        s = r["stem"]
        u = Counter()
        for k, cf, b in preds(s):
            if 0.15 <= cf <= 0.50 and r4_lolos(k, *b):
                u[k] += 1
        su = sum(BOBOT_U.get(k, BOBOT_LAIN) * n for k, n in u.items())
        tg_box = max([cf for k, cf, b in preds(s) if k == "tangga"], default=0.0)
        sg = C[s]["seg"]
        tg_seg = max([float(cf) for c, cf in zip(sg["cls"], sg["conf"]) if SEG[int(c)] == "tangga"], default=0.0)
        skor[s] = dict(U=su, U_detail=dict(u), G=r["jarak_label"], E=max(tg_box, tg_seg), E_box=tg_box, E_seg=tg_seg,
                       D=-C[s]["lum"], lum=C[s]["lum"], lap=C[s]["lap"])
    elig = {
        "U": lambda r: skor[r["stem"]]["U"] > 0,
        "G": lambda r: r["jarak_label"] >= CELAH_G,
        "E": lambda r: r["lokasi"] == "lorong-lt3-eskalator-alfa-tower" and skor[r["stem"]]["E"] >= 0.25,
        "D": lambda r: r["lokasi"] in ("tangga-naik-alfa-lt2", "tangga-naik-lt3-alfa-tower"),
        "W": lambda r: True,
    }
    # D: utamakan gelap; "tangga turun" diberi bonus kalau ada di TURUN (diisi dari pemeriksaan visual, lihat LOG)
    TURUN = json.loads((OUT / "tangga_turun.json").read_text(encoding="utf-8")) if (OUT / "tangga_turun.json").exists() else {}

    def turun(r):
        for a0, a1 in TURUN.get(r["video"], []):
            if a0 <= r["t"] <= a1:
                return True
        return False

    terpilih = []
    tol = {}  # alasan tolak
    pov_n = Counter()
    vid_n = Counter()
    luar_target = int(np.ceil(0.40 * sum(q for _, q in KUOTA)))

    def dup_dengan(r, ref):
        i = idx[r["stem"]]
        ph = C[r["stem"]]["phash"]
        for x in ref:
            j = idx[x["stem"]]
            if float(En[i] @ En[j]) >= COS_DUP:
                return f"cos {float(En[i] @ En[j]):.2f} vs {x['stem']}"
            if ham(ph, C[x["stem"]]["phash"]) <= PHASH_DUP:
                return f"phash {ham(ph, C[x['stem']]['phash'])} vs {x['stem']}"
        return None

    def boleh(r):
        if blur[r["stem"]]:
            return "buram"
        if any(x["stem"] == r["stem"] for x in terpilih):
            return "sudah"
        if vid_n[r["video"]] >= MAKS_VIDEO:
            return "maks 5 per video"
        for x in terpilih:
            if x["video"] == r["video"] and abs(x["t"] - r["t"]) < JARAK_PILIH:
                return "< 3 s dari terpilih"
        # duplikat: hanya dibandingkan dengan frame lokasi yang sama (lokasi beda tidak mungkin kembar) - lebih cepat
        ref = [x for x in lab_train + terpilih if x["lokasi"] == r["lokasi"]]
        d = dup_dengan(r, ref)
        if d:
            return "duplikat " + d
        return None

    def ambil(r, bucket, alasan):
        r = dict(r)
        r["bucket"] = bucket
        r["alasan"] = alasan
        terpilih.append(r)
        pov_n[r["pov"]] += 1
        vid_n[r["video"]] += 1

    def pov_ok(r):
        return pov_n[r["pov"]] - pov_n["mata" if r["pov"] == "dada" else "dada"] < 3

    jitter = {r["stem"]: rng.random() * 1e-6 for r in pool}

    def urut(bucket, kand):
        if bucket == "U":
            return sorted(kand, key=lambda r: -(skor[r["stem"]]["U"] + jitter[r["stem"]]))
        if bucket == "G":
            return sorted(kand, key=lambda r: -(skor[r["stem"]]["G"] + jitter[r["stem"]]))
        if bucket == "E":
            return sorted(kand, key=lambda r: -(skor[r["stem"]]["E"] + jitter[r["stem"]]))
        if bucket == "D":
            return sorted(kand, key=lambda r: (-int(turun(r)), skor[r["stem"]]["lum"] + jitter[r["stem"]]))
        return kand

    # kuota luar per bucket non-indoor: target luar dibagi proporsional ke U, G, W
    q_luarbisa = sum(q for b, q in KUOTA if b in ("U", "G", "W"))
    sisa = 0
    KQ = dict(KUOTA)
    KUOTA_URUT = [(b, KQ[b]) for b in URUTAN]
    for bucket, q in KUOTA_URUT:
        q = q + sisa
        kand = [r for r in pool if elig[bucket](r)]
        n0 = len(terpilih)
        if bucket == "W":
            # farthest-point: jarak = 1 - cos maksimum ke semua berlabel + terpilih
            ref_idx = [idx[x["stem"]] for x in lab_train + terpilih]
            Ef = En[[idx[r["stem"]] for r in kand]]
            maxcos = (Ef @ En[ref_idx].T).max(1)
            n_luar_w = int(np.ceil(max(0, luar_target - sum(x["lokasi"] in LUAR for x in terpilih))))
            while len(terpilih) - n0 < q:
                perlu_luar = sum(x["lokasi"] in LUAR for x in terpilih) < luar_target
                order = np.argsort(-(1 - maxcos))
                pilih_i = None
                for tahap in ((True, True), (True, False), (False, False)):
                    for i in order:
                        r = kand[i]
                        if tahap[0] and perlu_luar and r["lokasi"] not in LUAR:
                            continue
                        if tahap[1] and not pov_ok(r):
                            continue
                        alasan = boleh(r)
                        if alasan is None:
                            pilih_i = i
                            break
                        tol.setdefault(r["stem"], alasan)
                    if pilih_i is not None:
                        break
                if pilih_i is None:
                    break
                r = kand[pilih_i]
                ambil(r, "W", f"terjauh dari berlabel+terpilih (1-cos {1 - maxcos[pilih_i]:.2f})")
                maxcos = np.maximum(maxcos, Ef @ En[idx[r["stem"]]])
        else:
            urutan = urut(bucket, kand)
            if bucket in ("U", "G"):
                luar_b = int(np.ceil(q * max(0, luar_target - sum(x["lokasi"] in LUAR for x in terpilih)) /
                                     max(1, sum(qq for bb, qq in KUOTA_URUT if bb in ("U", "G", "W") and
                                                URUTAN.index(bb) >= URUTAN.index(bucket)) + sisa)))
            else:
                luar_b = 0
            for tahap in ("luar", "pov", "bebas"):
                for r in urutan:
                    if len(terpilih) - n0 >= q:
                        break
                    if tahap == "luar" and (r["lokasi"] not in LUAR or sum(x["lokasi"] in LUAR for x in terpilih[n0:]) >= luar_b):
                        continue
                    if tahap in ("luar", "pov") and not pov_ok(r):
                        continue
                    alasan = boleh(r)
                    if alasan:
                        tol.setdefault(r["stem"], alasan)
                        continue
                    sk = skor[r["stem"]]
                    if bucket == "U":
                        al = "ragu: " + ", ".join(f"{k} {n}" for k, n in sorted(sk["U_detail"].items(), key=lambda x: -x[1]))
                    elif bucket == "G":
                        al = f"celah {sk['G']:.0f} s dari frame berlabel"
                    elif bucket == "E":
                        al = f"tangga di eskalator? box {sk['E_box']:.2f} seg {sk['E_seg']:.2f}"
                    else:
                        al = ("turun, " if turun(r) else "") + f"luminansi {sk['lum']:.0f}"
                    ambil(r, bucket, al)
        sisa = q - (len(terpilih) - n0)
    # simpan
    with (OUT / "pilihan.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["stem", "video", "lokasi", "pov", "t", "bucket", "skor_U", "U_detail", "jarak_label_s", "tangga_box", "tangga_seg",
                     "luminansi", "laplacian", "luar", "alasan"])
        for r in terpilih:
            sk = skor[r["stem"]]
            wr.writerow([r["stem"], r["video"], r["lokasi"], r["pov"], f"{r['t']:.3f}", r["bucket"], f"{sk['U']:.1f}",
                         json.dumps(sk["U_detail"]), f"{r['jarak_label']:.1f}", f"{sk['E_box']:.2f}", f"{sk['E_seg']:.2f}",
                         f"{sk['lum']:.0f}", f"{sk['lap']:.0f}", int(r["lokasi"] in LUAR), r["alasan"]])
    info = dict(n=len(terpilih), per_bucket=Counter(r["bucket"] for r in terpilih), per_lokasi=Counter(r["lokasi"] for r in terpilih),
                pov=Counter(r["pov"] for r in terpilih), luar=sum(r["lokasi"] in LUAR for r in terpilih), buram_pool=n_blur,
                elig={b: sum(1 for r in pool if elig[b](r)) for b, _ in KUOTA},
                cos_terpusat_acak=dict(median=float(np.median(cs_acak)), p95=float(np.percentile(cs_acak, 95))),
                cos_mentah_acak=dict(median=float(np.median(cs_raw)), p95=float(np.percentile(cs_raw, 95))),
                tolak=Counter(v.split(" ")[0] for v in tol.values()))
    (OUT / "pilihan_info.json").write_text(json.dumps(info, indent=2, default=dict), encoding="utf-8")
    print(json.dumps(info, indent=2, default=dict))
    sheets(terpilih, C)
    log(f"- [R0-4] Pilihan {len(terpilih)} frame (seed {SEED}): {dict(info['per_bucket'])}, luar {info['luar']}, pov {dict(info['pov'])}. "
        f"Buram di pool {n_blur} (Laplacian 540x960 < 0,5 x median +-5 s atau < 15). Berkas: data/ronde2/pilihan.csv, pilihan_*.png, pilihan_info.json.")


PAL = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40), (148, 103, 189), (140, 86, 75), (227, 119, 194), (23, 190, 207)]


def thumb(r, cc, tw=270):
    img = cv2.imread(str(FB / r["video"] / f"{r['stem']}.jpg"))
    h, w = img.shape[:2]
    k = cc["kotak"]
    for c, cf, b in zip(k["cls"], k["conf"], k["xyxy"]):
        if cf < 0.15:
            continue
        col = PAL[int(c)][::-1]
        x1, y1, x2, y2 = [int(v) for v in b]
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 6 if cf >= 0.5 else 3)
        cv2.putText(img, f"{KOTAK[int(c)]} {cf:.2f}", (x1, max(30, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 6, cv2.LINE_AA)
        cv2.putText(img, f"{KOTAK[int(c)]} {cf:.2f}", (x1, max(30, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 1.2, col, 2, cv2.LINE_AA)
    s = tw / w
    t = cv2.resize(img, (tw, int(h * s)), interpolation=cv2.INTER_AREA)
    bar = np.full((40, tw, 3), 255, np.uint8)
    cv2.putText(bar, f"[{r['bucket']}] {r['lokasi'][:20]}", (3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 180), 1, cv2.LINE_AA)
    cv2.putText(bar, f"{r['pov']} t={r['t']:.0f}s {r['alasan'][:30]}", (3, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
    return np.vstack([bar, t])


def sheets(terpilih, C):
    for f in OUT.glob("pilihan_*.png"):
        f.unlink()  # sheet lama buatan skrip ini sendiri (bukan data label)
    for b, _ in KUOTA:
        rs = [r for r in terpilih if r["bucket"] == b]
        if not rs:
            continue
        ths = [thumb(r, C[r["stem"]]) for r in rs]
        kol = 6
        hmax = max(t.shape[0] for t in ths)
        ths = [np.vstack([t, np.full((hmax - t.shape[0], t.shape[1], 3), 255, np.uint8)]) for t in ths]
        while len(ths) % kol:
            ths.append(np.full_like(ths[0], 255))
        rows = [np.hstack([np.hstack([t, np.full((hmax, 6, 3), 255, np.uint8)]) for t in ths[i:i + kol]]) for i in range(0, len(ths), kol)]
        cv2.imwrite(str(OUT / f"pilihan_{b}.png"), np.vstack(rows))


# ------------------------------------------------------------------ revisi R0 (keputusan Jeka, 12 Nov 2026)
REVISI = OUT / "revisi_r0.json"


def cmd_revisi(a):
    """Terapkan keputusan Jeka di R0 ke pilihan.csv (salinan sebelum revisi: pilihan_awal_r0.csv).
    revisi_r0.json: buang {stem: alasan}, ganti_buram [stem], wajib [stem], maks_lokasi {lokasi: n}, total n. Isi ulang dari U."""
    cfg = json.loads(REVISI.read_text(encoding="utf-8"))
    awal = list(csv.DictReader((OUT / "pilihan_awal_r0.csv").open(encoding="utf-8")))
    pool, lab_train, _ = bangun_pool()
    for r in pool + lab_train:
        cek_train(r["lokasi"])
    P = {r["stem"]: r for r in pool}
    C = {r["stem"]: muat_cache(r["stem"]) for r in pool + lab_train}
    stems_all = [r["stem"] for r in lab_train + pool]
    E = np.stack([C[s]["embed"] for s in stems_all])
    E = E - E.mean(0)
    E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
    idx = {s: i for i, s in enumerate(stems_all)}
    per_video = defaultdict(list)
    for r in pool + lab_train:
        per_video[r["video"]].append(r)
    blur, med_video = {}, {}
    for v, rs in per_video.items():
        med_video[v] = float(np.median([C[x["stem"]]["lap"] for x in rs]))
        for r in rs:
            tet = [C[x["stem"]]["lap"] for x in rs if abs(x["t"] - r["t"]) <= 5.0]
            lp = C[r["stem"]]["lap"]
            blur[r["stem"]] = lp < BLUR_REL * float(np.median(tet)) or lp < BLUR_ABS
    skor_awal = {x["stem"]: float(x["skor_U"] or 0) for x in awal}

    sel = []
    for x in awal:
        r = dict(P[x["stem"]])
        r["bucket"], r["alasan"] = x["bucket"], x["alasan"]
        sel.append(r)
    catat = []
    for st, al in cfg["buang"].items():
        assert any(r["stem"] == st for r in sel), st
        sel = [r for r in sel if r["stem"] != st]
        catat.append(f"buang {st}: {al}")

    def boleh(r, sel, maks_lok):
        if blur[r["stem"]]:
            return "buram"
        if any(x["stem"] == r["stem"] for x in sel):
            return "sudah"
        if sum(x["video"] == r["video"] for x in sel) >= MAKS_VIDEO:
            return "maks video"
        if r["lokasi"] in maks_lok and sum(x["lokasi"] == r["lokasi"] for x in sel) >= maks_lok[r["lokasi"]]:
            return "maks lokasi"
        if any(x["video"] == r["video"] and abs(x["t"] - r["t"]) < JARAK_PILIH for x in sel):
            return "< 3 s"
        for x in lab_train + sel:
            if x["lokasi"] != r["lokasi"]:
                continue
            if float(E[idx[r["stem"]]] @ E[idx[x["stem"]]]) >= COS_DUP or ham(C[r["stem"]]["phash"], C[x["stem"]]["phash"]) <= PHASH_DUP:
                return "duplikat"
        return None

    # ganti buram: kandidat terdekat di video yang sama, tidak buram DAN Laplacian >= 1,25 x median video (filter lama meloloskan buram gerak)
    for st in cfg["ganti_buram"]:
        lama = next(r for r in sel if r["stem"] == st)
        sel = [r for r in sel if r["stem"] != st]
        kand = sorted((r for r in pool if r["video"] == lama["video"] and r["stem"] != st), key=lambda r: (abs(r["t"] - lama["t"]), r["t"]))
        for r in kand:
            if C[r["stem"]]["lap"] < 1.25 * med_video[r["video"]] or boleh(r, sel, {}) is not None:
                continue
            r = dict(r)
            r["bucket"] = lama["bucket"]
            r["alasan"] = f"pengganti t={lama['t']:.0f}s (buram), celah {r['jarak_label']:.0f} s"
            sel.append(r)
            catat.append(f"ganti buram {st} (lap {C[st]['lap']:.0f}) -> {r['stem']} (lap {C[r['stem']]['lap']:.0f}, median video {med_video[r['video']]:.0f})")
            break
        else:
            catat.append(f"ganti buram {st}: TIDAK ada pengganti")
    # batas per lokasi: wajib dipertahankan; sisanya urut bucket E,D,G,U,W; G per celah, U per skor
    prio = {"E": 0, "D": 1, "G": 2, "U": 3, "W": 4}
    for lok, n in cfg["maks_lokasi"].items():
        di = [r for r in sel if r["lokasi"] == lok]
        for st in cfg["wajib"]:
            assert any(r["stem"] == st for r in di), f"wajib hilang: {st}"
        wajib = [r for r in di if r["stem"] in cfg["wajib"]]
        lain = sorted((r for r in di if r["stem"] not in cfg["wajib"]),
                      key=lambda r: (prio[r["bucket"]], -(r["jarak_label"] if r["bucket"] == "G" else 0), -skor_awal.get(r["stem"], 0), r["stem"]))
        simpan = {r["stem"] for r in wajib + lain[: max(0, n - len(wajib))]}
        for r in di:
            if r["stem"] not in simpan:
                catat.append(f"potong {lok} (maks {n}): {r['stem']} [{r['bucket']}]")
        sel = [r for r in sel if r["lokasi"] != lok or r["stem"] in simpan]
    # isi ulang dari U (urut skor U)
    skor_u = {}
    for r in pool:
        su, det = 0.0, Counter()
        k = C[r["stem"]]["kotak"]
        for c, cf, b in zip(k["cls"], k["conf"], k["xyxy"]):
            kl = KOTAK[int(c)]
            if 0.15 <= cf <= 0.50 and r4_lolos(kl, *b):
                su += BOBOT_U.get(kl, BOBOT_LAIN)
                det[kl] += 1
        skor_u[r["stem"]] = (su, det)
    rng = random.Random(SEED)
    jit = {r["stem"]: rng.random() * 1e-6 for r in pool}
    for r in sorted(pool, key=lambda r: -(skor_u[r["stem"]][0] + jit[r["stem"]])):
        if len(sel) >= cfg["total"] or skor_u[r["stem"]][0] <= 0:
            break
        if boleh(r, sel, cfg["maks_lokasi"]) is None:
            r = dict(r)
            r["bucket"] = "U"
            r["alasan"] = "isi ulang R0, ragu: " + ", ".join(f"{k} {n}" for k, n in skor_u[r["stem"]][1].most_common())
            sel.append(r)
            catat.append(f"isi U {r['stem']} (skor {skor_u[r['stem']][0]:.1f})")
    luar = sum(r["lokasi"] in LUAR for r in sel)
    if len(sel) != cfg["total"] or luar < 0.40 * len(sel):
        sys.exit(f"BERHENTI: {len(sel)} frame, luar {luar}")
    with (OUT / "pilihan.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["stem", "video", "lokasi", "pov", "t", "bucket", "skor_U", "U_detail", "jarak_label_s", "luminansi", "laplacian", "luar", "alasan"])
        for r in sel:
            su, det = skor_u[r["stem"]]
            wr.writerow([r["stem"], r["video"], r["lokasi"], r["pov"], f"{r['t']:.3f}", r["bucket"], f"{su:.1f}", json.dumps(dict(det)),
                         f"{r['jarak_label']:.1f}", f"{C[r['stem']]['lum']:.0f}", f"{C[r['stem']]['lap']:.0f}", int(r["lokasi"] in LUAR), r["alasan"]])
    (OUT / "revisi_r0_catatan.txt").write_text("\n".join(catat) + "\n", encoding="utf-8")
    sheets(sel, C)
    info = dict(n=len(sel), per_bucket=Counter(r["bucket"] for r in sel), per_lokasi=Counter(r["lokasi"] for r in sel),
                pov=Counter(r["pov"] for r in sel), luar=luar)
    (OUT / "pilihan_info.json").write_text(json.dumps(info, indent=2, default=dict), encoding="utf-8")
    print("\n".join(catat))
    print(json.dumps(info, indent=2, default=dict))
    log(f"- [R0-10] Revisi R0 diterapkan (`ronde2_pilih.py revisi`, konfigurasi revisi_r0.json, catatan revisi_r0_catatan.txt, "
        f"sebelum revisi: pilihan_awal_r0.csv): {len(sel)} frame, {dict(info['per_bucket'])}, luar {luar}, pov {dict(info['pov'])}.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("aksi", choices=["pool", "studi", "pilih", "revisi"])
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    {"pool": cmd_pool, "studi": cmd_studi, "pilih": cmd_pilih, "revisi": cmd_revisi}[a.aksi](a)


if __name__ == "__main__":
    main()
