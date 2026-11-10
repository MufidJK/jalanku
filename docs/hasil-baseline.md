# Hasil Baseline JalanKu (kotak + segmentasi)

Status: hasil training dan evaluasi pada **val kampus** (54 frame), 10 November 2026. Belum ada evaluasi test (label lokasi test `selasar-lt11`, `pot-lt11`, `taman-ubm` belum ada).
Semua angka di dokumen ini berasal dari run sebenarnya (`runs/baseline/<run>/meta.json`, `results.csv`, dan `runs/baseline/eval/`), tidak ada estimasi. Folder `runs/` dan `models/` tidak masuk Git.

Ringkasan satu paragraf: baseline YOLO26n mencapai **mAP50 0,455 / mAP50-95 0,263** untuk model kotak (data gabung) dan **mask mAP50 0,634 / mAP50-95 0,523** untuk segmentasi (data kampus saja). Data publik menaikkan mAP kotak sebesar +0,036 (mAP50) dan +0,040 (mAP50-95) dibanding kampus saja, tetapi F1 pada conf terbaik hampir sama (0,443 vs 0,448), dan selisih per kelas sebagian besar kecil dibanding ketidakpastian val yang sempit (lihat Batasan). Kelas tipis (pilar, pohon) dan objek kecil masih sangat lemah.

## 1. Environment

| Item | Nilai |
|---|---|
| GPU | NVIDIA GeForce RTX 4060 Laptop, 8 GB (8.188 MiB), driver 596.36 |
| Software | Python 3.12.10, torch 2.14.1+cu132 (CUDA 13.2, cuDNN 9.24), ultralytics 8.4.188 |
| Sistem | Windows 11 (10.0.26300), CPU Intel Core i7-13620H (10 core fisik / 16 thread), RAM 17 GB total (±2,5 GB bebas saat training), disk bebas 107 GB |
| Bobot awal | `yolo26n.pt` dan `yolo26n-seg.pt` (COCO resmi Ultralytics, rilis v8.4.0) di `models/pretrained/`. SHA-256: `9B09CC8B...AD4FEF` (detect), `361FBFAB...B71E73F` (seg) |
| Commit repo saat run | `2db6253` (skrip training/evaluasi belum di-commit) |

Catatan environment: variabel `OMP_NUM_THREADS=1` aktif di shell yang dipakai. Ini tidak mempengaruhi training (dataloader memakai 4 worker), tetapi mempengaruhi pengukuran CPU (lihat bagian 6).

## 2. Perintah dan pengaturan

Semua run dari root repo, satu per satu (tidak paralel):

```
python tools/latih_baseline.py --run kotak-gabung
python tools/latih_baseline.py --run kotak-kampus
python tools/latih_baseline.py --run seg-kampus
python tools/evaluasi_baseline.py                                                         # val, galat, contact sheet, kecepatan
python tools/evaluasi_baseline.py --aksi cm025                                            # confusion matrix conf 0,25
python tools/evaluasi_baseline.py --aksi kecepatan --out runs/baseline/eval/kecepatan_koreksi   # kecepatan setelah perbaikan thread
```

Pengaturan sama untuk semua run: `seed=0`, `deterministic=True`, `imgsz=640`, `batch=16`, `workers=4`, `cache=False`, AMP aktif (lolos pengecekan), augmentasi dan hyperparameter default Ultralytics (tidak ada yang diubah, termasuk `fliplr`). Optimizer `auto` memilih **AdamW** di ketiga run (iterasi < 10.000; lr 0,000833 untuk kotak, 0,001429 untuk seg), `nbs=64` sehingga accumulate = 4.

| Run | Model | Data (train / val) | Epoch maks | Patience |
|---|---|---|---|---|
| `kotak-gabung` | yolo26n | gabung: 3.080 gambar (kampus x4 + publik 2.300) / kampus val 54 | 100 | 30 |
| `kotak-kampus` | yolo26n | kampus: 195 / 54 (ablasi, tanpa oversampling) | 300 | 100 |
| `seg-kampus` | yolo26n-seg | `dataset-gabung-seg` = kampus saja: 195 / 54 | 300 | 100 |

Epoch maks dan patience `kotak-kampus` dan `seg-kampus` dinaikkan dari rencana awal (150/50) menjadi 300/100 atas keputusan Jeka, supaya perbandingan tidak tercampur kurang latih akibat langkah optimizer per epoch yang jauh lebih sedikit pada data kecil.

### Waktu dan langkah optimizer (dari `meta.json`)

| Run | Epoch berjalan | Best epoch | Berhenti karena | Waktu latih | Batch diproses | **Langkah optimizer** | Langkah / epoch | VRAM puncak (reserved) |
|---|---|---|---|---|---|---|---|---|
| `kotak-gabung` | 69 | 39 | early stop (patience 30) | 2.866 s (47,8 mnt) | 13.317 | **3.466** | 50,2 | 2,65 GiB |
| `kotak-kampus` | 160 | 60 | early stop (patience 100) | 506 s (8,4 mnt) | 2.080 | **529** | 3,3 | 2,77 GiB |
| `seg-kampus` | 227 | 127 | early stop (patience 100) | 1.409 s (23,5 mnt) | 2.951 | **747** | 3,3 | 3,48 GiB |

Langkah optimizer dihitung dari pemanggilan `optimizer.step()` yang benar-benar terjadi (langkah yang dilewati GradScaler karena gradien inf tidak terhitung); tidak ada run yang di-resume, jadi tidak ada epoch yang terhitung dua kali.

**Pengamatan penting:** walau batas epoch dinaikkan ke 300, kedua run kampus berhenti lebih awal (epoch 160 dan 227) karena metrik val tidak membaik selama 100 epoch. Jadi `kotak-kampus` tetap hanya mendapat **529 langkah optimizer, 6,6 kali lebih sedikit** daripada `kotak-gabung` (3.466). Dengan patience 100, ini menunjukkan bahwa menambah epoch tidak lagi menaikkan metrik val untuk data kampus saja, tetapi **ini tidak membuktikan** bahwa jumlah langkah tidak berpengaruh: perbedaan langkah (dan ukuran data) tetap menjadi bagian dari perbandingan gabung vs kampus.

## 3. Hasil model kotak (val kampus, 54 frame, 319 instance)

P, R, F1 adalah nilai pada conf yang memaksimalkan F1 rata-rata kelas (conf 0,302 untuk gabung, 0,300 untuk kampus). mAP dihitung pada conf 0,001 (cara standar Ultralytics). **Kelas dengan n < 20 ditandai: angkanya kurang bisa dipercaya.** Angka di sini dari evaluasi ulang `best.pt` dan bisa berbeda tipis dari angka di log training (mis. 0,2612 vs 0,263 untuk mAP50-95 gabung) karena pengaturan batch validasi berbeda.

### 3.1 `kotak-gabung` (`models/baseline/kotak-gabung_best.pt`)

| mAP50 | mAP50-95 | P | R | F1 |
|---|---|---|---|---|
| 0,455 | 0,263 | 0,561 | 0,409 | 0,443 |

| Kelas | n val | mAP50 | mAP50-95 | P | R | F1 | Catatan |
|---|---|---|---|---|---|---|---|
| pilar | 50 | 0,161 | 0,088 | 0,499 | 0,160 | 0,242 | |
| pohon | 10 | 0,089 | 0,035 | 0,000 | 0,000 | 0,000 | n < 20; tidak ada deteksi pohon di conf 0,302 |
| tepian | 45 | 0,263 | 0,080 | 0,334 | 0,356 | 0,344 | |
| orang | 52 | 0,605 | 0,365 | 0,780 | 0,538 | 0,637 | |
| tanaman_pot | 13 | 0,554 | 0,301 | 0,892 | 0,308 | 0,458 | n < 20 |
| kursi | 36 | 0,532 | 0,373 | 0,698 | 0,417 | 0,522 | |
| kendaraan | 108 | 0,544 | 0,273 | 0,620 | 0,491 | 0,548 | |
| tangga | 5 | 0,895 | 0,587 | 0,662 | 1,000 | 0,797 | n < 20 (hanya 5 instance) |

### 3.2 `kotak-kampus` (ablasi, `models/baseline/kotak-kampus_best.pt`)

| mAP50 | mAP50-95 | P | R | F1 |
|---|---|---|---|---|
| 0,420 | 0,223 | 0,558 | 0,422 | 0,448 |

| Kelas | n val | mAP50 | mAP50-95 | P | R | F1 | Catatan |
|---|---|---|---|---|---|---|---|
| pilar | 50 | 0,108 | 0,031 | 0,551 | 0,080 | 0,140 | |
| pohon | 10 | 0,024 | 0,014 | 0,230 | 0,100 | 0,139 | n < 20 |
| tepian | 45 | 0,289 | 0,093 | 0,312 | 0,356 | 0,332 | |
| orang | 52 | 0,636 | 0,349 | 0,700 | 0,615 | 0,655 | |
| tanaman_pot | 13 | 0,327 | 0,179 | 0,606 | 0,308 | 0,408 | n < 20 |
| kursi | 36 | 0,458 | 0,285 | 0,781 | 0,397 | 0,527 | |
| kendaraan | 108 | 0,521 | 0,242 | 0,556 | 0,521 | 0,538 | |
| tangga | 5 | 0,995 | 0,589 | 0,731 | 1,000 | 0,844 | n < 20 (hanya 5 instance) |

### 3.3 Perbandingan `kotak-gabung` vs `kotak-kampus`

| Kelas | n val | mAP50 gabung | mAP50 kampus | Selisih | mAP50-95 gabung | mAP50-95 kampus | Selisih | F1 gabung | F1 kampus | Catatan |
|---|---|---|---|---|---|---|---|---|---|---|
| pilar | 50 | 0,161 | 0,108 | +0,053 | 0,088 | 0,031 | +0,057 | 0,242 | 0,140 | |
| pohon | 10 | 0,089 | 0,024 | +0,065 | 0,035 | 0,014 | +0,021 | 0,000 | 0,139 | n < 20 |
| tepian | 45 | 0,263 | 0,289 | -0,027 | 0,080 | 0,093 | -0,013 | 0,344 | 0,332 | |
| orang | 52 | 0,605 | 0,636 | -0,031 | 0,365 | 0,349 | +0,016 | 0,637 | 0,655 | |
| tanaman_pot | 13 | 0,554 | 0,327 | +0,227 | 0,301 | 0,179 | +0,122 | 0,458 | 0,408 | n < 20 |
| kursi | 36 | 0,532 | 0,458 | +0,074 | 0,373 | 0,285 | +0,088 | 0,522 | 0,527 | |
| kendaraan | 108 | 0,544 | 0,521 | +0,023 | 0,273 | 0,242 | +0,031 | 0,548 | 0,538 | |
| tangga | 5 | 0,895 | 0,995 | -0,100 | 0,587 | 0,589 | -0,002 | 0,797 | 0,844 | n < 20 |
| **semua** | 319 | 0,455 | 0,420 | +0,036 | 0,263 | 0,223 | +0,040 | 0,443 | 0,448 | |

Pada conf tetap 0,25 (IoU 0,5): gabung TP 126 / FP 108 / FN 193 (F1 0,456), kampus TP 135 / FP 139 / FN 184 (F1 0,455).

**Interpretasi (jujur):**
- **Apakah data publik membantu?** Sedikit, dan hanya di sisi mAP. mAP50 naik +0,036 dan mAP50-95 +0,040, tetapi F1 pada titik operasi praktis sama (0,443 vs 0,448; di conf 0,25: 0,456 vs 0,455). Gabung memberi lebih sedikit false positive (108 vs 139) dengan recall sedikit lebih rendah (126 vs 135 TP).
- **Kelas yang tampak terbantu:** `tanaman_pot` (+0,227 mAP50, tetapi n = 13 sehingga sangat rapuh), `kursi` (+0,074 / +0,088), `pilar` (+0,053 / +0,057; n = 50, tetapi angka mutlaknya tetap rendah: 0,161), `kendaraan` (+0,023 / +0,031, kecil). `pohon` naik +0,065 tetapi kedua model tidak berguna (0,089 dan 0,024; n = 10).
- **Kelas yang tidak terbantu atau mungkin dirugikan:** `tangga` (-0,100 mAP50, tetapi n = 5, selisih ini setara satu instance, dan mAP50-95 sama: 0,587 vs 0,589), `orang` (-0,031 mAP50, tetapi +0,016 mAP50-95), `tepian` (-0,027 / -0,013; n = 45). Kemungkinan penyebab (belum diuji): label publik tidak lengkap (orang dan kendaraan jauh sering tidak dilabel, lihat `docs/dataset-publik.md`), pseudo-label COCO, definisi `tepian` dari satu sumber (OOD) yang berbeda dari kampus, dan `tangga` publik yang terbatas pada tangga normal.
- **Seberapa kuat kesimpulannya?** Lemah. Val hanya 3 lokasi dan 319 instance, 76% instance (243) berasal dari satu lokasi (`dapsut`), hanya satu seed, dan tidak ada interval kepercayaan. Selisih sekitar ±0,03 per kelas tidak bisa dibedakan dari noise. Yang bisa dikatakan dengan cukup aman hanya arah umum: gabung ≥ kampus pada mAP, setara pada F1.
- Selisih langkah optimizer (3.466 vs 529) dan ukuran data ikut menjadi bagian dari "efek data publik"; ablasi ini tidak memisahkannya.

## 4. Hasil model segmentasi (`seg-kampus`, val kampus: 54 frame, 67 instance)

`models/baseline/seg-kampus_best.pt`. P, R, F1 pada conf terbaik (box 0,685; mask 0,699).

| Jenis | mAP50 | mAP50-95 | P | R | F1 |
|---|---|---|---|---|---|
| box | 0,648 | 0,530 | 0,890 | 0,568 | 0,677 |
| mask | 0,634 | 0,523 | 0,883 | 0,554 | 0,665 |

Per kelas (mask):

| Kelas | n val | mAP50 | mAP50-95 | P | R | F1 | Catatan |
|---|---|---|---|---|---|---|---|
| jalur_jalan | 33 | 0,613 | 0,468 | 0,830 | 0,515 | 0,636 | |
| jalan_kendaraan | 23 | 0,899 | 0,798 | 0,900 | 0,783 | 0,837 | |
| tangga | 11 | 0,390 | 0,303 | 0,921 | 0,364 | 0,521 | n < 20 |

Per kelas (box dari model segmentasi):

| Kelas | n val | mAP50 | mAP50-95 | P | R | F1 | Catatan |
|---|---|---|---|---|---|---|---|
| jalur_jalan | 33 | 0,613 | 0,500 | 0,821 | 0,515 | 0,633 | |
| jalan_kendaraan | 23 | 0,942 | 0,820 | 0,935 | 0,826 | 0,877 | |
| tangga | 11 | 0,390 | 0,270 | 0,914 | 0,364 | 0,520 | n < 20 |

Tambahan: IoU piksel agregat pada conf 0,25 (gabungan semua frame val): jalur_jalan 0,636, jalan_kendaraan 0,767, tangga 0,788. Ini ukuran tambahan dari skrip evaluasi, bukan metrik bawaan Ultralytics.

## 5. Plot Ultralytics

Plot bawaan `val` (conf 0,001, untuk kurva dan mAP) ada di:

| Run | Folder | Berkas penting |
|---|---|---|
| kotak-gabung | `runs/baseline/eval/kotak-gabung-val/` | `confusion_matrix.png`, `confusion_matrix_normalized.png`, `BoxPR_curve.png`, `BoxF1_curve.png`, `BoxP_curve.png`, `BoxR_curve.png`, `val_batch*_pred.jpg` |
| kotak-kampus | `runs/baseline/eval/kotak-kampus-val/` | sama |
| seg-kampus | `runs/baseline/eval/seg-kampus-val/` | sama, ditambah `MaskPR_curve.png`, `MaskF1_curve.png`, `MaskP_curve.png`, `MaskR_curve.png` |

**Peringatan membaca confusion matrix bawaan:** karena dihitung di conf 0,001, kolom/baris `background` membengkak (mis. gabung: 1.028 FP pilar, 1.149 FP tepian, 1.122 FP kendaraan) dan tidak menggambarkan titik operasi. Untuk itu ditambahkan versi conf 0,25 (matriks mentah dan ternormalisasi) di `runs/baseline/eval/<run>-val-conf025/confusion_matrix.png` dan `confusion_matrix_normalized.png`. Angka TP di matriks Ultralytics sedikit berbeda dari tabel galat di bagian 7 karena aturan pencocokan berbeda.

Kurva training per run: `runs/baseline/<run>/results.png`, `results.csv`. Log: `runs/baseline/<run>/train.log`.

## 6. Kecepatan inferensi (kecepatan LAPTOP, bukan HP)

fp32, tanpa ekspor (PyTorch langsung), batch 1, `imgsz=640` (sisi panjang; Ultralytics hanya mem-padding ke kelipatan 32), conf 0,25, warm-up 10 prediksi, **median** atas 54 frame val, preprocess/inference/postprocess dipisah. File: `runs/baseline/eval/kecepatan_koreksi/kecepatan.json`.

| Model | Perangkat | Preprocess (ms) | Inference (ms) | Postprocess (ms) | Total (ms) | FPS | p95 total (ms) |
|---|---|---|---|---|---|---|---|
| kotak-gabung | GPU (RTX 4060 Laptop) | 1,3 | 9,8 | 1,3 | 12,6 | 79,6 | 17,3 |
| kotak-gabung | CPU 1 thread | 2,1 | 59,3 | 0,6 | 62,3 | 16,1 | 85,9 |
| kotak-gabung | CPU 10 thread | 1,6 | 32,6 | 0,7 | 35,1 | 28,5 | 50,5 |
| kotak-kampus | GPU | 1,3 | 9,9 | 1,3 | 13,0 | 77,1 | 17,5 |
| kotak-kampus | CPU 1 thread | 1,7 | 51,5 | 0,6 | 53,9 | 18,6 | 67,8 |
| kotak-kampus | CPU 10 thread | 1,5 | 34,0 | 0,7 | 36,1 | 27,7 | 50,0 |
| seg-kampus | GPU | 1,5 | 12,9 | 1,8 | 16,4 | 61,1 | 21,2 |
| seg-kampus | CPU 1 thread | 1,8 | 77,8 | 2,4 | 83,1 | 12,0 | 97,0 |
| seg-kampus | CPU 10 thread | 1,5 | 43,8 | 2,0 | 47,6 | 21,0 | 56,8 |

Catatan kecepatan:
- Model akhir untuk perbandingan: `kotak-gabung` (box) dan `seg-kampus` (segmentasi). `kotak-kampus` berarsitektur sama dengan `kotak-gabung` sehingga kecepatannya sama dalam batas noise.
- Ini kecepatan laptop (RTX 4060 Laptop, i7-13620H). **Bukan kecepatan HP**; kecepatan di HP harus diukur sendiri setelah ekspor (TFLite/NCNN, INT8/FP16).
- Noise antar-run sekitar 10-20% (pengukuran GPU yang sama pada run evaluasi pertama memberi 12,9 ms untuk gabung dan 14,0 ms untuk seg).
- Pengukuran CPU pertama (`runs/baseline/eval/kecepatan.json` dan bagian Kecepatan di `runs/baseline/eval/tabel.md`) **salah label**: Ultralytics memanggil `torch.set_num_threads(8)` saat predict pertama di CPU sehingga baris "1 thread" dan "10 thread" sebenarnya berjalan di 8 thread. Hasil yang benar ada di `kecepatan_koreksi/` (jumlah thread diset setelah setup dan diverifikasi sesudah pengukuran). Berkas yang salah (`eval/kecepatan.json` dan bagian Kecepatan lama di `eval/tabel.md`) sudah dihapus pada 10 Nov 2026 atas persetujuan Mufid.

## 7. Analisis galat dan contoh kualitatif

Dasar: prediksi conf >= 0,25, IoU >= 0,5, pencocokan greedy per kelas (`runs/baseline/eval/<run>/galat.json`). Contact sheet 16 frame val (8 terbaik + 8 terburuk, bergantian antar lokasi; kiri GT, kanan prediksi), model `kotak-gabung`, `kotak-kampus`, `seg-kampus`:

| Run | Contact sheet 16 | Bagus (8) | Terburuk (8) |
|---|---|---|---|
| kotak-gabung | `runs/baseline/eval/kotak-gabung/kontak_16.jpg` | `.../kontak_bagus.jpg` | `.../kontak_terburuk.jpg` |
| kotak-kampus | `runs/baseline/eval/kotak-kampus/kontak_16.jpg` | `.../kontak_bagus.jpg` | `.../kontak_terburuk.jpg` |
| seg-kampus | `runs/baseline/eval/seg-kampus/kontak_16.jpg` | `.../kontak_bagus.jpg` | `.../kontak_terburuk.jpg` |

Skor pemilihan: F1 per frame (kotak) atau rata-rata IoU per kelas (segmentasi). Daftar frame ada di `kontak_pilihan.json`. Catatan: yang saya periksa secara visual adalah sheet `kotak-gabung` (bagus dan terburuk) dan `seg-kampus` (bagus dan terburuk); sheet `kotak-kampus` hanya dibuat, belum saya lihat satu per satu, jadi pernyataan kualitatif di bawah hanya berlaku untuk dua model itu.

### 7.1 Galat per kelas, model kotak (conf 0,25)

| Kelas | gabung TP / FP / FN | kampus TP / FP / FN |
|---|---|---|
| pilar | 8 / 6 / 42 | 2 / 5 / 48 |
| pohon | 0 / 3 / 10 | 0 / 4 / 10 |
| tepian | 14 / 38 / 31 | 23 / 49 / 22 |
| orang | 28 / 9 / 24 | 31 / 14 / 21 |
| tanaman_pot | 2 / 0 / 11 | 4 / 3 / 9 |
| kursi | 17 / 9 / 19 | 15 / 8 / 21 |
| kendaraan | 53 / 41 / 55 | 55 / 52 / 53 |
| tangga | 4 / 2 / 1 | 5 / 4 / 0 |

Recall menurut ukuran objek (akar luas kotak, piksel pada gambar 640):

| Ukuran | GT | Ditemukan gabung (recall) | Ditemukan kampus (recall) |
|---|---|---|---|
| < 32 | 48 | 6 (0,125) | 8 (0,167) |
| 32-64 | 125 | 41 (0,328) | 41 (0,328) |
| 64-128 | 112 | 57 (0,509) | 62 (0,554) |
| >= 128 | 34 | 22 (0,647) | 24 (0,706) |

Hasil per lokasi val (gabung, F1 pada conf 0,25): dapsut 0,45 (GT 243), perpus-lt9-ubm-tower 0,49 (GT 54), tangga-naik-lt9-lt10-ubm-tower 0,43 (GT 22). Kampus: 0,45 / 0,46 / 0,51.

### 7.2 Temuan (yang terlihat di sheet dan angka)

1. **Recall rendah secara umum, terutama objek kecil dan tipis.** Pilar hanya 8 dari 50 ditemukan (gabung); objek kecil (< 32 px) recall 12,5% dan objek 32-64 px hanya 32,8%; recall baru melewati separuh di kelas ukuran 64-128 px (0,509). Di sheet terlihat jajaran tiang kaca/rangka di fasad (frame `tangga-naik-lt9-lt10`) berlabel pilar di GT (10 FN, 0 TP), sedangkan model tidak memprediksinya.
2. **Eskalator terbaca `tangga`.** Pada frame `tangga-naik-lt9-lt10` yang berisi eskalator (GT tidak melabel eskalator sesuai `kelas.md` v1.5), model kotak memberi `tangga` pada eskalator. Kedua FP tangga `kotak-gabung` (conf 0,80 dan 0,45) jatuh di frame `tangga-naik-lt9-lt10` dan di sheet terlihat menutupi eskalator; `kotak-kampus` punya FP tangga conf 0,76 di lokasi yang sama (4 FP tangga total, tidak saya lihat satu per satu). Ini kasus yang wajar diperkirakan: hard negative eskalator belum ada di data latih (dugaan, belum diuji).
3. **Tangga gelap terlewat.** Satu frame tangga yang gelap (GT: satu kotak tangga besar) tidak mendapat deteksi tangga dari model kotak (hanya satu `orang` FP); model segmentasi juga hanya menutup bagian bawah tangga yang terang pada frame lain, anak tangga atas yang gelap tidak tercakup.
4. **Deretan motor rapat di `dapsut`.** Frame parkir motor padat memberi banyak kotak kendaraan prediksi, termasuk kotak bertumpuk, sementara GT sengaja tidak melabel barisan belakang yang rapat (keputusan Checkpoint 4, `data/pilot-v2/LOG.md`). Kendaraan FP gabung 41 dan kampus 52, semuanya di `dapsut`; ini konsisten dengan batasan label tersebut, tetapi **tidak saya cek satu per satu**, jadi sebagian bisa jadi galat model yang sebenarnya.
5. **`tepian` banyak false positive.** 38 FP (gabung) dan 49 (kampus) berbanding 14 dan 23 TP; semua FP gabung (38 dari 38) ada di `dapsut`. Di sheet terlihat kotak tepian di area gerbang dan zebra cross dapsut (GT juga melabel tepian di sana). Tidak diperiksa per kotak, jadi belum jelas berapa yang salah model dan berapa yang label hilang. Model kampus saja justru punya recall tepian yang sama (0,356) dan TP lebih banyak (23 vs 14), tetapi FP juga lebih banyak.
6. **Tanaman pot kecil di rak terlewat.** Di `perpus-lt9-ubm-tower` GT melabel pot di rak; model gabung hanya menemukan 2 dari 13 pot pada conf 0,25 (recall 0,31 pada conf terbaik). Catatan: `kelas.md` memutuskan "pot kecil di rak tidak dilabel", sedangkan GT val perpus tampak melabel pot di rak; aturan label ini perlu dicek (lihat rekomendasi).
7. **Duplikat kotak kursi/orang di jarak jauh.** Frame perpus dengan banyak kursi jauh memberi kotak kursi/orang bertumpuk kecil; kursi dan orang yang dekat terdeteksi baik.
8. **Segmentasi: `jalur_jalan` vs `jalan_kendaraan` tertukar.** Matriks conf 0,25: 3 GT jalan_kendaraan diprediksi jalur_jalan, 2 sebaliknya; selain itu 12 jalur_jalan dan 7 tangga terlewat, dan 10 jalur_jalan serta 5 jalan_kendaraan prediksi tanpa GT. Di sheet: karpet lobi perpus (GT jalur_jalan) diprediksi jalan_kendaraan; permukaan berpasir/jalan di dapsut (GT jalan_kendaraan) diprediksi jalur_jalan; pada frame parkir motor, mask jalan_kendaraan menutup tembok dan motor.
9. **Yang tidak saya temukan / tidak dicek:** dari frame yang saya lihat (16 frame model kotak-gabung, 16 frame seg-kampus) tidak ada FP yang jelas berasal dari pantulan kaca atau poster; kasus pelat landasan eskalator juga tidak muncul sebagai FP yang terlihat. Daftar FP lengkap ada di `galat.json` (`fp_daftar`), tetapi belum saya telusuri seluruhnya.

## 8. Batasan

- **Val kecil dan sempit:** 54 frame dari 3 lokasi, 319 instance (kotak) dan 67 (segmentasi). 76% instance kotak ada di `dapsut`. Frame dalam satu lokasi berasal dari video yang sama sehingga saling berkorelasi.
- **Kelas dengan n < 20:** pohon (10), tanaman_pot (13), tangga kotak (5), tangga segmentasi (11). Angkanya tidak boleh dibaca sebagai kemampuan model.
- **Val dipakai untuk memilih checkpoint:** `best.pt` dan early stopping memilih epoch terbaik di val yang sama dengan yang dilaporkan, jadi semua angka cenderung optimistis, dan efeknya mungkin lebih besar untuk run kampus (lebih banyak epoch yang dibandingkan: 160 dan 227 vs 69). Belum ada data test.
- **Satu seed, tanpa interval kepercayaan.** Selisih kecil antar run tidak bisa dibedakan dari noise.
- **Label publik tidak murni:** sebagian label adalah pseudo-label COCO (`yolo11x.pt`), objek kecil/jauh dibuang atau tidak dilabel, definisi kelas tidak sama dengan `kelas.md` (lihat `docs/dataset-publik.md`). Gambar ROD/OOD yang memuat pohon penuh dibuang, jadi pohon di data gabung hanya berasal dari Trotoar, Unstructured, dan kampus.
- **Label kampus:** dari autolabel + review satu orang; barisan objek rapat di belakang (parkiran, dapsut, lab) sengaja tidak dilabel; 15 frame blind dilabel manual.
- **Kamera monokular:** tidak ada informasi kedalaman; jarak objek tidak bisa diukur.
- **Kecepatan laptop, bukan HP.** Lihat bagian 6; juga `OMP_NUM_THREADS=1` di environment dan noise 10-20%.
- **Perbandingan gabung vs kampus tidak memisahkan penyebab:** ukuran data, oversampling kampus x4, dan jumlah langkah optimizer (3.466 vs 529) berubah bersamaan.
- Pengaturan baseline default (belum ada tuning); batch 16, `cache=False`, `deterministic=True`.

## 9. Rekomendasi putaran 2

Berdasarkan galat di val (bukan kesimpulan yang sudah diuji):

**Data yang perlu dilabel lebih dulu**
1. **Pilar dan objek tipis/kecil jauh** (recall pilar 0,16; objek < 32 px 12,5%): frame di `dapsut`, garasi/parkiran, jalan, tiang lampu, dan fasad kaca dengan banyak tiang. Putuskan juga aturan untuk rangka/sirip kaca di fasad (GT val melabelnya pilar).
2. **Hard negative eskalator** (eskalator terbaca tangga) dan frame tangga dengan cahaya redup/gelap; tambah frame tangga naik dan turun karena val hanya punya 5 (kotak) dan 11 (seg) instance.
3. **`tepian`:** banyak FP di `dapsut`. Perlu lebih banyak lokasi dengan kerb/zebra/batas jalan, termasuk frame tanpa tepian.
4. **`pohon` dan `tanaman_pot`** (n val 10 dan 13): perlu lebih banyak contoh dan val yang lebih besar supaya angkanya bisa dipercaya; cek ulang aturan "pot kecil di rak" yang tampak tidak konsisten dengan GT val perpus.
5. **Permukaan:** `jalur_jalan` vs `jalan_kendaraan` untuk karpet lobi dan permukaan ambigu di dapsut; tambah frame lobi/koridor dan jalan dengan marka; pertimbangkan aturan permukaan yang lebih tegas atau satu kelas "permukaan datar" untuk fase awal.
6. Prioritas lokasi mengikuti rencana Checkpoint 4: frame pengisi jeda di video panjang (`dapsut`, `perpus-lt9`, `parkiran-motor-b1`, `lorong-lt3-eskalator`, `samping-ubm`, `halaman-ubm`, `lorong-lt5`), dipilih lewat active learning (model baseline ini sebagai pre-label dan pemilih frame yang ragu).

**Yang bisa disetel (tidak dikerjakan sekarang)**
- Resolusi lebih besar (`imgsz` 960/1280) untuk objek kecil dan pilar; recall objek < 64 px sangat rendah.
- Ambang conf per kelas (conf F1 terbaik 0,30; beberapa kelas butuh ambang lain), dan penanganan duplikat kotak (NMS/IoU).
- Seimbangkan sampling per kelas dan oversampling kampus; jangan menambah epoch untuk gabung (best epoch 39 dari 69).
- Lebih dari satu seed dan val yang lebih besar/lokasi lebih banyak sebelum menyimpulkan efek data publik; pertimbangkan val terpisah dari pemilihan checkpoint.
- Ekspor ke format HP (TFLite/NCNN) dan ukur kecepatan sebenarnya di perangkat.

## 10. Berkas

| Berkas | Keterangan | Git |
|---|---|---|
| `tools/latih_baseline.py` | skrip training | di-commit |
| `tools/evaluasi_baseline.py` | skrip evaluasi (metrik, galat, contact sheet, kecepatan) | di-commit |
| `docs/hasil-baseline.md` | dokumen ini | di-commit |
| `models/baseline/<run>_best.pt` | salinan `best.pt` | di-gitignore (`*.pt`) |
| `models/pretrained/yolo26n*.pt` | bobot COCO | di-gitignore |
| `runs/baseline/<run>/` | bobot, `results.csv`, `train.log`, `meta.json`, plot training | di-gitignore (`runs/`) |
| `runs/baseline/eval/` | metrik, galat, plot val, contact sheet, kecepatan | di-gitignore |
| `runs/baseline/_smoke/` | smoke test (disimpan atas permintaan) | di-gitignore |
