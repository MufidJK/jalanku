"""validasi_ronde2.py - section 6.1-6.3 ronde 2: cek simpan, validasi label hasil review, kualitas draft.

Dijalankan dari root repo:
  python tools/validasi_ronde2.py simpan     # 6.1 JSON yang tidak disimpan setelah draft (mtime <= acuan R1-7)
  python tools/validasi_ronde2.py validasi   # 6.2 kelas, titik, header, R4 (hitung saja), R6, dua kelas satu objek
  python tools/validasi_ronde2.py kualitas   # 6.3 draft (data/ronde2-auto-backup) vs label akhir (data/ronde2-review)

Hanya MEMBACA JSON. Tidak ada label yang diubah: R4 diterapkan saat membangun dataset (tools/bangun_dataset_ronde2.py),
di sini hanya dihitung. Keluaran ke data/ronde2/ (validasi_*.csv, kualitas_draft*.csv).
Frame yang dikeluarkan (data/ronde2/bocor/dikeluarkan.csv) tidak ada di folder review, jadi otomatis tidak ikut.
"""
import csv
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import cek_test_set as cts  # noqa: E402
import kualitas_auto as ka  # noqa: E402

REV = Path("data/ronde2-review")
AUTO = Path("data/ronde2-auto-backup")
OUT = Path("data/ronde2")
KELAS = Path("data/pilot/classes.txt").read_text().split()
KOTAK, PERMUKAAN = ka.KOTAK, ka.PERMUKAAN
KOTAK_OBJ = [k for k in KOTAK if k != "tangga"]
ACUAN_MTIME = dt.datetime(2026, 11, 12, 22, 46, 4)  # LOG R1-7: JSON draft terakhir ditulis
W, H, S = 1080, 1920, 0.5
# pasangan beda kelas yang sah bertumpuk (v1.8: batang pohon dalam bedeng = pohon; pengendara = orang di atas kendaraan)
PASANGAN_SAH = {frozenset(("pohon", "tanaman_pot")), frozenset(("orang", "kendaraan")), frozenset(("orang", "kursi"))}


def stems():
    return sorted(p.stem for p in REV.glob("*.json"))


def baca(folder, stem):
    return json.loads((folder / f"{stem}.json").read_text(encoding="utf-8"))


def raster(points):
    m = np.zeros((int(H * S), int(W * S)), np.uint8)
    cv2.fillPoly(m, [np.round(np.asarray(points, float) * S).astype(np.int32)], 1)
    return m.astype(bool)


def lolos_r4(label, points):
    return cts.lolos_r4(label, cts.bbox(points, W, H))


def fmt(b):
    return "%d,%d,%d,%d" % tuple(round(v) for v in b)


def asal(s, draft_keys):
    """auto-kasar = shape draft yang tidak diubah sama sekali; draft-diedit = description r2 tapi titik berubah; manual."""
    d = s.get("description") or ""
    if (s["label"], json.dumps(s["points"])) in draft_keys:
        return "draft-tak-diubah (" + d + ")"
    if d.startswith("r2 "):
        return "draft-diedit (" + d + ")"
    return "manual"


def cmd_simpan():
    rows = []
    for st in stems():
        m = dt.datetime.fromtimestamp((REV / f"{st}.json").stat().st_mtime)
        sama = (REV / f"{st}.json").read_bytes() == (AUTO / f"{st}.json").read_bytes()
        if m <= ACUAN_MTIME or sama:
            rows.append((st, m.strftime("%Y-%m-%d %H:%M:%S"), "byte-identik dengan draft" if sama else "isi beda"))
    print(f"{len(stems())} frame di review; tidak disimpan setelah draft (mtime <= {ACUAN_MTIME} atau byte-identik): {len(rows)}")
    for r in rows:
        print("  ", *r)
    with open(OUT / "validasi_tidak_disimpan.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["stem", "mtime", "status"])
        w.writerows(rows)


def cmd_validasi():
    err, r4, r6, dua, n_shape = [], Counter(), [], [], Counter()
    for st in stems():
        d = baca(REV, st)
        raw = (REV / f"{st}.json").read_bytes()
        if b"\r\n" not in raw:
            err.append((st, "bukan CRLF"))
        if d.get("imagePath") != f"{st}.jpg" or (d.get("imageWidth"), d.get("imageHeight")) != (W, H) or d.get("imageData"):
            err.append((st, "header salah"))
        draft_keys = {(s["label"], json.dumps(s["points"])) for s in baca(AUTO, st)["shapes"]}
        sh = d["shapes"]
        obj = []
        for i, s in enumerate(sh):
            p = np.asarray(s["points"], float)
            n_shape[s["label"]] += 1
            if s["label"] not in KELAS:
                err.append((st, f"#{i} label tidak dikenal: {s['label']}"))
                continue
            if s.get("shape_type") not in ("polygon", "rectangle") or len(p) < 3:
                err.append((st, f"#{i} {s['label']} shape_type {s.get('shape_type')} / {len(p)} titik"))
                continue
            if p.min() < -1 or p[:, 0].max() > W + 1 or p[:, 1].max() > H + 1:
                err.append((st, f"#{i} {s['label']} titik di luar gambar ({fmt(p.min(0).tolist() + p.max(0).tolist())})"))
            if s["label"] in KOTAK_OBJ:
                if not lolos_r4(s["label"], s["points"]):
                    r4[s["label"]] += 1
                    continue  # tidak masuk dataset, tidak ikut cek R6
                obj.append((i, s, raster(s["points"]), cts.bbox(s["points"], W, H), asal(s, draft_keys)))
        # tangga: kotak gabungan per frame
        tp = [np.asarray(s["points"], float) for s in sh if s["label"] == "tangga" and len(s["points"]) >= 3]
        if tp and not lolos_r4("tangga", np.vstack(tp)):
            r4["tangga (gabungan)"] += 1
        # R6 sekelas: containment mask >= 0.8; dua kelas satu objek: beda kelas, IoU kotak >= 0.7 atau containment >= 0.8
        for a in range(len(obj)):
            for b in range(a + 1, len(obj)):
                ia, sa, ma, ba, oa = obj[a]
                ib, sb, mb, bb, ob = obj[b]
                inter = int((ma & mb).sum())
                if not inter:
                    continue
                cont = inter / max(1, min(int(ma.sum()), int(mb.sum())))
                iou = ka.iou(ba, bb)
                kecil = (ia, sa, ba, oa) if ma.sum() <= mb.sum() else (ib, sb, bb, ob)
                besar = (ib, sb, bb, ob) if kecil[0] == ia else (ia, sa, ba, oa)
                if sa["label"] == sb["label"] and cont >= 0.8:
                    r6.append(dict(stem=st, kelas=sa["label"], containment=round(cont, 2), iou_kotak=round(iou, 2),
                                   kecil_id=kecil[0], kecil_bbox=fmt(kecil[2]), kecil_asal=kecil[3],
                                   besar_id=besar[0], besar_bbox=fmt(besar[2]), besar_asal=besar[3]))
                elif sa["label"] != sb["label"] and (iou >= 0.7 or cont >= 0.8):
                    sah = frozenset((sa["label"], sb["label"])) in PASANGAN_SAH and iou < 0.7
                    dua.append(dict(stem=st, kelas_a=sa["label"], id_a=ia, bbox_a=fmt(ba), asal_a=oa,
                                    kelas_b=sb["label"], id_b=ib, bbox_b=fmt(bb), asal_b=ob, iou_kotak=round(iou, 2),
                                    containment=round(cont, 2), catatan="pasangan wajar (cek cepat)" if sah else "PERIKSA"))
        # permukaan: jalur_jalan vs jalan_kendaraan bertumpuk
        mk = ka.mask(sh)
        a_, b_ = mk["jalur_jalan"], mk["jalan_kendaraan"]
        if a_.sum() and b_.sum():
            inter = int((a_ & b_).sum())
            frac = inter / min(int(a_.sum()), int(b_.sum()))
            if frac >= 0.05:
                dua.append(dict(stem=st, kelas_a="jalur_jalan", id_a="", bbox_a="", asal_a="", kelas_b="jalan_kendaraan",
                                id_b="", bbox_b="", asal_b="", iou_kotak="", containment=round(frac, 2),
                                catatan=f"PERIKSA permukaan bertumpuk {inter / (S * S):.0f} px"))
    print(f"{len(stems())} frame | shape per kelas: {dict(n_shape)}")
    print(f"error struktur: {len(err)}")
    for e in err:
        print("  ", *e)
    print(f"R4 (dibuang saat bangun dataset, tanpa pengecualian): {sum(r4.values())} {dict(r4)}")
    print(f"R6 sekelas containment >= 0.8: {len(r6)}")
    for r in r6:
        print(f"   {r['stem']} {r['kelas']} cont {r['containment']} iou {r['iou_kotak']} | kecil #{r['kecil_id']} "
              f"[{r['kecil_bbox']}] {r['kecil_asal']} | besar #{r['besar_id']} [{r['besar_bbox']}] {r['besar_asal']}")
    print(f"dua kelas satu objek (kandidat): {len(dua)} (PERIKSA {sum(r['catatan'].startswith('PERIKSA') for r in dua)})")
    for r in dua:
        print(f"   {r['stem']} {r['kelas_a']}#{r['id_a']} [{r['bbox_a']}] vs {r['kelas_b']}#{r['id_b']} [{r['bbox_b']}] "
              f"iou {r['iou_kotak']} cont {r['containment']} -> {r['catatan']}")
    for nama, rows in (("validasi_r6.csv", r6), ("validasi_dua_kelas.csv", dua)):
        with open(OUT / nama, "w", newline="", encoding="utf-8") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
    with open(OUT / "validasi_ringkas.json", "w", encoding="utf-8") as f:
        json.dump(dict(frame=len(stems()), shape=n_shape, error=err, r4=r4, r6=len(r6), dua_kelas=len(dua)), f, indent=1)


def muat_r4(folder, st):
    return [s for s in baca(folder, st)["shapes"]
            if not (s["label"] in KOTAK_OBJ and not lolos_r4(s["label"], s["points"]))]


def sumber(s):
    d = s.get("description") or ""
    return "model" if d.startswith("r2 model") else ("auto" if d.startswith("r2 auto") else "lain")


def cmd_kualitas():
    st_all = stems()
    st = defaultdict(Counter)
    for stem in st_all:
        sp, sg = muat_r4(AUTO, stem), muat_r4(REV, stem)
        og = ka.objek(sg)
        for k in KOTAK:
            if k == "tangga":
                pred = ka.objek(sp).get(k, [])
                src = ["auto"] * len(pred)
            else:
                ps = [s for s in sp if s["label"] == k]
                pred = [ka.kotak_dari(s["points"]) for s in ps]
                src = [sumber(s) for s in ps]
            gt = og.get(k, [])
            pas, fp, fn = ka.cocokkan(pred, gt, 0.5)
            c = st[("kotak", k)]
            c["gt"] += len(gt); c["pred"] += len(pred); c["tp"] += len(pas); c["fp"] += len(fp); c["fn"] += len(fn)
            c["tp_iou07"] += sum(v >= 0.7 for _, _, v in pas)
            for i, _, _ in pas:
                c["tp_" + src[i]] += 1
            for i in range(len(pred)):
                c["pred_" + src[i]] += 1
        mp, mg = ka.mask(sp), ka.mask(sg)
        for k in PERMUKAAN:
            a_, g_ = mp[k], mg[k]
            c = st[("mask", k)]
            c["i"] += int((a_ & g_).sum()); c["pa"] += int(a_.sum()); c["pg"] += int(g_.sum()); c["u"] += int((a_ | g_).sum())
    # hitung edit pada shape (setelah filter R4 yang sama)
    e = defaultdict(Counter)
    for stem in st_all:
        a, r = muat_r4(AUTO, stem), muat_r4(REV, stem)
        sisa_a = list(range(len(a)))
        kunci = defaultdict(list)
        for i in sisa_a:
            kunci[(a[i]["label"], json.dumps(a[i]["points"]))].append(i)
        sisa_r = []
        for j, s in enumerate(r):
            kk = (s["label"], json.dumps(s["points"]))
            if kunci.get(kk):
                sisa_a.remove(kunci[kk].pop()); e[s["label"]]["sama"] += 1
            else:
                sisa_r.append(j)
        for j in list(sisa_r):  # diedit: kelas sama, kotak IoU >= 0.5 (termasuk digambar ulang)
            bj = ka.kotak_dari(r[j]["points"])
            cal = [i for i in sisa_a if a[i]["label"] == r[j]["label"] and ka.iou(ka.kotak_dari(a[i]["points"]), bj) >= 0.5]
            if cal:
                i = max(cal, key=lambda i: ka.iou(ka.kotak_dari(a[i]["points"]), bj))
                sisa_a.remove(i); sisa_r.remove(j); e[a[i]["label"]]["diedit"] += 1
        for j in list(sisa_r):  # ganti kelas: beda kelas, kotak IoU >= 0.5
            bj = ka.kotak_dari(r[j]["points"])
            cal = [i for i in sisa_a if ka.iou(ka.kotak_dari(a[i]["points"]), bj) >= 0.5]
            if cal:
                i = max(cal, key=lambda i: ka.iou(ka.kotak_dari(a[i]["points"]), bj))
                sisa_a.remove(i); sisa_r.remove(j); e[a[i]["label"]]["ganti_kelas"] += 1; e[r[j]["label"]]["dari_kelas_lain"] += 1
        for i in sisa_a:
            e[a[i]["label"]]["dihapus"] += 1
        for j in sisa_r:
            e[r[j]["label"]]["ditambah"] += 1
    rows = []
    for (jenis, k), c in st.items():
        r = dict(jenis=jenis, kelas=k)
        if jenis == "kotak":
            r.update(gt=c["gt"], draft=c["pred"], tp=c["tp"], fp=c["fp"], fn=c["fn"],
                     precision=ka.bagi(c["tp"], c["pred"]), recall=ka.bagi(c["tp"], c["gt"]),
                     tp_iou_ge_07=c["tp_iou07"],
                     p_model=ka.bagi(c["tp_model"], c["pred_model"]), n_model=c["pred_model"],
                     p_auto=ka.bagi(c["tp_auto"], c["pred_auto"]), n_auto=c["pred_auto"])
        else:
            if k == "tangga":
                r["jenis"] = "mask"
            r.update(gt=c["pg"], draft=c["pa"], precision=ka.bagi(c["i"], c["pa"]), recall=ka.bagi(c["i"], c["pg"]),
                     iou=ka.bagi(c["i"], c["u"]))
        if not (jenis == "mask" and k == "tangga"):
            r.update({x: e[k][x] for x in ("sama", "diedit", "ganti_kelas", "dihapus", "ditambah", "dari_kelas_lain")})
        rows.append(r)
    kol = ["jenis", "kelas", "gt", "draft", "tp", "fp", "fn", "precision", "recall", "tp_iou_ge_07", "iou", "p_model", "n_model",
           "p_auto", "n_auto", "sama", "diedit", "ganti_kelas", "dihapus", "ditambah", "dari_kelas_lain"]
    with open(OUT / "kualitas_draft.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, kol)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(st_all)} frame (draft vs label akhir, R4 di kedua sisi, IoU 0.5)")
    for r in rows:
        ext = (f"tp {r['tp']} fp {r['fp']} fn {r['fn']} | P model {r['p_model']} (n {r['n_model']}) P auto {r['p_auto']} (n {r['n_auto']})"
               if r["jenis"] == "kotak" else f"IoU {r['iou']}")
        ed = (f" | sama {r['sama']} diedit {r['diedit']} ganti_kelas {r['ganti_kelas']} dihapus {r['dihapus']} ditambah {r['ditambah']}"
              if "sama" in r else "")
        print(f"{r['jenis']:5s} {r['kelas']:16s} gt {r['gt']!s:7s} draft {r['draft']!s:7s} P {r['precision']!s:6s} R {r['recall']!s:6s} {ext}{ed}")


if __name__ == "__main__":
    {"simpan": cmd_simpan, "validasi": cmd_validasi, "kualitas": cmd_kualitas}[sys.argv[1]]()
