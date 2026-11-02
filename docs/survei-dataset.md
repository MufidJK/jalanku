# Survei Dataset Publik JalanKu

Terakhir diperbarui: 2 November 2026
Penanggung jawab: Kenzu

Dokumen ini mencatat dataset publik yang dipakai untuk melatih model JalanKu, dataset yang ditolak beserta alasannya, dan sumber data untuk tiap kelas. Daftar kelas mengikuti `docs/kelas.md` v1.2.

Status pencarian: **ditutup**. Kalau setelah pilot ada kelas yang lemah, solusinya tambah data kampus atau potongan SANPO, bukan cari dataset baru.

Rencana: beberapa dataset publik digabung jadi satu dataset JalanKu. Kelas tiap dataset dipetakan ke ID kelas JalanKu (0 sampai 9), kelas yang tidak dipakai dibuang.

Tanda **[CEK]** berarti informasinya belum diverifikasi. Tanda **(usulan)** berarti pemetaan kelas belum diputuskan tim.

## Ringkasan dataset yang lolos (6)

| No | Nama | Link | Jumlah gambar | Tipe label | Lisensi | Dipakai untuk kelas |
|----|------|------|---------------|------------|---------|---------------------|
| 1 | ROD-Dataset | [Kaggle](https://www.kaggle.com/datasets/abtinzandi/obstacle-detection-dataset), [Hugging Face](https://huggingface.co/datasets/Abtinzandi/Obstacle-Detection-Dataset-YOLO) | 24.326 | Kotak (YOLO TXT) | MIT | pohon, orang, kursi, tanaman_pot, kendaraan, pilar, tangga, jalan_kendaraan |
| 2 | OOD | [Roboflow](https://universe.roboflow.com/fpn/ood-pbnro) | 10.000 | Kotak | CC BY 4.0 | tepian (sumber utama), pilar, pohon, orang, kendaraan, kursi, tangga |
| 3 | Unstructured Road (India) | [Roboflow](https://universe.roboflow.com/mtechcv/unstructured-road-obstacle-detection) | 2.208 | Kotak | CC BY 4.0 | pohon, kendaraan, pilar, tangga |
| 4 | Dataset Lingkungan Trotoar Ver2 (Indonesia) | [Roboflow](https://universe.roboflow.com/dataset-lingkungan-trotoar-ver2/dataset-labelled) | 1.440 | Kotak | CC BY 4.0 | pohon, orang, kendaraan, pilar, tanaman_pot, kursi |
| 5 | Sidewalk Segment (lemnix) | [Kaggle](https://www.kaggle.com/datasets/lemnix/sidewalk-segment-dataset) | sekitar 2.200 | Segmentasi (mask PNG, VOC2007) | CC BY-SA 4.0 | jalur_jalan |
| 6 | SANPO (cadangan) | [Google Research](https://google-research-datasets.github.io/sanpo_dataset/) | sangat besar (sekitar 6 TB total) | Segmentasi | CC BY 4.0 | jalur_jalan, jalan_kendaraan, tepian (kalau masih kurang) |

## Detail per dataset

### 1. ROD-Dataset

- 24.326 gambar, 40.195 kotak, 25 kelas.
- Split bawaan: train 19.186 gambar, validation 3.511, test 1.629.
- Proyeknya mirip JalanKu (YOLOv8n di Android + TTS untuk tunanetra).
- Lisensi MIT, tapi sebagian gambar berasal dari Roboflow Universe dan ikut lisensi aslinya.
- **Tidak ada kelas Curb.** Jangan pakai ROD untuk tepian.

Daftar 25 kelas dan pemetaan:

| ID ROD | Kelas ROD | Kelas JalanKu |
|--------|-----------|---------------|
| 0 | Bike | (usulan) cek dulu isinya sepeda atau motor |
| 1 | Building | dibuang |
| 2 | Car | kendaraan |
| 3 | Person | orang |
| 4 | Stairs | tangga |
| 5 | Traffic sign | dibuang |
| 6 | Electrical Pole | pilar |
| 7 | Road | jalan_kendaraan (kotak, bukan mask) |
| 8 | Motorcycle | kendaraan |
| 9 | Dustbin | dibuang |
| 10 | Dog | dibuang |
| 11 | Manhole | dibuang |
| 12 | Tree | pohon |
| 13 | Guard rail | dibuang |
| 14 | Pedestrian crosswalk | dibuang |
| 15 | Truck | (usulan) kendaraan |
| 16 | Bus | (usulan) kendaraan |
| 17 | Bench | (usulan) kursi |
| 18 | Traffic Cone | dibuang |
| 19 | Fire hydrant | dibuang |
| 20 | Traffic Barrel | dibuang |
| 21 | Plant Pot | tanaman_pot |
| 22 | Electrical Box | dibuang |
| 23 | Chair | kursi |
| 24 | Bicycle Rack | dibuang |

### 2. OOD (Roboflow, versi asli)

- 10.000 gambar, 22 kelas rintangan outdoor untuk tunanetra.
- Sumber utama kelas **tepian** (dari curb).
- Pakai project `fpn/ood-pbnro` saja. **Jangan pakai salinannya "SOD" (lamao/sod-enect).**
- Halaman Universe hanya menampilkan 20 dari 22 nama kelas. [CEK] 2 kelas sisanya dilihat di `data.yaml` saat download.

Pemetaan 20 kelas yang terlihat:

| Kelas OOD | Kelas JalanKu |
|-----------|---------------|
| curb | tepian |
| pole | pilar |
| street_light | (usulan) pilar |
| tree | pohon |
| person | orang |
| car | kendaraan |
| motorcycle | kendaraan |
| bus, truck | (usulan) kendaraan |
| bench | (usulan) kursi |
| stairs | tangga |
| spherical_roadblock | (usulan) belum diputuskan, sama seperti bollard di Lingkungan Trotoar |
| bicycle, cane, dog, train, bus_stop, fire_hydrant, stop_sign, traffic_light | dibuang |

### 3. Unstructured Road Obstacle Detection (India)

- 2.208 gambar, foto kamera HP di jalur pejalan kaki jalanan India.
- [CEK] Split bawaan dilihat saat download.
- **Jangan dicampur dengan project lain yang mirip**: `mtechcv/obstacle-detection-bgabd` dan `unstructuredroadobstacles/unstructured-road-obstacles` (6.156 gambar, nama kelasnya juga rusak). Keduanya kemungkinan versi lain dari data yang sama dan bisa bikin gambar dobel.

| Kelas Unstructured Road | Kelas JalanKu |
|-------------------------|---------------|
| tree | pohon |
| vehicle | kendaraan |
| two-wheeler-vehicle | kendaraan |
| pole | pilar |
| stairs | tangga |
| signboard | dibuang |
| indian-street-dog | dibuang |

### 4. Dataset Lingkungan Trotoar Ver2 (Indonesia)

- 1.440 gambar (sudah dicek, semua di split train). Angka 930 yang sempat terlihat sebelumnya kemungkinan jumlah gambar di satu versi dataset.
- Satu-satunya dataset Indonesia yang dipakai. POV pejalan kaki di trotoar kota Indonesia, gambar landscape.
- Versi "Dataset 2 PseudoLabelled - v8 Fixed": label dibuat otomatis, tapi dari cek visual kotaknya rapi. Sekitar 9 sampai 16 kotak per gambar.
- Kemungkinan berasal dari frame video (banyak gambar mirip). Aman karena hanya dipakai untuk training.
- Pakai project ini saja. Jangan pakai salinannya (Temp-1, Dataset 2 PseudoLabelled by Riset Image, final_model_dataset_testing, contoh, My First Project).
- **Nama kelas rusak** (sudah dikonfirmasi): teks README Roboflow terbaca jadi nama kelas, misalnya "Roboflow is an end-to-end computer vision platform that helps you" dan "==============================". Saat download, petakan ulang lewat nomor kelas di `data.yaml`, dicocokkan dengan warna kotak di beberapa gambar.
- Nama kelas asli menurut halaman dataset: bangku, mobil, motor, orang, pilar, plang, pot, tembok, tempat sampah, tiang.
- Pemetaan sementara dari cek visual:

| Warna kotak | Isi | Kelas JalanKu |
|-------------|-----|---------------|
| hijau-limau | batang pohon dan palem | pohon |
| biru muda | mobil | kendaraan |
| ungu | motor | kendaraan |
| merah | orang | orang |
| pink muda | tiang lampu | pilar |
| oranye | bollard, balok beton | (usulan) pilar atau dibuang |
| toska | plang | dibuang |
| kuning, biru tua, magenta | tempat sampah, pot, lainnya | [CEK] saat download |

### 5. Sidewalk Segment (lemnix)

- Format VOC2007 segmentasi, mask PNG di folder `SegmentationClass`, sekitar 2.200 gambar, 1,42 GB.
- Trotoar dengan guiding block kuning, POV pejalan kaki (China). Dipakai untuk **jalur_jalan**.
- Sebagian gambar adalah salinan yang diputar. **Salinan dan aslinya harus masuk split yang sama** supaya tidak bocor.
- File `test.txt` kosong (0 B).
- Lisensi CC BY-SA 4.0: kalau dataset turunan kita dipublikasikan, lisensinya harus sama.
- [CEK] Daftar kelas yang ada di mask, dilihat saat download.

### 6. SANPO (cadangan)

- Dataset Google, POV mata dan dada, wajah dan plat nomor sudah diblur.
- Taksonominya mencakup road, curb, sidewalk, paved trail.
- Ukuran total sekitar 6 TB, jadi **download selektif** lewat `gsutil` (lensa kiri + segmentation mask saja).
- Hanya dipakai kalau jalur_jalan atau jalan_kendaraan masih kurang setelah pilot.

## Peta kelas ke sumber data

| ID | Kelas | Sumber |
|----|-------|--------|
| 0 | pilar | ROD (Electrical Pole), OOD (pole, street_light), Unstructured Road (pole), Lingkungan Trotoar (tiang lampu); pilar gedung dari video kampus |
| 1 | pohon | ROD, OOD, Unstructured Road, Lingkungan Trotoar |
| 2 | tepian | OOD (curb) (+ SANPO) |
| 3 | orang | ROD, OOD, Lingkungan Trotoar |
| 4 | tanaman_pot | ROD (Plant Pot), Lingkungan Trotoar |
| 5 | kursi | ROD (Chair, Bench), OOD (bench), Lingkungan Trotoar (bangku) |
| 6 | kendaraan | ROD, OOD, Unstructured Road, Lingkungan Trotoar |
| 7 | jalur_jalan | lemnix (+ SANPO), video kampus |
| 8 | jalan_kendaraan | ROD (Road, kotak) (+ SANPO); video kampus belum ada rekaman jalan kendaraan |
| 9 | tangga | ROD, OOD, Unstructured Road, video kampus |

## Hal yang perlu dicek saat penggabungan

- **Definisi label tiap dataset bisa beda dengan aturan kita.** Contoh: aturan kita untuk pohon hanya batang, tapi kotak "tree" di dataset publik kemungkinan mencakup seluruh pohon termasuk daun. Kendaraan di aturan kita hanya yang terparkir, sedangkan dataset publik melabel semua kendaraan. Cek beberapa gambar per kelas sebelum digabung.
- **Label bolong**: objek yang ada di gambar tapi tidak dilabel karena dataset aslinya tidak punya kelas itu (misalnya tepi trotoar di gambar ROD). Dicek saat pilot.
- **Keseimbangan**: ROD jauh lebih besar dari dataset lain dan data kampus. Ambil subset secukupnya.

## Dataset yang ditolak (11)

| Nama | Alasan |
|------|--------|
| light-poles (samuelayman) | foto drone, bukan POV pejalan kaki |
| dngomnh/sidewalk | tanpa label (cadangan jauh: ambil 100-200 gambar lalu label sendiri) |
| sidewalk-cracks (ansariusama152) | isinya retakan, bukan rintangan |
| PAVE | tidak ada gambar, hanya merujuk ke SANPO |
| SOD | salinan OOD |
| PEDESTRIAN | label per video, tanpa kotak |
| OD Obstacle Dataset (GitHub TW0521) | gabungan COCO/VOC/TT100K, lisensi tidak jelas |
| SideGuide | perlu formulir izin, daftar kelas tidak publik, kamera di kursi roda |
| Freiburg | data robot + LiDAR |
| RampNet | panorama Street View |
| uB-VisioGeoloc | tidak ada link download |

Juga tidak bisa dipakai: ITOD Indonesian Traffic Obstacle Dataset (kamera mobil), data skripsi ITS Surabaya tentang trotoar (tidak publik), guidio-blind-assist (tidak ada dataset), dataset captioning trotoar Indonesia (bukan label deteksi).

## Catatan penting

- **Atribusi wajib**: dataset CC BY 4.0 dan CC BY-SA 4.0 harus disebut nama pembuat dan link-nya di laporan akhir.
- Dataset tidak di-commit ke repo. Simpan di laptop atau Drive.
- Jumlah data publik yang dipakai diambil secukupnya supaya seimbang dengan data kampus. Data kampus tetap yang paling penting.