# Dataset Publik JalanKu: Sumber, Atribusi, dan Pemetaan Kelas

Status: **final setelah Checkpoint P2** (10 November 2026).
Dokumen ini dipakai untuk atribusi di laporan akhir dan sebagai catatan pemetaan. Log detail (hitungan, gambar yang dibuang, kendala) ada di `data/publik/LOG.md` (lokal, tidak di-commit). Survei awal: `docs/survei-dataset.md`.

Data mentah dan hasil konversi ada di `data/publik/<nama>/{raw,jalanku}/` dan **tidak masuk Git**. Diproses oleh `tools/siapkan_publik.py`.

## Atribusi

| No | Dataset | Pembuat / workspace | Link | Lisensi | Versi yang dipakai | Diunduh |
|----|---------|---------------------|------|---------|--------------------|---------|
| 1 | ROD-Dataset | Abtin Zandi (Kaggle `abtinzandi`) | https://www.kaggle.com/datasets/abtinzandi/obstacle-detection-dataset | MIT (sebagian gambar berasal dari Roboflow Universe dan mengikuti lisensi aslinya; daftar sumber di `raw/citations.txt`) | salinan Kaggle, dibuat 5 Okt 2026 | 9 Nov 2026 |
| 2 | OOD | workspace Roboflow `fpn` | https://universe.roboflow.com/fpn/ood-pbnro | CC BY 4.0 | v1 (27 Mei 2023), tanpa augmentasi | 9 Nov 2026 |
| 3 | Unstructured Road Obstacle Detection | workspace Roboflow `mtechcv` | https://universe.roboflow.com/mtechcv/unstructured-road-obstacle-detection | CC BY 4.0 | v11 (16 Okt 2023), tanpa augmentasi | 9 Nov 2026 |
| 4 | Dataset Lingkungan Trotoar Ver2 (Indonesia) | workspace Roboflow `dataset-lingkungan-trotoar-ver2`, proyek `dataset-labelled`; diunduh dari fork `jeka-workspace/dataset-labelled-sqkiz` | https://universe.roboflow.com/dataset-lingkungan-trotoar-ver2/dataset-labelled | CC BY 4.0 | fork v1 (dibuat 9 Nov 2026, tanpa preprocessing dan augmentasi) | 9 Nov 2026 |
| 5 | Sidewalk Segment | pengguna Kaggle `lemnix` | https://www.kaggle.com/datasets/lemnix/sidewalk-segment-dataset | CC BY-SA 4.0 (turunan yang dipublikasikan wajib berlisensi sama) | salinan Kaggle (file tertanggal 17 Jun 2023) | 9 Nov 2026 |

## Pemetaan kelas

Model kotak: `0 pilar, 1 pohon, 2 tepian, 3 orang, 4 tanaman_pot, 5 kursi, 6 kendaraan, 7 tangga`.
Model segmentasi: `0 jalur_jalan, 1 jalan_kendaraan, 2 tangga`.
Kelas yang tidak tercantum = dibuang. Gambar dikecilkan ke 640 piksel sisi panjang (tidak pernah diperbesar).

### ROD (25 kelas, pemetaan lewat nama kelas)
| Kelas ROD | JalanKu |
|---|---|
| Bike, Car, Motorcycle, Truck, Bus | kendaraan |
| Person | orang |
| Stairs | tangga |
| Electrical Pole | pilar |
| Bench, Chair | kursi |
| Plant Pot | tanaman_pot |
| Tree | **gambar dibuang** (kotak menutup seluruh pohon, bentrok aturan batang saja; usulan, menunggu P1) |
| Road | dibuang (kotak jalan, bukan kelas kotak JalanKu) |
| Building, Traffic sign, Dustbin, Dog, Manhole, Guard rail, Pedestrian crosswalk, Traffic Cone, Fire hydrant, Teraffic Barrel (sic), Electrical Box, Bicycle Rack | dibuang |

### OOD (22 kelas, lewat nama)
| Kelas OOD | JalanKu |
|---|---|
| curb | tepian |
| pole, street_light, spherical_roadblock, warning_column | pilar |
| person | orang |
| car, motorcycle, bicycle, bus, truck | kendaraan |
| bench | kursi |
| stairs | tangga |
| tree | **gambar yang memuat tree dibuang seluruhnya** |
| bus_stop, crutch, dog, fire_hydrant, stop_sign, traffic_light, train, waste_container | dibuang |

### Unstructured Road v11 (7 kelas, lewat nama)
| Kelas | JalanKu |
|---|---|
| tree | pohon (batang; sudah dicek di sampel) |
| vehicle, two-wheeler | kendaraan |
| pole | pilar |
| stairs | tangga |
| signboard, dog | dibuang |

### Lingkungan Trotoar (nama kelas rusak, lewat ID)
| ID | Isi | JalanKu |
|---|---|---|
| 1 | motor | kendaraan |
| 9 | mobil | kendaraan |
| 2 | orang | orang |
| 3 | batang pohon | pohon |
| 4 | kolom bangunan | pilar |
| 6 | bollard, balok beton | pilar |
| 21 | tiang (lampu, listrik, rambu) | pilar |
| 5 | pot tanaman | tanaman_pot |
| 7 | kursi, bangku | kursi |
| 0, 8, 10, 11 | plang, tempat sampah, lampu lalu lintas, zebra cross | dibuang |
| 12-20 | 1 sampai 5 kotak per ID (total 20) | diabaikan |

### Sidewalk Segment (lemnix)
Mask VOC punya 2 nilai: 0 = latar, 1 = **jalur guiding block saja** (bukan seluruh trotoar). **Tidak dipakai** (keputusan P1): definisinya bentrok dengan `jalur_jalan` di `kelas.md`. Model segmentasi baseline hanya memakai data kampus. SANPO tidak diunduh.

## Tahap setelah P1: filter, pemilihan, isi label COCO

Dijalankan oleh `tools/siapkan_publik.py terpilih <nama>`. Hasil tiap kotak (asal `asli` atau `coco_fill`) tercatat di `data/publik/<nama>/manifest_kotak.csv` (lokal).

1. **Filter kotak kecil** (aturan `kelas.md`, di gambar 640 px): kelas umum sisi pendek minimal 32 px; pilar/pohon/tepian sisi panjang minimal 32 px dan sisi pendek minimal 8 px. Gambar yang jadi kosong dibuang.
2. **Pemilihan gambar:** Trotoar semua; Unstructured semua yang berlabel; OOD hanya gambar yang punya kelas selain orang/kendaraan; ROD hanya gambar yang punya tangga, tanaman_pot, atau kursi. Gambar ROD dan OOD yang memuat pohon penuh (`Tree`/`tree`) dibuang.
3. **Isi label COCO** (`yolo11x.pt`, conf 0.5, imgsz 640): person orang; car, motorcycle, bus, truck, bicycle kendaraan; chair, bench kursi; potted plant tanaman_pot. Kotak ditambahkan kalau IoU dengan kotak asli sekelas tidak lebih dari 0,5 dan lolos filter kotak kecil.
4. **Pengetat COCO fill** (saat penyusunan gabung): kotak COCO dibuang kalau bersarang (interseksi / luas kotak terkecil >= 0,8) di kotak asli sekelas, atau kalau IoU > 0,5 dengan kotak asli kelas lain (contoh: tangga terbaca kursi). Khusus `tanaman_pot`: kalau kotak COCO dan kotak asli bersarang, yang lebih besar dipakai (pot + tanaman, satu objek sesuai `kelas.md`) dan yang lebih kecil (pot saja) dibuang, dari sumber mana pun; kotak COCO yang menampung dua kotak pot asli atau lebih dibuang supaya dua objek tidak tergabung.
5. **Dedup ROD** (`siapkan_publik.py dedup rod`, sebelum pemilihan): ROD berisi banyak salinan augmentasi satu adegan (rotasi, cutout hitam, grayscale, flip; satu adegan bisa sampai 46 salinan). Dua gambar dianggap salinan kalau inlier ORB + RANSAC >= 30, atau kemiripan embedding ResNet50 >= 0,85 dengan himpunan kelas label asli identik. Gambar paling bersih (sedikit piksel hitam, bukan grayscale) dipertahankan; yang lain dibuang hanya kalau berpasangan langsung dengannya (tanpa chaining).

**Keterbatasan yang diketahui:**
- `tepian` dan `tangga` tidak bisa diisi (COCO tidak punya kelasnya). Gambar yang memuat tepian atau tangga yang tidak dilabel dataset aslinya tetap bolong.
- Label hasil COCO adalah pseudo-label, bukan label manusia. Ada false positive (contoh di ROD: tangga terbaca kursi, jaket terbaca orang) dan duplikat (kotak COCO tanaman_pot menutup pot plus tanaman di atas kotak ROD yang hanya pot).
- Objek di luar COCO (pilar, pohon) tetap hanya berasal dari label asli.
- Kotak kecil di bawah ambang dibuang dari label asli maupun COCO, jadi objek kecil di kejauhan menjadi latar.
- Dedup hanya dijalankan untuk ROD. Trotoar (frame video) dan dataset lain mungkin masih punya frame yang mirip; tidak dicek.
- 138 label duplikat persis dari label asli Trotoar (motor dan mobil digabung jadi kendaraan) dibuang otomatis oleh Ultralytics saat load.

## Penyusunan dataset gabung

Dijalankan oleh `tools/bangun_dataset_gabung.py --skip-nested 0.8 --skip-lintas-iou 0.5`.
- **Kotak** (`data/dataset-gabung-kotak`): train = kampus train (195 frame) di-oversample 4 kali (780) + publik terpilih 2.300 gambar (Trotoar 700, Unstructured 600, OOD 600, ROD 400; pemilihan round-robin berbasis kelas, seed 20261110). Total 3.080 gambar train, porsi kampus 25,3%. Val = kampus val saja (54 frame: dapsut, perpus-lt9-ubm-tower, tangga-naik-lt9-lt10-ubm-tower).
- **Segmentasi** (`data/dataset-gabung-seg`): kampus saja (195 train, 54 val), tanpa data publik.
- Instance train kotak setelah validasi Ultralytics: pilar 3.276, pohon 1.728, tepian 1.000, orang 2.089, tanaman_pot 769, kursi 1.818, kendaraan 3.803, tangga 829 (total 15.312). Val: 319 instance.
- Dataset tidak masuk Git. Asal tiap gambar ada di `sumber.csv` dan tiap kotak publik (asli/coco_fill, dipakai atau alasan dibuang) di `kotak_akhir.csv` di dalam folder dataset.

## Hal yang berlaku untuk semua dataset publik
- Definisi label tiap dataset tidak sama dengan `kelas.md` v1.5: tidak ada filter ukuran objek (campus: sisi pendek minimal 32 px di gambar 640, objek tipis 32 dan 8 px), kendaraan jauh sering tidak dilabel, orang sering tidak dilabel di dataset yang tidak punya kelas orang.
- Atribusi di laporan akhir wajib mencantumkan pembuat dan link di tabel atas.
