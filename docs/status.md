# Status JalanKu

Terakhir diperbarui: 16 November 2026

## Ringkasan
Aplikasi ML pendeteksi rintangan dan jalur jalan untuk pengguna tunanetra lewat kamera HP, dengan peringatan suara, getar, dan tampilan. Proyek UAS Machine Learning (Mufid, Nicksen, Kenzu). Prototipe pendamping, bukan pengganti tongkat atau alat bantu resmi. Perkiraan jarak hanya kasar.

Aplikasi sudah berjalan ujung ke ujung: halaman web di Chrome HP mengirim frame kamera ke server FastAPI di laptop (lewat hotspot HP dan HTTPS lokal), server menjalankan model kotak dan model segmentasi, lalu membalas satu peringatan per frame. Tahap sekarang: persiapan tes bareng di kelas Machine Learning (Rabu, 18 November), lalu uji lapangan, laporan, dan video demo (akhir November). Batas pengumpulan UAS 12 Desember 2026.

## Selesai

### Data dan label
- 8 kelas kotak (pilar, pohon (batang), tepian, orang, tanaman_pot, kursi, kendaraan, tangga) dan 3 kelas segmentasi (jalur_jalan, jalan_kendaraan, tangga), aturan di `docs/kelas.md` (v1.8)
- Data kampus berlabel 391 frame (pilot 249, ronde 2 66, ronde 4 142) ditambah dataset publik (`docs/dataset-publik.md`, `docs/survei-dataset.md`)
- Audit label (`docs/hasil-audit.md`) dan pemeriksaan kebocoran lokasi test
- Split per lokasi: val = dapsut, perpus-lt9, tangga-naik-lt9-lt10; test = selasar lantai 11, pot lantai 11, taman-ubm (`docs/test-set.md`)

### Model
- Baseline (`docs/hasil-baseline.md`), ronde 2 (`docs/hasil-ronde2.md`), ronde 3-4, ensemble, dan TTA; aturan pemilihan tiap ronde ditulis sebelum hasilnya ada
- Model final kotak: ensemble WBF 4 model YOLO (3 di imgsz 960, 1 di 1280). Model final segmentasi: `r2-seg-v3` (imgsz 640). Ambang per kelas dikunci dari val
- Test set dievaluasi satu kali sesudah semuanya dikunci (`docs/hasil-test-final.md`): mAP50 0,305, mAP50-95 0,172, F1 0,308 (val: mAP50 0,613). Peringatan tingkat frame: presisi 100% (0 salah dari 48 frame tanpa rintangan), recall 67%. Segmentasi jalur_jalan IoU 0,81; jalan_kendaraan gagal di test
- Kecepatan (laptop RTX 4060, mode Performance): model kotak ensemble 49,5 ms per frame, seluruh request server sekitar 66-76 ms

### Aplikasi
- Server (`src/server/`): FastAPI, ensemble + WBF, segmentasi, logika bahaya (kelas, posisi kiri/tengah/kanan 30/40/30, jarak dari tepi bawah kotak), stabilisasi antar frame per sesi, satu peringatan per frame (tingkat tertinggi). Menyajikan halaman web di "/"
- Peringatan dari segmentasi: "Tangga di depan", "Area kendaraan, hati-hati", "Jalur terhalang", dan "Hati-hati, jalur tidak terlihat" (kamera mepet tembok/pintu atau tidak melihat jalur 3 frame berturut-turut)
- Web (`src/web/`): kamera belakang, kotak dan garis zona di layar, banner status, suara bahasa Indonesia (tingkat 3 memotong suara lain), getar untuk tingkat 3 (tetap jalan saat Bisu), Wake Lock, status jalur, mode mock untuk tes tanpa server
- Frame berikutnya dikirim begitu balasan tiba (jeda minimum 200 ms). Banner tanpa peringatan baru berganti setelah 2 balasan berturut-turut dan memakai gaya info, supaya tidak berkedip
- Mode rekam opsional di server (`JALANKU_REKAM=1`): menyimpan frame yang diterima dan hasilnya ke `data/rekam/` (lokal, tidak di-commit) untuk analisis
- Aturan peringatan dari ablasi (16 November), semuanya bisa dimatikan lewat `config.yaml` atau menu Atur:
  - "Tangga di depan" dari segmentasi harus muncul 3 dari 3 frame (sebelumnya 2 dari 3)
  - Objek berjarak "jauh" tidak jadi peringatan saat segmentasi tidak melihat apa pun (kamera mepet permukaan)
  - Benda ringan (kursi, tanaman pot) berkelas sama tidak diucapkan ulang dalam 8 detik
  - Hasil ablasi (data non-test saja): tangga asli di 6 video tangga kampus tetap tertangkap pada detik yang sama; peringatan tangga palsu di rekaman uji rumah turun sekitar setengah; ucapan per menit di rumah turun dari 39 ke 25

### Uji
- Gladi di HP lewat hotspot dan HTTPS (15-16 November): kamera, suara, dan peringatan berjalan; sekitar 4 frame per detik, jeda stabil selama pemakaian
- Diagnosa "kamera mepet tembok": segmentasi kosong saat mepet; di 3.790 frame video kampus non-test, peringatan "jalur tidak terlihat" muncul terutama saat kamera memang menghadap tembok, pintu, rak, atau eskalator

## Sedang jalan
- Persiapan tes bareng Rabu 18 November di kelas dan lab komputer (Mufid membawa laptop server). Rekaman server dinyalakan supaya ambang bisa dinilai ulang dengan data kampus
- Mufid memegang semua pekerjaan aplikasi sampai tes; Nicksen dan Kenzu standby

## Belum
- Menilai ulang ambang (tangga dari segmentasi, kotak tangga "jauh", area kendaraan, kotak kendaraan) memakai rekaman kampus dari tes Rabu
- Uji lapangan di kampus, video demo, README cara menjalankan, laporan akhir
- Opsi melatih ulang model dengan semua data berlabel (ditunda sampai sesudah tes Rabu)
- Panduan UAS resmi dari dosen dan izin publikasi data kampus

## Keputusan
- Data: dataset publik (link dicatat, tidak diunggah ulang) ditambah video kampus UBM Serpong; wajah diblur sebelum frame dibagikan
- Gambar kampus dan rekaman tidak di-commit ke repo; bobot model disimpan di Drive bersama, bukan di Git
- Test set (lantai 11 dan taman) tidak dipakai untuk training maupun untuk memilih ambang atau aturan; sudah dievaluasi sekali dan tidak dipakai lagi
- Split per video atau lokasi, bukan acak per frame
- Aplikasi = halaman web di HP + server di laptop lewat jaringan lokal. Tidak di-deploy ke internet (butuh GPU, dan frame kamera bersifat pribadi)
- Rintangan di luar 8 kelas ditangani lewat jalur jalan (jalur tertutup = ada halangan)
- Pohon dilabel batangnya saja
- Satu peringatan per frame, dipilih dari tingkat bahaya; pesan suara umum, tidak menjanjikan nama benda yang selalu benar
- Roboflow opsional (plan gratis membuat data jadi publik)

## Keterbatasan yang sudah diketahui
- Model turun sekitar setengah di lokasi yang belum pernah dilihat (domain gap), terutama taman dan bangku
- Jarak dekat/sedang/jauh ditebak dari posisi tepi bawah kotak di layar, jadi ikut berubah saat sudut kamera berubah. Pakai pose pegang HP yang sama (di dada, lurus ke depan)
- Segmentasi bisa mengira furnitur berukir sebagai tangga, dan tidak mengenali eskalator sebagai tangga
- Ambang kendaraan rendah (0,10) bisa memunculkan "kendaraan" palsu di dalam ruangan; "Area kendaraan" baru teruji di lokasi training
- Kerb dan undakan kecil di lokasi baru adalah risiko terbesar; pengguna tetap memakai tongkat

## Catatan dosen (lisan)
Originalitas, UI/UX bagus, fungsi jalan dengan baik. Dataset publik boleh. Disarankan image segmentation. Cukup berjalan di HP; akan ada pameran. Panduan UAS resmi belum keluar.
