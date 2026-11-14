# Hasil Ronde 2 JalanKu (label v2 + 66 frame baru, latih ulang, banding di val)

Status: 14 November 2026. Semua angka dari run sebenarnya (`runs/ronde2/<run>/meta.json`, `results.csv`, `runs/ronde2/eval/`). Evaluasi hanya pada **val kampus v2 (54 frame)**. Test set tidak disentuh di ronde ini. Folder `data/`, `runs/`, `models/` tidak masuk Git.

Ringkasan: dari empat run, hanya model kotak **960 px** yang jelas lebih baik dari baseline (mAP50 0,537 vs 0,498; mAP50-95 0,312 vs 0,296; F1 0,532 vs 0,483), terutama di `tepian` dan objek 32-64 px, dengan biaya CPU sekitar 2 kali. Pada 640 px, koreksi label dan 66 frame baru **tidak menaikkan** angka keseluruhan (selisih di bawah noise val), walau recall `pilar`, `tepian`, `pohon` naik. Model segmentasi baru setara di mAP dan sedikit lebih baik di recall dan IoU piksel permukaan.

## 1. Setup

Environment sama dengan baseline: RTX 4060 Laptop 8 GB, Python 3.12.10, torch 2.14.1+cu132, ultralytics 8.4.188, commit `65a1fc9` (skrip ronde 2 belum di-commit). Pengaturan sama dengan baseline kecuali yang tertulis: yolo26n / yolo26n-seg COCO, batch 16, seed 0, deterministic, augmentasi default, optimizer auto (AdamW di semua run), best checkpoint pada val.

| Run | Data train | imgsz | Epoch maks / patience | Epoch berjalan | Epoch terbaik | Waktu | Langkah optimizer | VRAM puncak |
|---|---|---|---|---|---|---|---|---|
| `r2-kotak-v2bersih` | gabung-kotak-v2bersih, 3.032 gambar | 640 | 100 / 30 | 49 | 19 | 22,5 mnt | 2.462 | 2,70 GiB |
| `r2-kotak-v3` | gabung-kotak-v3, 3.296 gambar | 640 | 100 / 30 | 49 | 19 | 23,5 mnt | 2.669 | 2,65 GiB |
| `r2-kotak-v3-960` | gabung-kotak-v3, 3.296 gambar | 960 | 100 / 30 | 79 | 49 | 82,2 mnt | 4.214 | 6,24 GiB |
| `r2-seg-v3` | gabung-seg-v3, 249 gambar | 640 | 300 / 100 | 205 | 105 | 15,9 mnt | 831 | 3,46 GiB |

Semua run berhenti karena early stopping dan selesai dalam satu segmen (tidak ada resume). "Epoch terbaik" dibaca dari mAP50-95 tertinggi di `results.csv`.

Perubahan dari rencana awal: run 1 memakai `v2bersih`, bukan `v2`. `v2bersih` = v2 dikurangi 12 frame train yang memperlihatkan area test `taman-ubm` (lihat `docs/test-set.md`, bagian kebocoran). Baseline dilatih dengan 12 frame itu dan dengan label v1 (sebelum audit).

Data:

| Dataset | Kampus train | Gambar train kotak (kampus x4 + publik 2.300) | Porsi kampus |
|---|---|---|---|
| v2 (acuan) | 195 | 3.080 | 25,3% |
| v2bersih | 183 | 3.032 | 24,1% |
| v3 | 249 (183 + 66 baru) | 3.296 | 30,2% |

Val semua varian byte-identik dengan val v2 (SHA-256), bagian publik juga. Tidak ada lokasi val atau test di train (assert di `tools/bangun_dataset_ronde2.py`).

## 2. Pemilihan frame

Pool: 2.904 frame lokasi training, 195 sudah berlabel, 751 dibuang karena < 3 s dari frame berlabel, sisa 1.958. Dipilih 70 frame (seed 20261113), 4 dikeluarkan saat review karena memperlihatkan `taman-ubm` (1 lorong-lt3 lewat kaca, 3 jalanan-ubm). **Dipakai: 66 frame.**

| Bucket | Jumlah | Isi |
|---|---|---|
| U (model ragu di kelas lemah) | 38 | |
| G (celah >= 25 s dari frame berlabel) | 12 | termasuk 4 frame tangga turun parkiran |
| W (paling beda secara embedding) | 8 | |
| E (eskalator terbaca tangga) | 7 | hard negative |
| D (tangga sulit) | 1 | target 7; kandidat lain ternyata dinding bordes atau duplikat |

Lokasi: parkiran-motor-b1 10, samping-ubm 10, halaman-ubm 10, lorong-lt3-eskalator 9, jalanan-ubm 7, lab-iota1-lt9 6, lorong-lt5 4, lorong-lt9 4, alfamart-lt2 3, lab1-lt5 2, tangga-naik-lt3 1. Luar ruang 27 dari 66 (41%). Dada 33, mata 33.

## 3. Studi sumber draft (di val, pengukuran saja)

Biaya edit = 5 x FN + 2 x FP + 3 x TP dengan IoU < 0,7. Sumber termurah per kelas di 54 frame val:

| Kelas | Sumber dipakai | Catatan |
|---|---|---|
| pilar | gabungan model + auto, conf 0,25 | biaya 97; auto saja 117, model saja 130 |
| pohon, kursi | gabungan, conf 0,35 | keputusan Jeka di R0 (tabel memilih auto) |
| tepian, orang, tanaman_pot, kendaraan, tangga | auto | |
| jalur_jalan, jalan_kendaraan, tangga (mask) | auto | IoU piksel auto 0,96 / 0,92 / 0,90 vs model 0,64 / 0,77 / 0,79 |

Bias: model dipilih pada val ini, dan ambang auto disetel pada frame pilot, jadi kedua sumber terlihat lebih baik daripada di frame baru.

## 4. Kualitas draft vs label akhir (66 frame, IoU 0,5, R4 di kedua sisi)

| Kelas | Label akhir | Draft | P | R | Dihapus | Ditambah |
|---|---|---|---|---|---|---|
| pilar | 75 | 112 | 0,571 | 0,853 | 48 | 11 |
| pohon | 35 | 39 | 0,897 | 1,000 | 4 | 0 |
| tepian | 77 | 118 | 0,568 | 0,870 | 51 | 10 |
| orang | 16 | 39 | 0,359 | 0,875 | 25 | 2 |
| tanaman_pot | 16 | 11 | 0,455 | 0,312 | 6 | 11 |
| kursi | 38 | 47 | 0,787 | 0,974 | 9 | 1 |
| kendaraan | 13 | 23 | 0,478 | 0,846 | 12 | 2 |
| tangga (kotak) | 6 | 2 | 1,000 | 0,333 | 0 | 2 |

Pilar: draft dari model P 0,781 (n 64), dari auto P 0,292 (n 48). Kursi: model 0,935 (n 31), auto 0,500 (n 16). Mask: jalur_jalan IoU 0,650, jalan_kendaraan 0,427, tangga 0,439. Draft permukaan jauh lebih buruk di frame baru daripada di studi val (0,96 / 0,92 / 0,90), sesuai bias yang dicatat di bagian 3. Rincian: `data/ronde2/kualitas_draft.csv`.

## 5. Hasil model kotak (val v2, 54 frame, 263 instance)

Jalur kode sama dengan `runs/baseline/eval-v2/v2` (`tools/evaluasi_ronde2.py` memanggil fungsi `evaluasi_baseline.py`); baseline yang diulang di sini identik dengan angka lama. mAP pada conf 0,001; P, R, F1 pada conf yang memaksimalkan F1 rata-rata kelas.

| Model | imgsz | mAP50 | mAP50-95 | P | R | F1 | conf F1 terbaik | Selisih mAP50 | Selisih mAP50-95 |
|---|---|---|---|---|---|---|---|---|---|
| baseline (`kotak-gabung`) | 640 | 0,498 | 0,296 | 0,621 | 0,434 | 0,483 | 0,431 | | |
| `r2-kotak-v2bersih` | 640 | 0,482 | 0,295 | 0,629 | 0,464 | 0,454 | 0,297 | -0,016 | -0,001 |
| `r2-kotak-v3` | 640 | 0,485 | 0,288 | 0,491 | 0,492 | 0,475 | 0,201 | -0,013 | -0,008 |
| `r2-kotak-v3-960` | 960 | **0,537** | **0,312** | 0,615 | 0,526 | **0,532** | 0,307 | +0,039 | +0,016 |

mAP50 per kelas (\* = n < 20, angka kurang bisa dipercaya):

| Kelas | n val | baseline | v2bersih | v3 | v3-960 |
|---|---|---|---|---|---|
| pilar | 34 | 0,384 | 0,407 | 0,462 | 0,397 |
| pohon \* | 10 | 0,089 | 0,100 | 0,147 | 0,195 |
| tepian | 45 | 0,263 | 0,174 | 0,280 | **0,492** |
| orang | 29 | 0,690 | 0,709 | 0,728 | 0,629 |
| tanaman_pot \* | 10 | 0,492 | 0,427 | 0,297 | 0,481 |
| kursi | 22 | 0,622 | 0,581 | 0,569 | 0,637 |
| kendaraan | 108 | 0,550 | 0,518 | 0,544 | 0,501 |
| tangga \* | 5 | 0,895 | 0,938 | 0,851 | 0,962 |

Recall per kelas (pada conf F1 terbaik masing-masing model):

| Kelas | n val | baseline | v2bersih | v3 | v3-960 |
|---|---|---|---|---|---|
| pilar | 34 | 0,298 | 0,257 | 0,366 | 0,311 |
| pohon \* | 10 | 0,000 | 0,100 | 0,200 | 0,200 |
| tepian | 45 | 0,222 | 0,134 | 0,378 | 0,578 |
| orang | 29 | 0,642 | 0,751 | 0,759 | 0,690 |
| tanaman_pot \* | 10 | 0,300 | 0,500 | 0,350 | 0,339 |
| kursi | 22 | 0,591 | 0,545 | 0,591 | 0,636 |
| kendaraan | 108 | 0,418 | 0,422 | 0,491 | 0,457 |
| tangga \* | 5 | 1,000 | 1,000 | 0,800 | 1,000 |

Galat pada conf 0,25 dan IoU 0,5 (TP / FP / FN):

| Kelas | baseline | v2bersih | v3 | v3-960 |
|---|---|---|---|---|
| pilar | 11 / 3 / 23 | 6 / 2 / 28 | 12 / 4 / 22 | 11 / 2 / 23 |
| pohon | 0 / 3 / 10 | 1 / 0 / 9 | 1 / 1 / 9 | 2 / 3 / 8 |
| tepian | 14 / 38 / 31 | 12 / 11 / 33 | 14 / 20 / 31 | 22 / 26 / 23 |
| orang | 22 / 15 / 7 | 21 / 12 / 8 | 21 / 12 / 8 | 21 / 16 / 8 |
| tanaman_pot | 2 / 0 / 8 | 7 / 5 / 3 | 3 / 6 / 7 | 4 / 1 / 6 |
| kursi | 14 / 12 / 8 | 12 / 8 / 10 | 12 / 7 / 10 | 14 / 18 / 8 |
| kendaraan | 53 / 41 / 55 | 46 / 18 / 62 | 52 / 28 / 56 | 52 / 39 / 56 |
| tangga | 4 / 2 / 1 | 5 / 8 / 0 | 4 / 4 / 1 | 5 / 4 / 0 |
| **semua** | 120 / 114 / 143 | 110 / 64 / 153 | 119 / 82 / 144 | 131 / 109 / 132 |

Recall per ukuran objek (akar luas kotak, px pada skala 640 untuk semua model), ditemukan / GT:

| Ukuran | baseline | v2bersih | v3 | v3-960 |
|---|---|---|---|---|
| < 32 | 4 / 24 (0,167) | 2 / 24 (0,083) | 4 / 24 (0,167) | 5 / 24 (0,208) |
| 32-64 | 38 / 102 (0,373) | 36 / 102 (0,353) | 39 / 102 (0,382) | 47 / 102 (0,461) |
| 64-128 | 56 / 104 (0,538) | 48 / 104 (0,462) | 55 / 104 (0,529) | 57 / 104 (0,548) |
| >= 128 | 22 / 33 (0,667) | 24 / 33 (0,727) | 21 / 33 (0,636) | 22 / 33 (0,667) |

### Yang membaik dan yang tidak

- **Koreksi label saja (baseline ke v2bersih): tidak menaikkan mAP.** mAP50 -0,016, mAP50-95 -0,001. Yang berubah adalah titik operasi: di conf 0,25 FP turun dari 114 ke 64, tetapi TP juga turun dari 120 ke 110. FP `tepian` turun dari 38 ke 11 dan `kendaraan` dari 41 ke 18. FP `tangga` naik dari 2 ke 8.
- **66 frame baru pada 640 (v2bersih ke v3): mAP keseluruhan sama** (mAP50 +0,003, mAP50-95 -0,007), tetapi kelas sasaran naik: `pilar` mAP50 +0,055 dan TP 6 ke 12, `tepian` +0,106, `pohon` +0,047. `tanaman_pot` turun -0,130 (n = 10). TP total 110 ke 119, FP 64 ke 82.
- **960 px (v3 ke v3-960): kenaikan terbesar.** mAP50 +0,052, mAP50-95 +0,024 dibanding v3 640. `tepian` mAP50 0,280 ke 0,492 dan TP 14 ke 22; objek 32-64 px recall 0,382 ke 0,461. Tetapi `orang` (-0,099), `pilar` (-0,065) dan `kendaraan` (-0,043) turun dibanding v3 640, dan FP `kursi` naik dari 7 ke 18.
- **Pilar tetap lemah:** recall tertinggi 0,366, 22 sampai 28 dari 34 pilar val terlewat di semua model.
- **Objek < 32 px tetap hampir tidak terdeteksi:** 2 sampai 5 dari 24.
- **Eskalator terbaca tangga belum terukur membaik:** FP `tangga` di conf 0,25 adalah 2 (baseline), 8, 4, 4. Tujuh frame hard negative eskalator belum cukup, atau efeknya tidak terlihat di val ini. Saya tidak memeriksa FP itu satu per satu.

## 6. Hasil model segmentasi (val v2, 54 frame, 67 instance, mask)

| Model | mAP50 | mAP50-95 | P | R | F1 |
|---|---|---|---|---|---|
| baseline (`seg-kampus`) | 0,634 | 0,523 | 0,883 | 0,554 | 0,665 |
| `r2-seg-v3` | 0,647 | 0,524 | 0,868 | 0,606 | 0,692 |

| Kelas | n val | mAP50 baseline | mAP50 r2 | R baseline | R r2 | IoU piksel baseline | IoU piksel r2 |
|---|---|---|---|---|---|---|---|
| jalur_jalan | 33 | 0,613 | 0,613 | 0,515 | 0,636 | 0,635 | 0,684 |
| jalan_kendaraan | 23 | 0,899 | 0,874 | 0,783 | 0,783 | 0,767 | 0,825 |
| tangga \* | 11 | 0,390 | 0,455 | 0,364 | 0,399 | 0,788 | 0,738 |

IoU piksel = agregat semua frame val pada conf 0,25. mAP praktis sama (+0,013 / +0,001). Recall `jalur_jalan` dan IoU piksel dua kelas permukaan naik; presisi `jalur_jalan` turun dari 0,830 ke 0,669; IoU piksel `tangga` turun (n = 11).

## 7. Kecepatan (laptop ini, bukan HP)

fp32, PyTorch tanpa ekspor, batch 1, conf 0,25, warm-up 10, median atas 54 frame val. `runs/ronde2/eval/kecepatan.json`.

| Model | imgsz | GPU total (ms) | GPU FPS | CPU 1 thread (ms) | FPS | CPU 10 thread (ms) | FPS |
|---|---|---|---|---|---|---|---|
| baseline kotak | 640 | 10,5 | 95,0 | 46,0 | 21,7 | 27,2 | 36,7 |
| `r2-kotak-v2bersih` | 640 | 11,4 | 87,5 | 48,2 | 20,8 | 28,4 | 35,3 |
| `r2-kotak-v3` | 640 | 12,3 | 81,5 | 47,4 | 21,1 | 28,1 | 35,5 |
| `r2-kotak-v3-960` | 960 | 11,8 | 84,7 | 98,1 | 10,2 | 45,1 | 22,2 |
| baseline seg | 640 | 13,8 | 72,6 | 69,9 | 14,3 | 37,7 | 26,5 |
| `r2-seg-v3` | 640 | 13,4 | 74,5 | 71,0 | 14,1 | 37,4 | 26,7 |

Di GPU laptop, 960 dan 640 sama cepat (model nano; waktu didominasi overhead, bukan komputasi), jadi angka GPU tidak membedakan keduanya. Di CPU, 960 butuh 2,1 kali waktu 640 pada 1 thread dan 1,6 kali pada 10 thread. Untuk HP, angka CPU lebih relevan sebagai gambaran rasio, tetapi kecepatan HP yang sebenarnya harus diukur setelah ekspor.

## 8. Rekomendasi

- **Model kotak: `r2-kotak-v3-960`**, dengan syarat kecepatan di HP cukup setelah ekspor. Kalau 960 terlalu lambat di HP, pakai **`r2-kotak-v3` (640)**: angkanya setara baseline, recall kelas lemah lebih baik, dan tidak dilatih dengan 12 frame yang bocor ke area test. Baseline tidak layak dipakai untuk evaluasi test karena kebocoran itu.
- **Model segmentasi: `r2-seg-v3`.** Setara di mAP, lebih baik di recall dan IoU piksel permukaan, dan bebas frame bocor.

## 9. Batasan

- **Val hanya 54 frame dari 3 lokasi**, 263 instance kotak dan 67 segmentasi; frame satu lokasi berasal dari video yang sama. Selisih sekitar ±0,03 per kelas tidak bisa dibedakan dari noise.
- **Kelas dengan n < 20:** pohon (10), tanaman_pot (10), tangga kotak (5), tangga mask (11).
- **Checkpoint dipilih pada val yang sama** dengan yang dilaporkan, jadi semua angka cenderung optimistis. Run 960 membandingkan lebih banyak epoch (79 vs 49), jadi bias ini sedikit lebih besar untuknya.
- **Satu seed per run**, tanpa interval kepercayaan.
- **Efek 960 tidak terpisah dari lama latih:** run 960 mendapat 4.214 langkah optimizer, run 640 mendapat 2.669. Tidak ada run v2bersih pada 960, dan model 640 tidak diuji pada inferensi 960.
- **Baseline vs v2bersih mengubah dua hal sekaligus:** label v1 ke v2 dan pembuangan 12 frame.
- **Frame baru dipilih dengan model baseline** (ketidakpastian) dan draftnya sebagian dari model yang sama; label akhir dari review satu orang.
- **Kecepatan laptop, bukan HP.** Noise antar pengukuran sekitar 10-20%.
- **Belum ada evaluasi test.** Itu tugas terpisah.

## 10. Berkas

| Berkas | Keterangan | Git |
|---|---|---|
| `tools/ronde2_pilih.py`, `ronde2_draft.py`, `ronde2_cek_bocor.py` | pemilihan frame, draft, cek kebocoran | commit |
| `tools/validasi_ronde2.py`, `bangun_dataset_ronde2.py` | validasi review, dataset v2bersih / v3 | commit |
| `tools/latih_ronde2.py`, `evaluasi_ronde2.py` | training dan evaluasi ronde 2 | commit |
| `docs/hasil-ronde2.md`, `docs/kelas.md` (v1.8), `docs/test-set.md` | dokumen | commit |
| `data/ronde2/` (LOG.md, csv), `data/ronde2-review/`, `data/dataset-*-v2bersih`, `-v3` | data kerja dan dataset | tidak |
| `runs/ronde2/<run>/`, `runs/ronde2/eval/` | bobot, log, metrik, plot, contact sheet | tidak |
| `models/ronde2/<run>_best.pt` | salinan best.pt | tidak |

Perintah:

```
python tools/bangun_dataset_ronde2.py v2bersih
python tools/bangun_dataset_ronde2.py v3
python tools/latih_ronde2.py --run r2-kotak-v2bersih      # lalu r2-kotak-v3, r2-kotak-v3-960, r2-seg-v3
python tools/evaluasi_ronde2.py --aksi val
python tools/evaluasi_ronde2.py --aksi kecepatan
```
