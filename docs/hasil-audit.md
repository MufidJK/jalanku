# Hasil Audit Label Kampus (11 November 2026)

Ditulis untuk: Jeka dan tim JalanKu yang perlu membaca hasil baseline setelah label kampus dikoreksi. Semua angka berasal dari run di `runs/baseline/eval-v2/` dan dari berkas di `data/audit-kampus/`.

## Ringkasan
- Label kampus (train dan val) diperiksa terhadap aturan tertulis R1-R7 (`docs/kelas.md` v1.6). **155 kotak dihapus dari 75 file JSON** (val 66, train 89), dan Jeka menambah 8 label yang kurang.
- **Modelnya tidak berubah.** Bobot `kotak-gabung_best.pt` dan `kotak-kampus_best.pt` sama persis (hash identik) dengan yang dilatih di baseline; yang berubah hanya ground truth val. Bobot itu dilatih pada label train v1, yang masih memuat inkonsistensi yang sama.
- mAP50 `kotak-gabung` pada val naik dari 0.455 (v1) menjadi 0.498 (v2), mAP50-95 dari 0.263 menjadi 0.296. **Aturan R4 (ambang ukuran) saja, ditambahkan di atas aturan lain, menyumbang +0.026 mAP50 (61% dari kenaikan) dan +0.023 mAP50-95 (71%).**
- Kenaikan itu terutama **koreksi label, bukan perbaikan model**. Contohnya pilar: dari 23 kotak pilar val yang dihapus (R1 dan R7), model tidak pernah menemukan satupun di v1.

## 1. Apa yang diaudit dan kenapa
Saat meninjau contact sheet terburuk di `docs/hasil-baseline.md`, kami menemukan label kampus yang tidak konsisten: sirip dan kosen dinding kaca dilabel pilar, orang di balik kaca dilabel orang, pot kecil di rak dilabel tanaman_pot, kotak di bawah ambang ukuran, kotak ganda pada satu objek, dan benda yang bukan kelasnya (lampu neon, kaki meja, badan gerbang putar). Ground truth yang tidak konsisten membuat skor tidak bisa dibaca: model dihukum karena tidak menemukan benda yang menurut aturan memang tidak boleh dilabel.

Yang diaudit: 249 frame pilot (195 train di 12 lokasi, 54 val di 3 lokasi). Sumber label sama dengan builder dataset: 234 JSON di `data/pilot-v2/` dan 15 JSON blind di `data/pilot-v2-blind/`. Lokasi test dan `data/frame-blur/` tidak disentuh.

## 2. Aturan yang dipakai
Lengkapnya di `docs/kelas.md` v1.6.

| Aturan | Isi singkat |
|---|---|
| R1 | Sirip, mullion, kosen, kusen pintu, bagian dinding/fasad/balustrade bukan pilar, bahan apa pun. Kolom bebas tetap pilar. |
| R2 | Orang di balik kaca (ruang yang tidak bisa dimasuki) tidak dilabel. Kalau ragu, tetap orang. |
| R3 | Pot kecil di rak tidak dilabel. |
| R4 | Ambang ukuran (1080x1920): kelas biasa sisi terpendek >= 96 px; pilar/pohon/tepian sisi terpanjang >= 96 px dan terpendek >= 24 px. |
| R5 | Tanpa pantulan, mural, poster, patung; eskalator tidak dilabel. |
| R6 | Satu objek satu kotak: kotak ganda atau parsial dihapus. |
| R7 | Di luar kelas: gerbang putar, badan portal, kaki meja, lampu langit-langit, kabinet listrik, penyangga pohon. |

Tidak dibuka ulang: barisan motor dan kursi yang rapat di latar sengaja tidak dilabel (opsi a), semua bentuk tangga digabung jadi satu kotak, pohon = batang saja. Kerucut lalu lintas = pilar.

## 3. Cara kerja
1. `tools/audit_label_kampus.py` (hanya membaca): cek ukuran R4, duplikat IoU > 0.9, titik di luar gambar; review visual 60 contact sheet pilar, orang, dan tanaman_pot per lokasi (val dulu); petunjuk model (val saja) dari `galat.json`.
2. Setiap usul memakai nama aturan. Yang tidak yakin ditandai "ragu" dan diputuskan Jeka per ID di CHECKPOINT A1; yang tidak tercakup aturan masuk daftar keputusan Jeka. Tidak ada label val yang diubah demi skor.
3. Penghapusan (`--terapkan`): tiap shape diverifikasi (kelas, bbox, hash titik) sebelum dihapus; format JSON X-AnyLabeling dipertahankan byte demi byte; cadangan di `data/pilot-v2-tune/sebelum-audit/`.
4. Jeka menambah 8 label kurang di X-AnyLabeling (4 dari tahap A dan 4 kerucut di dapsut); semuanya diperiksa ulang (label valid, bbox sesuai, R4 lolos) dan `tools/validasi_pilot_v2.py` lolos (0 error).
5. Dataset dibangun ulang sebagai versi baru; dataset lama dan `runs/baseline/eval/` tidak diubah.

## 4. Apa yang berubah
### 4.1 Kotak yang dihapus per aturan, split, dan kelas

| Aturan | val | train | Total |
|---|---|---|---|
| KJ | - | tanaman_pot 1 | 1 |
| R1 | pilar 17 | pilar 32 | 49 |
| R2 | orang 5 | orang 1 | 6 |
| R3 | tanaman_pot 2 | - | 2 |
| R4 | kendaraan 2, kursi 14, orang 18 | kendaraan 16, kursi 2, orang 6, pilar 2, pohon 3, tanaman_pot 1, tepian 11 | 75 |
| R5 | - | orang 3, pilar 1 | 4 |
| R6 | orang 1 | kursi 1, orang 4, tanaman_pot 1 | 7 |
| R7 | pilar 6, tanaman_pot 1 | pilar 4 | 11 |
| **Total** | **66** | **89** | **155** |

`KJ` = satu keputusan Jeka tanpa aturan tertulis (kotak tanaman_pot di sudut tembok hitam, `jalanan-ubm_..._mata_t0029031#0`). Daftar lengkap per ID: `data/audit-kampus/diterapkan.csv`; bukti sebelum/sesudah: `data/audit-kampus/sebelum_sesudah/`.

### 4.2 Jumlah instance kotak per kelas
Dihitung dari file label (kampus; tangga digabung satu kotak per frame). v2-noR4 = semua perubahan kecuali R4.

**Val**

| Kelas | v1 | v2-noR4 | v2 |
|---|---|---|---|
| pilar | 50 | 34 | 34 |
| pohon | 10 | 10 | 10 |
| tepian | 45 | 45 | 45 |
| orang | 52 | 47 | 29 |
| tanaman_pot | 13 | 10 | 10 |
| kursi | 36 | 36 | 22 |
| kendaraan | 108 | 110 | 108 |
| tangga | 5 | 5 | 5 |
| **total** | 319 | 297 | 263 |

**Train kampus**

| Kelas | v1 | v2-noR4 | v2 |
|---|---|---|---|
| pilar | 151 | 114 | 112 |
| pohon | 82 | 82 | 79 |
| tepian | 168 | 168 | 157 |
| orang | 93 | 85 | 79 |
| tanaman_pot | 47 | 45 | 44 |
| kursi | 155 | 154 | 152 |
| kendaraan | 271 | 271 | 255 |
| tangga | 20 | 20 | 20 |
| **total** | 987 | 939 | 898 |

Dataset gabung (kampus x4 + publik): train 15450 kotak (v1) menjadi 15094 (v2); val sama dengan val kampus. Bagian publik **identik byte demi byte** dengan v1: 2300 gambar dan 2300 file label, `sumber.csv` bagian publik, dan `kotak_akhir.csv` (11.847 baris) sama persis. Validasi Ultralytics `YOLODataset`: 0 gambar korup di `dataset-kampus-kotak-v2` (train 195, val 54), `dataset-kampus-kotak-v2-noR4` (195, 54), `dataset-kampus-seg-v2` (195, 54), `dataset-gabung-kotak-v2` (train 3080, val 54), dan `dataset-gabung-seg-v2` (195, 54); jumlah instance per kelas dari Ultralytics sama dengan tabel di atas (untuk gabung train, Ultralytics membuang label ganda pada beberapa gambar publik, sama seperti v1).

### 4.3 Perubahan di val yang dikerjakan Jeka setelah daftar audit
- 4 pilar dari tahap A dan 4 kerucut ditambah sebagai label kurang: 7 pilar dan 1 orang (`perpus-lt9..._dada_t0004999`, blind). Model menemukan 3 dari 7 pilar baru pada `kotak-gabung` dan 1 pada `kotak-kampus`.
- **Koreksi R6 oleh Jeka (disengaja):** pada `dapsut_02_dada_t0060020` dan `dapsut_02_mata_t0057020`, satu kotak kendaraan lama menutupi dua mobil. Jeka memangkas kotak itu dan menambah satu kotak kendaraan untuk mobil di sebelahnya, sehingga satu objek satu kotak (R6). Jumlah kendaraan val: 108 menjadi 108 (R4 membuang 2, dua kotak hasil pemecahan menambah 2).
- `dapsut_01_dada_t0044026`: polygon `jalur_jalan` digambar ulang (23 titik, satu titik bergeser hingga 80 px, IoU mask v1 vs v2 = 0,988). Perubahan ini dipertahankan (keputusan Jeka). Ini **satu-satunya perubahan label segmentasi**, dan bukan bagian audit; karena itu label seg tidak persis identik dengan v1 (248 dari 249 file identik). Evaluasi segmentasi tidak diulang: perubahannya satu polygon di satu frame val (selisih luas sekitar 1%), di luar tujuan audit.

## 5. Evaluasi ulang bobot yang sama (tanpa retraining)
Bobot: `models/baseline/kotak-gabung_best.pt` dan `kotak-kampus_best.pt`. Val: kampus val v1 (319 instance), v2-noR4 (297), v2 (263). mAP dihitung pada conf 0.001; P, R, F1 pada conf yang memaksimalkan F1 rata-rata kelas; galat pada conf 0.25 dan IoU 0.5 (cara `tools/evaluasi_baseline.py`). Run v1 diulang di `eval-v2/v1/` dan **cocok dengan `runs/baseline/eval/` sampai 4 desimal** (mAP50, mAP50-95, P, R untuk ketiga model), jadi selisihnya murni dari ground truth.

### 5.1 Keseluruhan

**kotak-gabung (kampus + publik)**

| Versi val | n instance | mAP50 | mAP50-95 | P | R | F1 |
|---|---|---|---|---|---|---|
| v1 (asli) | 319 | 0.455 | 0.263 | 0.561 | 0.409 | 0.443 |
| v2-noR4 | 297 | 0.472 | 0.272 | 0.637 | 0.390 | 0.459 |
| v2 (semua) | 263 | 0.498 | 0.296 | 0.621 | 0.434 | 0.483 |
| Selain R4 (v2-noR4 - v1) | | +0.017 | +0.010 | +0.077 | -0.019 | +0.015 |
| **R4 di atas itu (v2 - v2-noR4)** | | +0.026 | +0.023 | -0.016 | +0.044 | +0.024 |
| Total (v2 - v1) | | +0.043 | +0.033 | +0.060 | +0.025 | +0.040 |

**kotak-kampus (kampus saja)**

| Versi val | n instance | mAP50 | mAP50-95 | P | R | F1 |
|---|---|---|---|---|---|---|
| v1 (asli) | 319 | 0.420 | 0.223 | 0.558 | 0.422 | 0.448 |
| v2-noR4 | 297 | 0.435 | 0.232 | 0.570 | 0.438 | 0.464 |
| v2 (semua) | 263 | 0.463 | 0.257 | 0.561 | 0.477 | 0.480 |
| Selain R4 (v2-noR4 - v1) | | +0.015 | +0.009 | +0.012 | +0.015 | +0.016 |
| **R4 di atas itu (v2 - v2-noR4)** | | +0.028 | +0.025 | -0.010 | +0.040 | +0.016 |
| Total (v2 - v1) | | +0.044 | +0.034 | +0.002 | +0.055 | +0.032 |

**Berapa dari perubahan yang berasal dari R4:** pada `kotak-gabung`, R4 menyumbang +0.026 dari total +0.043 mAP50 (61%) dan +0.023 dari +0.033 mAP50-95 (71%). Pada `kotak-kampus`: +0.028 dari +0.044 mAP50 (65%) dan +0.025 dari +0.034 mAP50-95 (74%). Angka ini adalah efek R4 yang ditambahkan **setelah** aturan lain; efek R4 sendirian di atas v1 tidak dijalankan, jadi kontribusi bisa sedikit berbeda menurut urutan. R4 hanya menyentuh val orang (-18), kursi (-14), dan kendaraan (-2).

### 5.2 Per kelas (`kotak-gabung`)

| Kelas | n v1 / noR4 / v2 | mAP50 v1 | mAP50 noR4 | mAP50 v2 | mAP50-95 v1 | mAP50-95 noR4 | mAP50-95 v2 | R v1 | R v2 | Catatan |
|---|---|---|---|---|---|---|---|---|---|---|
| pilar | 50 / 34 / 34 | 0.161 | 0.384 | 0.384 | 0.088 | 0.206 | 0.206 | 0.16 | 0.30 |  |
| pohon | 10 / 10 / 10 | 0.089 | 0.089 | 0.089 | 0.035 | 0.035 | 0.035 | 0.00 | 0.00 | n < 20 di val: angka kurang bisa dipercaya |
| tepian | 45 / 45 / 45 | 0.263 | 0.263 | 0.263 | 0.080 | 0.080 | 0.080 | 0.36 | 0.22 |  |
| orang | 52 / 47 / 29 | 0.605 | 0.581 | 0.690 | 0.365 | 0.375 | 0.472 | 0.54 | 0.64 |  |
| tanaman_pot | 13 / 10 / 10 | 0.554 | 0.492 | 0.492 | 0.301 | 0.251 | 0.251 | 0.31 | 0.30 | n < 20 di val: angka kurang bisa dipercaya |
| kursi | 36 / 36 / 22 | 0.532 | 0.532 | 0.622 | 0.373 | 0.373 | 0.460 | 0.42 | 0.59 |  |
| kendaraan | 108 / 110 / 108 | 0.544 | 0.539 | 0.550 | 0.273 | 0.270 | 0.275 | 0.49 | 0.42 |  |
| tangga | 5 / 5 / 5 | 0.895 | 0.895 | 0.895 | 0.587 | 0.587 | 0.587 | 1.00 | 1.00 | n < 20 di val: angka kurang bisa dipercaya |

### 5.3 Per kelas (`kotak-kampus`)

| Kelas | n v1 / noR4 / v2 | mAP50 v1 | mAP50 noR4 | mAP50 v2 | mAP50-95 v1 | mAP50-95 noR4 | mAP50-95 v2 | R v1 | R v2 | Catatan |
|---|---|---|---|---|---|---|---|---|---|---|
| pilar | 50 / 34 / 34 | 0.108 | 0.226 | 0.226 | 0.031 | 0.070 | 0.070 | 0.08 | 0.15 |  |
| pohon | 10 / 10 / 10 | 0.024 | 0.024 | 0.024 | 0.014 | 0.014 | 0.014 | 0.10 | 0.10 | n < 20 di val: angka kurang bisa dipercaya |
| tepian | 45 / 45 / 45 | 0.289 | 0.289 | 0.289 | 0.093 | 0.093 | 0.093 | 0.36 | 0.32 |  |
| orang | 52 / 47 / 29 | 0.636 | 0.577 | 0.652 | 0.349 | 0.354 | 0.432 | 0.62 | 0.76 |  |
| tanaman_pot | 13 / 10 / 10 | 0.327 | 0.397 | 0.397 | 0.179 | 0.215 | 0.215 | 0.31 | 0.40 | n < 20 di val: angka kurang bisa dipercaya |
| kursi | 36 / 36 / 22 | 0.458 | 0.458 | 0.599 | 0.285 | 0.285 | 0.404 | 0.40 | 0.59 |  |
| kendaraan | 108 / 110 / 108 | 0.521 | 0.514 | 0.524 | 0.242 | 0.231 | 0.236 | 0.52 | 0.50 |  |
| tangga | 5 / 5 / 5 | 0.995 | 0.995 | 0.995 | 0.589 | 0.589 | 0.589 | 1.00 | 1.00 | n < 20 di val: angka kurang bisa dipercaya |

### 5.4 Galat pada conf 0.25 (`kotak-gabung`): TP / FP / FN

| Kelas | v1 | v2-noR4 | v2 |
|---|---|---|---|
| pilar | 8 / 6 / 42 | 11 / 3 / 23 | 11 / 3 / 23 |
| pohon | 0 / 3 / 10 | 0 / 3 / 10 | 0 / 3 / 10 |
| tepian | 14 / 38 / 31 | 14 / 38 / 31 | 14 / 38 / 31 |
| orang | 28 / 9 / 24 | 26 / 11 / 21 | 22 / 15 / 7 |
| tanaman_pot | 2 / 0 / 11 | 2 / 0 / 8 | 2 / 0 / 8 |
| kursi | 17 / 9 / 19 | 17 / 9 / 19 | 14 / 12 / 8 |
| kendaraan | 53 / 41 / 55 | 53 / 41 / 57 | 53 / 41 / 55 |
| tangga | 4 / 2 / 1 | 4 / 2 / 1 | 4 / 2 / 1 |

Recall per ukuran objek (akar luas pada gambar 640):

| Ukuran | v1 | v2-noR4 | v2 |
|---|---|---|---|
| <32 px | 6/48 = 0.12 | 6/48 = 0.12 | 4/24 = 0.17 |
| 32-64 px | 41/125 = 0.33 | 43/112 = 0.38 | 38/102 = 0.37 |
| 64-128 px | 57/112 = 0.51 | 56/104 = 0.54 | 56/104 = 0.54 |
| >=128 px | 22/34 = 0.65 | 22/33 = 0.67 | 22/33 = 0.67 |

Confusion matrix conf 0.25: `runs/baseline/eval-v2/<v1|v2-noR4|v2>/<run>-val-conf025/confusion_matrix.png`. Plot PR/F1: `<run>-val/`. Contact sheet frame terburuk dan terbaik: `<run>/kontak_terburuk.jpg`, `kontak_bagus.jpg`, `kontak_16.jpg`.

### 5.5 Efek samping: deteksi nyata yang kini dihitung FP

| FP pada `kotak-gabung`, conf 0.25 | v1 | v2-noR4 | v2 |
|---|---|---|---|
| orang (semua) | 9 | 11 | 15 |
| orang di bawah ambang R4 (sisi pendek < 96 px) | 2 | 2 | 6 |
| orang di lokasi tangga-naik-lt9-lt10 (dinding kaca) | 4 | 7 | 7 |
| kursi (semua) | 9 | 9 | 12 |
| kursi di bawah ambang R4 | 3 | 3 | 6 |

Model mendeteksi orang di balik kaca dan benda kecil yang memang nyata. Setelah R2 dan R4 menghapus label itu dari ground truth, deteksi tersebut dihitung FP. Jadi sebagian presisi `orang` yang turun adalah harga dari aturannya, bukan kesalahan model yang bertambah. Apakah deteksi seperti itu diinginkan di produk (misalnya orang jauh yang nyata) adalah keputusan produk, bukan metrik.

## 6. Pembacaan jujur
- **Modelnya tidak berubah, hanya ground truth.** Selisih skor adalah selisih cara kita menilai, bukan model yang lebih baik. Jangan dilaporkan sebagai peningkatan model.
- **Pilar: 50 menjadi 34 instance di val, dan kenaikannya adalah koreksi label.** Dari 50 pilar val, 23 dihapus (R1: 17 sirip/kosen dinding kaca dan fasad di `tangga-naik-lt9-lt10` serta fasad logam di dapsut; R7: 6 lampu neon, kaki meja, dan badan gerbang putar), lalu 7 pilar ditambah (kolom dan tiang yang tadinya terlewat, termasuk 4 kerucut). Semua 23 kotak yang dihapus adalah kotak yang tidak pernah ditemukan model di v1 (23 dari 23 FN; sirip fasad dan kosen kaca bukan sesuatu yang bisa dicocokkan sebagai tiang). Karena itu mAP50 pilar `kotak-gabung` naik dari 0.161 menjadi 0.384 dan recall dari 0.16 menjadi 0.30, padahal TP hanya naik dari 8 ke 11 (3 dari 7 label baru). Kenaikan skor pilar terutama koreksi label, bukan model yang lebih pandai mendeteksi tiang. (Pada angka 50 menjadi 27 yang kami sebut saat keputusan: itu sebelum 7 label pilar ditambah.)
- **Bobot dilatih pada label train v1.** Train v1 masih memuat inkonsistensi yang sama (di train yang dihapus: R1 32, R2 1, R4 41, R5 4, R6 6, R7 4, KJ 1). Jadi model belum pernah belajar aturan baru; skor v2 bukan hasil model yang dilatih dengan aturan itu. Melatih ulang di train v2 adalah langkah terpisah dan belum dikerjakan.
- **Kelas dengan sedikit instance tetap berisik.** pohon (n=10), tanaman_pot (n=10 sesudah audit), dan tangga (n=5) di bawah 20 instance; satu seed, satu split lokasi, dan mayoritas instance val berasal dari dapsut. Perubahan kecil di kelas itu jangan dibaca sebagai tren.
- **R4 membuang benda kecil dari penilaian, bukan membuat model bisa mendeteksinya.** Recall objek < 32 px terlihat naik karena pembaginya menyusut (jumlah GT < 32 px turun dari 48 menjadi 24). Benda kecil yang dideteksi model kini dihitung FP (bagian 5.5).
- **R2 membuat model tampak lebih sering salah pada orang di balik kaca.** Model mendeteksi mereka dengan conf tinggi; itu keputusan produk yang perlu dibahas, bukan sekadar urusan label.
- **Orang: mAP50 naik (0.605 menjadi 0.690) tetapi presisi turun (0.78 menjadi 0.63).** Val orang kehilangan 18 GT kecil yang sulit (R4) dan 5 orang di balik kaca (R2), jadi recall naik (0.54 menjadi 0.64), sementara deteksi nyata atas benda itu kini FP (bagian 5.5).

## 7. Kelemahan yang tersisa
- **tepian** (mAP50 0.263, FP 38, FN 31): tidak tersentuh audit. Kerb panjang dilabel per segmen sekitar 270 px, sedangkan model menggambar kotak yang tidak cocok dengan potongan itu (banyak FP berupa serpihan kerb).
- **pohon** (n=10, mAP50 0.089): hampir tidak terdeteksi; terlalu sedikit data untuk menyimpulkan.
- **pilar** masih lemah (recall 0.30): tiang tipis dan jauh serta kolom terpotong di tepi frame.
- **tanaman_pot** (recall 0.30): semak dan planter di tanah sering terlewat.
- **kendaraan** (FP 41, FN 55): kotak gabungan di barisan motor rapat dan kotak yang bergeser; barisan rapat di latar memang tidak dilabel (opsi a).
- **Eskalator terbaca tangga** (R5: eskalator memang tidak dilabel).

## 8. Berkas dan cara mengulang
- Alat: `tools/audit_label_kampus.py` (`--terapkan`, `--uji`), `tools/bangun_dataset_kampus.py` (`--akhiran`, `--json-akar`), `tools/bangun_dataset_gabung.py` (`--akhiran`), `tools/evaluasi_baseline.py` (`--versi-data`), `tools/validasi_pilot_v2.py` (kini menerima shape `rectangle`).
- Bukti audit: `data/audit-kampus/` (kandidat.csv, ringkasan.md, catatan-review.md, final_usulan.csv, diterapkan.csv, sebelum_sesudah/). Cadangan label asli: `data/pilot-v2-tune/sebelum-audit/`.
- Dataset: `data/dataset-kampus-kotak-v2`, `data/dataset-kampus-seg-v2`, `data/dataset-gabung-kotak-v2`, `data/dataset-gabung-seg-v2`, dan `data/dataset-kampus-kotak-v2-noR4` (varian tanpa R4, hanya untuk val). Dataset lama tidak diubah.
- Hasil evaluasi: `runs/baseline/eval-v2/{v1,v2-noR4,v2}/`.

Mengulang:
```
python tools/bangun_dataset_kampus.py --akhiran=-v2
python tools/bangun_dataset_gabung.py --akhiran=-v2 --oversample 4 --cap trotoar=700 --cap unstructured=600 --cap ood=600 --cap rod=400 --seed 20261110 --skip-nested 0.8 --skip-lintas-iou 0.5
python tools/evaluasi_baseline.py --versi-data=-v2 --out runs/baseline/eval-v2/v2 --aksi val
python tools/evaluasi_baseline.py --versi-data=-v2 --out runs/baseline/eval-v2/v2 --aksi cm025
```
