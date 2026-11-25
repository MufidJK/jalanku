"""Cek langsung per model (utama, lalu tiap model cadangan), model DIPAKSA satu-satu, dengan 7 aturan yang sama
seperti cek_langsung.py. Gemini sungguhan: 12 panggilan per model, jeda >= 4,5 dtk antar panggilan.

    venv\\Scripts\\python -I tests\\zanite\\cek_cadangan.py

- Daftar model dibaca dari config.yaml (zanite.rantai). Tiap model dijalankan lewat
  cek_langsung.utama(model_paksa=...): jalur server asli, satu model, tanpa model cadangan, batas_waktu_s dari config.
- Aturan 5 (median latensi <= 3,0 dtk) hanya berlaku untuk model utama; untuk model cadangan latensi hanya dilaporkan.
- Hanya data/zanite/tes_bersih.jpg dan tes_banner.jpg yang dikirim. Kunci dibaca dari .env dan tidak pernah dicetak/ditulis.
- Hasil: data/zanite/hasil_cadangan.md. Aturan TIDAK dilonggarkan; panggilan yang gagal di sisi penyedia (503, waktu habis)
  dilaporkan terpisah supaya jelas mana yang kegagalan model dan mana yang Google sedang padat.
"""
import asyncio
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cek_langsung as cl  # noqa: E402

KELUAR = cl.ROOT / "data" / "zanite" / "hasil_cadangan.md"
WAJIB = (1, 2, 6, 7)          # gagal salah satu = model cadangan dikeluarkan dari config.yaml


def gagal_penyedia(hasil):
    """Panggilan yang jatuh ke kalimat cadangan karena penyedia (bukan penjaga isi): (kode, jumlah)."""
    return [h for h in hasil if h["jenis"] == "cadangan" and h["penjaga"] not in cl.PENJAGA_ISI]


async def jalankan(daftar):
    semua = []
    for i, entri in enumerate(daftar):
        if i:
            await asyncio.sleep(cl.JEDA_S)
        model = entri.model
        print(f"\n===== {model} ({'utama' if i == 0 else 'cadangan'}) =====", flush=True)
        z, hasil = await cl.utama(model_paksa=tuple(entri))
        r, rincian, med = cl.nilai(hasil)
        semua.append(dict(model=model, utama=i == 0, z=z, hasil=hasil, r=r, rincian=rincian, med=med))
    return semua


def ringkas(m):
    r, utama = m["r"], m["utama"]
    aturan = (1, 2, 3, 4, 5, 6, 7) if utama else (1, 2, 3, 4, 6, 7)
    lulus = [i for i in aturan if r[i]]
    gagal = [i for i in aturan if not r[i]]
    galat = Counter(h["penjaga"] for h in gagal_penyedia(m["hasil"]))
    return aturan, lulus, gagal, galat


def tulis(semua):
    baris = [
        "# Hasil cek langsung per model (model utama dan cadangan)",
        "",
        f"Tanggal: {time.strftime('%Y-%m-%d')}. Skrip: `tests/zanite/cek_cadangan.py` (memakai `cek_langsung.utama(model_paksa=...)`: "
        "jalur server asli, in-process, satu model dipaksa, tanpa model cadangan).",
        f"Tiap model: 6 kasus x {cl.PUTARAN} putaran = {len(semua[0]['hasil'])} panggilan, jeda >= {cl.JEDA_S} dtk. Gambar: `tes_bersih.jpg` / `tes_banner.jpg` "
        "(garasi parkir tanpa orang). Aturan sama persis dengan `cek_langsung.py` (lihat `hasil_app.md`), tidak dilonggarkan. "
        "Aturan 5 (median latensi <= 3,0 dtk) hanya berlaku untuk model utama.",
        "",
        "## Ringkasan",
        "",
        "| Model | Peran | Aturan lulus | Aturan gagal | Median latensi | Galat yang terlihat |",
        "|---|---|---|---|---|---|",
    ]
    for m in semua:
        aturan, lulus, gagal, galat = ringkas(m)
        gal = "; ".join(f"{k} x{n}" for k, n in sorted(galat.items())) or "tidak ada"
        baris.append(f"| `{m['model']}` | {'utama' if m['utama'] else 'cadangan'} | {len(lulus)}/{len(aturan)} ({', '.join(map(str, lulus)) or '-'}) | "
                     f"{', '.join(map(str, gagal)) or '-'} | {m['med']:.2f} dtk | {gal} |")
    baris += ["", "Aturan 4 adalah target lunak (kerucut disebut). Aturan yang membuat model cadangan dikeluarkan dari `config.yaml`: "
              f"{', '.join(map(str, WAJIB))}.", ""]
    for m in semua:
        aturan, lulus, gagal, galat = ringkas(m)
        sakit = gagal_penyedia(m["hasil"])
        baris.append(f"- `{m['model']}`: {len(sakit)} dari {len(m['hasil'])} panggilan jatuh ke kalimat cadangan karena penyedia"
                     + (" (" + ", ".join(f"{h['kode']}{h['putaran']}={h['penjaga']}" for h in sakit) + ")" if sakit else "")
                     + (". Aturan yang gagal mungkin disebabkan ini, bukan isi jawaban model; baca bagian modelnya." if sakit and gagal else "."))
    baris.append("")
    for m in semua:
        isi = cl.tulis_laporan(m["z"], m["hasil"], m["r"], m["rincian"], m["med"], dengan_sebelumnya=False)
        isi = re.sub(r"^(#{1,4}) ", lambda x: "#" * (len(x.group(1)) + 1) + " ", isi, flags=re.M)
        isi = isi.replace("## Hasil cek langsung Zanite (Tahap 6, Bagian C)", f"## Model `{m['model']}` ({'utama' if m['utama'] else 'cadangan'})", 1)
        baris += [isi, ""]
    return "\n".join(baris)


def main():
    import yaml
    konfig = yaml.safe_load((cl.ROOT / "src" / "server" / "config.yaml").read_text(encoding="utf-8")) or {}
    daftar = cl.zn.Pengaturan(konfig.get("zanite")).rantai
    semua = asyncio.run(jalankan(daftar))
    teks = tulis(semua)
    cl.pastikan_tanpa_kunci(teks)
    KELUAR.write_text(teks, encoding="utf-8")
    print(f"\nTersimpan: {KELUAR.relative_to(cl.ROOT)}")
    for m in semua:
        aturan, lulus, gagal, galat = ringkas(m)
        print(f"{m['model']}: lulus {len(lulus)}/{len(aturan)} (gagal: {gagal or '-'}); median {m['med']:.2f} dtk; galat: {dict(galat) or '-'}")


if __name__ == "__main__":
    main()
