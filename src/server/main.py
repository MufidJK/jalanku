import json
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime

import cv2
import numpy as np

from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from deteksi import ROOT, MesinDeteksi, muat_config, sinkron_gpu
from logika import MesinLogika
from zanite import buat_zanite


WEB_DIR = ROOT / "src" / "web"


def siapkan_rekam(app: FastAPI):
    """Mode rekam (mati secara bawaan): hanya aktif kalau JALANKU_REKAM=1."""
    app.state.dir_rekam = None
    app.state.hitung_rekam = 0

    if os.environ.get("JALANKU_REKAM") != "1":
        return

    try:
        dir_rekam = ROOT / "data" / "rekam" / datetime.now().strftime("%Y%m%d-%H%M%S")
        dir_rekam.mkdir(parents=True, exist_ok=True)
        app.state.dir_rekam = dir_rekam
        print(f"[JalanKu] Mode REKAM aktif: {dir_rekam}")
    except Exception as error:
        print(f"[JalanKu] Gagal menyiapkan folder rekam: {error}")


def rekam(app: FastAPI, data_gambar, sesi_id, hasil_deteksi, hasil):
    """Simpan JPEG yang diterima + satu baris log.jsonl. Tidak boleh membuat request gagal."""
    dir_rekam = app.state.dir_rekam
    if dir_rekam is None:
        return

    try:
        app.state.hitung_rekam += 1
        nomor = app.state.hitung_rekam

        # X-Sesi dari klien: bersihkan sebelum jadi nama file.
        sesi_aman = re.sub(r"[^A-Za-z0-9_-]", "_", sesi_id)[:32] or "default"
        (dir_rekam / f"{nomor:05d}_{sesi_aman}.jpg").write_bytes(data_gambar)

        nama_seg = hasil_deteksi.get("nama_kelas_seg", {})
        kelas_seg = hasil_deteksi.get("kelas_seg", [])
        peringatan = hasil.get("peringatan")

        baris = {
            "nomor": nomor,
            "waktu": datetime.now().isoformat(timespec="milliseconds"),
            "sesi": sesi_id,
            "waktu_ms": hasil.get("waktu_ms"),
            "jumlah_seg": len(kelas_seg),
            "kelas_seg": [nama_seg.get(int(k), str(k)) for k in kelas_seg],
            "jalur": hasil.get("jalur"),
            "peringatan": peringatan["pesan"] if peringatan else None,
            "objek": [
                {
                    "kelas": o["kelas"],
                    "conf": o["conf"],
                    "posisi": o["posisi"],
                    "jarak": o["jarak"],
                }
                for o in hasil.get("objek", [])
            ],
        }

        with open(dir_rekam / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(baris, ensure_ascii=False) + "\n")
    except Exception as error:
        print(f"[JalanKu] Gagal merekam: {error}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = muat_config()

    print("[JalanKu] Memuat model...")

    app.state.nama_model = str(config.get("nama_model", "model"))
    app.state.mesin_deteksi = MesinDeteksi(config)
    app.state.mesin_logika = MesinLogika(config)

    # Zanite (asisten suara). Gagal apa pun = Zanite mati, bagian lain jalan seperti biasa.
    app.state.zanite = buat_zanite(config, ROOT)

    siapkan_rekam(app)

    app.state.siap = True

    print("[JalanKu] Server siap.")

    yield

    app.state.siap = False
    print("[JalanKu] Server berhenti.")


app = FastAPI(
    title="JalanKu API",
    version="2.0.0",
    lifespan=lifespan,
)


def catat_untuk_zanite(app: FastAPI, sesi_id, hasil):
    """Simpan deteksi terakhir sesi ini untuk Zanite. Tidak boleh membuat /api/deteksi gagal."""
    try:
        zanite = getattr(app.state, "zanite", None)
        if zanite is not None and zanite.siap:
            zanite.catat_deteksi(sesi_id, hasil)
    except Exception as error:
        print(f"[JalanKu] Gagal mencatat deteksi untuk Zanite: {type(error).__name__}")


@app.get("/api/status")
async def status(request: Request):
    return {
        "siap": getattr(request.app.state, "siap", False),
        "model": getattr(request.app.state, "nama_model", "model"),
        "versi_kontrak": 1,
        # true hanya kalau Zanite aktif di config DAN kuncinya ada. Tidak ada info tentang kuncinya.
        "zanite": bool(getattr(getattr(request.app.state, "zanite", None), "siap", False)),
    }


@app.post("/api/deteksi")
async def deteksi(
    request: Request,
    x_sesi: str | None = Header(default=None, alias="X-Sesi"),
):
    try:
        data_gambar = await request.body()

        if not data_gambar:
            return JSONResponse(
                status_code=400,
                content={"error": "Gambar kosong."},
            )

        # waktu_ms = seluruh pemrosesan server per permintaan:
        # decode + semua model + WBF + logika.
        mulai = time.perf_counter()

        gambar = cv2.imdecode(
            np.frombuffer(data_gambar, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )

        if gambar is None:
            return JSONResponse(
                status_code=400,
                content={"error": "Format gambar tidak valid."},
            )

        hasil_deteksi = request.app.state.mesin_deteksi.prediksi(
            gambar
        )

        sesi_id = x_sesi.strip() if x_sesi and x_sesi.strip() else "default"

        hasil = request.app.state.mesin_logika.proses(
            hasil_deteksi,
            sesi_id=sesi_id,
        )

        sinkron_gpu()

        hasil["waktu_ms"] = round(
            (time.perf_counter() - mulai) * 1000,
            2,
        )

        rekam(request.app, data_gambar, sesi_id, hasil_deteksi, hasil)
        catat_untuk_zanite(request.app, sesi_id, hasil)

        return hasil

    except Exception as error:
        print(f"[JalanKu] Error: {error}")

        return JSONResponse(
            status_code=500,
            content={"error": "Gagal memproses gambar."},
        )


@app.post("/api/zanite")
async def zanite_jawab(
    request: Request,
    x_sesi: str | None = Header(default=None, alias="X-Sesi"),
):
    """Semua pemeriksaan dan jawaban (termasuk jalur gagal) ada di zanite.py."""
    zanite = getattr(request.app.state, "zanite", None)
    if zanite is None:
        return JSONResponse(
            content={"jawaban": "Zanite belum aktif di server.", "jenis": "mati", "alasan": "mati", "model": None}
        )
    return await zanite.tangani(request, x_sesi)


# Halaman web (src/web/). Harus SETELAH semua route /api supaya
# tidak menutupi route di atas.
app.mount(
    "/",
    StaticFiles(directory=str(WEB_DIR), html=True),
    name="web",
)
