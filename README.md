# JalanKu

Prototipe pendamping untuk pengguna tunanetra: mendeteksi rintangan di depan lewat kamera HP dan memberi peringatan suara. Proyek UAS Machine Learning (Mufid, Nicksen, Kenzu).

> Ini prototipe, bukan pengganti alat bantu resmi. Perkiraan jarak dari ukuran kotak hanya kasar.

## Struktur folder

| Folder       | Isi                                                    |
| ------------ | ------------------------------------------------------ |
| `docs/`      | Dokumentasi, panduan anotasi, profil tim (`docs/tim/`) |
| `data/`      | Dataset (data mentah tidak di-commit)                  |
| `notebooks/` | Notebook training dan evaluasi                         |
| `src/`       | Kode final                                             |
| `models/`    | Bobot model (`*.pt` tidak di-commit)                   |
| `reference/` | Kode lama, hanya referensi                             |

## Setup (Windows)

Pakai **PowerShell** lewat VS Code: buka VS Code, `ctrl + j` > New Terminal, pastikan tab terminalnya bertuliskan `powershell`. Jalankan perintah satu per satu.

1. Pasang **Python 3.12.10** (bukan versi lain), Git, dan VS Code. Cek versinya:
   ```
   python --version
   ```
   Harus keluar `Python 3.12.10`. Kalau beda, kabari tim sebelum lanjut.
2. Clone repo ke `C:\`:
   ```
   cd C:\
   git clone https://github.com/mufidjk/jalanku.git
   cd jalanku
   ```
   Repo ini private. Pastikan sudah accept undangan di GitHub. Saat clone, mungkin muncul jendela login GitHub: login dengan akun yang diundang.
3. Buat dan aktifkan virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
   Berhasil kalau prompt diawali `(venv)`. Kalau muncul error "running scripts is disabled", jalankan ini sekali, jawab `Y`, lalu ulangi `venv\Scripts\activate`:
   ```
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```
   Setiap kali buka terminal baru, aktifkan lagi: `cd C:\jalanku` lalu `venv\Scripts\activate`.
4. Pasang PyTorch (GPU NVIDIA, CUDA 13.2). Langkah ini harus **sebelum** langkah 5:
   ```
   pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cu132
   ```
   Kalau laptop kamu tidak punya GPU NVIDIA, ganti `cu132` di akhir URL dengan `cpu`.
5. Pasang dependensi:
   ```
   pip install -r requirements.txt
   ```
6. Cek:
   ```
   python -c "import torch, ultralytics; print(torch.cuda.is_available(), ultralytics.__version__)"
   ```
   Hasil yang diharapkan: `True 8.4.188` (kalau tanpa GPU, `False` juga boleh).
7. Kalau Terminal dibuka dari luar VS Code:
   ```
   Arahkan kursor ke File > Open Folder > Pilih folder jalanku yang telah terclone di C:/jalanku
   ```

## Aturan kerja tim

- Jangan push langsung ke `main`. Selalu bikin cabang (contoh: `nama/tugas`), push, lalu buka Pull Request.
- Sebelum mulai: `git switch main` lalu `git pull`.
- Cek `git status` sebelum `git add`. Jangan `git add .` secara buta.
- Jangan commit: `venv/`, `.env`/API key, `*.pt`, `runs/`, dataset mentah, foto yang memuat wajah orang.
- Setiap PR direview minimal satu orang lain sebelum merge.
- Kalau bingung atau error, berhenti dan tanya. Jangan `git push --force` / `git reset --hard` kalau belum paham.
