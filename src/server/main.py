import time
from contextlib import asynccontextmanager

import cv2
import numpy as np

from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from deteksi import ROOT, MesinDeteksi, muat_config, sinkron_gpu
from logika import MesinLogika


WEB_DIR = ROOT / "src" / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = muat_config()

    print("[JalanKu] Memuat model...")

    app.state.nama_model = str(config.get("nama_model", "model"))
    app.state.mesin_deteksi = MesinDeteksi(config)
    app.state.mesin_logika = MesinLogika(config)

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


@app.get("/api/status")
async def status(request: Request):
    return {
        "siap": getattr(request.app.state, "siap", False),
        "model": getattr(request.app.state, "nama_model", "model"),
        "versi_kontrak": 1,
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

        return hasil

    except Exception as error:
        print(f"[JalanKu] Error: {error}")

        return JSONResponse(
            status_code=500,
            content={"error": "Gagal memproses gambar."},
        )


# Halaman web (src/web/). Harus SETELAH semua route /api supaya
# tidak menutupi route di atas.
app.mount(
    "/",
    StaticFiles(directory=str(WEB_DIR), html=True),
    name="web",
)
