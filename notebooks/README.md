# Notebook laporan JalanKu

Empat notebook ini adalah **lapisan penyajian** untuk laporan UAS: mereka **membaca** hasil yang sudah tersimpan (`data/`, `runs/`, `docs/`, `src/`)
lalu menampilkannya dengan tabel, grafik, dan penjelasan singkat. Tidak ada pelatihan, tidak ada evaluasi baru, tidak ada inferensi model,
dan tidak ada berkas `.pt` yang dimuat. Semua angka dihitung oleh sel kode dari berkas sumber, kecuali satu bagian di Notebook 04 yang diberi label
"dicatat manual oleh penguji".

Setiap notebook disimpan **beserta keluarannya** (tabel dan grafik sudah ada di dalam berkas `.ipynb`), jadi bisa dibaca tanpa menjalankan apa pun.

## Isi tiap notebook

| Notebook | Isi | Sumber utama |
|---|---|---|
| `01_dataset.ipynb` | Kelas yang dideteksi (8 kotak, 3 segmentasi), sumber data (video kampus dan dataset publik), lokasi dan pembagian train/val/test per lokasi, pra-pemrosesan (frame, pemburaman wajah, label draf, audit), jumlah gambar dan instance, contoh gambar, keterbatasan (termasuk kebocoran lokasi taman-ubm). | `docs/kelas.md`, `docs/dataset-publik.md`, `docs/test-set.md`, `docs/hasil-audit.md`, `data/dataset-gabung-*-v4/`, `data/dataset-test-*/` |
| `02_training.ipynb` | Perangkat dan versi, semua run pelatihan (baseline, ronde 2, 3, 4) dengan pengaturan dan hasil, riwayat ronde dan aturan pemilihan yang ditulis sebelum hasil, kurva pelatihan model final, pembacaan overfitting dan early stopping. | `runs/baseline/*`, `runs/ronde2/*`, `data/test-final/LOG.md`, `docs/hasil-baseline.md`, `docs/hasil-ronde2.md` |
| `03_evaluasi.ipynb` | Protokol evaluasi, perbandingan semua model di val, pemilihan ambang per kelas, matriks konfusi val dan test, hasil test (kotak dan segmentasi), penurunan val ke test dan "kutukan pemenang", contoh kualitatif. | `data/test-final/t1/`, `data/test-final/t1_val/`, `docs/hasil-test-final.md` |
| `04_aplikasi.ipynb` | Arsitektur HP-server, logika peringatan, kecepatan, kesetaraan server dan evaluasi offline, ablasi aturan peringatan (tanpa pelatihan), ambang kendaraan 0,10 ke 0,25, kamera menempel tembok, catatan uji pemakaian (manual). | `src/server/`, `src/web/`, `data/server-v2/`, `data/aturan-peringatan/`, `data/diagnosa-mepet/` |

Notebook 03 memakai fungsi pencocokan dari `tools/` untuk menghitung ulang matriks konfusi dari prediksi yang sudah tersimpan (bukan evaluasi baru;
angkanya dicocokkan lebih dulu dengan yang tercatat). Notebook 04 memakai `src/server/logika.py` untuk menghitung tabel tingkat bahaya.
Kedua modul itu tidak memuat torch, dan notebook mematikan penulisan bytecode supaya tidak ada berkas baru di `tools/` atau `src/`.

## Data tidak ada di Git

Folder `data/`, `runs/`, dan `models/` **tidak masuk Git** (ukuran besar, dan berisi frame kampus). Karena itu:

- Di komputer lain, notebook hanya bisa **dibaca** dari keluaran yang tersimpan. Sel persiapan di tiap notebook mencetak daftar berkas yang tidak ditemukan.
- Menjalankan ulang hanya bisa dilakukan di laptop yang memiliki folder-folder itu (laptop Mufid).
- Gambar yang ditampilkan hanya dari daftar putih privasi (frame kampus yang wajahnya sudah diburamkan, plot Ultralytics, dan beberapa lembar kontak). Tidak ada gambar dari rekaman rumah.

## Menjalankan ulang di laptop Mufid

Dari akar repo (PowerShell), memakai `venv` proyek:

```
venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks\01_dataset.ipynb
venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks\02_training.ipynb
venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks\03_evaluasi.ipynb
venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks\04_aplikasi.ipynb
```

Syarat: semua paket di `notebooks/requirements.txt` (`ipykernel`, `nbconvert`, `nbclient`, `jupyter_client`, `ipython`, `numpy`, `matplotlib`, `Pillow`, dan `PyYAML`)
terpasang di `venv` (`venv\Scripts\python -m pip install -r notebooks\requirements.txt`). Tiap notebook selesai dalam beberapa detik dan harus berjalan dari atas ke bawah tanpa galat.
`requirements.txt` di akar repo tidak diubah.

## Catatan penting

- Angka pada notebook adalah angka dari run yang sudah ada. Jika ada angka acuan yang tidak cocok, bagian "Pemeriksaan angka acuan" di tiap notebook menampilkannya apa adanya; tidak ada yang disesuaikan.
- Test set dievaluasi satu kali dan terkunci. Notebook hanya membaca hasil itu.
- Prototipe ini pendamping, bukan pengganti tongkat.
