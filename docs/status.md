# Status JalanKu

Terakhir diperbarui: 3 November 2026

## Ringkasan
Aplikasi ML pendeteksi rintangan dan jalur jalan untuk pengguna tunanetra lewat kamera HP, dengan peringatan suara. Proyek UAS Machine Learning (Mufid, Nicksen, Kenzu). Prototipe pendamping, bukan pengganti alat bantu resmi. Perkiraan jarak dari ukuran kotak hanya kasar.

## Selesai
- Setup lokal Mufid (Python 3.12.10, PyTorch GPU RTX 4060, Ultralytics)
- Setup lokal Nicksen (GTX 1650 Ti 4 GB)
- Kenzu sudah clone repo dan install PyTorch CPU (belum dites)
- Perkenalan tim lengkap (`docs/tim/`)
- Repo publik, README setup, kerangka folder, `.gitignore`
- Aturan repo di GitHub: perubahan ke `main` wajib lewat Pull Request dan 1 approval
- Tes awal YOLO bawaan (COCO): pohon, pilar, tepian tidak dikenali
- Daftar 10 kelas v1.2 dan aturan anotasi (`docs/kelas.md`)
- Panduan anotasi v1.0 draft (`docs/panduan-anotasi.md`)
- Survei dataset publik selesai: 6 dipakai, 12 ditolak (`docs/survei-dataset.md`)
- Rekaman video kampus batch pertama: 39 video, POV mata dan dada (`docs/rekam-video.md`)
- Kode prototipe lama masuk `reference/` (sudah dicek tidak ada API key)
- Google Drive bersama untuk data dan video mentah (akses terbatas, link dibagikan lewat grup)

## Sedang jalan
- Mufid: script ekstraksi frame dan blur wajah (`extract_frames.py`)
- Kenzu: rekam taman kampus (lokasi test outdoor, POV dada)
- Nicksen: perbandingan 2-3 alat label yang jalan lokal

## Belum
- Contoh visual benar/salah di panduan anotasi (menunggu frame yang sudah diblur)
- Download dataset publik, isi bagian [CEK] di survei dataset, gabungkan jadi satu dataset
- Keputusan kelas v1.3: definisi kendaraan (terparkir saja atau semua), pohon (batang saja atau seluruh pohon), dan pemetaan kelas yang masih usulan
- Dataset kampus berlabel, model sendiri, kode final di `src/`
- Keputusan model (segmentation, kotak, atau dua model) dan cara aplikasi jalan di HP
- Panduan UAS resmi dari dosen

## Keputusan
- Data: dataset publik (catat link, tidak diunggah ulang) ditambah video kampus UBM Serpong
- Dataset publik yang dipakai, alasan penolakan, dan peta kelas ada di `docs/survei-dataset.md`
- Pilar gedung, jalur_jalan dalam gedung, dan kondisi kampus tetap dari video sendiri
- Rintangan di luar 10 kelas tidak dilabel; ditangani lewat jalur_jalan (jalur tertutup = ada halangan)
- Wajah wajib diblur sebelum frame dibagikan atau diunggah ke layanan lain
- Test set: lantai 11 UBM Tower dan taman kampus, tidak dipakai training
- Split per video atau lokasi, bukan acak per frame
- Roboflow opsional (plan gratis membuat data jadi publik)

## Catatan dosen (lisan)
Originalitas, UI/UX bagus, fungsi jalan dengan baik. Dataset publik boleh. Disarankan image segmentation. Panduan UAS resmi belum keluar.