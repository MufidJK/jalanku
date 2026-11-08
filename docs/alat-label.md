# Alat Label JalanKu

Versi 1.0, 7 November 2026. Dites oleh Mufid di laptop Windows (RTX 4060, X-AnyLabeling versi CPU). Percobaan awal oleh Nicksen (X-AnyLabeling 4.2.3).

## Ringkasan

- **Alat:** X-AnyLabeling 4.3.1, jalan lokal di Windows, data tidak keluar dari laptop.
- **Cara ngelabel:** semua objek dilabel sebagai **polygon dengan bantuan SAM** (Segment Anything 2.1 Tiny), bukan kotak manual.
- **Export:** YOLO Seg. Label polygon bisa dipakai untuk model segmentasi dan juga model kotak (Ultralytics mengubah polygon jadi kotak otomatis).
- **Rencana model:** dua model (keputusan Mufid sebagai lead, 6 Nov 2026), lihat bagian "Rencana model".

## Kenapa X-AnyLabeling

| Kebutuhan | Hasil |
|---|---|
| Install di Windows tanpa Docker atau hak admin | Ya, lewat `pip` di venv terpisah |
| Kotak dan polygon | Ya, dua-duanya |
| Bantuan AI | Ya, SAM (klik objek, polygon jadi otomatis) dan model YOLO untuk pre-label |
| Export format YOLO | Ya, YOLO HBB (kotak) dan YOLO Seg (segmentasi), dites terbaca Ultralytics |
| Data tetap lokal | Ya, label disimpan sebagai `.json` di sebelah gambar |
| Kerja bertiga | Bisa (satu file label per gambar, tiap orang pegang folder berbeda), belum dites |

Label Studio dan CVAT tidak dites. CVAT butuh Docker, Label Studio butuh server lokal; dua-duanya lebih berat dipasang dibanding X-AnyLabeling yang sudah memenuhi semua kebutuhan di atas.

## Cara install (Windows)

Pakai venv **terpisah** dari venv JalanKu, karena X-AnyLabeling membawa versi OpenCV, PyQt, dan ONNX Runtime sendiri yang bisa menimpa versi di `requirements.txt`.

```
mkdir C:\xanylabeling
cd C:\xanylabeling
py -3.12 -m venv venv
venv\Scripts\activate
python -m pip install -U pip
pip install "x-anylabeling-cvhub[cpu]"
xanylabeling version
```

Versi yang dites: `4.3.1`. Versi GPU butuh CUDA dan cuDNN tambahan; versi CPU sudah cukup untuk SAM Tiny.

Menjalankan aplikasi:

```
cd C:\xanylabeling
venv\Scripts\activate
xanylabeling
```

Jendela PowerShell biarkan terbuka selama aplikasi dipakai.

## Cara pakai

1. **File > Open Dir**, pilih folder gambar.
2. **Upload > Upload Label Classes File**, pilih `classes.txt` (10 kelas, urut sesuai `docs/kelas.md`, baris pertama = ID 0). Daftar ini **hilang setiap aplikasi ditutup**, jadi wajib di-upload ulang. Cek panel Labels berisi 10 kelas sebelum mulai.
3. **Ctrl+A** untuk membuka panel AI, pilih model **Segment Anything 2.1 (Tiny)** (download sekitar 150 MB, sekali saja), Output **Polygon**.
4. Untuk tiap objek:
   - **Q** lalu klik objek (titik positif). Klik lagi bagian yang belum ikut.
   - **E** lalu klik bagian yang salah ikut (titik negatif).
   - **B** untuk menghapus semua titik dan mulai ulang.
   - **F** untuk selesai, lalu pilih label.
5. **Ctrl+S** untuk simpan. Label tersimpan sebagai `.json` di sebelah gambar.

Contoh: `tanaman_pot` butuh 2 klik (satu di pot, satu di daun), karena pot dan tanaman dihitung satu objek.

## Hasil tes (5-6 November 2026)

Diuji di 2 frame kampus (dapsut dan lorong lt9).

| Cara | Waktu |
|---|---|
| Kotak manual | sekitar 1 menit per frame (5 objek), sekitar 5 detik per objek |
| Polygon manual (tes Nicksen) | sekitar 1 menit per objek |
| Polygon dengan SAM | sekitar 4 detik per objek, 1-3 klik |

Hasil SAM rapi: lantai (`jalur_jalan`) otomatis bolong di area pot sehingga tidak tumpang tindih, dan tangga ikut dengan pegangannya.

Kesimpulan: polygon dengan SAM sama cepat atau lebih cepat dari kotak manual, dan hasilnya lebih banyak dipakai.

## Export

Menu **Export > YOLO Seg** (atau YOLO HBB untuk kotak), lalu pilih `classes.txt`.

Dicek dengan Ultralytics 8.4.x: nomor kelas benar (contoh `4 tanaman_pot`, `7 jalur_jalan`, `9 tangga`), koordinat 0-1, terbaca tanpa error, dan bentuknya sama persis saat digambar ulang.

Hal yang wajib diperhatikan:

1. **Lokasi hasil export.** File `.txt` masuk ke folder `labels\` di **sebelah** folder gambar, bukan di dalamnya. Contoh: gambar di `data\tes-alat\` hasilnya di `data\labels\`. Kalau folder itu sudah ada, aplikasi bertanya: **Yes** = gabung, **No** = hapus folder lama, **Cancel** = batal. Supaya tidak saling timpa, satu folder gambar = satu export.
2. **YOLO Seg mengabaikan kotak, YOLO HBB mengabaikan polygon.** Tidak ada peringatan. Karena itu semua objek dilabel dengan satu cara saja: polygon.
3. **Gambar yang belum dilabel tetap dibuatkan `.txt` kosong.** Bagi YOLO, file kosong artinya "tidak ada objek". Hanya gambar yang sudah selesai dilabel yang boleh ikut training.

## Polygon bisa jadi kotak

Saat dataset polygon dibaca Ultralytics dalam mode deteksi (kotak), setiap polygon otomatis diubah jadi kotak yang pas. Jadi satu set label kampus bisa dipakai untuk model segmentasi dan model kotak sekaligus. Kebalikannya tidak bisa: label kotak tidak bisa diubah jadi polygon tanpa bantuan model lain.

Kalau label polygon dan kotak dicampur dalam satu dataset, Ultralytics hanya memakai kotaknya (polygon dibuang, ada peringatan di log).

## Rencana model

Dataset publik utama berformat kotak (ROD, OOD, Unstructured Road, Lingkungan Trotoar), sedangkan yang segmentasi hanya lemnix dan SANPO. Diputuskan memakai **dua model**:

| Model | Kelas | Data |
|---|---|---|
| Kotak (deteksi) | pilar, pohon, tepian, orang, tanaman_pot, kursi, kendaraan, tangga | Kampus (polygon jadi kotak) + 4 dataset publik kotak |
| Segmentasi | jalur_jalan, jalan_kendaraan, tangga | Kampus + lemnix (+ SANPO cadangan) |

Mulai kelas v1.5 (8 November 2026), **tangga masuk dua model**: model kotak untuk peringatan jarak, model segmentasi untuk bentuk dan arah tangga. Menurut `docs/survei-dataset.md`, lemnix hanya dipakai untuk jalur_jalan dan taksonomi SANPO yang tercatat hanya road, curb, sidewalk, paved trail, jadi sumber data segmentasi tangga saat ini hanya kampus (frame `tangga-naik*` dan frame lain yang ada tangganya). Belum dicek apakah SANPO punya kelas tangga.

Kelebihan: semua dataset publik terpakai, dan sesuai fungsi aplikasi (benda di depan + permukaan yang aman diinjak). Konsekuensi: dua model jalan bersamaan di HP, perlu optimasi saat tahap aplikasi.

Alternatif yang tidak dipilih:
- Satu model segmentasi, kotak dataset publik diubah jadi polygon otomatis pakai SAM (`yolo_bbox2segment` di Ultralytics). Hasil otomatis perlu dicek manual.
- Satu model kotak saja. Paling sederhana, tapi `jalur_jalan` dan `jalan_kendaraan` jadi kotak raksasa yang tidak berguna untuk navigasi.

## Temuan untuk panduan anotasi

Kasus yang muncul saat tes dan belum ada aturannya:
- Pohon jauh atau di balik pagar: dilabel atau tidak?
- Batang pohon tertutup daun: aturan "batang saja" susah dipraktekkan (bahan keputusan kelas v1.3).
- Tiang beton gerbang: termasuk `pilar` atau tidak?

## Belum dites

- Daftar kelas permanen (supaya tidak perlu upload `classes.txt` tiap buka aplikasi).
- Pre-label otomatis pakai model YOLO segmentasi COCO untuk orang, kendaraan, kursi, dan pot.
- Kecepatan SAM di laptop tanpa GPU NVIDIA.
- Alur kerja bertiga: membagi folder dan menggabungkan hasil.