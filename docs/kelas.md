# Daftar Kelas dan Panduan Anotasi (v1.7, 11 November 2026)

Status: dipakai untuk pilot ngelabel. Masih bisa direvisi setelah pilot.

## Kelas

| ID | Kelas | Yang dilabel |
|---|---|---|
| 0 | pilar | Tiang gedung, tiang lampu jalan, tiang rambu, bollard, kerucut lalu lintas. Bukan sirip, kosen, atau bagian dinding (lihat R1) |
| 1 | pohon | Hanya batang pohon yang tumbuh dari tanah |
| 2 | tepian | Tepi trotoar, undakan tunggal, perbedaan tinggi lantai (bukan tangga) |
| 3 | orang | Berdiri, berjalan, atau duduk (satu kelas) |
| 4 | tanaman_pot | Pot dan tanamannya, satu objek |
| 5 | kursi | Kursi dan bangku, termasuk bangku taman |
| 6 | kendaraan | Motor, mobil, sepeda, truk, dan bus, terparkir maupun bergerak |
| 7 | jalur_jalan | Permukaan untuk pejalan kaki, termasuk dalam gedung |
| 8 | jalan_kendaraan | Jalan yang dipakai motor dan mobil |
| 9 | tangga | Tangga naik atau turun dengan dua anak tangga atau lebih |

## Aturan umum
- Semua objek dilabel sebagai polygon dengan bantuan SAM (lihat `docs/alat-label.md`). Kelas 0-6 dan 9 dipakai model kotak (polygon diubah otomatis jadi kotak), kelas 7-9 dipakai model segmentasi. Jadi **tangga (9) masuk dua model**: model kotak untuk peringatan, model segmentasi untuk bentuknya.
- Beri label hanya objek yang terlihat jelas. Bagian yang tertutup jangan ditebak.
- Objek terpotong di tepi gambar tetap dilabel kalau bagian yang terlihat jelas.
- Objek yang terlalu kecil dilewati (sementara: kurang dari sekitar 32 piksel pada sisi terpendek di gambar 640; di frame 1080x1920 artinya 96 piksel).
- **Objek tipis (pilar, pohon, tepian)** memakai aturan sendiri, karena tiang dan batang memang sempit: cukup sisi terpanjang minimal 96 piksel dan sisi terpendek minimal 24 piksel di frame 1080x1920 (di gambar 640: 32 dan 8 piksel).
- Jangan melabel pantulan di kaca, gambar di poster, atau patung.
- Rintangan di luar 10 kelas (tempat sampah, plang, tembok, pembatas) tidak dilabel, dan lantai di bawahnya tidak masuk jalur_jalan.
- Ragu antara dua kelas: tulis di catatan dan tanya tim, jangan tebak.
- Aturan audit R1 sampai R7 (v1.6) ada di bagian "Aturan audit label" di bawah.

## Aturan per kelas
- **pohon:** batang saja dari pangkal ke atas sejauh terlihat, daun dan tajuk tidak ikut. Kalau batang sebagian tertutup daun, label bagian batang yang terlihat saja. Pohon dalam pot masuk tanaman_pot.
- **pilar:** tiang lampu jalan dilabel utuh dari pangkal sampai kepala lampu. Bollard (tonggak pendek di trotoar atau pintu masuk, termasuk yang bulat dan balok beton pendek) juga masuk pilar.
- **tanaman_pot:** pot dan tanaman dalam satu kotak atau mask.
- **kendaraan:** semua motor, mobil, sepeda, truk, dan bus, baik yang terparkir maupun yang sedang bergerak. Pengendaranya dilabel terpisah sebagai orang.
- **orang:** semua postur masuk satu kelas. Orang yang hanya sebagian kecil terlihat (sementara: kurang dari sekitar sepertiga tubuh) dilewati.
- **jalur_jalan:** permukaan yang diperuntukkan pejalan kaki: lantai lobi dan koridor, selasar, trotoar, jalur paving. Rumput, parkiran dengan kendaraan, dan area tertutup objek tidak masuk.
- **jalan_kendaraan:** jalan yang dipakai motor dan mobil. Kalau ragu permukaannya untuk pejalan kaki atau kendaraan, dan kendaraan memakainya, label jalan_kendaraan.
- **tepian:** satu undakan atau tepi yang tingginya berubah (tepi trotoar, satu anak tangga di pintu masuk). Dua anak tangga atau lebih masuk tangga.
- **tangga:** satu kotak atau mask untuk seluruh bagian tangga yang terlihat, naik maupun turun. Pegangan tangga ikut di dalamnya, tidak dilabel terpisah. Eskalator tidak dilabel (sementara), termasuk pelat landasannya.

## Aturan audit label (v1.6, hasil audit label kampus 10-11 November 2026)
Dipakai untuk melabel dan memeriksa ulang label. Nomor aturan dipakai di `data/audit-kampus/` dan `docs/hasil-audit.md`.

- **R1. Bagian dinding bukan pilar, apa pun bahannya.** Sirip, mullion, kosen, bingkai, kusen/jamb pintu dan jendela, serta bagian fasad, dinding, dan pagar balustrade (kaca, logam, batu) adalah bagian dari dinding, bukan tiang bebas, dan tidak dilabel. Kolom atau tiang yang berdiri bebas di depan atau di samping dinding kaca tetap pilar (termasuk tiang beton gerbang).
- **R2. Orang di balik kaca bukan orang.** Orang yang terlihat lewat jendela atau dinding kaca di ruang yang tidak bisa dimasuki langsung oleh pengguna bukan rintangan dan tidak dilabel. Orang di sisi pengguna, atau di ambang pintu yang terbuka, tetap orang. **Pemutus:** kalau ragu apakah orang itu di balik kaca, tetap dilabel orang.
- **R3. Pot kecil di rak tidak dilabel.** tanaman_pot hanya untuk pot atau buket yang berdiri di lantai atau tanah di ruang jalan.
- **R4. Ambang ukuran** (frame 1080x1920): kelas biasa sisi terpendek minimal 96 px; kelas tipis (pilar, pohon, tepian) sisi terpanjang minimal 96 px dan sisi terpendek minimal 24 px. Kotak di bawah ambang tidak masuk label.
- **R5.** Tidak melabel pantulan, poster, mural, atau patung. Eskalator dan pelat landasannya tidak dilabel.
- **R6. Satu objek satu kotak.** Kotak ganda atau kotak parsial pada objek yang sudah punya kotak penuh dihapus. Satu objek tidak boleh punya dua kelas.
- **R7. Di luar kelas, tidak dilabel:** badan gerbang putar (turnstile) dan badan portal, lengan palang horizontal, kaki meja, lampu langit-langit, kabinet listrik, penyangga atau patok pohon, serta gagang pintu dan kusen pintu (v1.7). Tiang vertikal portal yang berdiri bebas tetap pilar.

## Aturan permukaan (jalur_jalan dan jalan_kendaraan)
Dipakai kalau tidak jelas permukaan itu untuk pejalan kaki atau kendaraan. Putuskan per frame dari bukti yang terlihat, bukan dari nama lokasi.

- **jalan_kendaraan** kalau salah satu terpenuhi:
  - ada kendaraan di permukaan itu,
  - ada marka jalan (panah, garis lajur, zebra cross),
  - permukaannya nyambung langsung ke jalan tanpa pembatas.
- **jalur_jalan** kalau dipisah dari jalan oleh kerb, pagar, atau rumput, dan tidak ada tanda kendaraan.
- **Masih ambigu:** pilih jalan_kendaraan (lebih aman untuk tunanetra) dan catat bahwa permukaannya ambigu supaya bisa dicek ulang.
- Area parkir dengan kendaraan, termasuk lantai parkiran basement, adalah jalan_kendaraan.
- Karpet, lantai lobi, dan koridor dalam gedung adalah jalur_jalan. Eskalator tidak masuk keduanya.
- Pelat landasan eskalator (pelat logam bergerigi sebelum anak tangga eskalator) bukan jalur_jalan dan tidak dilabel. Lantai di sekitarnya tetap jalur_jalan.

## Keputusan kasus pilot
Kasus yang muncul saat pilot dan sudah diputuskan (8 November 2026).

| Kasus | Keputusan |
|---|---|
| Delineator oranye (tiang pembatas jalur) | pilar, sama seperti bollard |
| Tiang stainless di atas umpak batu | pilar, umpaknya ikut |
| Tembok planter rendah | bukan tepian, tidak dilabel |
| Planter batu permanen | bukan tanaman_pot, tidak dilabel |
| Pot kecil di rak | tidak dilabel, bukan rintangan di lantai |
| Lantai di balik pagar kaca, beda level | tidak dilabel |
| Batu pijakan di rumput | jalur_jalan |
| Grating drainase di jalur | ikut permukaan di sekitarnya |
| Pohon jauh atau di balik pagar | dilabel hanya kalau batangnya jelas dan tidak terhalang pagar |
| Stool dan kursi bar | kursi |
| Tiang beton gerbang | pilar |
| Pelat landasan eskalator | tidak dilabel, bukan jalur_jalan |

Kasus tambahan dari audit label (11 November 2026):

| Kasus | Keputusan |
|---|---|
| Sirip, mullion, kosen, kusen pintu, ujung dinding, tiang pagar balustrade (kaca, logam, batu) | bukan pilar, tidak dilabel (R1) |
| Kolom bebas di depan atau samping dinding kaca | pilar (R1) |
| Orang di balik dinding kaca, di ruang yang tidak bisa dimasuki | tidak dilabel (R2); kalau ragu, tetap orang |
| Pot atau buket kecil di rak | tidak dilabel (R3) |
| Buket atau pot di lantai ruang jalan | tanaman_pot, dilabel |
| Kerucut lalu lintas | pilar, sama seperti delineator dan bollard |
| Gerbang putar (turnstile), badan portal, lengan palang | tidak dilabel (R7) |
| Tiang vertikal portal yang berdiri bebas | pilar |
| Kaki meja, lampu neon langit-langit, kabinet listrik, penyangga pohon | tidak dilabel (R7) |
| Kotak ganda atau parsial pada objek yang sudah punya kotak penuh | dihapus (R6) |
| Pantulan di lantai, mural, gambar di dinding | tidak dilabel (R5) |

Kasus tambahan dari review test set (11 November 2026, v1.7):

| Kasus | Keputusan |
|---|---|
| Ambang rendah sepanjang jendela (setinggi sekitar satu langkah) | tepian |
| Pohon yang ditanam di pot atau di bedeng planter bulat yang ditinggikan | tanaman_pot (pot dan pohon satu objek); dasar bedeng planter bukan tepian. Ini memperjelas "Planter batu permanen" di atas: yang berisi pohon dan berdiri di ruang jalan dilabel tanaman_pot, bukan lagi dilewati |
| Bangku beton atau kayu | kursi |
| Gagang pintu dan kusen pintu | tidak dilabel (R7, juga R1 untuk kusen) |
| Kerb antara jalur pejalan kaki dan jalan yang lebih tinggi atau lebih rendah | tepian |
| Orang terpotong tepi frame | dilabel kalau bagian yang terlihat jelas; aturan ukuran tetap berlaku (R4 dan sepertiga tubuh) |

## Batasan yang diakui
- Dahan rendah setinggi kepala kemungkinan tidak terdeteksi.
- Tepian dan tangga turun sulit dideteksi dari satu kamera; akurasinya tidak dijanjikan.

## Riwayat perubahan
- v1.7 (11 Nov 2026): keputusan review test set. Ambang rendah sepanjang jendela = tepian; pohon di pot atau bedeng planter bulat yang ditinggikan = tanaman_pot (pot dan pohon satu objek, dasar bedeng bukan tepian); bangku beton atau kayu = kursi; gagang pintu dan kusen pintu tidak dilabel (R7); kerb antara jalur pejalan kaki dan jalan yang beda tinggi = tepian; orang terpotong tepi frame dilabel kalau terlihat jelas (aturan ukuran tetap). ID 0 sampai 9 tidak berubah.
- v1.6 (11 Nov 2026): hasil audit label kampus. Tambah bagian "Aturan audit label" (R1-R7). R1 diperluas: sirip, kosen, kusen pintu, dan bagian dinding/fasad/balustrade bukan pilar, apa pun bahannya; kolom bebas tetap pilar. R2 baru: orang di balik kaca tidak dilabel, dengan pemutus ragu = tetap orang. R3-R5 (pot di rak, ambang ukuran, pantulan/poster/eskalator) ditegakkan di label. R6 baru: satu objek satu kotak. R7 baru: objek di luar kelas (turnstile, kaki meja, lampu langit-langit, kabinet listrik, penyangga pohon). Kerucut lalu lintas masuk pilar. ID 0 sampai 9 tidak berubah.
- v1.5 (8 Nov 2026): tangga juga dipakai model segmentasi (kelas 7-9 untuk segmentasi). Aturan ukuran objek tipis (pilar, pohon, tepian): sisi terpanjang minimal 96 piksel dan sisi terpendek minimal 24 piksel. Tambah aturan permukaan berdasarkan bukti per frame dan keputusan 11 kasus pilot. Pelat landasan eskalator tidak dilabel dan bukan jalur_jalan. ID 0 sampai 9 tidak berubah.
- v1.4 (7 Nov 2026): bollard masuk pilar, truk dan bus masuk kendaraan, mengikuti pemetaan dataset publik. ID 0 sampai 9 tidak berubah.
- v1.3 (7 Nov 2026): kendaraan mencakup yang bergerak (sebelumnya hanya terparkir) dan sepeda, mengikuti dataset publik. Pohon tetap batang saja, ditambah aturan batang tertutup daun. Bangku taman masuk kursi, tiang lampu jalan masuk pilar. Semua objek dilabel polygon. ID 0 sampai 9 tidak berubah.
- v1.2 (1 Nov 2026): tambah kelas 9 tangga. Anak tangga dan tangga turun dipindah dari tepian ke tangga. ID 0 sampai 8 tidak berubah.
- v1.1 (29 Okt 2026): 9 kelas awal.