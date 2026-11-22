"""Server HTTPS kecil untuk spike HP (Stage 2): model jalan DI browser HP.

Hanya stdlib. Jalankan dari root repo:
    venv\\Scripts\\python spike\\serve_https.py

- Pakai sertifikat self-signed yang SAMA dengan v1 (data/https/jalanku.crt + .key).
- Sajikan spike/hp/ di "/" dan models/onnx/ di "/models/".
- Header COOP/COEP supaya wasm multi-thread (SharedArrayBuffer) aktif.
- POST /report (opsional): halaman mengirim satu baris hasil, server mencetaknya.
  Dipakai untuk tes otomatis di laptop; di HP cukup tombol "Copy results".
"""
import mimetypes
import socket
import ssl
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8443
ROOT = Path(__file__).resolve().parent.parent
HP_DIR = ROOT / "spike" / "hp"
MODEL_DIR = ROOT / "models" / "onnx"
CERT = ROOT / "data" / "https" / "jalanku.crt"
KEY = ROOT / "data" / "https" / "jalanku.key"

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/octet-stream", ".onnx")


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/models/"):
            base, rel = MODEL_DIR, path[len("/models/"):]
        else:
            base, rel = HP_DIR, path.lstrip("/") or "index.html"
        target = (base / Path(*[p for p in rel.split("/") if p not in ("", ".", "..")])).resolve()
        if base.resolve() not in target.parents and target != base.resolve():
            return str(base / "__tidak_ada__")
        if target.is_dir():
            target = target / "index.html"
        return str(target)

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_POST(self):
        if self.path != "/report":
            self.send_error(404)
            return
        n = min(int(self.headers.get("Content-Length", 0)), 10000)
        print("[report]", self.rfile.read(n).decode("utf-8", "replace"), flush=True)
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        # diam untuk request normal; cetak hanya error (kode >= 400)
        if len(args) >= 2 and str(args[1]).isdigit() and int(args[1]) >= 400:
            super().log_message(fmt, *args)


PS_ALAMAT = (
    "$a = @(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } | Select-Object -ExpandProperty ifIndex); "
    "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $a -contains $_.InterfaceIndex } | "
    "ForEach-Object { $_.InterfaceAlias + '|' + $_.IPAddress }"
)


def lan_ips():
    """[(nama adapter, IPv4)] dari semua adapter aktif (tanpa 127.x / 169.254.x)."""
    hasil = []
    try:  # Windows: sama dengan data/https/jalankan-https.ps1
        out = subprocess.run(["powershell", "-NoProfile", "-Command", PS_ALAMAT],
                             capture_output=True, text=True, timeout=15).stdout
        for baris in out.splitlines():
            if "|" in baris:
                nama, ip = baris.strip().rsplit("|", 1)
                hasil.append((nama, ip))
    except (OSError, subprocess.SubprocessError):
        pass
    if not hasil:  # cadangan (bukan Windows / PowerShell gagal): rute default + nama host
        ips = []
        try:  # alamat interface rute default; tidak ada paket dikirim
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("192.0.2.1", 9))
            ips.append(s.getsockname()[0])
            s.close()
        except OSError:
            pass
        try:
            for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
                if ip not in ips:
                    ips.append(ip)
        except OSError:
            pass
        hasil = [("?", ip) for ip in ips]
    return [(n, ip) for n, ip in hasil if not ip.startswith(("169.254.", "127."))]


def main():
    for f in (CERT, KEY, HP_DIR / "index.html"):
        if not f.exists():
            print(f"Tidak ketemu: {f}")
            sys.exit(1)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(CERT), str(KEY))
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    ips = lan_ips()
    print()
    if ips:
        print("Alamat laptop saat ini (adapter aktif):")
        for nama, ip in ips:
            label = "   <-- kalau HP nyambung ke hotspot laptop" if ip.startswith("192.168.137.") else ""
            print(f"  {nama:<28} https://{ip}:{PORT}/{label}")
        print("Pilih URL sesuai cara HP tersambung.")
    else:
        print("Tidak ada IPv4 di adapter aktif. Sambungkan laptop ke Wi-Fi/hotspot, atau nyalakan Hotspot Seluler di laptop.")
    print(f"URL di laptop       : https://localhost:{PORT}/")
    print("(Chrome akan memberi peringatan sertifikat self-signed; lanjutkan saja.)")
    print("Tekan Ctrl+C untuk berhenti.\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Berhenti.")


if __name__ == "__main__":
    main()
