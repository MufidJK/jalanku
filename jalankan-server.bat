@echo off
rem JalanKu: jalankan server HTTPS (klik dua kali). Tutup jendela atau tekan Ctrl+C untuk berhenti.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "data\https\jalankan-https.ps1"
echo.
echo Server berhenti. Kalau ada pesan galat di atas, baca dulu sebelum menutup.
pause
