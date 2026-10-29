# Reference

Kode prototipe awal (dari Nicksen) sebagai bahan referensi. Bukan kode final dan tidak untuk di-import dari `src/`.

- Memakai Roboflow `inference`, `python-dotenv`, `pyttsx3`, dan OpenCV. Paket-paket ini belum ada di `requirements.txt`.
- Butuh `ROBOFLOW_API_KEY` di file `.env` (tidak masuk Git).
- Ide yang mungkin dipakai ulang: jeda pengucapan (cooldown) dan suara di thread terpisah di `speech.py`, serta pembagian arah kiri/depan/kanan di `rules.py`.