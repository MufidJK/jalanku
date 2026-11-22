@echo off
rem JalanKu: halaman tes model di HP (spike/hp, port 8443). Tutup jendela atau tekan Ctrl+C untuk berhenti.
cd /d "%~dp0"
venv\Scripts\python.exe spike\serve_https.py
echo.
echo Server berhenti. Kalau ada pesan galat di atas, baca dulu sebelum menutup.
pause
