from config import (
    NAMA_ID, KELAS_BAHAYA, BATAS_DEKAT, BATAS_SANGAT_DEKAT,
)


def arah(x_tengah, lebar):
    r = x_tengah / lebar
    if r < 0.33:
        return "kiri"
    if r > 0.67:
        return "kanan"
    return "depan"


def jarak(rasio_luas):
    if rasio_luas >= BATAS_SANGAT_DEKAT:
        return "sangat dekat"
    if rasio_luas >= BATAS_DEKAT:
        return "dekat"
    return "jauh"


def buat_pesan(deteksi, lebar, tinggi):
    """
    deteksi: list dict {kelas, x, y, w, h, conf}
    return: (kunci, teks, urgent) atau None
    Hanya objek terdekat (kotak terbesar) yang diumumkan.
    """
    if not deteksi:
        return None

    d = max(deteksi, key=lambda t: t["w"] * t["h"])
    rasio = (d["w"] * d["h"]) / (lebar * tinggi)
    nama = NAMA_ID.get(d["kelas"], d["kelas"])
    posisi = arah(d["x"], lebar)
    jrk = jarak(rasio)
    kunci = (d["kelas"], posisi, jrk)

    if jrk == "sangat dekat" and posisi == "depan":
        return kunci, f"Bahaya di depan, ada {nama}, berhenti", True
    if d["kelas"] in KELAS_BAHAYA and jrk != "jauh" and posisi == "depan":
        return kunci, f"Awas, ada {nama} di depan", True

    lokasi = "di depan" if posisi == "depan" else f"di sebelah {posisi}"
    if jrk == "jauh":
        return kunci, f"Ada {nama} {lokasi}", False
    return kunci, f"Ada {nama} {lokasi}, {jrk}", False
