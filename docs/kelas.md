# Daftar Kelas dan Panduan Anotasi (v1.3, 7 November 2026)

Status: dipakai untuk pilot ngelabel. Masih bisa direvisi setelah pilot.

## Kelas

| ID | Kelas | Yang dilabel |
|---|---|---|
| 0 | pilar | Tiang gedung, tiang lampu jalan, tiang rambu |
| 1 | pohon | Hanya batang pohon yang tumbuh dari tanah |
| 2 | tepian | Tepi trotoar, undakan tunggal, perbedaan tinggi lantai (bukan tangga) |
| 3 | orang | Berdiri, berjalan, atau duduk (satu kelas) |
| 4 | tanaman_pot | Pot dan tanamannya, satu objek |
| 5 | kursi | Kursi dan bangku, termasuk bangku taman |
| 6 | kendaraan | Motor, mobil, dan sepeda, terparkir maupun bergerak |
| 7 | jalur_jalan | Permukaan untuk pejalan kaki, termasuk dalam gedung |
| 8 | jalan_kendaraan | Jalan yang dipakai motor dan mobil |
| 9 | tangga | Tangga naik atau turun dengan dua anak tangga atau lebih |

## Aturan umum
- Semua objek dilabel sebagai polygon dengan bantuan SAM (lihat `docs/alat-label.md`). Kelas 0-6 dan 9 dipakai model kotak (polygon diubah otomatis jadi kotak), kelas 7-8 dipakai model segmentasi.
- Beri label hanya objek yang terlihat jelas. Bagian yang tertutup jangan ditebak.
- Objek terpotong di tepi gambar tetap dilabel kalau bagian yang terlihat jelas.
- Objek yang terlalu kecil dilewati (sementara: kurang dari sekitar 32 piksel pada sisi terpendek di gambar 640).
- Jangan melabel pantulan di kaca, gambar di poster, atau patung.
- Rintangan di luar 10 kelas (tempat sampah, plang, tembok, pembatas) tidak dilabel, dan lantai di bawahnya tidak masuk jalur_jalan.
- Ragu antara dua kelas: tulis di catatan dan tanya tim, jangan tebak.

## Aturan per kelas
- **pohon:** batang saja dari pangkal ke atas sejauh terlihat, daun dan tajuk tidak ikut. Kalau batang sebagian tertutup daun, label bagian batang yang terlihat saja. Pohon dalam pot masuk tanaman_pot.
- **pilar:** tiang lampu jalan dilabel utuh dari pangkal sampai kepala lampu.
- **tanaman_pot:** pot dan tanaman dalam satu kotak atau mask.
- **kendaraan:** semua motor, mobil, dan sepeda, baik yang terparkir maupun yang sedang bergerak. Pengendaranya dilabel terpisah sebagai orang.
- **orang:** semua postur masuk satu kelas. Orang yang hanya sebagian kecil terlihat (sementara: kurang dari sekitar sepertiga tubuh) dilewati.
- **jalur_jalan:** permukaan yang diperuntukkan pejalan kaki: lantai lobi dan koridor, selasar, trotoar, jalur paving. Rumput, parkiran dengan kendaraan, dan area tertutup objek tidak masuk.
- **jalan_kendaraan:** jalan yang dipakai motor dan mobil. Kalau ragu permukaannya untuk pejalan kaki atau kendaraan, dan kendaraan memakainya, label jalan_kendaraan.
- **tepian:** satu undakan atau tepi yang tingginya berubah (tepi trotoar, satu anak tangga di pintu masuk). Dua anak tangga atau lebih masuk tangga.
- **tangga:** satu kotak atau mask untuk seluruh bagian tangga yang terlihat, naik maupun turun. Pegangan tangga ikut di dalamnya, tidak dilabel terpisah. Eskalator tidak dilabel (sementara).

## Batasan yang diakui
- Dahan rendah setinggi kepala kemungkinan tidak terdeteksi.
- Tepian dan tangga turun sulit dideteksi dari satu kamera; akurasinya tidak dijanjikan.

## Riwayat perubahan
- v1.3 (7 Nov 2026): kendaraan mencakup yang bergerak (sebelumnya hanya terparkir) dan sepeda, mengikuti dataset publik. Pohon tetap batang saja, ditambah aturan batang tertutup daun. Bangku taman masuk kursi, tiang lampu jalan masuk pilar. Semua objek dilabel polygon. ID 0 sampai 9 tidak berubah.
- v1.2 (1 Nov 2026): tambah kelas 9 tangga. Anak tangga dan tangga turun dipindah dari tepian ke tangga. ID 0 sampai 8 tidak berubah.
- v1.1 (29 Okt 2026): 9 kelas awal.