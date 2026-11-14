# Test set JalanKu

Status: label final, tidak ada keputusan yang menunggu. Dibuat 11 November 2026, terakhir diubah 12 November 2026 (R6, dua duplikat tepian dan satu duplikat orang dihapus).

Test set dipakai **satu kali** di akhir, untuk membandingkan model baseline dan model ronde 2 bersama-sama. Tidak dipakai untuk memilih pengaturan, ambang, atau checkpoint.

## Mengapa lokasi ini
Tiga lokasi test (`selasar-lt11-ubm-tower`, `pot-lt11-ubm-tower`, `taman-ubm`) tidak muncul di data training maupun validasi kampus (15 lokasi pilot), jadi ini ukuran generalisasi ke tempat yang belum pernah dilihat model. Lantai 11 mewakili dalam gedung (selasar, koridor dengan pot, pintu kaca), taman-ubm mewakili luar gedung (plaza paving, pot besar, kolom, bangku, kerb, pohon, jalan kendaraan di kejauhan). Tiap lokasi direkam dua sudut pandang, dada dan mata (POV).

## Pemilihan frame
Dari 360 frame yang tersedia dipilih 91 frame (90 + 1 top-up), deterministik tanpa acak. Skrip: `tools/pilih_frame_test.py`; daftar: `data/test-review/daftar_test.csv`.
- Jatah: selasar dada 11 / mata 11, pot-lt11 dada 12 / mata 11 (lantai 11 = 45); taman-ubm dada 23 / mata 23 (termasuk 1 top-up) = 46.
- Garis waktu tiap video dibagi n slot, satu frame per slot. Pusat slot digeser -1/4 slot (dada) dan +1/4 slot (mata) supaya dada dan mata tidak memilih detik yang sama. Jarak minimal 3,0 detik antar frame satu video.
- Buram: variansi Laplacian (gambar 540x960 abu-abu) < 0,5 x median tetangga (+-5 detik) atau < 15; 55 frame buram dikeluarkan dari kandidat. Duplikat: jarak Hamming pHash 64 bit <= 6 (jarak terkecil antar terpilih: 10).
- Pemilihan hanya memakai timestamp, Laplacian, dan pHash. Tidak ada model yang dijalankan di frame test, termasuk model kita.

**Top-up kelas lemah:** dengan jarak 3 detik hanya 2 frame sisa yang memenuhi syarat. Satu ditambah (`taman-ubm ... mata_t0000000`, alasan "top-up: pohon"), satu tidak (tidak memuat kelas lemah). Kursi, kendaraan, tangga, dan jalan_kendaraan tidak bisa diisi.

## Cara pelabelan
1. **Auto-label** dengan pipeline pilot (`tools/autolabel_v2.py --izin-test`): SegFormer ADE20K, YOLO11x-seg COCO, Grounding DINO, SAM 2.1. `taman-ubm` diperlakukan sebagai lokasi luar (tuple baru di `LOKASI_LUAR`, tidak mengubah perilaku lokasi training). Tidak ada model hasil training kita yang dipakai.
2. **Cek mekanis sebelum review** (`tools/cek_test_set.py`): 9 shape melanggar R4 dihapus, 0 duplikat, 0 titik di luar gambar.
3. **Review manusia penuh** oleh Jeka di X-AnyLabeling: semua 91 frame, semua kelas, kotak dan permukaan. 17 frame yang sempat tidak tersimpan diperiksa ulang, 12 di antaranya berubah (turnstile dihapus, orang dan tepian ditambah).
4. **R4 diterapkan apa adanya** sesudah review, tanpa pengecualian, seperti di val: 28 shape dibuang (orang 19, tanaman_pot 8, kendaraan 1). Daftar di `data/test-review/r4_dibuang.csv`.
5. Salinan auto mentah disimpan tidak tersentuh di `data/test-review-auto-backup/` untuk mengukur kualitas auto-label.

Versi aturan: [kelas.md](kelas.md) **v1.7**. Auto-label dijalankan dengan pipeline yang disetel untuk v1.6; keputusan v1.7 (ambang jendela = tepian, bangku = kursi, pohon di planter bulat = tanaman_pot, kerb beda tinggi = tepian, gagang dan kusen pintu tidak dilabel, orang terpotong tepi frame dilabel) diterapkan lewat review manual.

Tiga shape tepian di ambang jendela rendah (`pot-lt11 dada_t0001000` satu, `dada_t0004032` dua) sempat terhapus lalu dikembalikan dari backup auto sesuai keputusan v1.7.

**R6 (12 November 2026):** tiga shape duplikat dihapus, kelas lain tidak berubah. Tepian di `taman-ubm_2026-11-07_01_dada_t0054000`: (1) shape ke-2, polygon 4 titik hasil auto, IoU 0,92 dengan shape ke-3 hasil rapian; (2) polygon auto 15 titik (description `auto-v2 gdino+sam 0.46`, bbox 816,690 sampai 1025,724), 98% memuat polygon rapi 91 titik (bbox 834,697 sampai 964,723) yang dipertahankan. Orang di `pot-lt11-ubm-tower_2026-10-30_01_mata_t0041029`: (3) polygon 28 titik (`auto-v2 yolo 0.48`, bbox 710,620 sampai 917,998), potongan dari orang yang sama dengan shape bbox 711,464 sampai 919,1224 yang dipertahankan. Tepian 53 jadi 51, orang 33 jadi 32 (lantai 11 20 jadi 19), total kotak 240 jadi 237. **Sengaja dibiarkan:** dua pasang tanaman_pot yang bertumpuk di `taman-ubm_2026-11-07_01_mata_t0000000` dan `taman-ubm_2026-11-07_01_mata_t0006999` sudah dicek dan ternyata objek yang berbeda, jadi tidak dihapus. Dataset kotak dan seg dibangun ulang dan tabel jumlah dan kualitas auto dihitung ulang tiap kali. JSON dan dataset sebelum tiap penghapusan ada di `data/test-review-aux/_sebelum-hapus-duplikat-r6/`, `_sebelum-hapus-duplikat-r6b/`, dan `_sebelum-hapus-duplikat-r6c/` (berurutan untuk penghapusan 1 sampai 3). Kedua model belum pernah dievaluasi di test set, jadi tidak ada hasil lama yang perlu diulang.

## Dataset
Konversi dan urutan kelas sama dengan dataset kampus v2 (`tools/bangun_dataset_kampus.py`). Skrip: `tools/bangun_dataset_test.py`. Semua shape tangga satu frame digabung jadi satu kotak; kotak dari titik polygon atau rectangle.
- `data/dataset-test-kotak/` (YOLO detect, 8 kelas): `images/test`, `labels/test`, `data.yaml` dengan `test:`.
- `data/dataset-test-seg/` (YOLO segment, 3 kelas): struktur sama.
- `train:` dan `val:` di YAML menunjuk folder yang sama hanya karena Ultralytics 8.4.x menolak YAML tanpa keduanya. **Jangan dipakai untuk melatih.**
- Validasi `YOLODataset`: 91 gambar, 0 korup, label txt = instance yang dibaca Ultralytics (kotak 237, seg 112).

### Jumlah instance (setelah R4)
| Kelas | Total | Lantai 11 | taman-ubm | Frame yang memuat |
|---|---|---|---|---|
| pilar | 38 | 7 | 31 | 29 |
| pohon | 3 | 0 | 3 | 2 |
| tepian | 51 | 30 | 21 | 21 |
| orang | 32 | 19 | 13 | 21 |
| tanaman_pot | 99 | 28 | 71 | 51 |
| kursi | 14 | 0 | 14 | 14 |
| kendaraan | **0** | 0 | 0 | 0 |
| tangga | **0** | 0 | 0 | 0 |
| jalur_jalan (seg) | 96 | 47 | 49 | 89 |
| jalan_kendaraan (seg) | 16 | 0 | 16 | 9 |
| tangga (seg) | **0** | 0 | 0 | 0 |

Kotak: 237 instance di 91 gambar (14 gambar tanpa objek kotak = background). Seg: 112 polygon (2 gambar tanpa permukaan).

## Kualitas auto-label (auto mentah vs label akhir Jeka)
Kotak cocok kalau IoU >= 0,5 (satu-satu, greedy). R4 diterapkan ke kedua sisi sebelum dibandingkan. File: `data/test-review/kualitas_auto.csv`, `kualitas_auto_edit.csv`; skrip `tools/kualitas_auto_test.py`.

| Kelas | GT | Auto | Precision | Recall | sama / diedit / dihapus / ditambah |
|---|---|---|---|---|---|
| pilar | 38 | 86 | 0,37 | 0,84 | 31 / 2 / 53 / 5 |
| pohon | 3 | 19 | 0,16 | 1,00 | 2 / 1 / 16 / 0 |
| tepian | 51 | 171 | 0,26 | 0,86 | 40 / 5 / 126 / 6 |
| orang | 32 | 45 | 0,60 | 0,84 | 22 / 5 / 18 / 5 |
| tanaman_pot | 99 | 106 | 0,63 | 0,68 | 36 / 31 / 39 / 32 |
| kursi | 14 | 4 | 0,00 | 0,00 | 0 / 0 / 4 / 14 |
| kendaraan | 0 | 3 | - | - | 0 / 0 / 3 / 0 |

| Permukaan (mask piksel) | IoU | Precision | Recall |
|---|---|---|---|
| jalur_jalan | 0,90 (lantai 11 0,88, taman 0,92) | 0,93 | 0,97 |
| jalan_kendaraan | 0,00 (auto tidak menghasilkan satu pun; 16 polygon ditambah manual) | - | 0,00 |

Ringkasan: auto menangkap sebagian besar objek (recall 0,84 sampai 1,0 untuk pilar, pohon, tepian, orang) tetapi menghasilkan banyak positif palsu (precision pilar 0,37, tepian 0,26, pohon 0,16), terutama tepian di taman. Kursi (bangku beton/kayu) dan jalan_kendaraan sama sekali tidak ditemukan auto. tanaman_pot paling sering diedit (31 dari 99 diedit bentuknya, 32 ditambah). Jalur_jalan sudah baik. Catatan: "dihapus" dan "ditambah" menghitung shape mentah, shape yang ditambah lalu dibuang karena R4 tidak ikut dihitung.

## Keterbatasan
- **kendaraan dan tangga: 0 instance** di kotak, dan tangga 0 di seg. Test set ini tidak bisa mengukur dua kelas itu. Satu motor di taman (93x67) dibuang oleh R4. Hasil pada kelas tersebut harus dibaca dari validasi, bukan test.
- Kelas kecil: pohon 3, kursi 14 (semuanya di taman-ubm), orang 32. mAP per kelas untuk kelas-kelas ini sangat berisik. jalan_kendaraan 16 polygon di 9 frame taman saja.
- Hanya dua lokasi (lantai 11 dan taman-ubm), satu hari rekaman per lokasi. Cuaca, pencahayaan, dan jenis permukaan terbatas. Lantai 11 hanya punya jalur_jalan, tanaman_pot, tepian, orang, pilar.
- Distribusi miring: tanaman_pot 99 dari 237 kotak, 71 di antaranya taman-ubm.
- R4 membuang banyak orang kecil di selasar (15) dan 8 tanaman_pot di taman; test set tidak menilai objek jauh.
- Flag `perlu_cek` dari auto masih ada di banyak JSON (tidak dibersihkan); tidak mempengaruhi dataset.
- Auto-label dijalankan dengan pipeline untuk aturan v1.6, review manual memakai v1.7 (lihat di atas).

## Kebocoran lokasi taman-ubm ke data latih (ditemukan 14 November 2026)
Saat review ronde 2, Jeka menemukan frame latih yang memperlihatkan area taman-ubm. Frame test sendiri tidak pernah masuk data latih, tetapi **tempat yang sama** terekam di video lokasi lain. Dicek ulang dengan embedding generik (ResNet50 ImageNet, bukan model kita; `tools/ronde2_cek_bocor.py`, hasil `data/ronde2/bocor/`) terhadap 195 frame train v2 dan semua frame ronde 2. Kontrol positif (frame yang ditemukan Jeka) ada di peringkat 7 dari 265.

Frame yang dikeluarkan (daftar lengkap: `data/ronde2/bocor/dikeluarkan.csv`, dipakai sebagai daftar pengecualian oleh `tools/bangun_dataset_ronde2.py`):

| Frame | Asal | Alasan |
|---|---|---|
| tangga-naik-alfa-lt2 dada t=0, 4, 8, 15 s; mata t=2, 3, 7, 11 s (8 frame) | train v2 (baseline) | awal video direkam di depan Maxx Coffee, area yang sama dengan taman-ubm (pilar marmer, lantai, kafe) |
| jalanan-ubm mata t=6, 18 s; dada t=87, 102 s (4 frame) | train v2 (baseline) | kemungkinan plaza drop-off yang sama (kanopi, deretan pot putih) |
| lorong-lt3-eskalator-alfa-tower mata t=210 s | ronde 2 | taman-ubm terlihat lewat kaca (temuan review) |
| jalanan-ubm dada t=97 s; mata t=3, 12 s | ronde 2 | kemungkinan plaza drop-off yang sama |

Dampak:
- **Baseline lama (`models/baseline/*`) dilatih dengan 12 frame bocor itu**, dan di `dataset-gabung-kotak(-v2)` setiap frame kampus di-oversample x4, jadi 48 dari 3.080 gambar latih model kotak (1,6%) berasal dari frame bocor. Model seg baseline (kampus saja, tanpa oversample) memuat 12 dari 195 frame latih. Baseline **tidak dilatih ulang** (keputusan Jeka).
- Akibatnya pada perbandingan test final, angka **baseline di taman-ubm kemungkinan sedikit terlalu optimis** (model pernah melihat tempat itu, walau dari frame lain). Model ronde 2 (`v2bersih`, `v3`) dilatih tanpa frame ini, jadi perbandingan baseline vs ronde 2 di taman-ubm **berat sebelah, menguntungkan baseline**. Kalau ronde 2 tetap lebih baik di taman-ubm, kesimpulan itu aman; kalau baseline lebih baik di taman-ubm saja, sebagian bisa karena kebocoran. Angka lantai 11 tidak terkena.
- Lokasi val (dapsut, perpus-lt9, tangga-naik-lt9-lt10) tidak terkait; perbandingan di val tidak terpengaruh.
- Cek ini hanya menangkap kemiripan visual. Frame latih lain dari lokasi luar UBM (halaman, samping, jalanan) yang memperlihatkan taman-ubm dari jauh mungkin masih ada; daftar urut kemiripan di `data/ronde2/bocor/skor.csv`.

## Protokol
1. Test set tidak masuk folder training, validasi, atau cache latihan mana pun. Dicek: 0 file frame test di `data/` di luar folder test.
2. Model dievaluasi di test set **hanya sekali**, baseline dan model ronde 2 bersama-sama, setelah semua pengaturan ronde 2 dikunci.
3. Tidak ada tuning (ambang konfidensi, NMS, pilihan checkpoint, augmentasi) berdasarkan hasil test.
4. Kalau test set diubah (label atau frame), tulis versi baru di dokumen ini dan evaluasi ulang kedua model bersama.
5. Model kita belum pernah dijalankan di frame test (termasuk untuk pra-label atau memilih frame). Pengecualian yang tercatat: cek kebocoran 14 Nov 2026 menjalankan ResNet50 ImageNet generik (bukan model JalanKu) pada frame mentah taman-ubm, atas izin Jeka, hanya untuk mencari frame latih yang bocor.

## Berkas
`data/test-review/` (91 gambar + 91 JSON, `daftar_test.csv`, `LOG.md`, `kualitas_auto*.csv`, `r4_dibuang.csv`), `data/test-review-auto-backup/`, `data/test-review-aux/` (sheet, cache, cadangan sebelum perubahan), `data/dataset-test-kotak/`, `data/dataset-test-seg/`. Semua di bawah `data/` (di-gitignore). Alat: `tools/pilih_frame_test.py`, `tools/cek_test_set.py`, `tools/buat_review_list.py`, `tools/validasi_test_set.py`, `tools/kualitas_auto_test.py`, `tools/bangun_dataset_test.py`.
