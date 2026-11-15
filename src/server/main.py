from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
import yaml

from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse

from deteksi import MesinDeteksi
from logika import MesinLogika


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "src" / "server" / "config.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    with open(CONFIG_PATH, encoding="utf-8") as file:
        config = yaml.safe_load(file)

    config["model_kotak"] = str(ROOT / config["model_kotak"])
    config["model_seg"] = str(ROOT / config["model_seg"])

    print("[JalanKu] Memuat model...")

    app.state.mesin_deteksi = MesinDeteksi(config)
    app.state.mesin_logika = MesinLogika(config)

    app.state.siap = True

    print("[JalanKu] Server siap.")

    yield

    app.state.siap = False
    print("[JalanKu] Server berhenti.")


app = FastAPI(
    title="JalanKu API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/status")
async def status(request: Request):
    siap = getattr(request.app.state, "siap", False)

    return {
        "siap": siap,
        "model": "baseline",
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

        gambar_array = np.frombuffer(
            data_gambar,
            dtype=np.uint8,
        )

        gambar = cv2.imdecode(
            gambar_array,
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

        return hasil

    except Exception as error:
        print(f"[JalanKu] Error: {error}")

        return JSONResponse(
            status_code=500,
            content={"error": "Gagal memproses gambar."},
        )
