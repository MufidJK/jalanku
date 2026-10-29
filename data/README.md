# Data

Isi folder ini tidak di-commit (lihat `.gitignore`). Hanya file ini dan `.gitkeep` yang masuk Git.

## Di mana datasetnya
- Video dan dataset kampus: Google Drive bersama (akses hanya anggota tim). Minta link ke Mufid.
- Dataset publik: link dan cara download ada di `docs/survei-dataset.md`. Jangan upload ulang ke repo atau Drive.

## Struktur lokal yang disarankan
data/
  video-mentah/    video dari kampus
  frame/           frame hasil ekstraksi (belum diblur)
  frame-blur/      frame setelah wajah diblur
  kampus/          dataset kampus berlabel (images/, labels/)
  publik/          dataset publik, satu subfolder per dataset

## Aturan
- Wajah wajib diblur sebelum gambar dibagikan ke Drive atau diunggah ke layanan lain.
- Satu lokasi dan satu video masuk satu split saja (train, val, atau test). Jangan acak per frame.
- Lokasi test tidak dipakai untuk training.