"""ronde4_rantai.py - jalankan beberapa run tools/latih_ronde2.py berurutan tanpa ditunggu (ronde 4, section 5 dan 7).

Tiap run: kalau meta.json sudah "selesai" dilewati; kalau folder run sudah ada (terputus) dilanjutkan dengan --resume;
kalau belum ada dimulai dari awal. Mulai/selesai tiap run dicatat di data/ronde4/LOG.md. Aman dijalankan ulang kapan saja.

  python tools/ronde4_rantai.py r4-kotak-v3-1280 r4-kotak-v3-960-seed1
"""
import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data/ronde4/LOG.md"


def log(s):
    s = f"- [R4-rantai] {datetime.datetime.now():%Y-%m-%d %H:%M} {s}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(s + "\n")
    print(s, flush=True)


def meta(run):
    p = ROOT / "runs/ronde2" / run / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main():
    runs = sys.argv[1:]
    if not runs:
        sys.exit(__doc__)
    for run in runs:
        rd = ROOT / "runs/ronde2" / run
        if meta(run).get("status") == "selesai":
            log(f"{run}: sudah selesai, dilewati.")
            continue
        cmd = [sys.executable, "tools/latih_ronde2.py", "--run", run]
        if (rd / "weights" / "last.pt").exists():
            cmd.append("--resume")
        elif rd.exists():
            log(f"{run}: folder run ada tapi tanpa last.pt; BERHENTI (periksa {rd.relative_to(ROOT)}).")
            sys.exit(1)
        log(f"{run}: mulai{' (--resume)' if '--resume' in cmd else ''}.")
        r = subprocess.run(cmd, cwd=ROOT)
        m = meta(run)
        if m.get("status") != "selesai":
            log(f"{run}: BELUM selesai (kode {r.returncode}, status {m.get('status')}). Rantai berhenti; jalankan ulang perintah rantai untuk lanjut.")
            sys.exit(1)
        ringkas = {k: m.get(k) for k in ("epoch_terakhir", "menit", "vram_puncak_gib") if k in m}
        log(f"{run}: SELESAI. {ringkas} best.pt -> models/ronde2/{run}_best.pt")
    log(f"semua run selesai: {', '.join(runs)}.")


if __name__ == "__main__":
    main()
