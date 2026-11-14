"""ronde2_draft.py - ronde 2 JalanKu, section 5: draft label untuk frame terpilih + folder review.

Dijalankan dari root repo SETELAH CHECKPOINT R0 disetujui:
  python tools/ronde2_draft.py auto      # autolabel_v2 hanya di frame terpilih -> data/ronde2/auto-cache/ (+ cache model di data/ronde2/auto-cache-pkl/)
  python tools/ronde2_draft.py draft     # draft per kelas dari sumber pilihan R0 -> data/ronde2-review/ + data/ronde2-auto-backup/

Sumber per kelas dibaca dari data/ronde2/sumber_draft_pilihan.json (hasil `ronde2_pilih.py studi`, boleh diubah Jeka di R0).
  kotak : "model@0.25" (prediksi kotak-gabung >= conf), "auto" (autolabel_v2), "union@0.25" (model + auto yang tidak tumpang IoU > 0,5)
  permukaan (jalur_jalan, jalan_kendaraan, tangga): "auto" atau "model@0.25" (seg-kampus)
Kelas kotak ditulis sebagai `rectangle`, permukaan sebagai `polygon`. tangga selalu polygon (dipakai dua model; builder
membuat kotak tangga dari gabungan polygon). Tiap shape diberi description = sumbernya.

Pembersihan otomatis sebelum direview (dicatat di data/ronde2/draft_dibuang.csv):
  R4 (ambang ukuran), clipping ke dalam gambar, duplikat sekelas (containment mask >= 0,8 atau IoU >= 0,7; skor lebih tinggi dipertahankan).

Tidak pernah menimpa: kalau data/ronde2-review/ atau data/ronde2-auto-backup/ sudah berisi file, berhenti.
"""
import argparse
import csv
import json
import os
import pickle
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from ronde2_pilih import (CACHE, FB, KOTAK, OUT, ROOT, SEG, TIPIS, cek_train, jenis_lokasi, log, r4_lolos)  # noqa: E402

REVIEW = ROOT / "data/ronde2-review"
BACKUP = ROOT / "data/ronde2-auto-backup"
AUTO = OUT / "auto-cache"
AUTO_PKL = OUT / "auto-cache-pkl"
KELAS_X = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "jalur_jalan", "jalan_kendaraan", "tangga"]
BOX_KELAS = [k for k in KOTAK if k != "tangga"]


def baca_pilihan():
    with (OUT / "pilihan.csv").open(encoding="utf-8") as f:
        rs = list(csv.DictReader(f))
    for r in rs:
        cek_train(r["lokasi"])
        if jenis_lokasi(r["lokasi"]) != "train":
            sys.exit(f"BERHENTI: {r['stem']} bukan lokasi training")
    return rs


def cmd_auto(a):
    rs = baca_pilihan()
    daftar = OUT / "auto-daftar.txt"
    daftar.write_text("\n".join(str((FB / r["video"] / f"{r['stem']}.jpg").relative_to(ROOT)) for r in rs) + "\n", encoding="utf-8")
    cmd = [sys.executable, "tools/autolabel_v2.py", "--daftar", str(daftar.relative_to(ROOT)), "--out", str(AUTO.relative_to(ROOT)),
           "--cache", str(AUTO_PKL.relative_to(ROOT)), "--device", "0"]
    log(f"- [R1-1] Mulai autolabel_v2 di {len(rs)} frame terpilih: {' '.join(cmd[1:])}")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode:
        sys.exit(f"autolabel_v2 gagal ({r.returncode})")
    n = len(list(AUTO.glob("*.json")))
    log(f"- [R1-2] autolabel_v2 selesai: {n} JSON di data/ronde2/auto-cache/.")


# ------------------------------------------------------------------ geometri
def bbox(p):
    p = np.asarray(p, float)
    return np.r_[p.min(0), p.max(0)]


def mask_dari(shape, h, w, s=0.25):
    m = np.zeros((int(h * s) + 1, int(w * s) + 1), np.uint8)
    p = np.asarray(shape["points"], float)
    if shape["shape_type"] == "rectangle":
        x1, y1, x2, y2 = bbox(p)
        cv2.rectangle(m, (int(x1 * s), int(y1 * s)), (int(x2 * s), int(y2 * s)), 1, -1)
    else:
        cv2.fillPoly(m, [np.round(p * s).astype(np.int32)], 1)
    return m.astype(bool)


def rect(label, b, skor, desc):
    x1, y1, x2, y2 = [float(v) for v in b]
    return {"review_status": "pending", "label": label, "score": round(float(skor), 3),
            "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], "group_id": None, "description": desc,
            "difficult": False, "shape_type": "rectangle", "flags": {}, "attributes": {}, "kie_linking": []}


def poly(label, pts, skor, desc, grup=None):
    return {"review_status": "pending", "label": label, "score": round(float(skor), 3),
            "points": [[round(float(x), 1), round(float(y), 1)] for x, y in pts], "group_id": grup, "description": desc,
            "difficult": False, "shape_type": "polygon", "flags": {}, "attributes": {}, "kie_linking": []}


def sederhana(pts, eps=2.0):
    c = np.asarray(pts, np.float32).reshape(-1, 1, 2)
    a = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
    return a if len(a) >= 3 else np.asarray(pts)


def tulis_json(path, d):
    """Format X-AnyLabeling seperti data/pilot-v2: indent 2, CRLF, tanpa newline akhir."""
    path.write_bytes(json.dumps(d, indent=2, ensure_ascii=False).replace("\n", "\r\n").encode("utf-8"))


def cmd_draft(a):
    rs = baca_pilihan()
    pil = json.loads((OUT / "sumber_draft_pilihan.json").read_text(encoding="utf-8"))
    for d in (REVIEW, BACKUP):
        if d.exists() and any(d.iterdir()):
            sys.exit(f"BERHENTI: {d} sudah berisi file; tidak ditimpa.")
    REVIEW.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=True)
    dibuang = []
    jumlah = Counter()
    for r in rs:
        stem = r["stem"]
        img_src = FB / r["video"] / f"{stem}.jpg"
        c = pickle.loads((CACHE / f"{stem}.pkl").read_bytes())
        h, w = c["h"], c["w"]
        aj = json.loads((AUTO / f"{stem}.json").read_text(encoding="utf-8"))
        auto = aj["shapes"]
        shapes = []

        def desc_auto(s):
            d = s.get("description") or ""
            return "r2 auto " + d.replace("auto-v2 ", "", 1) if d.startswith("auto-v2") else "r2 auto"

        # kotak
        for k in BOX_KELAS:
            src = pil[k]
            cand = []
            mcand = []
            if src.startswith(("model", "union")):
                t = float(src.split("@")[1])
                kk = c["kotak"]
                for ci, cf, b in zip(kk["cls"], kk["conf"], kk["xyxy"]):
                    if KOTAK[int(ci)] == k and cf >= t:
                        mcand.append((b, float(cf), f"r2 model {cf:.2f}"))
            acand = [(bbox(s["points"]), float(s.get("score") or 0.5), desc_auto(s)) for s in auto if s["label"] == k]
            if src.startswith("model"):
                cand = mcand
            elif src == "auto":
                cand = acand
            else:
                from ronde2_pilih import iou1
                cand = mcand + [x for x in acand if not any(iou1(x[0], [y[0]])[0] > 0.5 for y in mcand)]
            for b, sk, ds in cand:
                shapes.append(rect(k, b, sk, ds))
        # permukaan + tangga (polygon)
        for k in SEG:
            src = pil["seg:" + k]
            if src == "auto":
                for s in auto:
                    if s["label"] == k:
                        shapes.append(poly(k, s["points"], s.get("score") or 0.5, desc_auto(s), s.get("group_id")))
            else:
                t = float(src.split("@")[1])
                sg = c["seg"]
                for ci, cf, pts in zip(sg["cls"], sg["conf"], sg["poly"]):
                    if SEG[int(ci)] == k and cf >= t and len(pts) >= 3:
                        shapes.append(poly(k, sederhana(pts), cf, f"r2 model {cf:.2f}"))
        # clipping
        for s in shapes:
            p = np.asarray(s["points"], float)
            q = np.clip(p, [0, 0], [w - 1, h - 1])
            if np.abs(p - q).max() > 0:
                s["points"] = [[round(float(x), 1), round(float(y), 1)] for x, y in q]
                jumlah["clip"] += 1
        # R4
        sisa = []
        for s in shapes:
            x1, y1, x2, y2 = bbox(s["points"])
            if s["label"] in KOTAK and s["label"] != "tangga" and not r4_lolos(s["label"], x1, y1, x2, y2):
                dibuang.append([stem, s["label"], s["score"], s["description"], f"{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}", "R4"])
                continue
            sisa.append(s)
        shapes = sisa
        # duplikat sekelas
        masks = [mask_dari(s, h, w) for s in shapes]
        buang = set()
        order = sorted(range(len(shapes)), key=lambda i: -(shapes[i]["score"] or 0))
        for ii, i in enumerate(order):
            if i in buang:
                continue
            for j in order[ii + 1:]:
                if j in buang or shapes[j]["label"] != shapes[i]["label"]:
                    continue
                if shapes[i]["label"] in ("jalur_jalan", "jalan_kendaraan") and shapes[i]["group_id"] is not None:
                    pass
                it = int((masks[i] & masks[j]).sum())
                if not it:
                    continue
                un = int((masks[i] | masks[j]).sum())
                cont = it / max(1, min(masks[i].sum(), masks[j].sum()))
                if cont >= 0.8 or it / un >= 0.7:
                    buang.add(j)
                    x1, y1, x2, y2 = bbox(shapes[j]["points"])
                    dibuang.append([stem, shapes[j]["label"], shapes[j]["score"], shapes[j]["description"],
                                    f"{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}",
                                    f"duplikat (IoU {it / un:.2f}, containment {cont:.2f}) dari {shapes[i]['description']}"])
        shapes = [s for i, s in enumerate(shapes) if i not in buang]
        for s in shapes:
            jumlah[(s["label"], s["description"].split(" ")[1])] += 1
        d = {"version": "4.3.1", "flags": {}, "checked": False, "shapes": shapes, "imagePath": f"{stem}.jpg",
             "imageData": None, "imageHeight": h, "imageWidth": w, "description": ""}
        for tujuan in (REVIEW, BACKUP):
            os.link(img_src, tujuan / f"{stem}.jpg")
            tulis_json(tujuan / f"{stem}.json", d)
    with (OUT / "draft_dibuang.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["stem", "kelas", "skor", "sumber", "kotak", "alasan"])
        wr.writerows(dibuang)
    ring = {f"{k[0]}|{k[1]}": v for k, v in jumlah.items() if isinstance(k, tuple)}
    (OUT / "draft_jumlah.json").write_text(json.dumps(dict(per_kelas_sumber=ring, clip=jumlah["clip"],
                                                           dibuang=Counter(x[5].split(" ")[0] for x in dibuang)), indent=2), encoding="utf-8")
    log(f"- [R1-3] Draft {len(rs)} frame ke data/ronde2-review/ (hard link + JSON CRLF), salinan utuh di data/ronde2-auto-backup/. "
        f"Dibuang otomatis: {dict(Counter(x[5].split(' ')[0] for x in dibuang))}, clipping {jumlah['clip']} shape. Jumlah: {ring}")


CATATAN_MANUAL = {  # dari pemeriksaan visual sheet pilihan (R0)
    "lorong-lt9-ubm-tower_2026-10-30_01_dada_t0053000": "cermin toilet: orang di cermin = pantulan, jangan dilabel (R5)",
    # tangga tanpa draft (auto dan model seg tidak menemukan): wajib digambar manual
    "parkiran-motor-b1-ubm-tower_2026-10-30_01_dada_t0000000": "TANGGA TURUN tanpa draft: gambar polygon tangga",
    "parkiran-motor-b1-ubm-tower_2026-10-30_01_dada_t0003000": "TANGGA TURUN tanpa draft: gambar polygon tangga",
    "parkiran-motor-b1-ubm-tower_2026-10-30_01_dada_t0007022": "TANGGA TURUN tanpa draft: gambar polygon tangga",
    "parkiran-motor-b1-ubm-tower_2026-10-30_01_mata_t0000000": "TANGGA TURUN tanpa draft: gambar polygon tangga",
    "lorong-lt5-alfa-tower_2026-10-30_01_mata_t0060027": "TANGGA tanpa draft (auto 0; model seg 0,90): gambar polygon tangga",
}
TAMBAH_KERJA = 8  # menggambar satu polygon tangga dari nol


def cmd_review_list(a):
    """review_list.csv: urut perkiraan kerja. Kerja per shape = biaya studi val / jumlah draft (sumber terpilih) per kelas."""
    rs = baca_pilihan()
    pil = json.loads((OUT / "sumber_draft_pilihan.json").read_text(encoding="utf-8"))
    studi = list(csv.DictReader((OUT / "sumber_draft.csv").open(encoding="utf-8")))
    per_shape = {}
    for b in studi:
        if b["jenis"] == "kotak" and pil.get(b["kelas"]) == b["sumber"]:
            per_shape[b["kelas"]] = float(b["biaya"]) / max(1, float(b["n_draft"]))
        if b["jenis"] == "permukaan" and pil.get("seg:" + b["kelas"]) == b["sumber"]:
            per_shape["seg:" + b["kelas"]] = 3 * (1 - float(b["iou_piksel"]))  # 3 klik per penyesuaian x porsi salah
    alasan_auto = {}
    p = AUTO / "review_list.csv"
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8")):
            alasan_auto[Path(r["filename"]).stem] = r["alasan"]
    baris = []
    for r in rs:
        d = json.loads((REVIEW / f"{r['stem']}.json").read_text(encoding="utf-8"))
        n = Counter(s["label"] for s in d["shapes"])
        kerja = sum(per_shape.get(k if k in BOX_KELAS else "seg:" + k, 1.0) * v for k, v in n.items())
        cat = []
        if r["stem"] in CATATAN_MANUAL:
            cat.append(CATATAN_MANUAL[r["stem"]])
            if "tanpa draft" in CATATAN_MANUAL[r["stem"]]:
                kerja += TAMBAH_KERJA
        if r["bucket"] == "E":
            cat.append("eskalator: pastikan tidak ada tangga, pelat landasan bukan jalur_jalan")
            kerja += 3
        if r["lokasi"].startswith("parkiran") and n["tangga"]:
            cat.append("tangga turun: mask tangga utuh sampai anak tangga bawah")
            kerja += 3
        if r["bucket"] == "D" or (n["tangga"] and r["bucket"] != "E" and not r["lokasi"].startswith("parkiran")):
            cat.append("cek mask tangga (bagian gelap/atas ikut)")
        if n["tepian"]:
            cat.append(f"cek tepian ({n['tepian']}): kerb asli vs dasar planter/garis")
        if n["pilar"]:
            cat.append(f"cek pilar ({n['pilar']}): sirip/kosen bukan pilar (R1), tambah tiang terlewat")
        if n["pohon"]:
            cat.append(f"pohon ({n['pohon']}): batang saja")
        if n["kursi"] >= 4:
            cat.append(f"kursi ({n['kursi']}): hapus duplikat, R4")
        if n["kendaraan"] >= 5:
            cat.append(f"kendaraan ({n['kendaraan']}): barisan rapat di belakang boleh tidak dilabel")
        if n["orang"]:
            cat.append(f"orang ({n['orang']}): di balik kaca tidak dilabel (R2)")
        al = alasan_auto.get(r["stem"], "")
        if "permukaan ambigu" in al:
            cat.append("permukaan ambigu: jalur_jalan vs jalan_kendaraan")
        if not cat:
            cat.append("cek objek terlewat")
        baris.append(dict(urut=0, filename=f"{r['stem']}.jpg", bucket=r["bucket"], lokasi=r["lokasi"], pov=r["pov"],
                          perkiraan_kerja=round(kerja, 1), n_shape=sum(n.values()),
                          isi="; ".join(f"{k} {v}" for k, v in sorted(n.items())), catatan="; ".join(cat), alasan_auto=al))
    baris.sort(key=lambda b: (-b["perkiraan_kerja"], b["filename"]))
    for i, b in enumerate(baris):
        b["urut"] = i + 1
    with (OUT / "review_list.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, list(baris[0].keys()))
        wr.writeheader()
        wr.writerows(baris)
    log(f"- [R1-4] review_list.csv dibuat (urut perkiraan kerja; kerja per shape dari studi val: {json.dumps({k: round(v, 2) for k, v in per_shape.items()})}).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("aksi", choices=["auto", "draft", "review-list"])
    a = ap.parse_args()
    {"auto": cmd_auto, "draft": cmd_draft, "review-list": cmd_review_list}[a.aksi](a)


if __name__ == "__main__":
    main()
