# Panduan Anotasi Jalanku

**Versi:** 1.0  
**Mengacu pada:** `docs/kelas.md` v1.2 (1 November 2026)  
**Status:** Draft

## 1. Tujuan

Panduan ini digunakan sebagai acuan anotasi dataset Jalanku agar seluruh anggota tim menggunakan definisi kelas dan aturan anotasi yang konsisten.

Panduan ini mengacu pada `docs/kelas.md` v1.2. Jika terdapat kasus yang tidak jelas atau bertentangan dengan panduan ini, jangan menebak. Catat kasus tersebut dan tanyakan kepada tim.

---

## 2. Aturan Umum

1. Beri label hanya pada objek yang terlihat dengan jelas.
2. Bagian objek yang tertutup tidak boleh ditebak.
3. Objek yang terpotong di tepi gambar tetap diberi label jika bagian yang terlihat cukup jelas.
4. Objek yang terlalu kecil dilewati. Untuk sementara, objek dengan sisi terpendek kurang dari sekitar 32 piksel pada gambar 640 piksel dapat dilewati.
5. Jangan memberi label pada:
   - pantulan di kaca,
   - gambar objek pada poster atau layar,
   - patung.
6. Jika ragu antara dua kelas, jangan menebak. Catat kasus tersebut dan tanyakan kepada tim.
7. Gunakan satu kelas yang paling sesuai dengan definisi pada `kelas.md` v1.2.

---

## 3. Daftar Kelas

| ID | Kelas | Yang Dilabel |
|---|---|---|
| 0 | `pilar` | Tiang gedung, tiang lampu, dan tiang rambu |
| 1 | `pohon` | Batang pohon yang tumbuh dari tanah |
| 2 | `tepian` | Tepi trotoar, undakan tunggal, dan perbedaan tinggi lantai |
| 3 | `orang` | Orang yang berdiri, berjalan, atau duduk |
| 4 | `tanaman_pot` | Pot beserta tanamannya sebagai satu objek |
| 5 | `kursi` | Kursi dan bangku |
| 6 | `kendaraan` | Motor dan mobil yang terparkir |
| 7 | `jalur_jalan` | Permukaan yang diperuntukkan bagi pejalan kaki |
| 8 | `jalan_kendaraan` | Jalan yang digunakan motor dan mobil |
| 9 | `tangga` | Tangga naik atau turun dengan dua anak tangga atau lebih |

---

## 4. Panduan Per Kelas

### 4.1 `pilar`

Labeli:
- Tiang gedung.
- Tiang lampu.
- Tiang rambu.

Jangan membuat kelas terpisah untuk jenis tiangnya.

Jika bagian tiang tertutup objek lain, hanya labeli bagian yang terlihat.

---

### 4.2 `pohon`

Labeli:
- Batang pohon yang tumbuh langsung dari tanah.
- Batang dari pangkal ke atas sejauh bagian tersebut terlihat.

Jangan labeli:
- Pohon yang berada di dalam pot sebagai `pohon`.
- Dahan atau daun sebagai objek `pohon` secara terpisah.

**Catatan:** Pohon yang berada di dalam pot masuk kelas `tanaman_pot`.

---

### 4.3 `tepian`

Labeli:
- Tepi trotoar.
- Undakan tunggal.
- Perbedaan tinggi lantai yang bukan merupakan tangga.

**Aturan penting:**

> Satu undakan = `tepian`  
> Dua anak tangga atau lebih = `tangga`

Contoh:
- Pintu masuk dengan satu anak tangga → `tepian`.
- Perbedaan tinggi antara dua permukaan lantai → `tepian`.
- Tangga dengan dua anak tangga → `tangga`.

---

### 4.4 `orang`

Semua postur manusia masuk satu kelas:
- Berdiri.
- Berjalan.
- Duduk.

Orang yang terpotong di tepi gambar tetap dapat dilabeli jika bagian yang terlihat cukup jelas.

Namun, orang yang hanya terlihat sebagian kecil, sementara kurang dari sekitar sepertiga tubuh, dilewati.

Jangan menebak bagian tubuh yang tertutup.

---

### 4.5 `tanaman_pot`

Pot dan tanaman di dalamnya dianggap sebagai **satu objek**.

Labeli:
- Pot.
- Tanaman yang berada di dalam pot.

Gunakan satu kotak atau satu mask yang mencakup pot dan tanaman.

**Penting:** Jangan memisahkan pot dan tanaman menjadi dua objek berbeda.

---

### 4.6 `kursi`

Labeli:
- Kursi.
- Bangku.

Jika sebagian kursi tertutup objek lain, hanya anotasi bagian yang terlihat dengan jelas.

---

### 4.7 `kendaraan`

Untuk dataset Jalanku, kelas ini digunakan untuk:
- Motor yang terparkir.
- Mobil yang terparkir.

Jika kendaraan terparkir dan terlihat jelas, beri label `kendaraan`.

---

### 4.8 `jalur_jalan`

Labeli permukaan yang diperuntukkan bagi pejalan kaki, termasuk:
- Lantai lobi.
- Koridor.
- Selasar.
- Trotoar.
- Jalur paving.

Jangan memasukkan:
- Rumput.
- Parkiran dengan kendaraan.
- Area yang tertutup objek sehingga permukaannya tidak terlihat jelas.

---

### 4.9 `jalan_kendaraan`

Labeli permukaan jalan yang digunakan oleh:
- Motor.
- Mobil.

Jika terdapat keraguan apakah suatu permukaan digunakan untuk pejalan kaki atau kendaraan, perhatikan konteks penggunaannya.

Jika kendaraan menggunakan permukaan tersebut sebagai jalan, dapat diberi label `jalan_kendaraan`.

---

### 4.10 `tangga`

Labeli tangga yang:
- Naik.
- Turun.
- Memiliki dua anak tangga atau lebih.

Seluruh bagian tangga yang terlihat diberi **satu kotak atau satu mask**.

Pegangan tangga ikut berada di dalam anotasi tangga dan **tidak diberi label terpisah**.

**Eskalator tidak dilabel sementara.**

---

## 5. Kasus Sulit

### 5.1 Tangga vs Tepian

Ini merupakan salah satu kasus yang paling penting.

| Kondisi | Label |
|---|---|
| Tidak ada perubahan ketinggian | Sesuai objek/permukaan |
| Satu undakan | `tepian` |
| Dua anak tangga | `tangga` |
| Tiga atau lebih anak tangga | `tangga` |
| Tangga turun | `tangga` |
| Eskalator | Tidak dilabel sementara |

**Jangan menentukan berdasarkan tinggi saja. Hitung jumlah anak tangga yang terlihat.**

Jika jumlah anak tangga tidak dapat dipastikan karena tertutup atau sudut kamera, jangan menebak. Catat dan tanyakan kepada tim.

---

### 5.2 Pohon vs Tanaman Pot

Gunakan lokasi tumbuh sebagai pembeda utama.

**`pohon`:**
- Batang tumbuh langsung dari tanah.

**`tanaman_pot`:**
- Tanaman berada di dalam pot.
- Pot dan tanaman dilabel sebagai satu objek.

Contoh:
- Pohon di area taman → `pohon`.
- Tanaman hias di pot depan gedung → `tanaman_pot`.

---

### 5.3 Pilar vs Tiang

Keduanya masuk kelas yang sama: `pilar`.

Contoh:
- Pilar gedung → `pilar`.
- Tiang lampu → `pilar`.
- Tiang rambu → `pilar`.

Tidak perlu membuat kelas tambahan berdasarkan fungsi tiang.

---

### 5.4 Orang Terpotong

Orang yang berada di tepi frame tetap dapat dilabel jika bagian yang terlihat cukup jelas.

Namun, jika yang terlihat hanya sebagian kecil tubuh, sementara kurang dari sekitar sepertiga tubuh, objek dilewati.

Contoh:
- Setengah badan terlihat jelas → dapat dilabel.
- Hanya sebagian kecil kepala/tangan terlihat → dilewati.

Jangan menebak bentuk tubuh yang tidak terlihat.

---

## 6. Objek yang Tidak Boleh Dilabel

Jangan memberi anotasi pada:

- Pantulan objek di kaca.
- Gambar orang atau kendaraan pada poster.
- Gambar objek pada layar.
- Patung.
- Rintangan di luar 10 kelas (misalnya tempat sampah, plang, tembok, pembatas). Lantai di bawah rintangan itu juga tidak masuk `jalur_jalan`.
- Eskalator sementara.
- Objek yang terlalu kecil untuk dianotasi dengan jelas.

---

## 7. Aturan Saat Ragu

Jika sebuah objek dapat masuk ke lebih dari satu kelas dan tidak ada aturan yang cukup jelas:

1. Jangan menebak.
2. Jangan memaksakan kelas.
3. Catat frame atau kasusnya.
4. Tulis alasan keraguan.
5. Tanyakan kepada tim sebelum melanjutkan anotasi.

Konsistensi dataset lebih penting daripada memaksakan label pada kasus yang belum disepakati.

---

## 8. Checklist Sebelum Menyimpan Anotasi

Sebelum anotasi dianggap selesai, pastikan:

- [ ] Objek terlihat jelas.
- [ ] Bagian yang tertutup tidak ditebak.
- [ ] Objek terpotong tetap diperiksa dan dilabel jika memenuhi aturan.
- [ ] Objek terlalu kecil tidak dilabel.
- [ ] Pantulan dan gambar pada poster/layar tidak dilabel.
- [ ] Pohon dan tanaman pot dibedakan dengan benar.
- [ ] Satu undakan diberi label `tepian`.
- [ ] Dua anak tangga atau lebih diberi label `tangga`.
- [ ] Pegangan tangga tidak diberi label terpisah.
- [ ] Orang yang hanya terlihat sebagian kecil dilewati.
- [ ] Jika ragu, kasus dicatat dan ditanyakan kepada tim.

---

## 9. Catatan Keterbatasan

Beberapa kondisi diakui sebagai keterbatasan dataset dan sistem:

- Dahan rendah setinggi kepala kemungkinan tidak terdeteksi.
- Tepian dan tangga turun sulit dideteksi dari satu kamera.
- Akurasi pada kondisi tersebut tidak dijanjikan.

Panduan ini dapat diperbarui apabila hasil anotasi dan pengujian model menunjukkan kebutuhan perubahan aturan.

---

## 10. Referensi

- `docs/kelas.md` v1.2 — Daftar kelas dan panduan anotasi Jalanku.
- Dataset dan aturan tambahan yang disepakati tim Jalanku.