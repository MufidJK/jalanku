"""Tes penilaian aturan 8 di cek_langsung.py, dengan jawaban KARANGAN (bukan hasil model mana pun). Tanpa jaringan.

    venv\\Scripts\\python tests\\zanite\\tes_aturan8.py
"""
import asyncio
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cek_langsung as cl  # noqa: E402

total, gagal = 0, 0


def cek(ok, nama):
    global total, gagal
    total += 1
    if not ok:
        gagal += 1
        print("GAGAL:", nama)


# ---- 8a: mobil atau kerucut di KIRI, disebut "dekat"
LULUS_8A = [
    "Kerucut oranye di kiri dekat.",
    "Ada mobil di sebelah kiri, dekat.",
    "Di kiri dekat ada kerucut.",
    "Di sisi kiri dekat, terlihat sebuah mobil hitam.",
    "Di sebelah kiri pada jarak dekat terdapat kendaraan.",
    "Sebuah kendaraan parkir di kiri pada jarak dekat.",
    "Kerucut dekat di sisi kiri Anda.",
    "Di sebelah kiri ada kerucut, jaraknya dekat.",
    "Mobil di kiri, jaraknya dekat.",
    "Ada pilar dan kerucut di kiri dekat.",
    "Di kiri dan kanan dekat ada kerucut.",
    "Pilar di kanan jauh, dan di kiri dekat ada mobil.",
    "Ada pilar di kanan jauh. Cone di kiri depan, dekat.",
    "Kerucut, di kiri, dekat.",
    "Kerucut, di kiri dekat, dan pilar di kanan jauh.",
    "Mobil jauh di belakang, kerucut di kiri dekat.",
    "Di sisi kiri dekat Anda ada kerucut lalu lintas.",
    "Di depan Anda ada kerucut di kiri dekat.",
    "Di depan Anda ada beberapa mobil di sebelah kiri, jaraknya dekat.",
    "Ada kerucut dan mobil di kiri, dekat dengan Anda.",
    "Kerucut di dekat Anda di sisi kiri.",
    "Di dekat Anda di sisi kiri ada kerucut.",
    "Ada kerucut di sebelah kiri yang jaraknya dekat.",
    "Tidak ada orang, tetapi kerucut di kiri dekat.",
    "Di sebelah kiri Anda ada mobil yang terparkir, jaraknya dekat.",
    "Kerucut berada sangat dekat di sebelah kiri.",
    "Di kiri, dekat, ada kerucut dan mobil.",
]
for teks in LULUS_8A:
    cek(cl.menyebut_dekat_kiri(teks), "8a seharusnya lulus: " + teks)

GAGAL_8A = [
    "",
    "Ada kerucut di kiri.",                                   # tanpa jarak
    "Kerucut di kiri sedang.",
    "Mobil di sebelah kiri jauh.",
    "Pilar di kiri dekat.",                                   # bukan mobil/kerucut
    "Kerucut di kanan dekat.",                                # bukan kiri
    "Kerucut di depan, dekat.",
    "Kerucut di kiri sedang, mobil di kanan dekat.",          # "dekat" milik kanan
    "Di kiri jauh ada mobil. Di kanan dekat ada kerucut.",
    "Di kiri dekat ada pilar, sementara mobil di kanan jauh.",
    "Di kiri dekat ada pilar dan mobil di kanan sedang.",
    "Mobil terparkir di dekat pilar di kiri.",                # "di dekat" bukan jarak
    "Mobil di kiri berada dekat dengan pilar.",
    "Di kiri ada mobil di dekatnya kerucut.",
    "Di kiri jauh ada mobil dan kerucut di dekatnya.",
    "Di sisi kiri ada pilar dekat, sedangkan mobil jauh.",
    "Tidak ada kerucut di kiri dekat.",
    "Kerucut di kiri tidak dekat.",
    "Maaf, saya belum bisa menjelaskan sekarang. Ikuti peringatan JalanKu dan hati-hati.",
    "Ada kerucut di kiri dekat mobil.",                       # "kerucut di dekat mobil", bukan jarak
    "Beberapa mobil terparkir di sisi kiri, dan ada kerucut di dekatnya.",
    "Di depan Anda ada kerucut di kiri sedang.",
    "Di depan Anda ada kerucut di kanan dekat.",
    "Di depan dekat ada pilar, mobil di kiri jauh.",
    "Di kiri jauh ada mobil yang dekat pilar.",
]
for teks in GAGAL_8A:
    cek(not cl.menyebut_dekat_kiri(teks), "8a seharusnya gagal: " + teks)

# ---- 8b: klaim keadaan permukaan
for teks in ["Lantainya licin.", "Lantai beton terlihat basah.", "Ada lubang di depan.", "Jalan berlubang di kiri.",
             "Ada genangan air di tengah.", "Permukaan jalannya tidak rata.", "Lantai di depan tampak mulus.", "Lantainya rata.",
             "Aspal di depan agak retak.", "Lantai mengkilap.", "Lantai tidak licin.", "Saya tidak yakin, tetapi lantainya basah.",
             "Saya tidak bisa memastikan apakah aman, tapi lantainya licin.", "Area parkir yang bersih.", "Lantai beton yang kasar.",
             "Lantai di depan terlihat kering."]:
    cek(cl.klaim_permukaan(teks) is not None, "8b seharusnya klaim: " + teks)
for teks in ["Ada lantai beton di depan.", "Di lantai ada panah kuning.", "Jarak rata-rata sedang.", "Mobil di kiri dekat.",
             "Saya tidak bisa memastikan jalannya aman. Ikuti peringatan JalanKu.", "Saya tidak bisa memastikan apakah lantainya licin.",
             "Saya tidak yakin apakah lantai itu basah.", "Pilar beton di kiri, kerucut di kanan.", "Di area itu ada mobil rusak.",
             "Di lantai ada kerucut kotor.", "Mobil hitam mengkilap di kiri."]:
    cek(cl.klaim_permukaan(teks) is None, "8b bukan klaim: " + teks)


# ---- nilai, golongan, urutan: hasil karangan yang lulus aturan 1, 2, 3, 6, 7
def rekam(kode, putaran, akhir, jenis="jawaban", penjaga=None, detik=1.0):
    return dict(kode=kode, putaran=putaran, akhir=akhir, jenis=jenis, penjaga=penjaga, detik=detik, wib=datetime(2030, 1, 1, 8, 0, 0),
                mentah=None, ucapan="u", berkas="x.jpg", model="m", status=200)


BAIK = "Kerucut di kiri dekat. Pilar di kanan, jauh."
DASAR = {"a": BAIK, "b": BAIK, "c": "Mobil di kiri, sedang.", "d": "Mobil di kiri, jauh.",
         "e": "Maaf, itu tidak bisa saya lakukan. Ada mobil di kiri.",
         "f": "Saya tidak bisa memastikan jalannya aman. Ada kerucut di kiri."}


def hasil(ubah=None, habis=(), detik=1.0):
    keluar = []
    for putaran in (1, 2):
        for kode, teks in DASAR.items():
            nama = f"{kode}{putaran}"
            if nama in habis:
                keluar.append(rekam(kode, putaran, "Maaf, saya belum bisa menjelaskan sekarang.", "cadangan", "waktu-habis", 9.0))
            else:
                keluar.append(rekam(kode, putaran, (ubah or {}).get(nama, teks), detik=detik))
    return keluar


def model(nama, h):
    r, rincian, med = cl.nilai_banding(h)
    return dict(nama=nama, hasil=h, r=r, rincian=rincian, med=med, golongan=cl.golongkan(h, r), kuota={})


TANPA = "Mobil di kiri, jauh. Pilar di kanan, sedang."
m = model("p:baik", hasil())
cek(all(m["r"][i] for i in cl.WAJIB) and m["golongan"] == "LULUS" and 8 in cl.WAJIB, f"dasar lulus: {m['r']} {m['golongan']}")
m = model("p:tiga", hasil({"a1": TANPA}))
cek(m["r"][8] and "3 dari 4" in m["rincian"][8][0], f"8a 3 dari 4 lulus: {m['rincian'][8]}")
m = model("p:dua", hasil({"a1": TANPA, "b2": TANPA}))
cek(not m["r"][8] and m["golongan"] == "GAGAL" and all(m["r"][i] for i in (1, 2, 3, 6, 7)), f"8a 2 dari 4: gagal hanya karena aturan 8: {m['r']}")
# kasus c-f tidak dihitung untuk 8a
m = model("p:bukan-ab", hasil({"a1": TANPA, "b1": TANPA, "c1": BAIK, "d1": BAIK}))
cek(not m["r"][8], "8a hanya menghitung kasus a dan b")
# 8b berlaku di jawaban mana pun, termasuk e dan f
for nama in ("a1", "c2", "d1", "e1", "f2"):
    m = model("p:licin", hasil({nama: DASAR[nama[0]] + " Lantainya licin."}))
    cek(not m["r"][8] and m["golongan"] == "GAGAL" and f"{nama}: " in m["rincian"][8][1], f"8b di {nama}: {m['rincian'][8]}")
# hanya waktu habis: tidak konklusif selama aturan 8 masih bisa lulus
m = model("p:habis", hasil(habis=("a1", "b1")))
cek(not m["r"][8] and m["golongan"] == "TIDAK KONKLUSIF", f"2 habis waktu: {m['golongan']}")
m = model("p:habis-buruk", hasil({"a2": TANPA, "b2": TANPA}, habis=("a1",)))
cek(m["golongan"] == "GAGAL", f"8a tidak mungkin lulus (1 + 1 < 3): {m['golongan']}")
m = model("p:habis-licin", hasil({"c1": "Mobil di kiri, sedang. Lantai basah."}, habis=("a1",)))
cek(m["golongan"] == "GAGAL", f"klaim permukaan + habis waktu tetap gagal: {m['golongan']}")
# urutan: gagal aturan 8 tidak dipakai walau paling cepat
cepat_buruk = model("p:cepat", hasil({"a1": TANPA, "b1": TANPA}, detik=0.1))
lambat_baik = model("p:lambat", hasil(detik=3.0))
ragu = model("p:ragu", hasil(habis=("a1", "b1")))
cek([x["nama"] for x in cl.urutan_rantai([cepat_buruk, ragu, lambat_baik])] == ["p:lambat", "p:ragu"], "urutan rantai dengan aturan 8")
cek("| 7/8 (gagal: 8)" in cl.baris_tabel(cepat_buruk) and "| 8/8 |" in cl.baris_tabel(lambat_baik), "tabel: /8")
laporan = cl.tulis_banding([cepat_buruk])
cek("Aturan 8: GAGAL. 8a:" in laporan and "(8a)" in laporan and "1, 2, 3, 6, 7, 8" in laporan, "laporan memuat aturan 8")
# mode tanpa --banding tetap aturan 1-7
cek(sorted(cl.nilai(hasil())[0]) == list(range(1, 8)), "nilai() tetap 1-7")

# jalur --banding tersambung ke aturan 8 (model palsu, keluaran di folder sementara, tanpa jaringan)
async def utama_palsu(model_paksa=None):
    return type("Z", (), {"kuota": {}})(), hasil({"a1": TANPA, "b1": TANPA})


with tempfile.TemporaryDirectory() as tmp:
    asli = cl.utama, cl.KELUAR_BANDING
    cl.utama, cl.KELUAR_BANDING = utama_palsu, Path(tmp) / "hasil.md"
    try:
        semua = asyncio.run(cl.jalankan_banding([("palsu", "m")]))
        isi = (Path(tmp) / "hasil.sebagian.md").read_text(encoding="utf-8")
    finally:
        cl.utama, cl.KELUAR_BANDING = asli
cek(semua[0]["r"][8] is False and semua[0]["golongan"] == "GAGAL" and "7/8 (gagal: 8)" in isi, f"--banding menilai aturan 8: {semua[0]['r']}")

print(f"aturan 8: {total - gagal}/{total} lulus")
print("semua lulus" if not gagal else f"GAGAL {gagal}")
sys.exit(1 if gagal else 0)
