# Daftar Kelas dan Panduan Anotasi (v1, 29 Oktober 2026)

Status: sementara, direvisi setelah video kampus pertama dan uji auto-label.

## Kelas

| ID | Kelas | Yang dilabel |
|---|---|---|
| 0 | pilar | Tiang gedung, tiang lampu, tiang rambu |
| 1 | pohon | Hanya batang pohon yang tumbuh dari tanah |
| 2 | tepian | Tepi trotoar, anak tangga, tangga turun, perbedaan tinggi |
| 3 | orang | Berdiri, berjalan, atau duduk (satu kelas) |
| 4 | tanaman_pot | Pot dan tanamannya, satu objek |
| 5 | kursi | Kursi dan bangku |
| 6 | kendaraan | Motor dan mobil yang terparkir |
| 7 | jalur_jalan | Area datar yang bisa dilalui pejalan kaki |

## Aturan umum
- Beri label hanya objek yang terlihat jelas. Bagian yang tertutup jangan ditebak.
- Objek terpotong di tepi gambar tetap dilabel kalau bagian yang terlihat jelas.
- Objek yang terlalu kecil dilewati (sementara: kurang dari sekitar 32 piksel pada sisi terpendek di gambar 640).
- Jangan melabel pantulan di kaca, gambar di poster, atau patung.
- Ragu antara dua kelas: tulis di catatan dan tanya tim, jangan tebak.

## Aturan per kelas
- **pohon:** batang saja dari pangkal ke atas sejauh terlihat. Pohon dalam pot masuk tanaman_pot.
- **tanaman_pot:** pot dan tanaman dalam satu kotak atau mask.
- **orang:** semua postur masuk satu kelas. Orang yang hanya sebagian kecil terlihat (sementara: kurang dari sekitar sepertiga tubuh) dilewati.
- **jalur_jalan:** permukaan yang diperuntukkan pejalan kaki: trotoar, koridor, selasar, lobi, jalur paving. Rumput, parkiran dengan kendaraan, dan area tertutup objek tidak masuk.

## Batasan yang diakui
- Dahan rendah setinggi kepala kemungkinan tidak terdeteksi.
- Tepian dan tangga turun sulit dideteksi dari satu kamera; akurasinya tidak dijanjikan.