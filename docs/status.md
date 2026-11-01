# Status JalanKu

Terakhir diperbarui: 1 November 2026

## Ringkasan
Aplikasi ML pendeteksi rintangan dan jalur jalan untuk pengguna tunanetra lewat kamera HP, dengan peringatan suara. Proyek UAS Machine Learning (Mufid, Nicksen, Kenzu). Prototipe pendamping, bukan pengganti alat bantu resmi. Perkiraan jarak dari ukuran kotak hanya kasar.

## Selesai
- Setup lokal Mufid (Python 3.12.10, PyTorch GPU RTX 4060, Ultralytics)
- Setup lokal Nicksen (GTX 1650 Ti 4 GB) dan PR perkenalan (`docs/tim/nicksen.md`)
- Repo publik, README setup, kerangka folder, `.gitignore`
- Tes awal YOLO bawaan (COCO): pohon, pilar, tepian tidak dikenali
- Daftar 10 kelas v1.2 dan aturan anotasi awal (`docs/kelas.md`)
- Rekaman video kampus batch pertama: 39 video, POV mata dan dada (`docs/rekam-video.md`)
- Kode prototipe lama masuk `reference/` (sudah dicek tidak ada API key)
- Google Drive bersama untuk data dan video mentah (akses terbatas, link dibagikan lewat grup)

## Sedang jalan
- Kenzu: clone repo, survei dataset publik (`docs/survei-dataset.md`)
- Nicksen: panduan anotasi (`docs/panduan-anotasi.md`)
- Mufid: script ekstraksi frame dan blur wajah

## Belum
- Rekam taman kampus (lokasi test outdoor, POV dada)
- Dataset kampus berlabel, model sendiri, kode final di `src/`
- Keputusan model (segmentation, kotak, atau dua model) dan cara aplikasi jalan di HP
- Panduan UAS resmi dari dosen

## Keputusan
- Data: dataset publik (catat link, tidak diunggah ulang) ditambah video kampus UBM Serpong
- Dataset publik (detail di `docs/survei-dataset.md`):
  - Dipakai:
    - ROD-Dataset `abtinzandi/obstacle-detection-dataset` (rintangan dan tangga; MIT)
    - OOD Roboflow `fpn/ood-pbnro` (tepian dan rintangan; CC BY 4.0)
    - Unstructured Road Roboflow `mtechcv` (pohon, kendaraan, pilar, tangga; jalanan India dari kamera HP; CC BY 4.0)
    - Sidewalk Segment Kaggle `lemnix/sidewalk-segment-dataset` (jalur_jalan, segmentasi; CC BY-SA 4.0; sebagian gambar salinan yang diputar, jadi salinan dan aslinya harus satu split)
    - SANPO (cadangan untuk jalur_jalan, jalan_kendaraan, tepian; CC BY 4.0; diambil sebagian karena total sekitar 6 TB)
  - Ditolak: light-poles (foto drone), dngomnh/sidewalk (tanpa label), sidewalk-cracks, PAVE (tanpa gambar), SOD (salinan OOD), PEDESTRIAN (label per video, tanpa kotak), OD Obstacle Dataset TW0521 (gabungan COCO, lisensi tidak jelas), SideGuide (perlu izin, daftar kelas tidak dipublikasi), Freiburg (robot dan LiDAR), RampNet (Street View), uB-VisioGeoloc (tidak ada link)
  - Pilar gedung, jalur_jalan dalam gedung, dan kondisi kampus tetap dari video sendiri
- Wajah wajib diblur sebelum frame dibagikan atau diunggah ke layanan lain
- Test set: lantai 11 UBM Tower dan taman kampus, tidak dipakai training
- Split per video atau lokasi, bukan acak per frame
- Roboflow opsional (plan gratis membuat data jadi publik)

## Catatan dosen (lisan)
Originalitas, UI/UX bagus, fungsi jalan dengan baik. Dataset publik boleh. Disarankan image segmentation. Panduan UAS resmi belum keluar.