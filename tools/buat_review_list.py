"""buat_review_list.py - urutan review frame test: frame yang paling mungkin perlu diperbaiki di atas.

Sumber: JSON auto di data/test-review (setelah perbaikan mekanis), ringkasan_run.csv (alasan flag pipeline),
perbaikan_mekanis.csv. Tidak ada model yang dijalankan. Tulis data/test-review/review_list.csv.

Skor prioritas (jumlah):
  - alasan flag pipeline x bobot BOBOT_ALASAN (permukaan ambigu 3, pohon perlu cek 3, tepian kandidat 2, dst.)
  - shape difficult (skor ragu): 1 per shape
  - kelas yang diketahui sering salah/terlewat: tiap shape pilar 0,5, tepian 0,5, pohon 1, tanaman_pot 0,5
  - frame di lokasi yang diawali PERHATIAN: bonus manual (lihat PERHATIAN di bawah)
  - shape R4 yang dihapus mekanis dan hanya kurang <= 2 px dari ambang: 3 (kemungkinan perlu ditambah lagi)
  - frame tanpa satu pun shape objek di kelas yang diketahui sering terlewat: 2
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from autolabel_v2 import BOBOT_ALASAN, KELAS  # noqa: E402

D = Path("data/test-review")
BOBOT_KELAS = {"pilar": 0.5, "tepian": 0.5, "pohon": 1.0, "tanaman_pot": 0.5}
# keputusan manual yang diminta Jeka: frame ini wajib diputuskan saat review
PERHATIAN = {
    "taman-ubm_2026-11-07_01_dada_t0001000": (100, "PERMUKAAN: area batu kasar dengan kerb kuning melengkung di kiri bawah; "
                                                  "jalan_kendaraan jika dipakai kendaraan, kalau tidak jalur_jalan (keputusan Jeka)"),
}


def main():
    alasan = {}
    p = D / "ringkasan_run.csv"
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8")):
            alasan[r["filename"]] = r["alasan"]
    mekanis = {}
    p = D / "perbaikan_mekanis.csv"
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8")):
            mekanis.setdefault(r["frame"], []).append(r)
    daftar = {r["frame"]: r for r in csv.DictReader((D / "daftar_test.csv").open(encoding="utf-8"))}
    rows = []
    for j in sorted(D.glob("*.json")):
        d = json.loads(j.read_text(encoding="utf-8"))
        nama = d["imagePath"]
        sh = d["shapes"]
        c = Counter(s["label"] for s in sh)
        sulit = sum(bool(s.get("difficult")) for s in sh)
        skor_min = min((s["score"] for s in sh), default=0)
        sebab = [x for x in alasan.get(nama, "").split("; ") if x]
        pri = sum(BOBOT_ALASAN.get(x.split(" x")[0], 1) for x in sebab)
        pri += sulit + sum(BOBOT_KELAS.get(k, 0) * n for k, n in c.items())
        cat = []
        if sulit:
            cat.append(f"{sulit} shape difficult")
        if not any(c[k] for k in BOBOT_KELAS):
            pri += 2
            cat.append("tidak ada pilar/tepian/pohon/tanaman_pot (mungkin terlewat)")
        if not sh:
            cat.append("frame kosong")
        for m in mekanis.get(j.stem, []):
            w, h = [int(v) for v in m["alasan"].split()[-1].split("x")]
            kurang = max(0, 96 - min(w, h)) if m["kelas"] not in ("pilar", "pohon", "tepian") else 0
            cat.append(f"dihapus mekanis R4: {m['kelas']} {m['alasan']}")
            if 0 < kurang <= 2:
                pri += 3
                cat.append("(hanya kurang 1-2 px dari ambang, cek apakah perlu ditambah lagi)")
        if j.stem in PERHATIAN:
            pri += PERHATIAN[j.stem][0]
            cat.append(PERHATIAN[j.stem][1])
        dr = daftar.get(nama, {})
        rows.append({"filename": nama, "prioritas": round(pri, 1), "location": dr.get("location", ""), "pov": dr.get("pov", ""),
                     "timestamp_s": dr.get("timestamp_s", ""), "alasan_pipeline": "; ".join(sebab),
                     "skor_min": round(skor_min, 2), "n_shape": len(sh), "catatan": " | ".join(cat),
                     **{k: c[k] for k in KELAS}})
    rows.sort(key=lambda r: (-r["prioritas"], r["filename"]))
    for i, r in enumerate(rows, 1):
        r["no"] = i
    kol = ["no", "filename", "prioritas", "location", "pov", "timestamp_s", "alasan_pipeline", "catatan", "skor_min",
           "n_shape"] + KELAS
    with (D / "review_list.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, kol)
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "frame ->", D / "review_list.csv")
    for r in rows[:8]:
        print(r["no"], r["filename"][:48], r["prioritas"], r["catatan"][:80])


if __name__ == "__main__":
    main()
