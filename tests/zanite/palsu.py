"""Penyedia palsu untuk tes Zanite: tanpa jaringan sama sekali."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "server"))
import zanite as Z  # noqa: E402


class PenyediaPalsu(Z.Penyedia):
    """Mengembalikan teks mentah yang diatur. Bisa melempar galat atau tidur dulu.
    Mencatat setiap panggilan di .panggilan sebagai (jpeg_bytes, isi_teks)."""

    def __init__(self, mentah='{"jawaban": "Di kiri ada pilar, jaraknya sedang."}', galat=None, tidur=0.0):
        self.mentah = mentah
        self.galat = galat
        self.tidur = tidur
        self.panggilan = []

    async def jawab(self, jpeg_bytes, isi_teks):
        self.panggilan.append((jpeg_bytes, isi_teks))
        if self.tidur:
            await asyncio.sleep(self.tidur)
        if self.galat is not None:
            raise self.galat
        return self.mentah
