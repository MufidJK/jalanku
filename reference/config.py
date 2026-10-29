import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ROBOFLOW_API_KEY")

# Model sementara (COCO) untuk tes. Nanti ganti dengan model sendiri,
# formatnya "nama-project/nomor-versi". Cek ID model di dokumentasi Roboflow.
MODEL_ID = "yolov8n-640"
CONFIDENCE = 0.5
KAMERA_INDEX = 0

# Nama kelas model -> kata yang diucapkan
NAMA_ID = {
    "person": "orang",
    "car": "mobil",
    "motorcycle": "motor",
    "bus": "bus",
    "truck": "truk",
    "bicycle": "sepeda",
}
KELAS_DIPAKAI = set(NAMA_ID)

# Kelas yang dianggap berbahaya jika dekat di depan
KELAS_BAHAYA = {"car", "motorcycle", "bus", "truck"}

# Jarak kasar = luas kotak / luas frame (perkiraan, bukan jarak asli)
BATAS_DEKAT = 0.15
BATAS_SANGAT_DEKAT = 0.40

# Jeda minimal (detik) sebelum pesan yang sama diulang
JEDA_DETIK = 4
