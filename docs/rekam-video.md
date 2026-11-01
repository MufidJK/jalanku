# Rencana Perekaman Video

## Aturan rekam
- POV utama setinggi dada (untuk training dan test). POV sejajar mata hanya tambahan untuk training, tidak dipakai di test.
- HP posisi portrait (vertikal), sama di semua video. Kamera 1x, jangan zoom atau wide.
- Jalan pelan, berhenti sebentar di depan rintangan.
- Resolusi 1080p, 30 fps.
- Durasi per video 30 detik sampai 5 menit. Sebisa mungkin satu lokasi per video.
- Variasi: siang terang, sore, area ramai dan sepi.
- Hindari close-up wajah. Tetap akan diblur otomatis sebelum dipakai.

## Penamaan file
lokasi_tanggal_sesi_pov.mp4
```
contoh: lorong-lt9-ubm-tower_2026-10-30_01_dada.mp4
        lorong-lt9-ubm-tower_2026-10-30_01_mata.mp4
```

## Set test
Lokasi test tidak boleh dipakai untuk training sama sekali.
- **Lantai 11 UBM Tower** (selasar dan area pot). Indoor, kemungkinan tempat pameran.
- **Taman kampus** (di bawah Alfamart lt2). Outdoor. Rekam POV dada saja.

## Status rekaman (per 1 November 2026)
Total 39 video. Mata direkam Mufid, dada direkam Kenzu, kecuali disebut lain.

| Lokasi | Area | Tipe | Mata | Dada | Split |
|---|---|---|---|---|---|
| selasar-lt11 | UBM Tower | indoor | 01 | 01 | test |
| pot-lt11 | UBM Tower | indoor | 01 | 01 | test |
| taman | antara Alfa Tower dan UBM Tower | outdoor | - | belum direkam | test |
| lab-iota1-lt9 | UBM Tower | indoor | 01, 02 | 01, 02 | train |
| lorong-lt9 | UBM Tower | indoor | 01, 02, 03 | 01, 02, 03 | train |
| tangga-naik-lt9-lt10 | UBM Tower | indoor | 01 | 01 | train |
| perpus-lt9 | UBM Tower | indoor | 01 | 01 | train |
| parkiran-motor-b1 | UBM Tower | indoor (basement) | 01 | 01, 02 | train |
| lab1-lt5 | Alfa Tower | indoor | 01, 02 | 01 (Mufid), 02 | train |
| lorong-lt5 | Alfa Tower | indoor | 01 | 01 | train |
| lorong-lt3-eskalator | Alfa Tower | indoor | 01 | 01 | train |
| tangga-naik-lt3 | Alfa Tower | indoor | 01 | 01 | train |
| tangga-naik-alfa-lt2 | depan Maxx Coffee | semi-outdoor | 01 | 01 | train |
| alfamart-lt2 | antara Alfa Tower dan UBM Tower | indoor | 01 | 01 | train |
| dapsut | Alfa Tower, parkiran mobil, Dapur Alsut | indoor dan outdoor | 01, 02 | 01, 02 | train |

Catatan:
- Taman tidak terlihat di video tangga-naik-alfa-lt2 dan alfamart-lt2. Saat ekstraksi frame, cek lagi; frame yang memperlihatkan taman dibuang.
- Data outdoor untuk training hanya dari dapsut. Kekurangannya ditutup dataset publik.

## Penyimpanan
Video mentah disimpan di Google Drive `JalanKu-VideoMentah`, satu subfolder per orang. Jangan di-commit ke repo.