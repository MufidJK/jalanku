"""kualitas_auto.py - Stage 4: ukur kualitas label auto-v2 terhadap label manusia.

Dijalankan dari root repo: python tools/kualitas_auto.py

Perbandingan (GT = label manusia, prediksi = auto kecuali disebut lain):
  blind          : 15 frame blind, auto (data/pilot-v2-auto-backup) vs label blind (data/pilot-v2-blind). Ukuran utama.
  review         : frame pilot selain 36 frame tuning dan 15 frame blind, auto vs hasil review (data/pilot-v2).
  review-blind15 : 15 frame blind, auto vs hasil review. Dibandingkan dengan 'blind' untuk melihat bias reviewer.
  konsistensi    : 15 frame blind, hasil review (sebagai prediksi) vs label blind. Seberapa jauh review dari blind.
  tuning         : 36 frame tuning, auto vs review. Hanya info, tidak dipakai untuk keputusan.

Aturan (catatan Jeka 8 Nov 2026, lihat data/pilot-v2/LOG.md):
  - Kotak (pilar..kendaraan, tangga): kotak = bounding box polygon, cocok kalau IoU >= 0.5 (satu-satu, greedy).
  - Semua shape tangga dalam satu frame digabung jadi satu objek, di kedua sisi.
  - Permukaan (jalur_jalan, jalan_kendaraan, tangga): mask union per kelas per frame, precision/recall/IoU piksel.
  - Frame tanpa shape di GT tetap dihitung (frame kosong yang sudah dicek).
  - Kendaraan/kursi salah (FP) di parkiran, dapsut, lab1-lt5 dibuat potongan gambarnya untuk dicek mata.
    Hasil cek ditulis di data/pilot-v2/stage4_belakang.csv (kolom id, kategori: belakang / salah).
    'belakang' = objek asli yang sengaja tidak dilabel karena bertumpuk di belakang; dikeluarkan dari FP
    di kolom precision_adj, tapi precision utama tetap menghitungnya salah.
  - Subset 'yakin' = hanya shape auto dengan difficult: false.

Keluaran: data/pilot-v2/kualitas_auto.csv, kualitas_auto_frame.csv, kualitas_auto_edit.csv,
          data/pilot-v2/_stage4/fp_belakang.csv + lembar potongan.
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

AUTO = Path("data/pilot-v2-auto-backup")
REVIEW = Path("data/pilot-v2")
BLIND = Path("data/pilot-v2-blind")
OUT = REVIEW
CEK = REVIEW / "_stage4"
KELAS = Path("data/pilot/classes.txt").read_text().split()
KOTAK = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"]
PERMUKAAN = ["jalur_jalan", "jalan_kendaraan", "tangga"]
TUNING_NO = [13, 16, 29, 30, 39, 45, 47, 51, 52, 59, 88, 92, 97, 98, 99, 100, 101, 119, 124, 131, 143, 172,
             178, 182, 183, 186, 187, 188, 190, 193, 199, 203, 216, 219, 222, 243]
BELAKANG_LOK = ("parkiran-motor-b1", "dapsut", "lab1-lt5")
BELAKANG_KELAS = ("kendaraan", "kursi")
W, H = 1080, 1920
SKALA = 0.5                       # rasterisasi mask di 540x960


def muat(folder, stem):
    p = folder / f"{stem}.json"
    if not p.exists():
        raise FileNotFoundError(p)
    return json.loads(p.read_text(encoding="utf-8"))["shapes"]


def kotak_dari(points):
    p = np.asarray(points, float)
    x1, y1 = np.clip(p.min(0), 0, [W, H])
    x2, y2 = np.clip(p.max(0), 0, [W, H])
    return (x1, y1, x2, y2)


def objek(shapes, hanya_yakin=False):
    """kelas -> list kotak. Tangga digabung jadi satu objek per frame."""
    out = defaultdict(list)
    tangga = []
    for s in shapes:
        if s["label"] not in KOTAK or (hanya_yakin and s.get("difficult")):
            continue
        if s["label"] == "tangga":
            tangga += [list(map(float, q)) for q in s["points"]]
        else:
            out[s["label"]].append(kotak_dari(s["points"]))
    if tangga:
        out["tangga"].append(kotak_dari(tangga))
    return out


def mask(shapes, hanya_yakin=False):
    h, w = int(H * SKALA), int(W * SKALA)
    out = {k: np.zeros((h, w), np.uint8) for k in PERMUKAAN}
    for s in shapes:
        if s["label"] in PERMUKAAN and not (hanya_yakin and s.get("difficult")):
            p = np.round(np.asarray(s["points"], float) * SKALA).astype(np.int32)
            cv2.fillPoly(out[s["label"]], [p], 1)
    return {k: v.astype(bool) for k, v in out.items()}


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def cocokkan(pred, gt, ambang):
    """Greedy satu-satu berdasarkan IoU. Mengembalikan (pasangan, index pred tak cocok, index gt tak cocok)."""
    cal = sorted(((iou(p, g), i, j) for i, p in enumerate(pred) for j, g in enumerate(gt)), reverse=True)
    pi, gj, pas = set(), set(), []
    for v, i, j in cal:
        if v < ambang:
            break
        if i not in pi and j not in gj:
            pi.add(i); gj.add(j); pas.append((i, j, v))
    return pas, [i for i in range(len(pred)) if i not in pi], [j for j in range(len(gt)) if j not in gj]


def bagi(a, b):
    return round(a / b, 3) if b else ""


def bandingkan(nama_set, stems, sumber_pred, sumber_gt, belakang, rows, frows, fp_list, edit=None):
    for subset in ("semua", "yakin"):
        if subset == "yakin" and sumber_pred is not AUTO:
            continue
        yk = subset == "yakin"
        st = defaultdict(Counter)
        for stem in stems:
            sp, sg = muat(sumber_pred, stem), muat(sumber_gt, stem)
            op, og = objek(sp, yk), objek(sg)
            for k in KOTAK:
                pred, gt = op.get(k, []), og.get(k, [])
                pas, fp, fn = cocokkan(pred, gt, 0.5)
                pas3, fp3, _ = cocokkan(pred, gt, 0.3)
                c = st[("kotak", k)]
                c["frame"] += 1
                c["gt"] += len(gt); c["pred"] += len(pred)
                c["tp"] += len(pas); c["fp"] += len(fp); c["fn"] += len(fn); c["tp03"] += len(pas3)
                lain = [b for kk in KOTAK if kk != k for b in og.get(kk, [])]
                c["salah_kelas"] += sum(any(iou(pred[i], b) >= 0.5 for b in lain) for i in fp)
                if k in BELAKANG_KELAS and stem.startswith(BELAKANG_LOK):
                    for i in fp:
                        fid = f"{nama_set}|{subset}|{stem}|{k}|{i}"
                        if subset == "semua":
                            fp_list.append((fid, stem, k, pred[i], gt))
                        if belakang.get(fid.replace("|yakin|", "|semua|")) == "belakang":
                            c["fp_belakang"] += 1
                if subset == "semua" and (gt or pred):
                    frows.append([nama_set, stem, "kotak", k, len(gt), len(pred), len(pas), len(fp), len(fn), ""])
            mp, mg = mask(sp, yk), mask(sg)
            for k in PERMUKAAN:
                a, g = mp[k], mg[k]
                i, u = int((a & g).sum()), int((a | g).sum())
                c = st[("mask", k)]
                c["frame"] += 1
                c["i"] += i; c["pa"] += int(a.sum()); c["pg"] += int(g.sum()); c["u"] += u
                if u:
                    c["frame_ada"] += 1
                    c["iou_frame_sum"] += i / u
                    c["iou_frame_085"] += (i / u) >= 0.85
                if subset == "semua" and u:
                    frows.append([nama_set, stem, "mask", k, int(g.sum()), int(a.sum()), i, "", "", round(i / u, 3)])
        for (jenis, k), c in st.items():
            r = {"set": nama_set, "subset": subset, "jenis": jenis, "kelas": k, "frame": c["frame"]}
            if jenis == "kotak":
                fp_adj = c["fp"] - c["fp_belakang"]
                r.update(gt=c["gt"], auto=c["pred"], tp=c["tp"], fp=c["fp"], fn=c["fn"],
                         precision=bagi(c["tp"], c["tp"] + c["fp"]), recall=bagi(c["tp"], c["gt"]),
                         fp_belakang=c["fp_belakang"] if k in BELAKANG_KELAS else "",
                         precision_adj=bagi(c["tp"], c["tp"] + fp_adj) if k in BELAKANG_KELAS else "",
                         fp_salah_kelas=c["salah_kelas"],
                         precision_iou03=bagi(c["tp03"], c["pred"]), recall_iou03=bagi(c["tp03"], c["gt"]))
            else:
                r.update(gt=c["pg"], auto=c["pa"], tp=c["i"], fp=c["pa"] - c["i"], fn=c["pg"] - c["i"],
                         precision=bagi(c["i"], c["pa"]), recall=bagi(c["i"], c["pg"]), iou=bagi(c["i"], c["u"]),
                         frame_ada=c["frame_ada"], iou_frame_rata=bagi(c["iou_frame_sum"], c["frame_ada"]),
                         frame_iou_085=c["iou_frame_085"])
            if edit is not None and subset == "semua" and (jenis == "kotak" or k != "tangga"):
                e = edit[k]
                r.update(sama=e["sama"], diedit=e["diedit"], dihapus=e["dihapus"], ditambah=e["ditambah"])
            rows.append(r)


def hitung_edit(stems):
    """Jumlah shape auto yang sama / diedit / dihapus, dan shape yang ditambah reviewer, per kelas (shape mentah)."""
    e = defaultdict(Counter)
    ganti = Counter()
    for stem in stems:
        a = muat(AUTO, stem)
        r = muat(REVIEW, stem)
        sisa_a = list(range(len(a)))
        sisa_r = []
        kunci = defaultdict(list)
        for i in sisa_a:
            kunci[(a[i]["label"], json.dumps(a[i]["points"]))].append(i)
        for j, s in enumerate(r):
            kk = (s["label"], json.dumps(s["points"]))
            if kunci.get(kk):
                i = kunci[kk].pop()
                sisa_a.remove(i)
                e[s["label"]]["sama"] += 1
            else:
                sisa_r.append(j)
        for j in list(sisa_r):
            d = r[j].get("description") or ""
            if not d.startswith("auto-v2"):
                continue
            cal = [i for i in sisa_a if a[i]["description"] == d]
            if not cal:
                continue
            bj = kotak_dari(r[j]["points"])
            i = max(cal, key=lambda i: (a[i]["label"] == r[j]["label"], iou(kotak_dari(a[i]["points"]), bj)))
            sisa_a.remove(i); sisa_r.remove(j)
            e[a[i]["label"]]["diedit"] += 1
            if a[i]["label"] != r[j]["label"]:
                ganti[(a[i]["label"], r[j]["label"])] += 1
        for i in sisa_a:
            e[a[i]["label"]]["dihapus"] += 1
        for j in sisa_r:
            e[r[j]["label"]]["ditambah"] += 1
    return e, ganti


def lembar_fp(fp_list):
    CEK.mkdir(exist_ok=True)
    with open(CEK / "fp_belakang.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["no", "id", "frame", "kelas", "x1", "y1", "x2", "y2"])
        for n, (fid, stem, k, b, _) in enumerate(fp_list, 1):
            wr.writerow([n, fid, stem, k] + [int(v) for v in b])
    tiles = []
    for n, (fid, stem, k, b, gt) in enumerate(fp_list, 1):
        img = cv2.imread(str(REVIEW / f"{stem}.jpg"))
        for g in gt:
            cv2.rectangle(img, tuple(map(int, g[:2])), tuple(map(int, g[2:])), (0, 200, 0), 4)
        cv2.rectangle(img, tuple(map(int, b[:2])), tuple(map(int, b[2:])), (0, 0, 255), 6)
        x1, y1, x2, y2 = b
        bw, bh = x2 - x1, y2 - y1
        m = max(bw, bh) * 0.8 + 80
        c = img[int(max(0, y1 - m)):int(min(H, y2 + m)), int(max(0, x1 - m)):int(min(W, x2 + m))]
        s = 300 / max(c.shape[:2])
        c = cv2.resize(c, None, fx=s, fy=s)
        t = np.full((330, 300, 3), 255, np.uint8)
        t[30:30 + c.shape[0], :c.shape[1]] = c
        cv2.putText(t, f"{n} {k} {fid.split('|')[0]}", (4, 22), 0, 0.6, (0, 0, 0), 2)
        tiles.append(t)
    for p in range(0, len(tiles), 24):
        part = tiles[p:p + 24]
        while len(part) % 6:
            part.append(np.full_like(tiles[0], 255))
        grid = np.vstack([np.hstack(part[r:r + 6]) for r in range(0, len(part), 6)])
        cv2.imwrite(str(CEK / f"fp_belakang_{p // 24 + 1:02d}.jpg"), grid)


def main():
    semua = sorted(p.stem for p in Path("data/pilot/images").glob("*.jpg"))
    tuning = [semua[i - 1] for i in TUNING_NO]
    blind = sorted(p.stem for p in BLIND.glob("*.jpg"))
    assert len(blind) == 15 and not set(blind) & set(tuning)
    review = [s for s in semua if s not in tuning and s not in blind]
    print(f"frame: semua {len(semua)}, tuning {len(tuning)}, blind {len(blind)}, review {len(review)}")

    belakang = {}
    pb = OUT / "stage4_belakang.csv"
    if pb.exists():
        for r in csv.DictReader(open(pb, encoding="utf-8")):
            belakang[r["id"]] = r["kategori"].strip()

    rows, frows, fp_list = [], [], []
    e_rev, g_rev = hitung_edit(review)
    e_b15, _ = hitung_edit(blind)
    e_tun, _ = hitung_edit(tuning)
    bandingkan("blind", blind, AUTO, BLIND, belakang, rows, frows, fp_list)
    bandingkan("review", review, AUTO, REVIEW, belakang, rows, frows, fp_list, e_rev)
    bandingkan("review-blind15", blind, AUTO, REVIEW, belakang, rows, frows, fp_list, e_b15)
    bandingkan("konsistensi", blind, REVIEW, BLIND, belakang, rows, frows, [])
    bandingkan("tuning", tuning, AUTO, REVIEW, belakang, rows, frows, [], e_tun)

    kol = ["set", "subset", "jenis", "kelas", "frame", "gt", "auto", "tp", "fp", "fn", "precision", "recall",
           "iou", "frame_ada", "iou_frame_rata", "frame_iou_085", "fp_belakang", "precision_adj", "fp_salah_kelas",
           "precision_iou03", "recall_iou03", "sama", "diedit", "dihapus", "ditambah"]
    with open(OUT / "kualitas_auto.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, kol)
        wr.writeheader()
        wr.writerows(rows)
    with open(OUT / "kualitas_auto_frame.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["set", "frame", "jenis", "kelas", "gt", "auto", "tp_atau_irisan", "fp", "fn", "iou"])
        wr.writerows(frows)
    with open(OUT / "kualitas_auto_edit.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["set", "kelas", "sama", "diedit", "dihapus", "ditambah"])
        for nm, e in (("review", e_rev), ("review-blind15", e_b15), ("tuning", e_tun)):
            for k in KELAS:
                wr.writerow([nm, k, e[k]["sama"], e[k]["diedit"], e[k]["dihapus"], e[k]["ditambah"]])
    print("ganti label (review):", dict(g_rev))
    lembar_fp(fp_list)
    print(f"FP kendaraan/kursi di lokasi belakang: {len(fp_list)} (lembar di {CEK}), sudah dicek: {len(belakang)}")

    for r in rows:
        if r["subset"] == "semua" and r["set"] in ("blind", "review", "konsistensi"):
            extra = f"iou {r['iou']}" if r["jenis"] == "mask" else f"tp {r['tp']} fp {r['fp']} fn {r['fn']}"
            print(f"{r['set']:12s} {r['jenis']:5s} {r['kelas']:16s} P {r['precision']!s:6s} R {r['recall']!s:6s} {extra}")


if __name__ == "__main__":
    main()
