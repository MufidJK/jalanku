"""Cek kuota/latensi Gemini dari laptop: SATU panggilan hanya-teks dan SATU panggilan dengan gambar bersih.

    venv\\Scripts\\python -I tests\\zanite\\cek_kuota.py

- Model sama dengan server (config.yaml: entri gemini pertama di zanite.rantai). Batas waktu 30 dtk. Ulang oleh SDK dimatikan (attempts=1),
  jadi galat 429/503 muncul seketika dengan kode dan statusnya.
- Hanya data/zanite/tes_bersih.jpg yang dikirim (tanpa wajah).
- Yang dicetak: waktu (ms), berhasil atau kelas galat + kode HTTP + status/alasan dari Google (mis. RESOURCE_EXHAUSTED,
  nama metrik kuota). Kunci API TIDAK pernah dicetak: dibaca dari .env, dan setiap teks yang dicetak disensor.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "server"))

import yaml  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

load_dotenv(ROOT / ".env")
KUNCI = os.environ.pop("GEMINI_API_KEY", "").strip()
if not KUNCI:
    sys.exit("GEMINI_API_KEY tidak ada di .env")
config = yaml.safe_load(open(ROOT / "src" / "server" / "config.yaml", encoding="utf-8"))
MODEL = next((str(e["model"]) for e in (config.get("zanite") or {}).get("rantai") or [] if e.get("penyedia") == "gemini"), "gemini-3.1-flash-lite")
GAMBAR = ROOT / "data" / "zanite" / "tes_bersih.jpg"
BATAS_MS = 30000


def sensor(x, maks=1500):
    teks = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    teks = teks.replace(KUNCI, "***")
    return teks if len(teks) <= maks else teks[:maks] + f"... (+{len(teks) - maks} karakter)"


def panggil(nama, isi):
    klien = genai.Client(api_key=KUNCI, http_options=types.HttpOptions(
        timeout=BATAS_MS, retry_options=types.HttpRetryOptions(attempts=1)))
    cfg = types.GenerateContentConfig(
        temperature=0.3, max_output_tokens=300,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL))
    t0 = time.perf_counter()
    print(f"== {nama} (model {MODEL}, batas {BATAS_MS // 1000} dtk, ulang SDK mati)")
    try:
        r = klien.models.generate_content(model=MODEL, contents=isi, config=cfg)
        ms = round((time.perf_counter() - t0) * 1000)
        u = getattr(r, "usage_metadata", None)
        token = f"prompt={getattr(u, 'prompt_token_count', '?')} keluaran={getattr(u, 'candidates_token_count', '?')}" if u else "-"
        print(f"   BERHASIL {ms} ms; token {token}; jawaban: {sensor((r.text or '')[:120])!r}")
    except Exception as e:                                   # noqa: BLE001 - tujuan skrip ini memperlihatkan galatnya
        ms = round((time.perf_counter() - t0) * 1000)
        print(f"   GALAT {ms} ms; kelas={type(e).__name__}; kode HTTP={getattr(e, 'code', None)}; status={getattr(e, 'status', None)}")
        print(f"   pesan: {sensor(getattr(e, 'message', None) or str(e))}")
        rincian = getattr(e, "details", None)
        if rincian:
            print(f"   rincian: {sensor(rincian, 2500)}")


if __name__ == "__main__":
    panggil("1. hanya teks", "Jawab dengan satu kata: halo")
    time.sleep(5)                                            # jarak antar panggilan (aturan: minimal 4,5 dtk)
    gambar = types.Part.from_bytes(data=GAMBAR.read_bytes(), mime_type="image/jpeg")
    panggil("2. teks + data/zanite/tes_bersih.jpg", [gambar, "Sebutkan benda yang terlihat dan posisinya (kiri, tengah, kanan) dalam satu kalimat."])
