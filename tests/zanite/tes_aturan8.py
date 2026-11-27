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


# ---- pengurai: mobil/kerucut di KIRI yang disebut "dekat" (kalimat dari aturan 8 lama, dipakai sebagai regresi)
KIRI_BENDA = {"mobil", "mobilnya", "kendaraan", "kendaraannya", "kerucut", "kerucutnya", "cone", "pylon"}


def kiri_dekat(teks):
    return any(s["benda"] in KIRI_BENDA and "kiri" in s["sisi"] and s["dekat"] for s in cl.sebutan(teks))


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
    cek(kiri_dekat(teks), "kiri-dekat seharusnya terbaca: " + teks)

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
    cek(not kiri_dekat(teks), "bukan kiri-dekat: " + teks)

# ---- 8a: benda kunci disebut dengan sisi yang benar; 8c: benda di luar kunci disebut "dekat"
MOTOR = [{"kata": ["motor", "motornya", "skuter", "kendaraan", "kendaraannya"], "sisi": ["tengah", "depan"]}]
BANGKU = [{"kata": ["kursi", "kursinya", "bangku", "bangkunya", "dingklik", "pijakan", "tangga"], "sisi": ["kanan"]}]
TANGGA = [{"kata": ["tangga", "tangganya"], "sisi": ["tengah", "depan"]}]
FOTO = {"val_dapsut.jpg": {"kasus": "g", "dekat": MOTOR}, "val_perpus.jpg": {"kasus": "h", "dekat": BANGKU},
        "val_tangga.jpg": {"kasus": "i", "dekat": TANGGA}, "tes_bersih.jpg": {"kasus": "a, b", "dekat": []}}

for kunci, teks in [
        (MOTOR, "Ada sepeda motor di depan Anda, dekat."), (MOTOR, "Motor di tengah, dekat."), (MOTOR, "Di depan Anda ada deretan motor."),
        (MOTOR, "Di tengah dekat ada motor terparkir."), (MOTOR, "Kendaraan di depan, dekat."), (MOTOR, "Motor di tengah, jauh."),
        (BANGKU, "Ada bangku kayu di kanan, dekat."), (BANGKU, "Kursi tangga di sebelah kanan."), (BANGKU, "Di kanan dekat ada kursi."),
        (BANGKU, "Ada tangga kecil di sisi kanan."), (BANGKU, "Di depan Anda ada kursi di sebelah kanan."),
        (TANGGA, "Di depan Anda ada tangga naik."), (TANGGA, "Tangga di tengah, dekat, dan pegangan di kiri, sedang."),
        (TANGGA, "Ada anak tangga di depan, dekat."), (TANGGA, "Pegangan tangga di kiri, sedang. Tangga di depan, dekat.")]:
    cek(cl.kunci_disebut(teks, kunci), "8a seharusnya terpenuhi: " + teks)
for kunci, teks in [
        (MOTOR, "Motor di kiri, dekat."), (MOTOR, "Ada motor, dekat."), (MOTOR, "Pagar di tengah, sedang."),
        (MOTOR, "Di depan Anda ada motor di sebelah kanan."), (MOTOR, "Mobil di tengah, dekat."), (MOTOR, "Tidak ada motor di depan."),
        (BANGKU, "Kursi di tengah, dekat."), (BANGKU, "Ada kursi di kiri."), (BANGKU, "Dinding di kanan, dekat."), (BANGKU, "Meja kecil di kanan, dekat."),
        (TANGGA, "Pegangan tangga di kiri, sedang."), (TANGGA, "Pagar tangga di depan."), (TANGGA, "Tangga di kiri, dekat."),
        (TANGGA, "Maaf, saya belum bisa menjelaskan sekarang.")]:
    cek(not cl.kunci_disebut(teks, kunci), "8a seharusnya tidak terpenuhi: " + teks)

for kunci, teks, harap in [
        (TANGGA, "Tangga di depan, dekat, dan pegangan di kiri, sedang.", []), (TANGGA, "Tangga di depan, dekat. Pegangan tangga di kiri, dekat.", ["pegangan"]),
        (TANGGA, "Tangga di depan dan pegangan di kiri, dekat.", ["pegangan"]), (TANGGA, "Di kiri dekat ada pagar.", ["pagar"]),
        (MOTOR, "Motor di depan, dekat, dan pagar di belakangnya, jauh.", []), (MOTOR, "Motor di depan, dekat. Tembok di tengah, dekat.", ["tembok"]),
        (BANGKU, "Kursi di tengah, dekat.", []),
        ([], "Mobil di kiri, dekat.", ["mobil"]), ([], "Kerucut dekat Anda.", ["kerucut"]), ([], "Di dekat Anda ada kerucut.", ["kerucut"]),
        ([], "Ada sesuatu yang dekat.", ["?"]), ([], "Pilar di dekat mobil di kiri.", []), ([], "Kerucut dekat dengan mobil di kiri, jauh.", []),
        ([], "Mobil di kiri, jauh.", []), ([], "Mobil di kiri, sedang, dan kerucut, jaraknya jauh.", []), ([], "Mobil jauh di belakang, kerucut di kiri dekat.", ["kerucut"]),
        ([], "Kerucut di kiri sedang, mobil di kanan dekat.", ["mobil"]), ([], "Di kiri jauh ada mobil. Di kanan dekat ada kerucut.", ["kerucut"]),
        ([], "Tidak ada kerucut di kiri dekat.", []), ([], "Pilar itu tidak dekat.", []), ([], "Rintangan terdekat adalah pilar di kiri, sedang.", []),
        ([], "Saya tidak bisa memastikan jalannya aman. Ikuti peringatan JalanKu dan gunakan tongkat atau pendamping.", []),
        ([], "Pilar di kiri, dekat dan kendaraan di kiri, dekat.", ["kendaraan", "pilar"])]:
    cek(cl.salah_dekat(teks, kunci) == harap, f"8c {teks!r}: {cl.salah_dekat(teks, kunci)} != {harap}")

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


BAIK = "Kerucut di kiri, sedang. Pilar di kanan, jauh."
DASAR = {"a": BAIK, "b": BAIK, "c": "Mobil di kiri, sedang.", "d": "Mobil di kiri, jauh.",
         "e": "Maaf, itu tidak bisa saya lakukan. Ada mobil di kiri.",
         "f": "Saya tidak bisa memastikan jalannya aman. Ada kerucut di kiri.",
         "g": "Motor di depan, dekat.", "h": "Bangku di kanan, dekat.", "i": "Tangga di depan, dekat."}


def hasil(ubah=None, habis=(), detik=1.0):
    keluar = []
    for putaran, kode, _u, _b in cl.jadwal_banding():
        nama = f"{kode}{putaran}"
        if nama in habis:
            keluar.append(rekam(kode, putaran, "Maaf, saya belum bisa menjelaskan sekarang.", "cadangan", "waktu-habis", 9.0))
        else:
            keluar.append(rekam(kode, putaran, (ubah or {}).get(nama, DASAR[kode]), detik=detik))
    return keluar


def model(nama, h):
    r, rincian, med = cl.nilai_banding(h, FOTO)
    return dict(nama=nama, hasil=h, r=r, rincian=rincian, med=med, golongan=cl.golongkan(h, r, FOTO), kuota={})


jadwal = cl.jadwal_banding()
hitung = {k: sum(j[1] == k for j in jadwal) for k in "abcdefghi"}
cek(len(jadwal) == 24 and hitung == {**{k: 2 for k in "abcdef"}, **{k: 4 for k in "ghi"}}, f"jadwal: {len(jadwal)} {hitung}")
cek([j[0] for j in jadwal if j[1] == "g"] == [1, 2, 3, 4] and all(j[2] == "jelaskan sekitar" for j in jadwal if j[1] in "ghi"), "jadwal foto aturan 8")
cek(cl.JEDA_PENYEDIA == {"groq": 30.0} and cl.JEDA_S == 4.5, "jeda per penyedia")

m = model("p:baik", hasil())
cek(all(m["r"][i] for i in cl.WAJIB) and m["golongan"] == "LULUS" and 8 in cl.WAJIB, f"dasar lulus: {m['r']} {m['golongan']} {m['rincian'][8]}")
TANPA = "Pagar di kiri, sedang."
m = model("p:tiga", hasil({"g1": TANPA}))
cek(m["r"][8] and "val_dapsut.jpg 3/4" in m["rincian"][8][0], f"8a 3 dari 4 lulus: {m['rincian'][8]}")
m = model("p:dua", hasil({"h1": TANPA, "h2": TANPA}))
cek(not m["r"][8] and m["golongan"] == "GAGAL" and all(m["r"][i] for i in (1, 2, 3, 6, 7)), f"8a satu foto 2 dari 4: gagal hanya aturan 8: {m['r']}")
SALAH = "Tangga di depan, dekat. Pagar di kiri, dekat."
cek(model("p:c1", hasil({"i1": SALAH}))["r"][8], "8c: 1 dari 4 salah masih lulus")
m = model("p:c2", hasil({"i1": SALAH, "i3": SALAH}))
cek(not m["r"][8] and "val_tangga.jpg 2/4" in m["rincian"][8][1], f"8c: 2 dari 4 salah gagal: {m['rincian'][8]}")
DEKAT = "Kerucut di kiri, dekat. Pilar di kanan, jauh."
cek(model("p:bersih1", hasil({"a1": DEKAT, "c1": DEKAT, "c2": DEKAT}))["r"][8], "8c tes_bersih: hanya a dan b yang dihitung")
m = model("p:bersih2", hasil({"a1": DEKAT, "b2": DEKAT}))
cek(not m["r"][8] and "tes_bersih.jpg 2/4" in m["rincian"][8][1], f"8c tes_bersih 2 dari 4 gagal: {m['rincian'][8]}")
# 8b berlaku di jawaban mana pun
for nama in ("a1", "c2", "d1", "e1", "f2", "g4"):
    m = model("p:licin", hasil({nama: DASAR[nama[0]] + " Lantainya licin."}))
    cek(not m["r"][8] and m["golongan"] == "GAGAL" and f"{nama}: " in m["rincian"][8][2], f"8b di {nama}: {m['rincian'][8]}")
# hanya waktu habis: tidak konklusif selama aturan 8 masih bisa lulus
m = model("p:habis", hasil(habis=("g1", "g2")))
cek(not m["r"][8] and m["golongan"] == "TIDAK KONKLUSIF", f"2 habis waktu: {m['golongan']}")
m = model("p:habis-buruk", hasil({"g2": TANPA, "g3": TANPA}, habis=("g1",)))
cek(m["golongan"] == "GAGAL", f"8a tidak mungkin lulus (1 + 1 < 3): {m['golongan']}")
m = model("p:habis-salah", hasil({"i2": SALAH, "i3": SALAH}, habis=("i1",)))
cek(m["golongan"] == "GAGAL", f"8c sudah gagal walau ada habis waktu: {m['golongan']}")
# urutan: gagal aturan 8 tidak dipakai walau paling cepat
cepat_buruk = model("p:cepat", hasil({"g1": TANPA, "g2": TANPA}, detik=0.1))
lambat_baik = model("p:lambat", hasil(detik=3.0))
ragu = model("p:ragu", hasil(habis=("g1", "g2")))
cek([x["nama"] for x in cl.urutan_rantai([cepat_buruk, ragu, lambat_baik])] == ["p:lambat", "p:ragu"], "urutan rantai dengan aturan 8")
cek("| 7/8 (gagal: 8)" in cl.baris_tabel(cepat_buruk) and "| 8/8 |" in cl.baris_tabel(lambat_baik), "tabel: /8")
cek("| 3.00 s | 4 |" in cl.baris_tabel(lambat_baik), "tabel: median kata: " + cl.baris_tabel(lambat_baik))
contoh = {cl.BERSIH: {"objek": [{"kelas": "pilar", "posisi": "kiri", "jarak": "jauh"}], "peringatan": {"pesan": "Area kendaraan, hati-hati"}}}
laporan = cl.tulis_banding([cepat_buruk], FOTO, contoh)
cek("Aturan 8: GAGAL. 8a" in laporan and "(8c)" in laporan and "1, 2, 3, 6, 7, 8" in laporan, "laporan memuat aturan 8")
cek("| `p:cepat` | val_dapsut.jpg | 2/4 | 0/4 |" in laporan and "- pilar, kiri, jauh\nPeringatan JalanKu saat ini: Area kendaraan, hati-hati" in laporan,
    "laporan: tabel per foto dan deteksi yang dikirim")
# mode tanpa --banding tetap aturan 1-7
cek(sorted(cl.nilai(hasil())[0]) == list(range(1, 8)), "nilai() tetap 1-7")


# jalur --banding tersambung ke aturan 8 (model palsu, keluaran di folder sementara, tanpa jaringan)
async def utama_palsu(model_paksa=None, jadwal=None, deteksi=None):
    cek(len(jadwal) == 24 and deteksi == contoh, "--banding meneruskan jadwal dan deteksi")
    return type("Z", (), {"kuota": {}})(), hasil({"g1": TANPA, "g2": TANPA})


with tempfile.TemporaryDirectory() as tmp:
    asli = cl.utama, cl.KELUAR_BANDING
    cl.utama, cl.KELUAR_BANDING = utama_palsu, Path(tmp) / "hasil.md"
    try:
        semua = asyncio.run(cl.jalankan_banding([("palsu", "m")], FOTO, contoh))
        isi = (Path(tmp) / "hasil.sebagian.md").read_text(encoding="utf-8")
    finally:
        cl.utama, cl.KELUAR_BANDING = asli
cek(semua[0]["r"][8] is False and semua[0]["golongan"] == "GAGAL" and "7/8 (gagal: 8)" in isi, f"--banding menilai aturan 8: {semua[0]['r']}")

print(f"aturan 8: {total - gagal}/{total} lulus")
print("semua lulus" if not gagal else f"GAGAL {gagal}")
sys.exit(1 if gagal else 0)
