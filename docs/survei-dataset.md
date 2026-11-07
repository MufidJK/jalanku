# Survei Dataset Publik JalanKu

Terakhir diperbarui: 2 November 2026
Penanggung jawab: Kenzu

Dokumen ini mencatat dataset publik yang dipakai untuk melatih model JalanKu, dataset yang ditolak beserta alasannya, dan sumber data untuk tiap kelas. Daftar kelas mengikuti `docs/kelas.md` v1.2.

Status pencarian: **ditutup**. Kalau setelah pilot ada kelas yang lemah, solusinya tambah data kampus atau potongan SANPO, bukan cari dataset baru.

Rencana: beberapa dataset publik digabung jadi satu dataset JalanKu. Kelas tiap dataset dipetakan ke ID kelas JalanKu (0 sampai 9), kelas yang tidak dipakai dibuang.

Tanda **[CEK]** berarti informasinya belum diverifikasi.

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
| 0 | Bike | kendaraan (isinya campur sepeda dan motor; sejak v1.3 sepeda masuk kendaraan) |
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
| 15 | Truck | kendaraan |
| 16 | Bus | kendaraan |
| 17 | Bench | kursi |
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
- Halaman Universe hanya menampilkan 20 dari 22 nama kelas. Daftar lengkap dari `data.yaml` (urutan ID 0-21): bench, bicycle, bus, bus_stop, car, crutch, curb, dog, fire_hydrant, motorcycle, person, pole, spherical_roadblock, stairs, stop_sign, street_light, traffic_light, train, tree, truck, warning_column, waste_container. Dua kelas yang tidak tampil di halaman: `warning_column` dan `waste_container`. Di `data.yaml` tertulis `crutch`, di halaman tertulis `cane` (kemungkinan kelas yang sama, belum dicek di gambar).

Pemetaan 20 kelas yang terlihat:

| Kelas OOD | Kelas JalanKu |
|-----------|---------------|
| curb | tepian |
| pole | pilar |
| street_light | pilar (umumnya tiang penuh; foto malam kadang hanya kepala lampu) |
| tree | dibuang, gambar yang memuat tree tidak dipakai (kotak OOD menutup seluruh pohon termasuk daun, tidak cocok dengan aturan batang saja di v1.3) |
| person | orang |
| car | kendaraan |
| motorcycle, bicycle | kendaraan |
| bus, truck | kendaraan |
| bench | kursi (bangku taman utuh) |
| stairs | tangga |
| spherical_roadblock | pilar (sama seperti bollard) |
| crutch | dibuang (kemungkinan sama dengan cane) |
| waste_container | dibuang (tempat sampah tidak dilabel, sesuai aturan di kelas.md) |
| warning_column | pilar (sama seperti bollard) |
| cane, dog, train, bus_stop, fire_hydrant, stop_sign, traffic_light | dibuang |

### 3. Unstructured Road Obstacle Detection (India)

- 2.208 gambar, foto kamera HP di jalur pejalan kaki jalanan India.
- Versi yang dipakai: v11 (2023-10-16), tanpa augmentasi. Versi terbaru (v16) tidak dipakai karena bagian train-nya digandakan oleh augmentasi (5.080 gambar). Split bawaan v11: train 2.540, valid 296, test 0 (total 2.836 gambar). Angka 2.208 di atas adalah jumlah di tab Images halaman project, selisihnya dengan v11 belum dijelaskan.
- Kelas di `data.yaml` v11 (nc 7, ID 0-6): dog, pole, signboard, stairs, tree, two-wheeler, vehicle. Catatan: `data.yaml` hasil download ini menyebut project ID `obstacle-detection-bgabd`, yang sama dengan salinan di daftar peringatan di bawah. Yang kita unduh tetap dari halaman `unstructured-road-obstacle-detection` (v11, jumlah gambar cocok), jadi kemungkinan itu cuma ID internal project yang sama. Perlu dikonfirmasi ke Jeka.
- **Jangan dicampur dengan project lain yang mirip**: `mtechcv/obstacle-detection-bgabd` dan `unstructuredroadobstacles/unstructured-road-obstacles` (6.156 gambar, nama kelasnya juga rusak). Keduanya kemungkinan versi lain dari data yang sama dan bisa bikin gambar dobel.

| Kelas Unstructured Road | Kelas JalanKu |
|-------------------------|---------------|
| tree | pohon |
| vehicle | kendaraan |
| two-wheeler (di halaman: two-wheeler-vehicle) | kendaraan |
| pole | pilar |
| stairs | tangga |
| signboard | dibuang |
| dog (di halaman: indian-street-dog) | dibuang |

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
| oranye | bollard, balok beton | pilar |
| toska | plang | dibuang |

- Pemetaan nomor kelas (hasil cek gambar). Nama kelas di `data.yaml` rusak, jadi nomor dicocokkan lewat gambar berkotak dan lembar potongan per ID. Yang dipakai hanya ID 0-11 dan 21. ID 12-20 hanya 1 sampai 5 kotak, diabaikan. Warna di tabel atas itu warna tampilan Roboflow, jangan disamakan dengan nomor ID.

| ID | Objek | Jumlah kotak | Kelas JalanKu |
|----|-------|--------------|---------------|
| 0 | plang dan rambu | 539 | dibuang |
| 1 | motor | 2.843 | kendaraan |
| 2 | orang | 3.835 | orang |
| 3 | batang pohon | 2.445 | pohon |
| 4 | pilar atau kolom bangunan (sebagian mungkin tembok) | 187 | pilar |
| 5 | pot tanaman | 123 | tanaman_pot |
| 6 | bollard dan balok beton | 2.464 | pilar |
| 7 | kursi dan bangku | 938 | kursi |
| 8 | tempat sampah | 441 | dibuang |
| 9 | mobil | 3.765 | kendaraan |
| 10 | lampu lalu lintas | 48 | dibuang |
| 11 | marka zebra cross | 44 | dibuang |
| 21 | tiang (lampu, listrik, rambu) | 1.770 | pilar |

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

## Dataset yang ditolak (12)

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
| Objek Trotoar (skripsi-ridho) | banyak foto ke atas (lampu jalan berlatar langit), bukan POV pejalan kaki; gambar sudah teraugmentasi mosaic dan cutout sehingga jumlah aslinya jauh lebih kecil |

Juga tidak bisa dipakai: ITOD Indonesian Traffic Obstacle Dataset (kamera mobil), data skripsi ITS Surabaya tentang trotoar (tidak publik), guidio-blind-assist (tidak ada dataset), dataset captioning trotoar Indonesia (bukan label deteksi).

## Catatan penting

- **Atribusi wajib**: dataset CC BY 4.0 dan CC BY-SA 4.0 harus disebut nama pembuat dan link-nya di laporan akhir.
- Dataset tidak di-commit ke repo. Simpan di laptop atau Drive.
- Jumlah data publik yang dipakai diambil secukupnya supaya seimbang dengan data kampus. Data kampus tetap yang paling penting.

## Catatan untuk keputusan kelas v1.3

### Temuan yang mempengaruhi daftar kelas
- ROD `Bike` (ID 0, 323 kotak di train): isinya campuran sepeda dan motor, bukan sepeda saja. Dari 48 potongan acak (sekitar 15%): 28 sepeda, 17 motor (utuh atau sebagian seperti kaca depan, spion, garpu), 3 tidak jelas. Perkiraan sekitar 35% motor (bisa sampai sekitar 40%). Ini pembacaan visual dari sampel kecil, bukan hitungan pasti. Motor di sini kemungkinan tumpang tindih dengan `Motorcycle` (ID 8).
- Lingkungan Trotoar ID 6 (bollard dan balok beton pendek, 2.464 kotak): belum diputuskan, opsinya `pilar` atau dibuang. Jumlahnya besar, jadi keputusan ini berdampak ke v1.3.
- Lingkungan Trotoar ID 3 (batang pohon, 2.445 kotak): kotak hanya menutup batang tanpa daun. Pembacaan baru dari beberapa gambar, belum 10, jadi perlu dicek lagi sebelum diputuskan sebagai `pohon`.
- Lingkungan Trotoar ID 4 (kolom atau pilar, 187) dan ID 21 (tiang, 1.770): diusulkan masuk `pilar` (total 1.957 kotak). Keyakinan "cukup yakin": sebagian potongan ID 4 bisa saja bagian tembok, dan potongan ID 21 sangat sempit.
- Lingkungan Trotoar ID 1 (motor, 2.843): di satu gambar (cek_02) kotak ID 1 sempat menutup sepeda. Di 12 potongan yang dilihat hanya motor.

### Usulan
- Lingkungan Trotoar ID 1 dan 9 (motor dan mobil) digabung ke `kendaraan` (6.608 kotak).
- Tidak dilabel mengikuti `kelas.md`: plang dan rambu (ID 0, 539 kotak), tempat sampah (ID 8, 441), lampu lalu lintas (ID 10, 48), marka zebra cross (ID 11, 44). Total 1.072 kotak.
- Lingkungan Trotoar ID 12-20 diabaikan (1-5 kotak per ID, total 20 kotak).
- ROD `Bike` (ID 0) tidak dipetakan utuh ke satu kelas: sepeda dan motor perlu dipisahkan dulu sebelum dipakai.

### Belum pasti (semua sudah diputuskan, lihat bagian status di bawah)
- Nasib Lingkungan Trotoar ID 6 (`pilar` atau dibuang).
- Apakah ID 4 dan ID 21 layak digabung dalam satu kelas `pilar`.
- Perlakuan sepeda di ROD ID 0 terhadap daftar kelas JalanKu (masuk `kendaraan`, kelas sendiri, atau dibuang) dan cara memisahkan motornya.
- Nama kelas di `data.yaml` Lingkungan Trotoar rusak (teks README Roboflow), jadi semua pemetaan ID berasal dari pembacaan visual, bukan nama resmi.

### Status setelah kelas v1.3 (7 November 2026)

Keputusan di `docs/kelas.md` v1.3 menyelesaikan sebagian poin di atas:
- Sepeda masuk `kendaraan`, jadi ROD `Bike` (ID 0) dan OOD `bicycle` langsung dipetakan ke `kendaraan` tanpa perlu memisahkan motor dan sepeda.
- Bench (ROD dan OOD) masuk `kursi`, street_light OOD masuk `pilar`.
- Pohon tetap batang saja. Unstructured Road dan Lingkungan Trotoar ID 3 melabel batang saja, jadi bisa dipakai. OOD `tree` menutup seluruh pohon, jadi gambar OOD yang memuat pohon dibuang saat penggabungan.
- Unstructured Road kemungkinan hanya melabel satu objek per gambar (kendaraan parkir yang terlihat kadang tidak dilabel). Risiko label bolong, dicek saat penggabungan.

Keputusan tambahan (7 November 2026):
- Truck dan Bus (ROD ID 15-16, OOD bus dan truck) masuk `kendaraan`.
- Bollard dan balok beton (Lingkungan Trotoar ID 6) serta OOD spherical_roadblock dan warning_column masuk `pilar`.
- Lingkungan Trotoar ID 21 (tiang lampu, listrik, rambu) masuk `pilar`. Dari 38 kotak sampel, hampir semuanya tiang tipis.
- Lingkungan Trotoar ID 4 (kolom bangunan) masuk `pilar`. Dari 44 kotak sampel, sekitar 28 kolom yang jelas, sekitar 11 hanya pinggiran tembok atau kusen pintu, dan sekitar 5 salah objek. Tetap dipakai karena jumlahnya kecil (187 kotak), tapi ini sumber label kotor yang diketahui.