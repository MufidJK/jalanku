# Uji paritas logika Python vs JavaScript

`src/web/logika.js` harus memberi keluaran sama dengan `MesinLogika` di `src/server/logika.py`.

1. Ekspor config (sekali, atau `--force` kalau `config.yaml` berubah):
   `venv\Scripts\python src\server\ekspor_config_web.py`
2. Buat data uji (butuh `data/analisis-rekaman/cache_rekam.pkl`, hasil di `data/logika-js/`, menolak menimpa; hapus dulu kalau mau buat ulang):
   `venv\Scripts\python tests\logika\buat_kasus.py`
3. Jalankan uji: `node tests\logika\cek_logika.mjs` (kode keluar 0 = identik 100%, 1 = ada selisih).

Uji memeriksa: config JSON sinkron dengan `config.yaml`, 11.299 frame (aturan v1.1 hidup dan mati), 42 kasus sintetis (`kasus_sintetis.py`, salinan `data/server-v2/uji_logika.py`).
Ubah `config.yaml` atau `logika.py`: ulangi langkah 1 dan 2 (hapus `data/logika-js/*` dulu).
