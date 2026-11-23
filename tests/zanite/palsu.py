"""Penyedia palsu untuk tes Zanite: tanpa jaringan sama sekali."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "server"))
import zanite as Z  # noqa: E402


class PenyediaPalsu(Z.Penyedia):
    """Mengembalikan teks mentah yang diatur. Bisa melempar galat atau tidur dulu.
    Mencatat setiap panggilan di .panggilan sebagai (jpeg_bytes, isi_teks), dan model/ulang-nya di .model_dipanggil."""

    def __init__(self, mentah='{"jawaban": "Di kiri ada pilar, jaraknya sedang."}', galat=None, tidur=0.0):
        self.mentah = mentah
        self.galat = galat
        self.tidur = tidur
        self.panggilan = []
        self.model_dipanggil = []

    async def jawab(self, jpeg_bytes, isi_teks, model=None, ulang=True):
        self.panggilan.append((jpeg_bytes, isi_teks))
        self.model_dipanggil.append(model)
        if self.tidur:
            await asyncio.sleep(self.tidur)
        if self.galat is not None:
            raise self.galat
        return self.mentah


class PenyediaPerModel(Z.Penyedia):
    """Satu PenyediaPalsu per nama model: perilaku tiap model diatur sendiri. Model yang tidak terdaftar menggagalkan tes.
    .urutan = nama model yang dipanggil (berurutan), .ulang = nilai argumen `ulang` tiap panggilan."""

    def __init__(self, peta):
        self.peta = peta
        self.urutan = []
        self.ulang = []

    async def jawab(self, jpeg_bytes, isi_teks, model=None, ulang=True):
        self.urutan.append(model)
        self.ulang.append(ulang)
        return await self.peta[model].jawab(jpeg_bytes, isi_teks, model=model, ulang=ulang)
