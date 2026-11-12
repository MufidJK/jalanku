"""kualitas_auto_test.py - ukur kualitas auto-label (pipeline pilot) terhadap label manusia di test set.

Dijalankan dari root repo: python tools/kualitas_auto_test.py
Hanya membaca JSON; menulis data/test-review/kualitas_auto.csv dan kualitas_auto_edit.csv. Tidak menjalankan model apa pun.

Prediksi = data/test-review-auto-backup (auto mentah), GT = data/test-review (hasil review penuh Jeka).
Aturan sama dengan tools/kualitas_auto.py (pilot): kotak dari bounding box polygon, cocok kalau IoU >= 0.5 (satu-satu,
greedy); semua shape tangga per frame digabung; permukaan = mask union per kelas per frame (rasterisasi 540x960),
precision/recall/IoU piksel.
Beda dengan pilot: R4 (kelas kotak) diterapkan ke KEDUA sisi sebelum membandingkan (shape di bawah ambang bukan label,
jadi auto yang kecil tidak dihitung salah, dan GT tidak punya yang kecil). Frame kosong tetap dihitung.
Hitungan edit (sama / diedit / dihapus / ditambah) dilakukan pada shape mentah setelah filter R4 yang sama.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cek_test_set as cts  # noqa: E402
import kualitas_auto as ka  # noqa: E402

AUTO = Path("data/test-review-auto-backup")
REV = Path("data/test-review")
KOTAK, PERMUKAAN = ka.KOTAK, ka.PERMUKAAN


def muat(folder, stem):
    """Shape dengan filter R4 untuk kelas kotak non-tangga (tangga: tidak ada di test set, dijaga untuk kelengkapan)."""
    out = []
    for s in json.loads((folder / f"{stem}.json").read_text(encoding="utf-8"))["shapes"]:
        if s["label"] in KOTAK and s["label"] != "tangga" and not cts.lolos_r4(s["label"], cts.bbox(s["points"], 1080, 1920)):
            continue
        out.append(s)
    return out


def lokasi(stem):
    return "taman-ubm" if stem.startswith("taman-ubm") else "lantai-11"


def hitung_edit(stems):
    e = defaultdict(Counter)
    for stem in stems:
        a, r = muat(AUTO, stem), muat(REV, stem)
        sisa_a, sisa_r = list(range(len(a))), []
        kunci = defaultdict(list)
        for i in sisa_a:
            kunci[(a[i]["label"], json.dumps(a[i]["points"]))].append(i)
        for j, s in enumerate(r):
            kk = (s["label"], json.dumps(s["points"]))
            if kunci.get(kk):
                sisa_a.remove(kunci[kk].pop())
                e[s["label"]]["sama"] += 1
            else:
                sisa_r.append(j)
        for j in list(sisa_r):  # diedit: shape yang masih punya description auto-v2 yang sama
            d = r[j].get("description") or ""
            cal = [i for i in sisa_a if d.startswith("auto-v2") and a[i].get("description") == d]
            if cal:
                bj = ka.kotak_dari(r[j]["points"])
                i = max(cal, key=lambda i: (a[i]["label"] == r[j]["label"], ka.iou(ka.kotak_dari(a[i]["points"]), bj)))
                sisa_a.remove(i); sisa_r.remove(j)
                e[a[i]["label"]]["diedit"] += 1
        for j in list(sisa_r):  # diedit: digambar ulang (mis. jadi rectangle), kelas sama, kotak IoU >= 0.5
            bj = ka.kotak_dari(r[j]["points"])
            cal = [i for i in sisa_a if a[i]["label"] == r[j]["label"] and ka.iou(ka.kotak_dari(a[i]["points"]), bj) >= 0.5]
            if cal:
                i = max(cal, key=lambda i: ka.iou(ka.kotak_dari(a[i]["points"]), bj))
                sisa_a.remove(i); sisa_r.remove(j)
                e[a[i]["label"]]["diedit"] += 1
        for i in sisa_a:
            e[a[i]["label"]]["dihapus"] += 1
        for j in sisa_r:
            e[r[j]["label"]]["ditambah"] += 1
    return e


def bandingkan(nama, stems, rows):
    st = defaultdict(Counter)
    for stem in stems:
        sp, sg = muat(AUTO, stem), muat(REV, stem)
        op, og = ka.objek(sp), ka.objek(sg)
        for k in KOTAK:
            pred, gt = op.get(k, []), og.get(k, [])
            pas, fp, fn = ka.cocokkan(pred, gt, 0.5)
            pas3, _, _ = ka.cocokkan(pred, gt, 0.3)
            c = st[("kotak", k)]
            c["frame"] += 1
            c["gt"] += len(gt); c["pred"] += len(pred); c["tp"] += len(pas); c["fp"] += len(fp); c["fn"] += len(fn)
            c["tp03"] += len(pas3)
            lain = [b for kk in KOTAK if kk != k for b in og.get(kk, [])]
            c["salah_kelas"] += sum(any(ka.iou(pred[i], b) >= 0.5 for b in lain) for i in fp)
        mp, mg = ka.mask(sp), ka.mask(sg)
        for k in PERMUKAAN:
            a_, g_ = mp[k], mg[k]
            i, u = int((a_ & g_).sum()), int((a_ | g_).sum())
            c = st[("mask", k)]
            c["frame"] += 1
            c["i"] += i; c["pa"] += int(a_.sum()); c["pg"] += int(g_.sum()); c["u"] += u
            if u:
                c["frame_ada"] += 1
                c["iou_frame_sum"] += i / u
    e = hitung_edit(stems)
    for (jenis, k), c in st.items():
        r = {"set": nama, "jenis": jenis, "kelas": k, "frame": c["frame"]}
        if jenis == "kotak":
            r.update(gt=c["gt"], auto=c["pred"], tp=c["tp"], fp=c["fp"], fn=c["fn"],
                     precision=ka.bagi(c["tp"], c["tp"] + c["fp"]), recall=ka.bagi(c["tp"], c["gt"]),
                     fp_salah_kelas=c["salah_kelas"],
                     precision_iou03=ka.bagi(c["tp03"], c["pred"]), recall_iou03=ka.bagi(c["tp03"], c["gt"]))
        else:
            r.update(gt=c["pg"], auto=c["pa"], tp=c["i"], fp=c["pa"] - c["i"], fn=c["pg"] - c["i"],
                     precision=ka.bagi(c["i"], c["pa"]), recall=ka.bagi(c["i"], c["pg"]), iou=ka.bagi(c["i"], c["u"]),
                     frame_ada=c["frame_ada"], iou_frame_rata=ka.bagi(c["iou_frame_sum"], c["frame_ada"]))
        if jenis == "kotak" or k != "tangga":
            ee = e[k]
            r.update(sama=ee["sama"], diedit=ee["diedit"], dihapus=ee["dihapus"], ditambah=ee["ditambah"])
        rows.append(r)
    return e


def main():
    stems = sorted(p.stem for p in REV.glob("*.json"))
    assert all((AUTO / f"{s}.json").exists() for s in stems), "backup auto tidak lengkap"
    rows, edit_rows = [], []
    for nama, sub in (("semua", stems), ("lantai-11", [s for s in stems if lokasi(s) == "lantai-11"]),
                      ("taman-ubm", [s for s in stems if lokasi(s) == "taman-ubm"])):
        e = bandingkan(nama, sub, rows)
        for k in ka.KELAS:
            edit_rows.append([nama, k, e[k]["sama"], e[k]["diedit"], e[k]["dihapus"], e[k]["ditambah"]])
    kol = ["set", "jenis", "kelas", "frame", "gt", "auto", "tp", "fp", "fn", "precision", "recall", "iou", "frame_ada",
           "iou_frame_rata", "fp_salah_kelas", "precision_iou03", "recall_iou03", "sama", "diedit", "dihapus", "ditambah"]
    with open(REV / "kualitas_auto.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, kol)
        wr.writeheader()
        wr.writerows(rows)
    with open(REV / "kualitas_auto_edit.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["set", "kelas", "sama", "diedit", "dihapus", "ditambah"])
        wr.writerows(edit_rows)
    print(f"{len(stems)} frame")
    for r in rows:
        if r["set"] != "semua":
            continue
        ext = f"iou {r['iou']}" if r["jenis"] == "mask" else f"tp {r['tp']} fp {r['fp']} fn {r['fn']}"
        print(f"{r['jenis']:5s} {r['kelas']:16s} gt {r['gt']!s:7s} auto {r['auto']!s:7s} P {r['precision']!s:6s} R {r['recall']!s:6s} {ext} | "
              f"sama {r.get('sama', '')} diedit {r.get('diedit', '')} dihapus {r.get('dihapus', '')} ditambah {r.get('ditambah', '')}")


if __name__ == "__main__":
    main()
