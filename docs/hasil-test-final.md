# Hasil Test Final JalanKu

Status: 15 November 2026. Semua angka dari run sebenarnya (`data/test-final/t1/*.json`, `runs/test-final/`, log `data/test-final/LOG.md`). Test set dievaluasi **satu kali** per model, sesudah model final, ambang, dan cara mengukur dikunci dari val. Folder `data/`, `runs/`, `models/` tidak masuk Git.

## Ringkasan

- Di lokasi yang belum pernah dilihat (lantai 11 dan taman-ubm, 91 frame, 237 kotak) semua model turun kira-kira setengah dari angka val. Model kotak final (ensemble C2) turun dari mAP50 0,613 di val ke **0,305** di test, F1 dari 0,583 ke 0,308.
- C2 tetap yang tertinggi di test pada mAP50 (0,305) dan mAP50-95 (0,172), tetapi jaraknya ke model tunggal terbaik (`r4-kotak-v3-1280`: 0,292 / 0,160, F1 0,315) lebih kecil daripada margin derau 0,034. Keunggulan C2 di val sebagian adalah keberuntungan memilih (lihat bagian 7).
- Pada pengaturan app (ambang per kelas terkunci): C2 menemukan 77 dari 237 objek, 103 kotak salah, **1,13 kotak salah per frame** (lantai 11: 0,13; taman-ubm: 2,11). Recall objek dekat 21/68.
- Peringatan tingkat frame ("ada rintangan dekat di tengah"): C2 **tidak pernah salah memperingatkan** di 48 frame tanpa rintangan, tetapi melewatkan 14 dari 43 frame yang ada rintangannya (recall 0,67).
- Kelas yang gagal di test: `kursi` 0 dari 14 (bangku beton dan kayu di taman), `tepian` dekat 0 dari 22, `jalan_kendaraan` (seg) IoU 0,03. `kendaraan` dan `tangga` tidak ada di test, jadi hanya bisa dibaca dari val.
- Segmentasi `jalur_jalan` tetap baik (IoU piksel 0,81), tetapi model seg final tidak lebih baik dari baseline di test (baseline 0,86).
- Baseline diuntungkan di taman-ubm (kebocoran 12 frame latih) dan tetap yang terburuk di sana; kesimpulan "model ronde 2 ke atas lebih baik dari baseline" aman.

## 1. Protokol

1. Model final dan semua ambang dikunci dari **val v2 saja (54 frame)** sebelum ada satu pun angka test. Baris kunci ada di paling atas `data/test-final/LOG.md`.
2. Aturan pemilihan tiap ronde ditulis ke LOG **sebelum** hasil ronde itu ada (`[R3-3]`, `[R4-ATURAN]`, `[ENS-ATURAN]`, `[ENS-KEC-PROTOKOL]`).
3. Cara mengukur T1 ditulis sebelum test disentuh (`[T1-ATURAN]`) dan jalur kodenya (`tools/test_t1.py`) dijalankan dulu di val. Semua angka val yang sudah tercatat keluar persis sama (`[T1-UJI-VAL]`), baru sesudah itu test dijalankan sekali. Tidak ada run ulang.
4. Tidak ada model, ambang, label, atau config yang diubah sesudah test. Isi gambar dan label test sama sebelum dan sesudah (SHA-256).
5. Contact sheet test dibuat sesudah semua angka tersimpan.

Model final:

| | Model | Pengaturan |
|---|---|---|
| Kotak | **C2** = WBF per kelas dari 4 model: `r2-kotak-v3-960`, `r4-kotak-v3-960-seed1`, `r4-kotak-v4-960` (imgsz 960), `r4-kotak-v3-1280` (imgsz 1280) | IoU WBF 0,55; conf klaster = rata-rata atas 4 model; conf anggota di app 0,05 |
| Seg | `r2-seg-v3` (imgsz 640) | conf 0,25 |

Ambang per kelas terkunci untuk C2 (dari val, `ambang_val_ens.json`): pilar 0,25; pohon 0,25; tepian 0,20; orang 0,60; tanaman_pot 0,25; kursi 0,25; kendaraan 0,10; tangga 0,25. Ambang diturunkan dengan conf anggota 0,001; pada 0,05 TP, FN, dan recall dekat val identik dan FP 6 lebih rendah (82 jadi 76). Pengaturan app: `data/test-final/config_saran.yaml`.

Cara mengukur:

- **mAP50, mAP50-95, AP50 per kelas, F1**: satu jalur kode untuk semua model kotak (`tools/ensemble_val.py`, prediksi conf 0,001, pencocokan dan `ap_per_class` Ultralytics). Untuk C2, conf anggota 0,001 lalu WBF. F1 = rata-rata F1 per kelas pada satu conf global terbaik. Model tunggal juga punya tabel Ultralytics `val()` (lampiran); C1 dan C2 tidak, karena `val()` tidak bisa WBF.
- **Metrik berambang** (TP/FP/FN, recall dekat, FP per frame, class-agnostic, peringatan tingkat frame): dari prediksi conf 0,05 (pengaturan app; C2 conf anggota 0,05 lalu WBF). Cocok = kelas sama dan IoU >= 0,5. Dilaporkan pada conf 0,25 seragam untuk semua model, dan pada ambang terkunci untuk C2 dan `r2-kotak-v3-960` (final sebelumnya, dengan ambangnya sendiri).
- **Dekat** = tepi bawah kotak GT y2 >= 0,65 x tinggi gambar.
- **Class-agnostic** = semua 8 kelas dianggap satu kelas "rintangan".
- **Peringatan tingkat frame** = frame positif kalau ada kotak dekat (y2 >= 0,65) yang tumpang tindih dengan pita tengah x 0,33 sampai 0,67. Dibandingkan antara GT dan prediksi per frame.

## 2. Ronde 3 dan 4, ensemble/TTA, dan aturan pemilihan (semua di val)

| Langkah | Kandidat | Aturan (ditulis dulu) | Hasil di val | Keputusan |
|---|---|---|---|---|
| Ronde 3 | `r3-kotak-v3-960-s` (yolo26s) | F1 tabel >= n + 0,02; GPU <= 30 ms; recall dekat tidak turun | F1 0,482 vs 0,532 (gagal); GPU 10,9 ms; dekat 39/72 vs 33/72 | tetap `r2-kotak-v3-960` |
| Ronde 4, seed | `r4-kotak-v3-960-seed1` (sama persis, seed 1) | dipakai untuk mengukur derau | F1 0,498 vs 0,532 | margin derau **d = 0,034** |
| Ronde 4, 1280 | `r4-kotak-v3-1280` | F1 >= 0,532 + d | F1 0,536 (+0,004, gagal) | tidak dipilih; v4-1280 tidak dilatih |
| Ronde 4, data v4 | `r4-kotak-v4-960` (142 frame kampus baru, kampus 391 frame) | F1 >= 0,532 + d; dekat >= 33/72 | F1 0,507; dekat 27/72 (gagal dua-duanya) | tidak dipilih |
| Ronde 4, seg | `r4-seg-v4` | mask mAP50 >= 0,657; recall >= 0,606 | 0,642; 0,593 (gagal) | tetap `r2-seg-v3` |
| TTA | C1 = `r2-kotak-v3-960` + `augment=True` | F1 >= r2 + 0,034 (jalur sama); dekat >= r2; GPU <= 60 ms | F1 0,477 vs 0,516; GPU 64 ms (gagal) | tidak dipilih |
| Ensemble | C2 = WBF 4 model | sama | F1 0,583 (lolos, batas 0,550); dekat 34/72 (lolos); GPU lihat bawah | **dipilih** |

Margin derau: dua training identik yang hanya berbeda seed berselisih F1 0,034 di val. Selisih di bawah itu tidak dianggap perbaikan. Dengan ukuran ini, ronde 3 dan seluruh ronde 4 (resolusi 1280, 142 frame kampus tambahan) **tidak menghasilkan perbaikan yang terukur** pada model tunggal.

Protokol kecepatan C2: pengukuran pertama (laptop mode Balance, banyak aplikasi) memberi 80,5 ms per frame, di atas batas 60 ms. Jeka memutuskan pengukuran ulang **satu kali dan mengikat** dengan kondisi yang ditulis dulu (charger, mode Performance, laptop diam 5 menit, metode sama dengan `kecepatan.json`). Hasil: C2 ujung ke ujung median **49,5 ms** (model 48,4 + WBF 0,8; p95 56,6 ms); `r2-kotak-v3-960` sendiri 10,6 ms. Lolos. Penyimpangan tercatat: beberapa jendela aplikasi masih terbuka (hanya bisa memperlambat). Ini kecepatan GPU laptop (RTX 4060), bukan HP dan bukan server app; C2 sekitar 4,7 kali lebih lambat dari satu model.

## 3. Hasil kotak di test (91 frame, 237 kotak)

Tabel utama, semua model, satu jalur kode. Metrik berambang pada conf 0,25 seragam.

| Model | mAP50 | mAP50-95 | F1 | TP/FP/FN | FP per frame | Recall dekat | Recall sisanya |
|---|---|---|---|---|---|---|---|
| baseline-kotak | 0,209 | 0,120 | 0,239 | 66/145/171 | 1,59 | 14/68 | 52/169 |
| r2-kotak-v2bersih | 0,244 | 0,153 | 0,280 | 80/119/157 | 1,31 | 24/68 | 56/169 |
| r2-kotak-v3 | 0,237 | 0,131 | 0,278 | 74/120/163 | 1,32 | 24/68 | 50/169 |
| r2-kotak-v3-960 | 0,231 | 0,125 | 0,294 | 71/123/166 | 1,35 | 18/68 | 53/169 |
| r3-kotak-v3-960-s | 0,243 | 0,138 | 0,279 | 81/153/156 | 1,68 | 21/68 | 60/169 |
| r4-kotak-v3-960-seed1 | 0,280 | 0,144 | 0,273 | 83/150/154 | 1,65 | 22/68 | 61/169 |
| r4-kotak-v3-1280 | 0,292 | 0,160 | **0,315** | 95/136/142 | 1,49 | 20/68 | 75/169 |
| r4-kotak-v4-960 | 0,237 | 0,140 | 0,275 | 66/114/171 | 1,25 | 19/68 | 47/169 |
| C1 (TTA) | 0,236 | 0,135 | 0,279 | 84/181/153 | 1,99 | 23/68 | 61/169 |
| **C2 (final)** | **0,305** | **0,172** | 0,308 | 80/111/157 | **1,22** | 22/68 | 58/169 |

Bacaan:
- Semua model ronde 2 ke atas di atas baseline; C2 +0,096 mAP50 dari baseline.
- Antara model ronde 2 sampai 4 dan C2, sebagian besar selisih ada di dalam derau (d = 0,034 di val; di test 91 frame deraunya tidak lebih kecil). Yang cukup jelas hanya: baseline paling rendah, C2 dan `r4-kotak-v3-1280` paling tinggi.
- `r2-kotak-v3-960` (final sebelum ensemble), yang unggul di val, di test tidak lebih baik dari model 640 px.
- TTA (C1) menambah kotak salah tanpa menaikkan mAP, sama seperti di val.

### C2 pada pengaturan app (ambang terkunci)

| Subset | Frame | TP/FP/FN | Precision | Recall | FP per frame | Recall dekat | Frame TP/FP/FN/TN | Frame P | Frame R |
|---|---|---|---|---|---|---|---|---|---|
| semua | 91 | 77/103/160 | 0,428 | 0,325 | 1,13 | 21/68 (0,31) | 29/0/14/48 | 1,00 | 0,67 |
| lantai 11 | 45 | 37/6/47 | 0,860 | 0,440 | 0,13 | 12/36 (0,33) | 12/0/5/28 | 1,00 | 0,71 |
| taman-ubm | 46 | 40/97/113 | 0,292 | 0,261 | 2,11 | 9/32 (0,28) | 17/0/9/20 | 1,00 | 0,65 |
| dada | 46 | 38/45/81 | 0,458 | 0,319 | 0,98 | 11/34 (0,32) | 14/0/7/25 | 1,00 | 0,67 |
| mata | 45 | 39/58/79 | 0,402 | 0,331 | 1,29 | 10/34 (0,29) | 15/0/7/23 | 1,00 | 0,68 |

Pembanding, `r2-kotak-v3-960` pada ambangnya sendiri, semua frame: 67/124/170, FP per frame 1,36, dekat 16/68, frame 21/1/22/47 (recall 0,49). C2 lebih baik di setiap kolom.

- **Dalam gedung (lantai 11)**: sedikit kotak salah (6 di 45 frame), tetapi lebih dari separuh objek terlewat.
- **Luar gedung (taman-ubm)**: dua kotak salah per frame dan recall 0,26. Ini lingkungan tersulit bagi model.
- **Dada vs mata**: tidak ada beda yang berarti.

### Per kelas, C2 pada ambang terkunci

| Kelas | Ambang | n test | TP | FP | FN | P | R | Dekat | AP50 test | AP50 val |
|---|---|---|---|---|---|---|---|---|---|---|
| pilar | 0,25 | 38 | 15 | 9 | 23 | 0,63 | 0,39 | 5/7 | 0,463 | 0,488 |
| pohon * | 0,25 | 3 | 2 | 18 | 1 | 0,10 | 0,67 | 0/0 | 0,223 | 0,126 |
| tepian | 0,20 | 51 | 11 | 20 | 40 | 0,36 | 0,22 | **0/22** | 0,147 | 0,630 |
| orang | 0,60 | 32 | 13 | 5 | 19 | 0,72 | 0,41 | 1/3 | 0,567 | 0,787 |
| tanaman_pot | 0,25 | 99 | 36 | 48 | 63 | 0,43 | 0,36 | 15/25 | 0,405 | 0,564 |
| kursi * | 0,25 | 14 | **0** | 1 | 14 | 0,00 | 0,00 | 0/11 | 0,028 | 0,690 |
| kendaraan | 0,10 | 0 | 0 | 1 | 0 | - | - | - | - | 0,621 |
| tangga | 0,25 | 0 | 0 | 1 | 0 | - | - | - | - | 0,995 |

\* n < 20, angka sangat berisik. `kendaraan` dan `tangga` tidak punya instance di test: hanya angka val yang ada, dan angka val itu optimis (lihat bagian 7).

- **Bertahan**: pilar (AP50 hampir sama dengan val), orang dengan precision 0,72.
- **Turun tajam**: tepian (0,63 jadi 0,15; kerb dan ambang jendela di lokasi baru, dan tidak satu pun dari 22 tepian dekat ditemukan), kursi (bangku beton dan kayu taman tidak dikenali sama sekali; dugaan, belum diperiksa: data latih kebanyakan berisi kursi dalam gedung).
- **Banyak alarm palsu**: tanaman_pot (48 FP) dan pohon (18 FP untuk 3 pohon), hampir semuanya di taman.
- Recall per ukuran (px skala 640): < 32: 7/23; 32-64: 17/57; 64-128: 20/69; >= 128: 33/88. Objek besar pun hanya ditemukan 38%, jadi masalahnya bukan hanya objek kecil.

### Dua metrik tambahan (semua frame, conf 0,25 seragam)

| Model | Agnostik mAP50 | Agnostik TP/FP/FN | Frame TP/FP/FN/TN | Frame P | Frame R |
|---|---|---|---|---|---|
| baseline-kotak | 0,229 | 71/140/166 | 22/2/21/46 | 0,92 | 0,51 |
| r2-kotak-v2bersih | 0,293 | 83/116/154 | 27/3/16/45 | 0,90 | 0,63 |
| r2-kotak-v3 | 0,294 | 77/117/160 | 28/1/15/47 | 0,97 | 0,65 |
| r2-kotak-v3-960 | 0,246 | 74/120/163 | 22/1/21/47 | 0,96 | 0,51 |
| r3-kotak-v3-960-s | 0,281 | 82/152/155 | 27/1/16/47 | 0,96 | 0,63 |
| r4-kotak-v3-960-seed1 | 0,289 | 87/146/150 | 28/2/15/46 | 0,93 | 0,65 |
| r4-kotak-v3-1280 | **0,343** | 98/133/139 | 24/2/19/46 | 0,92 | 0,56 |
| r4-kotak-v4-960 | 0,271 | 68/112/169 | 24/1/19/47 | 0,96 | 0,56 |
| C1 (TTA) | 0,267 | 88/177/149 | 32/2/11/46 | 0,94 | **0,74** |
| C2 (final) | 0,257 | 83/108/154 | 27/0/16/48 | **1,00** | 0,63 |

- Mengabaikan kelas hampir tidak menolong (C2: 83 TP agnostik vs 80 per kelas). Jadi kegagalan di test adalah **objek tidak terdeteksi atau kotaknya meleset**, bukan salah kelas.
- Pada mAP class-agnostic C2 bukan yang terbaik (0,257; `r4-kotak-v3-1280` 0,343). Keunggulan C2 ada di skor per kelas dan di sedikitnya kotak salah.
- Peringatan tingkat frame jauh lebih baik daripada angka per kotak: precision 0,90 sampai 1,00 di semua model. C2 pada ambang terkunci: 29 benar, 0 salah, 14 terlewat. Untuk app, "ada sesuatu di depan" lebih bisa dipercaya daripada "itu benda apa".

## 4. Hasil segmentasi di test (91 frame, 112 polygon)

| Model | mask mAP50 | mAP50-95 | P | R | IoU piksel jalur_jalan | IoU piksel jalan_kendaraan |
|---|---|---|---|---|---|---|
| baseline-seg | 0,439 | 0,366 | 0,460 | 0,414 | **0,864** | 0,016 |
| **r2-seg-v3 (final)** | 0,461 | 0,362 | 0,516 | 0,449 | 0,809 | 0,028 |
| r4-seg-v4 | 0,453 | 0,350 | 0,487 | 0,438 | 0,781 | 0,001 |

- `jalur_jalan` (96 polygon): mask mAP50 0,86 sampai 0,89 dan IoU piksel 0,78 sampai 0,86 di ketiga model. Ini bagian yang paling bisa diandalkan di lokasi baru.
- `jalan_kendaraan` (16 polygon, 9 frame taman): gagal di semua model (IoU <= 0,03). mAP rata-rata rendah karena kelas ini.
- `tangga`: 0 di test.
- Model final **tidak lebih baik dari baseline** di test: mAP50 +0,02 (di bawah derau), IoU piksel jalur_jalan 0,05 lebih rendah. Di val urutannya terbalik (0,684 vs 0,635).
- IoU jalur_jalan `r2-seg-v3` per subset: lantai 11 0,788; taman-ubm 0,830; dada 0,763; mata 0,859.

## 5. Val vs test, model final

| | Val (54 frame) | Test (91 frame) |
|---|---|---|
| C2 mAP50 / mAP50-95 / F1 | 0,613 / 0,363 / 0,583 | 0,305 / 0,172 / 0,308 |
| C2 class-agnostic mAP50 | 0,533 | 0,257 |
| C2 ambang terkunci, TP/FP/FN | 150/76/113 | 77/103/160 |
| C2 precision / recall | 0,664 / 0,570 | 0,428 / 0,325 |
| C2 FP per frame | 1,41 | 1,13 |
| C2 recall dekat | 38/72 (0,53) | 21/68 (0,31) |
| C2 peringatan frame TP/FP/FN/TN | 19/3/1/31 (R 0,95) | 29/0/14/48 (R 0,67) |
| r2-seg-v3 mask mAP50 / P / R | 0,647 / 0,868 / 0,606 | 0,461 / 0,516 / 0,449 |
| r2-seg-v3 IoU piksel jalur_jalan | 0,684 | 0,809 |

Skor kotak di lokasi baru kira-kira **setengah** dari val. Penyebab yang bisa dibedakan: (a) lokasi baru (lokasi val juga tidak ada di data latih, tetapi test adalah lokasi dan jenis tempat yang lain lagi), (b) susunan kelas berbeda (test didominasi tanaman_pot dan tepian, tanpa kendaraan dan tangga yang tinggi di val), (c) model dan ambang dipilih di val. Rata-rata kelas di val dan test tidak mencakup kelas yang sama, jadi bandingkan juga per kelas (tabel bagian 3).

## 6. Kebocoran taman-ubm pada baseline

Baseline (`models/baseline/*`) dilatih dengan 12 frame yang memperlihatkan area taman-ubm (`docs/test-set.md`); model ronde 2 ke atas bersih. Jadi di taman-ubm perbandingan **berat sebelah menguntungkan baseline**. Angka lantai 11 tidak terkena.

| Kotak, conf 0,25 | Lantai 11: mAP50 | TP/FP/FN | dekat | taman-ubm: mAP50 | TP/FP/FN | dekat |
|---|---|---|---|---|---|---|
| baseline-kotak | 0,405 | 38/33/46 | 13/36 | 0,204 | 28/112/125 | **1/32** |
| r2-kotak-v2bersih | 0,388 | 38/22/46 | 13/36 | 0,249 | 42/97/111 | 11/32 |
| r2-kotak-v3-960 | 0,358 | 32/18/52 | 10/36 | 0,229 | 39/105/114 | 8/32 |
| r4-kotak-v3-1280 | 0,388 | 41/25/43 | 13/36 | 0,315 | 54/111/99 | 7/32 |
| C2 (final) | 0,401 | 40/19/44 | 13/36 | 0,329 | 40/92/113 | 9/32 |

Walau diuntungkan, baseline tetap terendah di taman-ubm (dan hanya menemukan 1 dari 32 objek dekat). Jadi perbaikan dari baseline ke model baru di luar gedung nyata. Di lantai 11 baseline setara dengan yang lain: di dalam gedung, ronde 2 sampai ensemble **tidak** memberi perbaikan yang terukur. Seg: baseline-seg IoU jalur_jalan di taman-ubm 0,876 vs final 0,830; di sini keunggulan baseline bisa sebagian karena kebocoran, tetapi di lantai 11 baseline juga lebih tinggi (0,851 vs 0,788).

## 7. Catatan "kutukan pemenang"

C2 dipilih karena skornya **paling tinggi di val**, dan ambangnya juga disetel di val yang sama. Memilih yang tertinggi dari banyak kandidat pada 54 frame hampir pasti mengambil sebagian keberuntungan, jadi angka val C2 (mAP50 0,613, F1 0,583) terlalu optimis sebagai perkiraan kemampuan sebenarnya. Test menunjukkan besarnya:

| Selisih C2 terhadap `r2-kotak-v3-960` | Val | Test |
|---|---|---|
| mAP50 | +0,093 | +0,074 |
| F1 | +0,067 | +0,014 |
| TP pada conf 0,25 | +4 | +9 |
| FP pada conf 0,25 | -62 | -12 |

Keunggulan mAP50 sebagian besar bertahan, keunggulan F1 hampir hilang, dan pengurangan kotak salah jauh lebih kecil daripada di val. Di test, model tunggal `r4-kotak-v3-1280` (yang **gagal** aturan val) setara dengan C2 dan lebih baik di F1, jumlah TP, dan mAP class-agnostic, dengan seperempat waktu inferensi. Itu **tidak** mengubah pilihan (aturan: tidak ada hasil test yang mengubah model), dan dengan satu test set 91 frame juga tidak membuktikan 1280 lebih baik. Yang bisa dikatakan dengan jujur: angka test C2 di dokumen ini adalah perkiraan yang tidak bias, karena test tidak dipakai memilih apa pun; angka val C2 tidak.

## 8. Pengecekan dataset publik untuk ronde 5 (tidak dipakai)

Sebelum test, dua dataset publik Roboflow dilihat sebagai calon ronde 5 (hanya melihat: tanpa membangun dataset, tanpa training; bukti di `data/intip-publik/`, skrip `tools/intip_publik.py`). Keduanya **ditolak** dan ronde 5 tidak dijalankan:

- **Objek Trotoar** (`skripsi-ridho/objek-trotoar`, 7.321 gambar 320x320): label `pohon` menutup seluruh pohon (bertentangan dengan aturan batang saja), `tiang` kebanyakan kepala lampu dari bawah, foto stok dari banyak negara, gambar sudah teraugmentasi (sekitar 3.200 gambar sumber unik, 1.141 nama sumber muncul di lebih dari satu split), dan orang tidak dilabel (model COCO menemukan orang di 994 gambar).
- **Sidewalk Barriers** (`sidewalk-barriers-datasets/sidewalk-barriers`, 26.064 gambar terdaftar, tanpa versi yang bisa diunduh): gabungan banyak sumber satu kelas dengan label bolong. Satu-satunya bagian yang layak, 560 frame jalan Korea, tidak melabel kerb sama sekali. Memakainya akan mengajarkan kerb sebagai latar dan merugikan `tepian`, sedangkan keuntungan untuk `pohon` nyaris tidak terukur (val n = 10, test n = 3).

## 9. Keterbatasan

- **Test kecil**: 91 frame, 237 kotak, dua lokasi, satu hari rekaman per lokasi. Selisih antar model di bawah kira-kira 0,03 sampai 0,05 mAP50 tidak bisa dibedakan dari derau.
- **Kelas tanpa atau dengan sedikit instance**: kendaraan 0, tangga 0 (kotak dan seg), pohon 3, kursi 14 (semua di taman), jalan_kendaraan 16 polygon di 9 frame. Kemampuan untuk kendaraan dan tangga **tidak terukur di lokasi baru**.
- **Derau training**: margin d = 0,034 diukur dari dua seed saja, di val. Anggota ensemble masing-masing satu seed.
- **Val dipakai berulang** untuk memilih model, ambang, dan ensemble (bagian 7).
- **Ambang terkunci dari conf anggota 0,001, app memakai 0,05**: di val selisihnya hanya 6 FP; di test tidak diperiksa terpisah.
- **Kecepatan** diukur di GPU laptop pada frame val, bukan di HP atau server app. C2 menjalankan 4 model per frame.
- **"Dekat" adalah heuristik kasar** dari posisi kotak di gambar (y2 >= 0,65), bukan jarak sebenarnya. Peringatan tingkat frame memakai heuristik yang sama.
- **R4** membuang objek kecil dari label, jadi objek jauh tidak dinilai.
- Label test mengikuti `kelas.md` v1.7, label latih terbaru v1.8 (planter dan semak = tanaman_pot diperluas di v1.8). Sebagian FP tanaman_pot di taman bisa berasal dari beda aturan ini; tidak diperiksa satu per satu.
- Baseline bocor di taman-ubm (bagian 6).

## 10. Kesimpulan untuk app

Cukup untuk **demo prototipe**, dengan batasan yang harus disampaikan:

1. Andalkan **jalur_jalan** (seg) dan **peringatan tingkat frame**; keduanya yang paling stabil di lokasi baru. Peringatan tidak pernah palsu di test, tetapi satu dari tiga frame berbahaya terlewat, jadi app tidak boleh diposisikan sebagai pengganti tongkat.
2. Jangan menjanjikan nama benda. Per kelas, hanya sekitar sepertiga objek ditemukan di lokasi baru.
3. **Kerb dan undakan dekat tidak terdeteksi** di test (0 dari 22). Ini risiko terbesar untuk pengguna.
4. Di luar gedung akan ada sekitar dua kotak salah per frame (pot, pohon). Peringatan suara sebaiknya memakai aturan tingkat frame dan butuh beberapa frame berturut-turut, bukan tiap kotak.
5. Bangku taman tidak dikenali. Kendaraan dan tangga belum teruji di lokasi baru.
6. Kalau 4 model terlalu berat di perangkat target, satu model (`r2-kotak-v3-960`, config `config_saran_final.yaml`) memberi peringatan tingkat frame yang lebih lemah (recall 0,49 vs 0,67) dengan seperlima waktu.

## 11. Berkas

- Angka: `data/test-final/t1/<model>.json`, `data/test-final/t1/tabel.md`; padanan val dengan jalur yang sama: `data/test-final/t1_val/`.
- Run Ultralytics: `runs/test-final/<model>-val/` (nama folder berakhiran `-val` karena fungsi baseline, isinya **test**), `runs/test-final/agnostik/`, `runs/test-final/val-ulang/` (val).
- Contact sheet test: `runs/test-final/C2_kontak_16.jpg`, `C2_kontak_terburuk.jpg`, `r2-seg-v3_kontak_16.jpg`.
- Log lengkap: `data/test-final/LOG.md`. Config app: `data/test-final/config_saran.yaml`.
- Alat: `tools/test_final.py` (T0), `tools/ensemble_val.py`, `tools/metrik_tambahan.py`, `tools/test_t1.py` (T1), `tools/intip_publik.py`.

## Lampiran: tabel lengkap test

Dibuat `python tools/test_t1.py --aksi tabel --data test`. Kolom tanpa keterangan = jalur sendiri (satu jalur untuk semua model); "Ultra" = tabel Ultralytics `val()` (hanya model tunggal; P/R/F1 pada conf F1 terbaik). "agn" = class-agnostic. "dekat" = y2 >= 0,65.

### Kotak, semua frame

| Model | mAP50 | mAP50-95 | F1 | mAP50 (Ultra) | mAP50-95 (Ultra) | P (Ultra) | R (Ultra) | F1 (Ultra) | TP/FP/FN 0,25 | P/R/F1 mikro 0,25 | FP/frame | dekat | jauh |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline-kotak | 0,209 | 0,120 | 0,239 | 0,209 | 0,120 | 0,306 | 0,327 | 0,278 | 66/145/171 | 0,313/0,278/0,295 | 1,59 | 14/68 (0,21) | 52/169 (0,31) |
| r2-kotak-v2bersih | 0,244 | 0,153 | 0,280 | 0,278 | 0,168 | 0,320 | 0,392 | 0,308 | 80/119/157 | 0,402/0,338/0,367 | 1,31 | 24/68 (0,35) | 56/169 (0,33) |
| r2-kotak-v3 | 0,237 | 0,131 | 0,278 | 0,231 | 0,122 | 0,287 | 0,305 | 0,276 | 74/120/163 | 0,381/0,312/0,343 | 1,32 | 24/68 (0,35) | 50/169 (0,30) |
| r2-kotak-v3-960 | 0,231 | 0,125 | 0,294 | 0,235 | 0,126 | 0,305 | 0,302 | 0,257 | 71/123/166 | 0,366/0,300/0,329 | 1,35 | 18/68 (0,26) | 53/169 (0,31) |
| r3-kotak-v3-960-s | 0,243 | 0,138 | 0,279 | 0,231 | 0,126 | 0,435 | 0,302 | 0,269 | 81/153/156 | 0,346/0,342/0,344 | 1,68 | 21/68 (0,31) | 60/169 (0,36) |
| r4-kotak-v3-960-seed1 | 0,280 | 0,144 | 0,273 | 0,324 | 0,173 | 0,263 | 0,381 | 0,273 | 83/150/154 | 0,356/0,350/0,353 | 1,65 | 22/68 (0,32) | 61/169 (0,36) |
| r4-kotak-v3-1280 | 0,292 | 0,160 | 0,315 | 0,294 | 0,162 | 0,470 | 0,481 | 0,324 | 95/136/142 | 0,411/0,401/0,406 | 1,49 | 20/68 (0,29) | 75/169 (0,44) |
| r4-kotak-v4-960 | 0,237 | 0,140 | 0,275 | 0,239 | 0,145 | 0,273 | 0,312 | 0,266 | 66/114/171 | 0,367/0,278/0,317 | 1,25 | 19/68 (0,28) | 47/169 (0,28) |
| C1 | 0,236 | 0,135 | 0,279 | - | - | - | - | - | 84/181/153 | 0,317/0,354/0,335 | 1,99 | 23/68 (0,34) | 61/169 (0,36) |
| C2 | 0,305 | 0,172 | 0,308 | - | - | - | - | - | 80/111/157 | 0,419/0,338/0,374 | 1,22 | 22/68 (0,32) | 58/169 (0,34) |

### Kotak, ambang per kelas terkunci (pengaturan app)

| Model | subset | TP/FP/FN | P/R/F1 mikro | FP/frame | dekat | jauh | frame TP/FP/FN/TN | frame P | frame R | agnostik TP/FP/FN |
|---|---|---|---|---|---|---|---|---|---|---|
| r2-kotak-v3-960 | semua (91) | 67/124/170 | 0,351/0,283/0,313 | 1,36 | 16/68 (0,24) | 51/169 (0,30) | 21/1/22/47 | 0,955 | 0,488 | 70/121/167 |
| r2-kotak-v3-960 | lantai11 (45) | 28/13/56 | 0,683/0,333/0,448 | 0,29 | 8/36 (0,22) | 20/48 (0,42) | 8/0/9/28 | 1,000 | 0,471 | 28/13/56 |
| r2-kotak-v3-960 | dada (46) | 34/56/85 | 0,378/0,286/0,325 | 1,22 | 8/34 (0,24) | 26/85 (0,31) | 10/0/11/25 | 1,000 | 0,476 | 36/54/83 |
| r2-kotak-v3-960 | mata (45) | 33/68/85 | 0,327/0,280/0,301 | 1,51 | 8/34 (0,24) | 25/84 (0,30) | 11/1/11/22 | 0,917 | 0,500 | 34/67/84 |
| r2-kotak-v3-960 | taman-ubm (46) | 39/111/114 | 0,260/0,255/0,257 | 2,41 | 8/32 (0,25) | 31/121 (0,26) | 13/1/13/19 | 0,929 | 0,500 | 42/108/111 |
| C2 | semua (91) | 77/103/160 | 0,428/0,325/0,369 | 1,13 | 21/68 (0,31) | 56/169 (0,33) | 29/0/14/48 | 1,000 | 0,674 | 81/99/156 |
| C2 | lantai11 (45) | 37/6/47 | 0,860/0,440/0,583 | 0,13 | 12/36 (0,33) | 25/48 (0,52) | 12/0/5/28 | 1,000 | 0,706 | 37/6/47 |
| C2 | dada (46) | 38/45/81 | 0,458/0,319/0,376 | 0,98 | 11/34 (0,32) | 27/85 (0,32) | 14/0/7/25 | 1,000 | 0,667 | 40/43/79 |
| C2 | mata (45) | 39/58/79 | 0,402/0,331/0,363 | 1,29 | 10/34 (0,29) | 29/84 (0,35) | 15/0/7/23 | 1,000 | 0,682 | 41/56/77 |
| C2 | taman-ubm (46) | 40/97/113 | 0,292/0,261/0,276 | 2,11 | 9/32 (0,28) | 31/121 (0,26) | 17/0/9/20 | 1,000 | 0,654 | 44/93/109 |

### Kotak, dua metrik tambahan (semua frame)

| Model | agn mAP50 | agn mAP50-95 | agn F1 | agn mAP50 (Ultra single_cls) | agn F1 (Ultra) | agn TP/FP/FN 0,25 | agn P/R 0,25 | frame TP/FP/FN/TN 0,25 | frame P | frame R |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline-kotak | 0,229 | 0,133 | 0,320 | 0,235 | 0,335 | 71/140/166 | 0,336/0,300 | 22/2/21/46 | 0,917 | 0,512 |
| r2-kotak-v2bersih | 0,293 | 0,171 | 0,389 | 0,331 | 0,408 | 83/116/154 | 0,417/0,350 | 27/3/16/45 | 0,900 | 0,628 |
| r2-kotak-v3 | 0,294 | 0,158 | 0,381 | 0,279 | 0,361 | 77/117/160 | 0,397/0,325 | 28/1/15/47 | 0,966 | 0,651 |
| r2-kotak-v3-960 | 0,246 | 0,137 | 0,346 | 0,250 | 0,318 | 74/120/163 | 0,381/0,312 | 22/1/21/47 | 0,957 | 0,512 |
| r3-kotak-v3-960-s | 0,281 | 0,152 | 0,357 | 0,274 | 0,349 | 82/152/155 | 0,350/0,346 | 27/1/16/47 | 0,964 | 0,628 |
| r4-kotak-v3-960-seed1 | 0,289 | 0,157 | 0,375 | 0,305 | 0,393 | 87/146/150 | 0,373/0,367 | 28/2/15/46 | 0,933 | 0,651 |
| r4-kotak-v3-1280 | 0,343 | 0,183 | 0,417 | 0,332 | 0,408 | 98/133/139 | 0,424/0,414 | 24/2/19/46 | 0,923 | 0,558 |
| r4-kotak-v4-960 | 0,271 | 0,152 | 0,326 | 0,281 | 0,353 | 68/112/169 | 0,378/0,287 | 24/1/19/47 | 0,960 | 0,558 |
| C1 | 0,267 | 0,156 | 0,359 | - | - | 88/177/149 | 0,332/0,371 | 32/2/11/46 | 0,941 | 0,744 |
| C2 | 0,257 | 0,170 | 0,345 | - | - | 83/108/154 | 0,435/0,350 | 27/0/16/48 | 1,000 | 0,628 |

### Kotak per subset (jalur sendiri mAP50 / mAP50-95; conf 0,25 TP/FP/FN, FP per frame, recall dekat, frame TP/FP/FN/TN)

#### lantai11 (45 frame)

| Model | mAP50 | mAP50-95 | F1 | TP/FP/FN | P/R/F1 mikro | FP/frame | dekat | frame TP/FP/FN/TN | agn mAP50 | agn TP/FP/FN |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline-kotak | 0,405 | 0,281 | 0,362 | 38/33/46 | 0,535/0,452/0,490 | 0,73 | 13/36 (0,36) | 12/1/5/27 | 0,427 | 38/33/46 |
| r2-kotak-v2bersih | 0,388 | 0,261 | 0,377 | 38/22/46 | 0,633/0,452/0,528 | 0,49 | 13/36 (0,36) | 13/0/4/28 | 0,461 | 38/22/46 |
| r2-kotak-v3 | 0,358 | 0,224 | 0,369 | 35/19/49 | 0,648/0,417/0,507 | 0,42 | 13/36 (0,36) | 12/0/5/28 | 0,427 | 35/19/49 |
| r2-kotak-v3-960 | 0,358 | 0,233 | 0,342 | 32/18/52 | 0,640/0,381/0,478 | 0,40 | 10/36 (0,28) | 9/0/8/28 | 0,381 | 32/18/52 |
| r3-kotak-v3-960-s | 0,390 | 0,261 | 0,376 | 39/28/45 | 0,582/0,464/0,517 | 0,62 | 12/36 (0,33) | 12/0/5/28 | 0,455 | 39/28/45 |
| r4-kotak-v3-960-seed1 | 0,376 | 0,240 | 0,365 | 38/26/46 | 0,594/0,452/0,514 | 0,58 | 11/36 (0,31) | 12/0/5/28 | 0,438 | 38/26/46 |
| r4-kotak-v3-1280 | 0,388 | 0,247 | 0,388 | 41/25/43 | 0,621/0,488/0,547 | 0,56 | 13/36 (0,36) | 12/0/5/28 | 0,465 | 41/25/43 |
| r4-kotak-v4-960 | 0,366 | 0,240 | 0,356 | 33/20/51 | 0,623/0,393/0,482 | 0,44 | 11/36 (0,31) | 11/0/6/28 | 0,404 | 33/20/51 |
| C1 | 0,374 | 0,238 | 0,367 | 40/28/44 | 0,588/0,476/0,526 | 0,62 | 13/36 (0,36) | 13/1/4/27 | 0,430 | 40/28/44 |
| C2 | 0,401 | 0,273 | 0,371 | 40/19/44 | 0,678/0,476/0,559 | 0,42 | 13/36 (0,36) | 12/0/5/28 | 0,391 | 40/19/44 |

#### dada (46 frame)

| Model | mAP50 | mAP50-95 | F1 | TP/FP/FN | P/R/F1 mikro | FP/frame | dekat | frame TP/FP/FN/TN | agn mAP50 | agn TP/FP/FN |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline-kotak | 0,180 | 0,118 | 0,209 | 34/70/85 | 0,327/0,286/0,305 | 1,52 | 7/34 (0,21) | 10/2/11/23 | 0,231 | 36/68/83 |
| r2-kotak-v2bersih | 0,221 | 0,148 | 0,238 | 40/61/79 | 0,396/0,336/0,364 | 1,33 | 10/34 (0,29) | 13/1/8/24 | 0,291 | 43/58/76 |
| r2-kotak-v3 | 0,232 | 0,132 | 0,256 | 36/57/83 | 0,387/0,303/0,340 | 1,24 | 10/34 (0,29) | 12/0/9/25 | 0,299 | 37/56/82 |
| r2-kotak-v3-960 | 0,204 | 0,116 | 0,278 | 36/55/83 | 0,396/0,303/0,343 | 1,20 | 8/34 (0,24) | 10/0/11/25 | 0,251 | 38/53/81 |
| r3-kotak-v3-960-s | 0,245 | 0,134 | 0,269 | 41/71/78 | 0,366/0,345/0,355 | 1,54 | 10/34 (0,29) | 12/0/9/25 | 0,292 | 41/71/78 |
| r4-kotak-v3-960-seed1 | 0,193 | 0,115 | 0,235 | 39/74/80 | 0,345/0,328/0,336 | 1,61 | 10/34 (0,29) | 12/0/9/25 | 0,268 | 41/72/78 |
| r4-kotak-v3-1280 | 0,264 | 0,153 | 0,282 | 44/61/75 | 0,419/0,370/0,393 | 1,33 | 9/34 (0,26) | 13/0/8/25 | 0,339 | 45/60/74 |
| r4-kotak-v4-960 | 0,245 | 0,134 | 0,268 | 32/48/87 | 0,400/0,269/0,322 | 1,04 | 9/34 (0,26) | 12/0/9/25 | 0,292 | 33/47/86 |
| C1 | 0,230 | 0,139 | 0,278 | 41/79/78 | 0,342/0,345/0,343 | 1,72 | 11/34 (0,32) | 14/1/7/24 | 0,286 | 43/77/76 |
| C2 | 0,277 | 0,168 | 0,285 | 39/50/80 | 0,438/0,328/0,375 | 1,09 | 11/34 (0,32) | 13/0/8/25 | 0,264 | 40/49/79 |

#### mata (45 frame)

| Model | mAP50 | mAP50-95 | F1 | TP/FP/FN | P/R/F1 mikro | FP/frame | dekat | frame TP/FP/FN/TN | agn mAP50 | agn TP/FP/FN |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline-kotak | 0,254 | 0,134 | 0,266 | 32/75/86 | 0,299/0,271/0,284 | 1,67 | 7/34 (0,21) | 12/0/10/23 | 0,232 | 35/72/83 |
| r2-kotak-v2bersih | 0,338 | 0,188 | 0,303 | 40/58/78 | 0,408/0,339/0,370 | 1,29 | 14/34 (0,41) | 14/2/8/21 | 0,308 | 40/58/78 |
| r2-kotak-v3 | 0,262 | 0,143 | 0,295 | 38/63/80 | 0,376/0,322/0,347 | 1,40 | 14/34 (0,41) | 16/1/6/22 | 0,294 | 40/61/78 |
| r2-kotak-v3-960 | 0,317 | 0,144 | 0,305 | 35/68/83 | 0,340/0,297/0,317 | 1,51 | 10/34 (0,29) | 12/1/10/22 | 0,249 | 36/67/82 |
| r3-kotak-v3-960-s | 0,324 | 0,192 | 0,308 | 40/82/78 | 0,328/0,339/0,333 | 1,82 | 11/34 (0,32) | 15/1/7/22 | 0,269 | 41/81/77 |
| r4-kotak-v3-960-seed1 | 0,352 | 0,174 | 0,306 | 44/76/74 | 0,367/0,373/0,370 | 1,69 | 12/34 (0,35) | 16/2/6/21 | 0,319 | 46/74/72 |
| r4-kotak-v3-1280 | 0,335 | 0,181 | 0,352 | 51/75/67 | 0,405/0,432/0,418 | 1,67 | 11/34 (0,32) | 11/2/11/21 | 0,359 | 53/73/65 |
| r4-kotak-v4-960 | 0,270 | 0,168 | 0,318 | 34/66/84 | 0,340/0,288/0,312 | 1,47 | 10/34 (0,29) | 12/1/10/22 | 0,264 | 35/65/83 |
| C1 | 0,311 | 0,152 | 0,298 | 43/102/75 | 0,297/0,364/0,327 | 2,27 | 12/34 (0,35) | 18/1/4/22 | 0,253 | 45/100/73 |
| C2 | 0,360 | 0,192 | 0,343 | 41/61/77 | 0,402/0,347/0,373 | 1,36 | 11/34 (0,32) | 14/0/8/23 | 0,259 | 43/59/75 |

#### taman-ubm (46 frame)

| Model | mAP50 | mAP50-95 | F1 | TP/FP/FN | P/R/F1 mikro | FP/frame | dekat | frame TP/FP/FN/TN | agn mAP50 | agn TP/FP/FN |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline-kotak | 0,204 | 0,118 | 0,238 | 28/112/125 | 0,200/0,183/0,191 | 2,43 | 1/32 (0,03) | 10/1/16/19 | 0,116 | 33/107/120 |
| r2-kotak-v2bersih | 0,249 | 0,150 | 0,284 | 42/97/111 | 0,302/0,275/0,288 | 2,11 | 11/32 (0,34) | 14/3/12/17 | 0,200 | 45/94/108 |
| r2-kotak-v3 | 0,241 | 0,133 | 0,284 | 39/101/114 | 0,279/0,255/0,266 | 2,20 | 11/32 (0,34) | 16/1/10/19 | 0,206 | 42/98/111 |
| r2-kotak-v3-960 | 0,229 | 0,117 | 0,269 | 39/105/114 | 0,271/0,255/0,263 | 2,28 | 8/32 (0,25) | 13/1/13/19 | 0,172 | 42/102/111 |
| r3-kotak-v3-960-s | 0,244 | 0,126 | 0,280 | 42/125/111 | 0,251/0,275/0,263 | 2,72 | 9/32 (0,28) | 15/1/11/19 | 0,171 | 43/124/110 |
| r4-kotak-v3-960-seed1 | 0,267 | 0,136 | 0,260 | 45/124/108 | 0,266/0,294/0,280 | 2,70 | 11/32 (0,34) | 16/2/10/18 | 0,199 | 49/120/104 |
| r4-kotak-v3-1280 | 0,315 | 0,171 | 0,328 | 54/111/99 | 0,327/0,353/0,340 | 2,41 | 7/32 (0,22) | 12/2/14/18 | 0,254 | 57/108/96 |
| r4-kotak-v4-960 | 0,261 | 0,150 | 0,273 | 33/94/120 | 0,260/0,216/0,236 | 2,04 | 8/32 (0,25) | 13/1/13/19 | 0,184 | 35/92/118 |
| C1 | 0,224 | 0,131 | 0,272 | 44/153/109 | 0,223/0,288/0,251 | 3,33 | 10/32 (0,31) | 19/1/7/19 | 0,174 | 48/149/105 |
| C2 | 0,329 | 0,178 | 0,302 | 40/92/113 | 0,303/0,261/0,281 | 2,00 | 9/32 (0,28) | 15/0/11/20 | 0,179 | 43/89/110 |

### Kotak per kelas, AP50 (jalur sendiri)

| Kelas | n | baseline-kotak | r2-kotak-v2bersih | r2-kotak-v3 | r2-kotak-v3-960 | r3-kotak-v3-960-s | r4-kotak-v3-960-seed1 | r4-kotak-v3-1280 | r4-kotak-v4-960 | C1 | C2 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pilar | 38 | 0,214 | 0,373 | 0,349 | 0,420 | 0,367 | 0,276 | 0,403 | 0,360 | 0,402 | 0,463 |
| pohon * | 3 | 0,173 | 0,110 | 0,092 | 0,150 | 0,084 | 0,444 | 0,170 | 0,102 | 0,138 | 0,223 |
| tepian | 51 | 0,103 | 0,135 | 0,092 | 0,134 | 0,107 | 0,068 | 0,197 | 0,116 | 0,108 | 0,147 |
| orang | 32 | 0,503 | 0,472 | 0,491 | 0,433 | 0,550 | 0,471 | 0,566 | 0,485 | 0,433 | 0,567 |
| tanaman_pot | 99 | 0,260 | 0,364 | 0,396 | 0,250 | 0,329 | 0,413 | 0,414 | 0,314 | 0,321 | 0,405 |
| kursi * | 14 | 0,001 | 0,014 | 0,003 | 0,000 | 0,022 | 0,010 | 0,005 | 0,046 | 0,015 | 0,028 |
| kendaraan * | 0 | - | - | - | - | - | - | - | - | - | - |
| tangga * | 0 | - | - | - | - | - | - | - | - | - | - |

### Kotak per kelas, TP/FP/FN conf 0,25

| Kelas | n | baseline-kotak | r2-kotak-v2bersih | r2-kotak-v3 | r2-kotak-v3-960 | r3-kotak-v3-960-s | r4-kotak-v3-960-seed1 | r4-kotak-v3-1280 | r4-kotak-v4-960 | C1 | C2 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pilar | 38 | 7/13/31 | 12/7/26 | 14/17/24 | 15/7/23 | 16/14/22 | 15/25/23 | 11/10/27 | 14/14/24 | 16/17/22 | 15/9/23 |
| pohon | 3 | 2/16/1 | 1/11/2 | 1/12/2 | 2/16/1 | 1/12/2 | 2/32/1 | 2/21/1 | 2/26/1 | 2/24/1 | 2/18/1 |
| tepian | 51 | 7/21/44 | 5/7/46 | 6/14/45 | 12/28/39 | 9/37/42 | 4/18/47 | 15/19/36 | 7/11/44 | 13/46/38 | 9/15/42 |
| orang | 32 | 20/29/12 | 16/19/16 | 16/10/16 | 18/17/14 | 18/22/14 | 17/21/15 | 20/19/12 | 17/16/15 | 19/22/13 | 18/19/14 |
| tanaman_pot | 99 | 30/58/69 | 46/71/53 | 37/64/62 | 24/50/75 | 37/66/62 | 45/51/54 | 47/65/52 | 26/45/73 | 34/65/65 | 36/48/63 |
| kursi | 14 | 0/4/14 | 0/2/14 | 0/1/14 | 0/2/14 | 0/0/14 | 0/0/14 | 0/1/14 | 0/1/14 | 0/4/14 | 0/1/14 |
| kendaraan | 0 | 0/2/0 | 0/0/0 | 0/0/0 | 0/1/0 | 0/2/0 | 0/2/0 | 0/0/0 | 0/0/0 | 0/1/0 | 0/0/0 |
| tangga | 0 | 0/2/0 | 0/2/0 | 0/2/0 | 0/2/0 | 0/0/0 | 0/1/0 | 0/1/0 | 0/1/0 | 0/2/0 | 0/1/0 |

### r2-kotak-v3-960: per kelas pada ambang terkunci

| Kelas | ambang | n | TP | FP | FN | P | R | F1 | dekat | jauh |
|---|---|---|---|---|---|---|---|---|---|---|
| pilar | 0,25 | 38 | 15 | 7 | 23 | 0,682 | 0,395 | 0,500 | 4/7 (0,57) | 11/31 (0,35) |
| pohon | 0,25 | 3 | 2 | 16 | 1 | 0,111 | 0,667 | 0,190 | 0/0 | 2/3 (0,67) |
| tepian | 0.2 | 51 | 13 | 35 | 38 | 0,271 | 0,255 | 0,263 | 0/22 (0,00) | 13/29 (0,45) |
| orang | 0,65 | 32 | 13 | 11 | 19 | 0,542 | 0,406 | 0,464 | 1/3 (0,33) | 12/29 (0,41) |
| tanaman_pot | 0,25 | 99 | 24 | 50 | 75 | 0,324 | 0,242 | 0,277 | 11/25 (0,44) | 13/74 (0,18) |
| kursi | 0,55 | 14 | 0 | 2 | 14 | 0,000 | 0,000 | 0,000 | 0/11 (0,00) | 0/3 (0,00) |
| kendaraan | 0,25 | 0 | 0 | 1 | 0 | 0,000 | - | 0,000 | 0/0 | 0/0 |
| tangga | 0,25 | 0 | 0 | 2 | 0 | 0,000 | - | 0,000 | 0/0 | 0/0 |

Recall per ukuran (px skala 640): <32 10/23 (0,43), 32-64 16/57 (0,28), 64-128 16/69 (0,23), >=128 25/88 (0,28)

FP yang menimpa GT kelas lain: kendaraan (prediksi) di atas GT kursi: 1, tangga (prediksi) di atas GT kursi: 1, tepian (prediksi) di atas GT kursi: 1

### C2: per kelas pada ambang terkunci

| Kelas | ambang | n | TP | FP | FN | P | R | F1 | dekat | jauh |
|---|---|---|---|---|---|---|---|---|---|---|
| pilar | 0,25 | 38 | 15 | 9 | 23 | 0,625 | 0,395 | 0,484 | 5/7 (0,71) | 10/31 (0,32) |
| pohon | 0,25 | 3 | 2 | 18 | 1 | 0,100 | 0,667 | 0,174 | 0/0 | 2/3 (0,67) |
| tepian | 0.2 | 51 | 11 | 20 | 40 | 0,355 | 0,216 | 0,268 | 0/22 (0,00) | 11/29 (0,38) |
| orang | 0.6 | 32 | 13 | 5 | 19 | 0,722 | 0,406 | 0,520 | 1/3 (0,33) | 12/29 (0,41) |
| tanaman_pot | 0,25 | 99 | 36 | 48 | 63 | 0,429 | 0,364 | 0,393 | 15/25 (0,60) | 21/74 (0,28) |
| kursi | 0,25 | 14 | 0 | 1 | 14 | 0,000 | 0,000 | 0,000 | 0/11 (0,00) | 0/3 (0,00) |
| kendaraan | 0.1 | 0 | 0 | 1 | 0 | 0,000 | - | 0,000 | 0/0 | 0/0 |
| tangga | 0,25 | 0 | 0 | 1 | 0 | 0,000 | - | 0,000 | 0/0 | 0/0 |

Recall per ukuran (px skala 640): <32 7/23 (0,30), 32-64 17/57 (0,30), 64-128 20/69 (0,29), >=128 33/88 (0,38)

FP yang menimpa GT kelas lain: tepian (prediksi) di atas GT kursi: 2, kendaraan (prediksi) di atas GT kursi: 1, tangga (prediksi) di atas GT kursi: 1, tanaman_pot (prediksi) di atas GT pilar: 1

### Segmentasi (mask)

| Model | mAP50 | mAP50-95 | P | R | F1 | IoU jalur_jalan | IoU jalan_kendaraan | IoU tangga |
|---|---|---|---|---|---|---|---|---|
| baseline-seg | 0,439 | 0,366 | 0,460 | 0,414 | 0,436 | 0,864 | 0,016 | 0,000 |
| r2-seg-v3 | 0,461 | 0,362 | 0,516 | 0,449 | 0,470 | 0,809 | 0,028 | - |
| r4-seg-v4 | 0,453 | 0,350 | 0,487 | 0,438 | 0,460 | 0,781 | 0,001 | 0,000 |

Per kelas (mask): baseline-seg: jalur_jalan n=96 mAP50 0,878 P 0,919 R 0,829, jalan_kendaraan n=16 mAP50 0,000 P 0,000 R 0,000; r2-seg-v3: jalur_jalan n=96 mAP50 0,856 P 0,861 R 0,836, jalan_kendaraan n=16 mAP50 0,067 P 0,170 R 0,062; r4-seg-v4: jalur_jalan n=96 mAP50 0,888 P 0,883 R 0,812, jalan_kendaraan n=16 mAP50 0,017 P 0,092 R 0,062

IoU piksel per subset:

| Model | subset | jalur_jalan | jalan_kendaraan | tangga |
|---|---|---|---|---|
| baseline-seg | semua (91) | 0,864 | 0,016 | 0,000 |
| baseline-seg | lantai11 (45) | 0,851 | 0,000 | 0,000 |
| baseline-seg | dada (46) | 0,860 | 0,000 | 0,000 |
| baseline-seg | mata (45) | 0,868 | 0,039 | 0,000 |
| baseline-seg | taman-ubm (46) | 0,876 | 0,022 | 0,000 |
| r2-seg-v3 | semua (91) | 0,809 | 0,028 | - |
| r2-seg-v3 | lantai11 (45) | 0,788 | 0,000 | - |
| r2-seg-v3 | dada (46) | 0,763 | 0,000 | - |
| r2-seg-v3 | mata (45) | 0,859 | 0,211 | - |
| r2-seg-v3 | taman-ubm (46) | 0,830 | 0,040 | - |
| r4-seg-v4 | semua (91) | 0,781 | 0,001 | 0,000 |
| r4-seg-v4 | lantai11 (45) | 0,804 | - | - |
| r4-seg-v4 | dada (46) | 0,773 | 0,000 | 0,000 |
| r4-seg-v4 | mata (45) | 0,790 | 0,004 | - |
| r4-seg-v4 | taman-ubm (46) | 0,758 | 0,001 | 0,000 |
