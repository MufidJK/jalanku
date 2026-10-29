# Status JalanKu

Terakhir diperbarui: 29 Oktober 2026

## Ringkasan
Aplikasi ML pendeteksi rintangan dan jalur jalan untuk pengguna tunanetra lewat kamera HP, dengan peringatan suara. Proyek UAS Machine Learning (Mufid, Nicksen, Kenzu). Prototipe pendamping, bukan pengganti alat bantu resmi. Perkiraan jarak dari ukuran kotak hanya kasar.

## Selesai
- Setup lokal Mufid (Python 3.12.10, PyTorch GPU, Ultralytics)
- Repo publik, README setup, kerangka folder, `.gitignore`
- Tes awal YOLO bawaan (COCO): pohon, pilar, tepian tidak dikenali
- Daftar 9 kelas v1.1 dan aturan anotasi awal (`docs/kelas.md`)
- Aturan rekam video kampus (`docs/rekam-video.md`)
- Kode prototipe lama masuk `reference/` (sudah dicek tidak ada API key)
- Google Drive bersama untuk data dan video mentah (akses terbatas, link dibagikan lewat grup)

## Sedang jalan
- Kenzu: survei dataset publik (`docs/survei-dataset.md`)
- Nicksen: setup, PR perkenalan, pengembangan panduan anotasi
- Mufid: persiapan rekam video kampus

## Belum
- Dataset sendiri, model sendiri, kode final di `src/`
- Script ekstraksi frame dan blur wajah
- Keputusan model (segmentation, kotak, atau dua model) dan cara aplikasi jalan di HP
- Panduan UAS resmi dari dosen

## Keputusan
- Data: dataset publik (catat link, tidak diunggah ulang) ditambah video kampus UBM Serpong
- Wajah wajib diblur sebelum frame dibagikan atau diunggah ke layanan lain
- Test set berasal dari lokasi yang tidak dipakai training
- Roboflow opsional (plan gratis membuat data jadi publik)

## Catatan dosen (lisan)
Originalitas, UI/UX bagus, fungsi jalan dengan baik. Dataset publik boleh. Panduan UAS resmi belum keluar.