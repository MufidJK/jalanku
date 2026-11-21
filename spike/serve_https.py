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


def lan_ips():
    ips = []
    try:  # alamat interface rute default (biasanya Wi-Fi hotspot); tidak ada paket dikirim
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
    return [ip for ip in ips if not ip.startswith(("169.254.", "127."))]


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
        print(f"IPv4 saat ini       : {', '.join(ips)}")
        print(f"URL untuk HP        : https://{ips[0]}:{PORT}/")
    else:
        print("Tidak ada IPv4 LAN. Sambungkan laptop ke hotspot HP dulu.")
    print(f"URL di laptop       : https://localhost:{PORT}/")
    print("(Chrome akan memberi peringatan sertifikat self-signed; lanjutkan saja.)")
    print("Tekan Ctrl+C untuk berhenti.\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Berhenti.")


if __name__ == "__main__":
    main()
