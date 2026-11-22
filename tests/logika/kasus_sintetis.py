"""42 kasus sintetis logika.py, disalin dari data/server-v2/uji_logika.py (aslinya TIDAK diubah).

Perbedaan dari aslinya:
- kasus dibungkus fungsi (11 kasus lama jadi k01..k11) dan tidak langsung dijalankan;
- MesinLogika diganti subclass perekam: tiap objek mesin, tiap panggilan proses() (masukan
  + keluaran Python) dan tiap ValueError saat konstruksi dicatat sebagai DATA. Data itu
  dimainkan ulang oleh cek_logika.mjs terhadap src/web/logika.js.
Asersi aslinya tetap dijalankan di sini, jadi keluaran Python yang direkam terbukti benar.
"""
import base64
import copy
import json
import re
import sys
import zlib
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "server"))
import logika as logika_py  # noqa: E402
from ekspor_config_web import KUNCI_LOGIKA, config_web  # noqa: E402


# ---------------------------------------------------------------- pengkodean data
def enkode_mask(m):
    """(n,h,w) bool -> {n,h,w,z}: baris per mask dipak bit (numpy packbits, big-endian), zlib, base64."""
    if m is None or len(m) == 0:
        return None
    n, h, w = m.shape
    bits = np.packbits(np.asarray(m, dtype=bool).reshape(n, h * w), axis=1)
    return {"n": int(n), "h": int(h), "w": int(w), "z": base64.b64encode(zlib.compress(bits.tobytes(), 6)).decode()}


def enkode_bits(bits, shape):
    """Sama dengan enkode_mask, tapi dari bit yang sudah dipak (format cache_rekam.pkl)."""
    n, h, w = (int(s) for s in shape)
    return {"n": n, "h": h, "w": w, "z": base64.b64encode(zlib.compress(bits.tobytes(), 6)).decode()}


def enkode_masukan(hd, mask_terkode=None):
    return {
        "objek": json.loads(json.dumps(hd["objek"])),
        "mask": mask_terkode if mask_terkode is not None else enkode_mask(hd["mask_seg"]),
        "kelas_seg": [int(k) for k in hd["kelas_seg"]],
        "nama_kelas_seg": {str(k): v for k, v in hd["nama_kelas_seg"].items()},
        "waktu_ms": hd["waktu_ms"],
    }


def salin_json(x):
    return json.loads(json.dumps(x))


# ---------------------------------------------------------------- perekam
RUNS = []  # diisi tiap kasus


class MesinLogika(logika_py.MesinLogika):
    """MesinLogika asli + catatan masukan/keluaran."""

    def __init__(self, config):
        self._run = {"config": config_web(config), "steps": [], "error": None}
        RUNS.append(self._run)
        try:
            super().__init__(config)
        except ValueError as e:
            self._run["error"] = {"tipe": "ValueError", "pesan": str(e)}
            raise

    def proses(self, hasil_deteksi, sesi_id="default", waktu_s=None):
        masukan = enkode_masukan(hasil_deteksi)
        keluar = super().proses(hasil_deteksi, sesi_id=sesi_id, waktu_s=waktu_s)
        self._run["steps"].append({"masukan": masukan, "sesi": sesi_id, "waktu_s": waktu_s, "keluar": salin_json(keluar)})
        return keluar


# ---------------------------------------------------------------- isi kasus (salinan uji_logika.py)
with open(ROOT / "src" / "server" / "config.yaml", encoding="utf-8") as _f:
    cfg_asli = yaml.safe_load(_f)
MesinLogika(cfg_asli)  # config.yaml asli harus valid
RUNS.clear()

# Semua kunci config yang dibaca logika.py harus ikut diekspor ke JS.
_sumber = (ROOT / "src" / "server" / "logika.py").read_text(encoding="utf-8")
_dibaca = set(re.findall(r'config\.get\(\s*"(\w+)"', _sumber)) | set(re.findall(r'config\[\s*"(\w+)"\s*\]', _sumber))
_dibaca |= set(re.findall(r'stabil\.get\(\s*"(\w+)"', _sumber)) - {"jendela", "minimal"}
assert _dibaca <= set(KUNCI_LOGIKA), f"kunci config belum diekspor: {_dibaca - set(KUNCI_LOGIKA)}"

cfg = {**cfg_asli, "seg_tangga_stabil_minimal": 2, "jauh_butuh_seg": False,
       "tahan_dekat_ms": 0, "samping_maks_tingkat": 3}  # v1.1 A/B mati untuk kasus lama
NS = {0: "jalur_jalan", 1: "jalan_kendaraan", 2: "tangga"}
H, W = 300, 200
def mask(frac):  # mengisi `frac` bagian ROI (y 200-300, x 60-140) dari kiri
    m = np.zeros((H, W), bool); m[200:300, 60:60 + int(80 * frac)] = True; return m
def hd(masks, kelas, objek=()):
    return dict(objek=list(objek), mask_seg=np.array(masks) if masks else None, kelas_seg=kelas, nama_kelas_seg=NS, waktu_ms=1.0)
def dua(h):
    ml = MesinLogika(cfg); a = ml.proses(h, "s"); b = ml.proses(h, "s"); return a, b
pilar = dict(kelas="pilar", conf=0.9, kotak=[0.4, 0.3, 0.6, 0.9])        # tengah dekat: 2*1*1 = 2.0 -> tingkat 3
pot = dict(kelas="tanaman_pot", conf=0.9, kotak=[0.7, 0.3, 0.95, 0.9])   # kanan dekat: 0.7 -> tingkat 1
orang = dict(kelas="orang", conf=0.9, kotak=[0.0, 0.3, 0.2, 0.9])         # kiri dekat: 1.4 -> tingkat 2

def k01():
    a, b = dua(hd([mask(1.0), mask(0.06)], [0, 2]))
    assert a["peringatan"] is None and b["peringatan"] == dict(pesan="Tangga di depan", kelas="tangga", posisi="tengah", jarak="dekat", tingkat=3) and b["jalur"]["status"] == "terhalang", b
def k02():
    _, b = dua(hd([mask(1.0), mask(0.04)], [0, 2])); assert b["peringatan"] is None and b["jalur"]["status"] == "terbuka", b
def k03():
    _, b = dua(hd([mask(0.5)], [1])); assert b["peringatan"]["pesan"] == "Area kendaraan, hati-hati" and b["peringatan"]["kelas"] == "jalan_kendaraan" and b["peringatan"]["tingkat"] == 2 and b["jalur"]["status"] == "tidak_jelas", b
def k04():
    _, b = dua(hd([mask(0.1), mask(0.3)], [0, 1])); assert b["peringatan"]["pesan"] == "Jalur terhalang" and b["jalur"] == dict(status="terhalang", persen_jalan=0.1), b
def k05():
    _, b = dua(hd([], [])); assert b["peringatan"] is None and b["jalur"] == dict(status="tidak_jelas", persen_jalan=0.0), b
def k06():
    _, b = dua(hd([mask(1.0)], [0], [pilar])); assert b["peringatan"] == dict(pesan="Pilar di depan, dekat", kelas="pilar", posisi="tengah", jarak="dekat", tingkat=3), b
def k07():
    _, b = dua(hd([mask(1.0)], [0], [pot])); assert b["peringatan"]["pesan"] == "Tanaman pot di kanan, dekat" and b["peringatan"]["tingkat"] == 1, b
def k08():
    _, b = dua(hd([mask(1.0), mask(0.5)], [0, 2], [pilar])); assert b["peringatan"]["kelas"] == "pilar", b      # seri tingkat 3 -> kotak
def k09():
    _, b = dua(hd([mask(0.1)], [0], [orang])); assert b["peringatan"]["pesan"] == "Orang di kiri, dekat", b     # seri tingkat 2 -> kotak
def k10():
    _, b = dua(hd([mask(1.0), mask(0.5)], [0, 2], [orang])); assert b["peringatan"]["pesan"] == "Tangga di depan", b  # seg tingkat 3 > kotak 2
def k11():
    ml = MesinLogika(cfg); t = hd([mask(1.0), mask(0.5)], [0, 2]); k = hd([mask(1.0)], [0])
    r = [ml.proses(x, "z")["peringatan"] is not None for x in (t, k, t, k, k, t)]; assert r == [False, False, True, False, False, False], r
# --- Kasus 12+: "Hati-hati, jalur tidak terlihat" (seg kosong, tembok/pintu) ---
TT = dict(pesan="Hati-hati, jalur tidak terlihat", kelas="jalur_jalan", posisi="tengah", jarak="dekat", tingkat=2)
kosong = hd([], []); terbuka = hd([mask(1.0)], [0]); terhalang = hd([mask(0.1)], [0])
def urut(frames, sesi="u", ml=None):
    ml = ml or MesinLogika(cfg); return [ml.proses(x, sesi) for x in frames]
def pes(hasil): return [h["peringatan"]["pesan"] if h["peringatan"] else None for h in hasil]
def k12():  # 1 frame kosong -> tidak ada peringatan; 2 frame -> tidak ada; 3 berturut -> muncul
    r = urut([kosong] * 3); assert pes(r) == [None, None, TT["pesan"]], pes(r)
    assert r[2]["peringatan"] == TT and r[2]["jalur"] == dict(status="tidak_jelas", persen_jalan=0.0), r[2]
    assert r[0]["jalur"] == dict(status="tidak_jelas", persen_jalan=0.0)
def k13():  # tetap muncul selama kosong terus; lalu jalur_jalan 80% -> hilang SEGERA, status terbuka
    r = urut([kosong] * 4 + [hd([mask(0.8)], [0])]); assert pes(r) == [None, None, TT["pesan"], TT["pesan"], None], pes(r)
    assert r[4]["jalur"]["status"] == "terbuka" and r[4]["jalur"]["persen_jalan"] == 0.8, r[4]["jalur"]
def k14():  # kosong, mask, kosong, kosong -> tidak ada (bukan 3 berturut)
    r = urut([kosong, terbuka, kosong, kosong]); assert pes(r) == [None] * 4, pes(r)
def k15():  # selang-seling "Jalur terhalang" & kosong: tidak saling membantu
    r = urut([terhalang, kosong] * 3); assert pes(r) == [None, None, "Jalur terhalang", None, "Jalur terhalang", None], pes(r)
def k16():  # kosong,kosong lalu terhalang: terhalang tidak ikut terhitung (1 dari 3)
    r = urut([kosong, kosong, terhalang]); assert pes(r) == [None, None, None], pes(r)
def k17():  # terhalang lalu kosong,kosong: kosong tidak lolos (hanya 2 berturut-turut)
    r = urut([terhalang, kosong, kosong]); assert pes(r) == [None, None, None], pes(r)
def k18():  # pilar dekat tengah (t3) + 3 kosong (t2): pilar menang
    r = urut([hd([], [], [pilar])] * 3); assert [h["peringatan"] and h["peringatan"]["kelas"] for h in r] == [None, "pilar", "pilar"], pes(r)
    assert r[2]["peringatan"]["tingkat"] == 3
def k19():  # seri t2 (orang kiri dekat) + 3 kosong: objek kotak menang
    r = urut([hd([], [], [orang])] * 3); assert pes(r)[2] == "Orang di kiri, dekat", pes(r)
def k20():  # dua X-Sesi tidak berbagi riwayat
    ml = MesinLogika(cfg); a = []
    for sesi in ("A", "B", "A", "B", "A", "B"): a.append((sesi, ml.proses(kosong, sesi)["peringatan"] is not None))
    assert [x[1] for x in a] == [False, False, False, False, True, True], a
def k21():  # "Tangga di depan" tetap 2-dari-3
    r = urut([hd([mask(1.0), mask(0.5)], [0, 2]), terbuka, hd([mask(1.0), mask(0.5)], [0, 2])]); assert pes(r) == [None, None, "Tangga di depan"], pes(r)
def k22():  # seg_kosong_minimal > stabil.jendela ditolak
    try: MesinLogika({**cfg, "seg_kosong_minimal": 4})
    except ValueError: return
    raise AssertionError("seharusnya ValueError")
def k23():  # seg_kosong_minimal dari config dipakai (2 -> muncul di frame ke-2)
    r = urut([kosong] * 2, ml=MesinLogika({**cfg, "seg_kosong_minimal": 2})); assert pes(r) == [None, TT["pesan"]], pes(r)
# --- Aturan C (seg_tangga_stabil_minimal) dan B (jauh_butuh_seg) ---
TG = hd([mask(1.0), mask(0.5)], [0, 2])
def kC(minimal, frames):
    return pes(urut(frames, ml=MesinLogika({**cfg, "seg_tangga_stabil_minimal": minimal})))
def k24():  # C=3: 2-dari-3 tidak cukup, 3-dari-3 baru lolos
    assert kC(3, [TG, terbuka, TG]) == [None, None, None]
    assert kC(3, [TG, TG, terbuka]) == [None, None, None]
    assert kC(3, [TG, TG, TG, TG]) == [None, None, "Tangga di depan", "Tangga di depan"]
    assert kC(2, [TG, terbuka, TG]) == [None, None, "Tangga di depan"]       # nilai 2 = lama
    assert pes(urut([TG, terbuka, TG])) == [None, None, "Tangga di depan"]   # default = lama
def k25():  # C=3 tidak menyentuh pesan seg lain (Area kendaraan / Jalur terhalang tetap 2-dari-3)
    kend = hd([mask(0.5)], [1])
    assert kC(3, [kend, terbuka, kend]) == [None, None, "Area kendaraan, hati-hati"]
    assert kC(3, [terhalang, terbuka, terhalang]) == [None, None, "Jalur terhalang"]
    assert kC(3, [kosong] * 3) == [None, None, TT["pesan"]]
def k26():  # seg_tangga_stabil_minimal > stabil.jendela atau < 1 ditolak
    for v in (4, 0):
        try: MesinLogika({**cfg, "seg_tangga_stabil_minimal": v})
        except ValueError: continue
        raise AssertionError(f"{v} seharusnya ValueError")
def objek_jauh(kelas="kursi", x=(0.4, 0.6)):  # y2 0.5 -> jauh; tengah
    return dict(kelas=kelas, conf=0.9, kotak=[x[0], 0.2, x[1], 0.5])
def pj(flag, masks, kelas, objek, n=3):
    ml = MesinLogika({**cfg, "jauh_butuh_seg": flag}); return urut([hd(masks, kelas, objek)] * n, ml=ml)
def k27():  # B on + seg kosong: objek jauh tidak jadi peringatan, tapi tetap ada di daftar objek
    tgg = objek_jauh("tangga"); r = pj(True, [], [], [tgg])
    assert [h["peringatan"] and h["peringatan"]["pesan"] for h in r] == [None, None, TT["pesan"]], pes(r)  # hanya jalur tidak terlihat
    assert all(len(h["objek"]) == 1 and h["objek"][0]["jarak"] == "jauh" and h["objek"][0]["kelas"] == "tangga" for h in r), r
    r0 = pj(False, [], [], [tgg]); assert r0[1]["peringatan"]["pesan"] == "Tangga di depan, jauh", pes(r0)  # B off = lama
def k28():  # B on tapi seg ADA mask: objek jauh tetap jadi peringatan
    r = pj(True, [mask(1.0)], [0], [objek_jauh("tangga")]); assert r[1]["peringatan"]["pesan"] == "Tangga di depan, jauh", pes(r)
def k29():  # B on + seg kosong: dekat dan sedang tidak pernah disaring
    dekat = dict(kelas="pilar", conf=0.9, kotak=[0.4, 0.3, 0.6, 0.9]); sedang = dict(kelas="pilar", conf=0.9, kotak=[0.4, 0.3, 0.6, 0.7])
    r = pj(True, [], [], [dekat]); assert r[1]["peringatan"]["pesan"] == "Pilar di depan, dekat", pes(r)
    r = pj(True, [], [], [sedang]); assert r[1]["peringatan"]["pesan"] == "Pilar di depan, sedang", pes(r)
def k30():  # B on + seg kosong: jauh disaring, objek dekat lain tetap menang; daftar objek utuh
    r = pj(True, [], [], [objek_jauh("tangga"), dict(kelas="orang", conf=0.9, kotak=[0.0, 0.3, 0.2, 0.9])])
    assert r[1]["peringatan"]["pesan"] == "Orang di kiri, dekat" and len(r[1]["objek"]) == 2, r[1]
def k31():  # B on: kunci kontrak tidak berubah
    r = pj(True, [], [], [objek_jauh()])[1]
    assert sorted(r) == ["jalur", "objek", "peringatan", "versi_kontrak", "waktu_ms"] and r["versi_kontrak"] == 1
    assert sorted(r["objek"][0]) == ["conf", "jarak", "kelas", "kotak", "posisi"]
# --- Aturan v1.1 A (tahan_dekat_ms) dan B (samping_maks_tingkat) ---
PD = hd([mask(1.0)], [0], [pilar]); KS = terbuka   # pilar tengah dekat (t3) / frame tanpa objek, jalur terbuka
def ut(frames_t, ml):  # frames_t = [(frame, waktu_s)]
    return pes([ml.proses(x, "a", waktu_s=t) for x, t in frames_t])
def mA(ms=1500, **kw): return MesinLogika({**cfg, "tahan_dekat_ms": ms, **kw})
PDP = "Pilar di depan, dekat"
def k32():  # A: sesudah pilar tengah+dekat hilang, peringatan sama diulang (teks + tingkat)
    ml = mA(); r = [ml.proses(x, "a", waktu_s=t)["peringatan"] for x, t in [(PD, 0.0), (PD, 0.25), (KS, 0.5), (KS, 1.0)]]
    assert r[0] is None and r[1] == r[2] == r[3] == dict(pesan=PDP, kelas="pilar", posisi="tengah", jarak="dekat", tingkat=3), r
def k33():  # A: kedaluwarsa tepat sesudah tahan_dekat_ms (<= ditahan, > tidak)
    assert ut([(PD, 0.0), (PD, 0.25), (KS, 1.75)], mA()) == [None, PDP, PDP]
    assert ut([(PD, 0.0), (PD, 0.25), (KS, 1.80)], mA()) == [None, PDP, None]
def k34():  # A: hasil tahanan tidak mengisi ulang waktu (tidak memperpanjang diri)
    fr = [(PD, 0.0), (PD, 0.25)] + [(KS, 0.25 + 0.25 * k) for k in range(1, 9)]  # 0.5 .. 2.25
    assert ut(fr, mA()) == [None, PDP] + [PDP] * 6 + [None, None], ut(fr, mA())
def k35():  # A: diisi ulang oleh peringatan dekat ASLI yang baru
    fr = [(PD, 0.0), (PD, 0.25), (KS, 1.0), (PD, 1.5), (PD, 1.75), (KS, 3.0), (KS, 3.3)]
    assert ut(fr, mA()) == [None, PDP, PDP, PDP, PDP, PDP, None], ut(fr, mA())
def k36():  # A: 0 = v1 (tanpa tahanan); default config (tanpa kunci) = v1
    fr = [(PD, 0.0), (PD, 0.25), (KS, 0.5)]
    assert ut(fr, mA(0)) == [None, PDP, None]
    assert ut(fr, MesinLogika({k: v for k, v in cfg.items() if k != "tahan_dekat_ms"})) == [None, PDP, None]
def k37():  # A: hanya objek tengah+dekat yang ditahan (bukan samping, bukan sedang, bukan seg)
    sedang = dict(kelas="pilar", conf=0.9, kotak=[0.4, 0.3, 0.6, 0.7]); OK = hd([mask(1.0)], [0], [orang])
    assert ut([(OK, 0.0), (OK, 0.25), (KS, 0.5)], mA()) == [None, "Orang di kiri, dekat", None]
    S = hd([mask(1.0)], [0], [sedang]); assert ut([(S, 0.0), (S, 0.25), (KS, 0.5)], mA()) == [None, "Pilar di depan, sedang", None]
    assert ut([(TG, 0.0), (TG, 0.25), (KS, 0.5)], mA()) == [None, "Tangga di depan", None]
def k38():  # A: tanpa waktu_s -> time.monotonic(); sesi terpisah tidak berbagi tahanan; kunci kontrak tetap
    ml = mA(); ml.proses(PD, "x"); r = ml.proses(PD, "x"); h = ml.proses(KS, "x"); assert h["peringatan"]["pesan"] == PDP, h
    assert ml.proses(KS, "y")["peringatan"] is None
    assert sorted(h) == ["jalur", "objek", "peringatan", "versi_kontrak", "waktu_ms"] and sorted(h["peringatan"]) == ["jarak", "kelas", "pesan", "posisi", "tingkat"]
    assert sorted(r["peringatan"]) == sorted(h["peringatan"])
KEND_LUAR = dict(kelas="kendaraan", conf=0.9, kotak=[0.0, 0.3, 0.25, 0.9])   # kiri dekat, 3*0.7 = 2.1 -> t3 di v1, 0 masuk tengah
KEND_MASUK = dict(kelas="kendaraan", conf=0.9, kotak=[0.05, 0.3, 0.42, 0.9]) # pusat 0.235 -> kiri, masuk tengah 0.12
def mB(mt=2, mn=0.10): return MesinLogika({**cfg, "samping_maks_tingkat": mt, "samping_masuk_tengah_min": mn})
def pB(ml, objek): _, b = [ml.proses(hd([mask(1.0)], [0], objek), "b") for _ in range(2)]; return b["peringatan"]
def k39():  # B: samping di luar zona tengah dibatasi ke tingkat 2 (teks sama)
    p = pB(mB(), [KEND_LUAR]); assert p["pesan"] == "Kendaraan di kiri, dekat" and p["tingkat"] == 2, p
    assert pB(MesinLogika(cfg), [KEND_LUAR])["tingkat"] == 3                    # 3 = v1
    assert pB(MesinLogika({k: v for k, v in cfg.items() if k != "samping_maks_tingkat"}), [KEND_LUAR])["tingkat"] == 3  # default = v1
def k40():  # B: samping yang masuk zona tengah >= min tidak dibatasi; di bawah min dibatasi
    assert pB(mB(2, 0.10), [KEND_MASUK])["tingkat"] == 3
    assert pB(mB(2, 0.15), [KEND_MASUK])["tingkat"] == 2
    kanan = dict(kelas="kendaraan", conf=0.9, kotak=[0.58, 0.3, 1.0, 0.9])    # pusat 0.79 -> kanan, masuk 0.12
    assert pB(mB(2, 0.10), [kanan])["pesan"] == "Kendaraan di kanan, dekat" and pB(mB(2, 0.10), [kanan])["tingkat"] == 3
def k41():  # B: objek tengah tidak tersentuh; tengah t3 menang atas samping yang dibatasi (skor 2.1 > 2.0)
    p = pB(mB(), [pilar]); assert p == dict(pesan="Pilar di depan, dekat", kelas="pilar", posisi="tengah", jarak="dekat", tingkat=3), p
    assert pB(mB(), [KEND_LUAR, pilar])["pesan"] == "Pilar di depan, dekat"
    assert pB(MesinLogika(cfg), [KEND_LUAR, pilar])["pesan"] == "Kendaraan di kiri, dekat"   # v1: skor tertinggi
    assert pB(mB(), [KEND_MASUK, pilar])["pesan"] == "Kendaraan di kiri, dekat"            # samping masuk tengah: t3, skor 2.1
def k42():  # B: tingkat seg tangga (3) mengalahkan samping yang dibatasi (2); tingkat 1/2 tidak naik
    ml = mB(); r = [ml.proses(hd([mask(1.0), mask(0.5)], [0, 2], [KEND_LUAR]), "c")["peringatan"] for _ in range(2)]
    assert r[1]["pesan"] == "Tangga di depan", r
    assert pB(mB(), [orang])["tingkat"] == 2 and pB(mB(), [pot])["tingkat"] == 1

KASUS = [(i, n, f) for i, (n, f) in enumerate([
    ("tangga seg 2 dari 2 frame -> 'Tangga di depan' t3, status terhalang", k01),
    ("tangga di bawah 5% ROI -> terbuka, tanpa peringatan", k02),
    ("kendaraan 50% ROI -> 'Area kendaraan, hati-hati' t2, tidak_jelas", k03),
    ("jalur 10% ROI -> 'Jalur terhalang', persen_jalan 0.1", k04),
    ("tanpa mask -> tidak_jelas, persen 0.0", k05),
    ("pilar tengah dekat + seg terbuka -> peringatan pilar t3", k06),
    ("tanaman pot kanan dekat -> t1", k07),
    ("seri tingkat 3 (pilar vs tangga seg) -> objek kotak", k08),
    ("seri tingkat 2 (orang kiri vs terhalang seg) -> objek kotak", k09),
    ("seg tangga t3 mengalahkan orang t2", k10),
    ("tangga 2-dari-3 per sesi, urutan t,k,t,k,k,t", k11),
    ("kosong 1 frame / 2 frame tanpa peringatan, 3 berturut -> 'jalur tidak terlihat' t2", k12),
    ("3 kosong lalu jalur_jalan 80% -> hilang segera, status terbuka", k13),
    ("kosong, mask, kosong, kosong -> tanpa peringatan", k14),
    ("selang-seling 'Jalur terhalang' & kosong tidak saling membantu", k15),
    ("kosong,kosong,terhalang -> tanpa peringatan", k16),
    ("terhalang,kosong,kosong -> tanpa peringatan", k17),
    ("pilar dekat tengah (t3) + 3 kosong -> pilar menang", k18),
    ("orang kiri (t2) + 3 kosong, seri -> objek kotak menang", k19),
    ("dua X-Sesi tidak berbagi riwayat", k20),
    ("'Tangga di depan' tetap 2-dari-3", k21),
    ("seg_kosong_minimal > stabil.jendela -> ValueError", k22),
    ("seg_kosong_minimal dari config dipakai (2)", k23),
    ("C: seg_tangga_stabil_minimal=3 -> 2-dari-3 ditolak, 3-dari-3 lolos; 2/default = lama", k24),
    ("C: pesan seg lain (kendaraan, terhalang, tidak terlihat) tidak terpengaruh", k25),
    ("C: seg_tangga_stabil_minimal di luar 1..jendela -> ValueError", k26),
    ("B: seg kosong + flag on -> objek jauh tidak jadi peringatan, tetap di daftar objek", k27),
    ("B: seg ada mask -> objek jauh tetap jadi peringatan", k28),
    ("B: dekat/sedang tidak pernah disaring", k29),
    ("B: jauh disaring, objek dekat lain menang, daftar objek utuh", k30),
    ("B: kunci kontrak tidak berubah", k31),
    ("v1.1 A: pilar tengah+dekat hilang -> peringatan sama (teks, tingkat) diulang", k32),
    ("v1.1 A: kedaluwarsa sesudah tahan_dekat_ms (<= ditahan)", k33),
    ("v1.1 A: tahanan tidak memperpanjang dirinya sendiri", k34),
    ("v1.1 A: diisi ulang oleh peringatan dekat asli yang baru", k35),
    ("v1.1 A: 0 / tanpa kunci = v1", k36),
    ("v1.1 A: samping, sedang, seg tidak ditahan", k37),
    ("v1.1 A: waktu_s None -> monotonic, per sesi, kontrak tetap", k38),
    ("v1.1 B: samping di luar tengah dibatasi t2; 3 / tanpa kunci = v1", k39),
    ("v1.1 B: samping masuk tengah >= min tidak dibatasi", k40),
    ("v1.1 B: objek tengah tidak tersentuh, tengah t3 menang", k41),
    ("v1.1 B: seg tangga t3 menang; t1/t2 tidak berubah", k42)], start=1)]
assert len(KASUS) == 42


def jalankan_semua():
    """Jalankan 42 kasus (asersi aslinya aktif). Hasil: [{nomor, nama, lulus, galat, runs}]."""
    hasil = []
    for nomor, nama, fn in KASUS:
        RUNS.clear()
        lulus, galat = True, ""
        try:
            fn()
        except AssertionError as e:
            lulus, galat = False, str(e)
        hasil.append({"nomor": nomor, "nama": nama, "lulus_python": lulus, "galat": galat, "runs": list(RUNS)})
    RUNS.clear()
    return hasil


if __name__ == "__main__":
    h = jalankan_semua()
    for r in h:
        print(("LULUS " if r["lulus_python"] else "GAGAL  ") + f"{r['nomor']}. {r['nama']}" + (f"  -> {r['galat']}" if r["galat"] else ""))
    sys.exit(0 if all(r["lulus_python"] for r in h) else 1)
