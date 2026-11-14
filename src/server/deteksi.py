
import time
from pathlib import Path

import torch
from ultralytics import YOLO


class MesinDeteksi:
    def __init__(self, config):
        self.config = config

        self.device = (
            0 if torch.cuda.is_available() else "cpu"
        )
        self.use_half = (
            torch.cuda.is_available()
            and config.get("half", True)
        )

        print(f"[JalanKu] Device: {self.device}")
        print(f"[JalanKu] Half precision: {self.use_half}")

        # Load kedua model satu kali saat server dimulai
        self.model_kotak = YOLO(config["model_kotak"])
        self.model_seg = YOLO(config["model_seg"])

        self.nama_kelas_kotak = self.model_kotak.names
        self.nama_kelas_seg = self.model_seg.names

        print("[JalanKu] Model kotak:", self.nama_kelas_kotak)
        print("[JalanKu] Model segmentasi:", self.nama_kelas_seg)

    def prediksi(self, gambar):
        """
        Input:
            gambar: numpy array BGR dari OpenCV

        Output:
            dict berisi hasil model kotak,
            hasil segmentasi, dan waktu inference.
        """

        mulai = time.perf_counter()

        hasil_kotak = self.model_kotak.predict(
            source=gambar,
            imgsz=self.config.get("imgsz", 640),
            conf=0.01,
            device=self.device,
            half=self.use_half,
            verbose=False,
        )[0]

        hasil_seg = self.model_seg.predict(
            source=gambar,
            imgsz=self.config.get("imgsz", 640),
            conf=0.01,
            device=self.device,
            half=self.use_half,
            verbose=False,
        )[0]

        # Pastikan operasi GPU selesai sebelum menghitung waktu
        if torch.cuda.is_available():
            torch.cuda.synchronize()

        waktu_ms = round(
            (time.perf_counter() - mulai) * 1000,
            2,
        )

        objek = []

        if hasil_kotak.boxes is not None:
            for box in hasil_kotak.boxes:
                kelas_id = int(box.cls.item())
                nama_kelas = self.nama_kelas_kotak[kelas_id]
                confidence = float(box.conf.item())

                threshold = self.config.get(
                    "conf_kelas", {}
                ).get(nama_kelas, 0.35)

                if confidence < threshold:
                    continue

                x1, y1, x2, y2 = (
                    box.xyxy[0].cpu().tolist()
                )

                tinggi, lebar = gambar.shape[:2]

                objek.append({
                    "kelas": nama_kelas,
                    "conf": round(confidence, 4),
                    "kotak": [
                        round(x1 / lebar, 4),
                        round(y1 / tinggi, 4),
                        round(x2 / lebar, 4),
                        round(y2 / tinggi, 4),
                    ],
                })



        mask_seg = None
        kelas_seg = []

        if hasil_seg.masks is not None and hasil_seg.boxes is not None:
            mask_seg = hasil_seg.masks.data.cpu().numpy()
            kelas_seg = [
                int(box.cls.item())
                for box in hasil_seg.boxes
            ]

        return {
            "objek": objek,
            "mask_seg": mask_seg,
            "kelas_seg": kelas_seg,
            "nama_kelas_seg": self.nama_kelas_seg,
            "waktu_ms": waktu_ms,
        }
