"""Mesin deteksi JalanKu: model kotak (tunggal atau ensemble WBF) + model segmentasi."""
import time
from pathlib import Path

import numpy as np
import torch
import yaml
from ultralytics import YOLO

from ensemble import WBF_IOU, wbf_gambar


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "src" / "server" / "config.yaml"


def muat_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file)


def path_model(nilai):
    """Path model di config relatif terhadap root repo."""
    p = Path(nilai)
    return str(p if p.is_absolute() else ROOT / p)


def sinkron_gpu():
    if torch.cuda.is_available():
        torch.cuda.synchronize()


class MesinDeteksi:
    def __init__(self, config):
        self.config = config

        pakai_gpu = torch.cuda.is_available()
        self.device = 0 if pakai_gpu else "cpu"
        self.use_half = bool(pakai_gpu and config.get("half", False))

        # half hanya dikirim kalau aktif (argumen ini sudah deprecated
        # di Ultralytics dan memicu peringatan walau False)
        self.opsi_half = {"half": True} if self.use_half else {}

        print(f"[JalanKu] Device: {self.device}")
        print(f"[JalanKu] Half precision: {self.use_half}")

        # Model kotak: ensemble (daftar anggota) atau satu model.
        # Semua model dimuat satu kali saat server dimulai.
        anggota = config.get("ensemble_kotak")

        if anggota:
            self.mode = "ensemble"
            self.kotak = [
                (YOLO(path_model(a["bobot"])), int(a["imgsz"]))
                for a in anggota
            ]
        else:
            self.mode = "tunggal"
            self.kotak = [(
                YOLO(path_model(config["model_kotak"])),
                int(config.get("imgsz", 640)),
            )]

        self.model_seg = YOLO(path_model(config["model_seg"]))

        self.nama_kelas_kotak = self.kotak[0][0].names
        self.nama_kelas_seg = self.model_seg.names

        for model, _ in self.kotak[1:]:
            if model.names != self.nama_kelas_kotak:
                raise ValueError(
                    "Kelas anggota ensemble tidak sama."
                )

        self.conf_prediksi = float(
            config.get("conf_prediksi_kotak", 0.05)
        )
        self.wbf_iou = float(config.get("wbf_iou", WBF_IOU))
        self.imgsz_seg = int(config.get("imgsz_seg", 640))
        self.conf_seg = float(config.get("conf_seg", 0.25))

        print(
            f"[JalanKu] Model kotak ({self.mode}, "
            f"{len(self.kotak)} model):",
            self.nama_kelas_kotak,
        )
        print("[JalanKu] Model segmentasi:", self.nama_kelas_seg)

        # Pemanasan supaya permintaan pertama tidak lambat
        kosong = np.zeros((640, 480, 3), dtype=np.uint8)
        self.prediksi(kosong)

    def _prediksi_anggota(self, model, imgsz, gambar):
        hasil = model.predict(
            source=gambar,
            imgsz=imgsz,
            conf=self.conf_prediksi,
            device=self.device,
            **self.opsi_half,
            verbose=False,
        )[0]

        tinggi, lebar = hasil.orig_shape

        return dict(
            w=lebar,
            h=tinggi,
            cls=hasil.boxes.cls.cpu().numpy().astype(int),
            conf=hasil.boxes.conf.cpu().numpy().astype(float),
            xyxy=hasil.boxes.xyxy.cpu().numpy().astype(float),
        )

    def deteksi_kotak(self, gambar):
        """
        Kotak akhir dalam piksel: dict w, h, cls, conf, xyxy.

        Ensemble: tiap anggota diprediksi dengan conf_prediksi_kotak,
        digabung per kelas dengan WBF, BARU disaring conf_kelas.
        Model tunggal: prediksi lalu saring conf_kelas.
        """

        daftar = [
            self._prediksi_anggota(model, imgsz, gambar)
            for model, imgsz in self.kotak
        ]

        if self.mode == "ensemble":
            pred = wbf_gambar(daftar, self.wbf_iou)
        else:
            pred = daftar[0]

        conf_kelas = self.config.get("conf_kelas", {})

        batas = np.array(
            [
                conf_kelas.get(self.nama_kelas_kotak[int(c)], 0.35)
                for c in pred["cls"]
            ],
            dtype=float,
        )

        lolos = pred["conf"] >= batas - 1e-9

        return dict(
            w=pred["w"],
            h=pred["h"],
            cls=pred["cls"][lolos],
            conf=pred["conf"][lolos],
            xyxy=pred["xyxy"][lolos],
        )

    def prediksi(self, gambar):
        """
        Input:
            gambar: numpy array BGR dari OpenCV

        Output:
            dict berisi objek (kotak 0-1), mask segmentasi seukuran
            gambar asli, dan waktu inference.
        """

        mulai = time.perf_counter()

        pred = self.deteksi_kotak(gambar)

        sinkron_gpu()
        selesai_kotak = time.perf_counter()

        hasil_seg = self.model_seg.predict(
            source=gambar,
            imgsz=self.imgsz_seg,
            conf=self.conf_seg,
            retina_masks=True,
            device=self.device,
            **self.opsi_half,
            verbose=False,
        )[0]

        mask_seg = None
        kelas_seg = []

        if hasil_seg.masks is not None and len(hasil_seg.masks.data):
            # retina_masks=True: (n, tinggi, lebar) gambar asli
            mask_seg = (hasil_seg.masks.data > 0.5).cpu().numpy()
            kelas_seg = hasil_seg.boxes.cls.cpu().numpy().astype(int).tolist()

        sinkron_gpu()

        selesai = time.perf_counter()
        waktu_ms = round((selesai - mulai) * 1000, 2)

        lebar, tinggi = pred["w"], pred["h"]
        objek = []

        for kelas_id, confidence, (x1, y1, x2, y2) in zip(
            pred["cls"], pred["conf"], pred["xyxy"]
        ):
            objek.append({
                "kelas": self.nama_kelas_kotak[int(kelas_id)],
                "conf": round(float(confidence), 4),
                "kotak": [
                    round(min(max(x1 / lebar, 0.0), 1.0), 4),
                    round(min(max(y1 / tinggi, 0.0), 1.0), 4),
                    round(min(max(x2 / lebar, 0.0), 1.0), 4),
                    round(min(max(y2 / tinggi, 0.0), 1.0), 4),
                ],
            })

        return {
            "objek": objek,
            "mask_seg": mask_seg,
            "kelas_seg": kelas_seg,
            "nama_kelas_seg": self.nama_kelas_seg,
            "waktu_ms": waktu_ms,
            # Rincian untuk pengukuran; tidak ikut ke balasan API
            "rincian_ms": {
                "kotak": round((selesai_kotak - mulai) * 1000, 2),
                "seg": round((selesai - selesai_kotak) * 1000, 2),
            },
        }
