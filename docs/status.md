# Status JalanKu

Terakhir diperbarui: 4 November 2026

## Ringkasan
Aplikasi ML pendeteksi rintangan dan jalur jalan untuk pengguna tunanetra lewat kamera HP, dengan peringatan suara. Proyek UAS Machine Learning (Mufid, Nicksen, Kenzu). Prototipe pendamping, bukan pengganti alat bantu resmi. Perkiraan jarak dari ukuran kotak hanya kasar.

Tahap sekarang: data kampus sudah siap, berikutnya memilih alat label dan format (kotak atau segmentasi), lalu ngelabel frame pilot.

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
- Script ekstraksi frame dan blur wajah (`tools/extract_frames.py`), versi library dikunci di `requirements.txt`
- Ekstraksi selesai: 39 video jadi 3.136 frame (sekitar 1 frame per detik), kepala orang diblur, dicek manual. Frame yang memperlihatkan taman (lokasi test) di salah satu video training dibuang
- Frame disimpan di Google Drive bersama, frame lokasi test dipisah dari frame training
- Kode prototipe lama masuk `reference/` (sudah dicek tidak ada API key)
- Google Drive bersama untuk data dan video mentah (akses terbatas, link dibagikan lewat grup)

## Sedang jalan
- Kenzu: tes setup PyTorch CPU, rekam taman kampus (lokasi test outdoor, POV dada), download 4 dataset publik format kotak, isi bagian [CEK] di survei dataset dan catatan untuk keputusan kelas v1.3
- Nicksen: perbandingan 2-3 alat label yang jalan lokal plus tes kecil kotak vs polygon (`docs/alat-label.md`), lalu contoh benar/salah per kelas di panduan anotasi v1.1
- Mufid: review PR, ekstrak dan blur video taman setelah direkam

## Belum
- Keputusan kelas v1.3: definisi kendaraan (terparkir saja atau semua), pohon (batang saja atau seluruh pohon), dan pemetaan kelas yang masih usulan
- Keputusan alat label dan format (kotak, segmentasi, atau dua model)
- Pilih sekitar 200-300 frame pilot, ngelabel, training baseline
- Gabungkan dataset publik jadi satu dataset (setelah v1.3 diputuskan)
- Dataset kampus berlabel lengkap, model sendiri, kode final di `src/`
- Cara aplikasi jalan di HP
- Panduan UAS resmi dari dosen dan izin publikasi data kampus

## Keputusan
- Data: dataset publik (catat link, tidak diunggah ulang) ditambah video kampus UBM Serpong
- Dataset publik yang dipakai, alasan penolakan, dan peta kelas ada di `docs/survei-dataset.md`
- Pilar gedung, jalur_jalan dalam gedung, dan kondisi kampus tetap dari video sendiri
- Rintangan di luar 10 kelas tidak dilabel; ditangani lewat jalur_jalan (jalur tertutup = ada halangan)
- Wajah wajib diblur sebelum frame dibagikan atau diunggah ke layanan lain
- Gambar kampus tidak di-commit ke repo sampai izin publikasi dari dosen jelas; contoh di dokumen dirujuk lewat nama file
- Test set: lantai 11 UBM Tower dan taman kampus, tidak dipakai training
- Split per video atau lokasi, bukan acak per frame
- Roboflow opsional (plan gratis membuat data jadi publik)

## Catatan dosen (lisan)
Originalitas, UI/UX bagus, fungsi jalan dengan baik. Dataset publik boleh. Disarankan image segmentation. Panduan UAS resmi belum keluar.