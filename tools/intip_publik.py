"""intip_publik.py - HANYA MELIHAT dua dataset publik calon ronde 5 (tidak membangun dataset, tidak melatih).

Membaca data/intip-publik/ (objek-trotoar/raw = export Roboflow v2; sidewalk-barriers/daftar.json + sampel/ = daftar
gambar dan sampel 780 gambar berkotak dari API Roboflow). Menulis hanya ke data/intip-publik/.

  python -I tools/intip_publik.py statistik   # -> data/intip-publik/statistik.json + cetak ringkasan
  python -I tools/intip_publik.py sheet       # -> <dataset>_sheet.png, <dataset>_sheet_fokus.png, <dataset>_crop_<kelas>.png
"""
import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
IP = ROOT / "data" / "intip-publik"
OT = IP / "objek-trotoar" / "raw"
SB = IP / "sidewalk-barriers"


def buka(path):
    """Image.open + orientasi EXIF diterapkan (anotasi Roboflow dibuat pada gambar yang sudah di-auto-orient)."""
    return ImageOps.exif_transpose(Image.open(path))


OT_NAMA = ["bangku taman", "batu", "lobang", "mobil", "motor", "pohon", "pot bunga", "tiang"]
FOKUS = {"objek-trotoar": ("pohon", "tiang"), "sidewalk-barriers": ("curb", "pole", "bollard", "cone")}
SEED = 20261115
WARNA = ["#ff3b30", "#34c759", "#0a84ff", "#ffd60a", "#ff9f0a", "#bf5af2", "#64d2ff", "#ff2d92", "#a2845e", "#30d158",
         "#5e5ce6", "#ffffff"]


def muat_ot():
    """-> list dict(id, path, split, w, h, boxes[(kelas, x1, y1, x2, y2) piksel], stem)."""
    out = []
    for sp in ("train", "valid", "test"):
        for p in sorted((OT / sp / "images").iterdir()):
            with buka(p) as im:
                w, h = im.size
            bx = []
            lab = OT / sp / "labels" / (p.stem + ".txt")
            for r in (lab.read_text().splitlines() if lab.exists() else []):
                f = r.split()
                if len(f) >= 5:
                    c, x, y, bw, bh = int(f[0]), *map(float, f[1:5])
                    bx.append((OT_NAMA[c], (x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h))
            out.append(dict(id=p.stem, path=p, split=sp, w=w, h=h, boxes=bx, stem=re.sub(r"\.rf\.[0-9a-f]+$", "", p.stem), grup=["semua"]))
    return out


def muat_sb():
    out = []
    for s in json.loads((SB / "sampel" / "sampel.json").read_text(encoding="utf-8")):
        p = SB / "sampel" / "images" / f"{s['id']}.jpg"
        with buka(p) as im:
            w, h = im.size
        aw, ah = s.get("w") or w, s.get("h") or h
        aw, ah = float(aw), float(ah)
        fx, fy = w / aw, h / ah
        bx = []
        for b in s["boxes"]:  # sebagian koordinat datang sebagai string
            x, y, bw, bh = (float(b[k]) for k in ("x", "y", "width", "height"))
            bx.append((b["label"], (x - bw / 2) * fx, (y - bh / 2) * fy, (x + bw / 2) * fx, (y + bh / 2) * fy))
        out.append(dict(id=s["id"], path=p, split=s["split"], w=w, h=h, boxes=bx, stem=s["name"], grup=s["grup"], anot=(aw, ah)))
    return out


def dhash(path, n=8):
    with buka(path) as im:
        g = im.convert("L").resize((n + 1, n), Image.BILINEAR)
    px = list(g.tobytes())
    v = 0
    for r in range(n):
        for c in range(n):
            v = (v << 1) | (px[r * (n + 1) + c] > px[r * (n + 1) + c + 1])
    return v


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def bentuk(data):
    """Per kelas: n, median tinggi/lebar, lebar relatif, tinggi relatif, porsi kotak menyentuh tepi atas."""
    k = defaultdict(list)
    for d in data:
        for c, x1, y1, x2, y2 in d["boxes"]:
            bw, bh = max(x2 - x1, 1e-6), max(y2 - y1, 1e-6)
            k[c].append((bh / bw, bw / d["w"], bh / d["h"], y1 / d["h"] < 0.02, y2 / d["h"]))
    out = {}
    for c, v in sorted(k.items()):
        out[c] = dict(n=len(v), rasio_t_per_l=dict(p10=q([a[0] for a in v], .1), median=q([a[0] for a in v], .5), p90=q([a[0] for a in v], .9)),
                      lebar_rel=dict(median=q([a[1] for a in v], .5), p90=q([a[1] for a in v], .9)),
                      tinggi_rel=dict(median=q([a[2] for a in v], .5), p90=q([a[2] for a in v], .9)),
                      sentuh_atas=sum(a[3] for a in v) / len(v), y2_rel_median=q([a[4] for a in v], .5))
    return out


def statistik():
    h = {}
    ot = muat_ot()
    hs = defaultdict(list)
    for d in ot:
        hs[dhash(d["path"])].append(d)
    stem = defaultdict(list)
    for d in ot:
        stem[d["stem"]].append(d)
    lintas = sum(1 for v in stem.values() if len({d["split"] for d in v}) > 1)
    lintas_h = sum(1 for v in hs.values() if len({d["split"] for d in v}) > 1)
    # stem yang sama: apakah gambarnya identik (dhash sama) atau varian augmentasi (dhash beda)?
    multi = [v for v in stem.values() if len(v) > 1]
    stem_varian = sum(1 for v in multi if len({dhash(d["path"]) for d in v}) > 1)
    h["objek-trotoar"] = dict(
        n_gambar=len(ot), split=Counter(d["split"] for d in ot), ukuran=Counter(f"{d['w']}x{d['h']}" for d in ot),
        instans=Counter(c for d in ot for c, *_ in d["boxes"]), gambar_per_kelas=Counter(c for d in ot for c in {b[0] for b in d["boxes"]}),
        stem_unik=len(stem), stem_lebih_dari_1=len(multi), salinan_per_stem=Counter(len(v) for v in stem.values()),
        stem_multi_dengan_gambar_berbeda=stem_varian, stem_lintas_split=lintas,
        dhash_unik=len(hs), dhash_lintas_split=lintas_h, kotak_per_gambar_median=statistics.median(len(d["boxes"]) for d in ot),
        bentuk=bentuk(ot), pohon_per_gambar=Counter(sum(1 for b in d["boxes"] if b[0] == "pohon") for d in ot if any(b[0] == "pohon" for b in d["boxes"])))
    sb = muat_sb()
    acak = [d for d in sb if "acak" in d["grup"]]
    hs2 = defaultdict(list)
    for d in acak:
        hs2[dhash(d["path"])].append(d)
    h["sidewalk-barriers"] = dict(
        n_sampel=len(sb), n_acak=len(acak), ukuran_acak=Counter(f"{d['w']}x{d['h']}" for d in acak).most_common(15),
        orientasi_acak=Counter("potret" if d["h"] > d["w"] * 1.1 else "lanskap" if d["w"] > d["h"] * 1.1 else "persegi" for d in acak),
        anotasi_beda_ukuran=sum(1 for d in sb if d["anot"] != (d["w"], d["h"])),
        dhash_unik_acak=len(hs2), kosong_acak=sum(1 for d in acak if not d["boxes"]), bentuk=bentuk(sb),
        curb_per_gambar=Counter(sum(1 for b in d["boxes"] if b[0] == "curb") for d in sb if "curb" in d["grup"]),
        nama_rf_acak=sum(1 for d in acak if re.search(r"_(jpg|png|jpeg|JPG)$", d["stem"])))
    (IP / "statistik.json").write_text(json.dumps(h, indent=1, ensure_ascii=False, default=lambda o: dict(o)), encoding="utf-8")
    print(json.dumps(h, indent=1, ensure_ascii=False, default=lambda o: dict(o)))


def _font(n=13):
    for f in ("arialbd.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, n)
        except OSError:
            pass
    return ImageFont.load_default()


def _ubin(d, sisi, peta, font):
    with buka(d["path"]) as im:
        im = im.convert("RGB")
    s = sisi / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BILINEAR)
    g = ImageDraw.Draw(im)
    for c, x1, y1, x2, y2 in d["boxes"]:
        w = WARNA[peta.setdefault(c, len(peta)) % len(WARNA)]
        g.rectangle([x1 * s, y1 * s, x2 * s, y2 * s], outline=w, width=2)
        t = c
        tb = g.textbbox((0, 0), t, font=font)
        ty = max(0, y1 * s - (tb[3] - tb[1]) - 4)
        g.rectangle([x1 * s, ty, x1 * s + tb[2] + 4, ty + tb[3] + 3], fill=w)
        g.text((x1 * s + 2, ty), t, fill="black", font=font)
    k = Image.new("RGB", (sisi, sisi + 16), "#202020")
    k.paste(im, ((sisi - im.width) // 2, (sisi - im.height) // 2))
    ImageDraw.Draw(k).text((3, sisi + 1), f"{d['split']} {d['w']}x{d['h']} {d['stem'][:34]}", fill="#dddddd", font=_font(11))
    return k


def _sheet(daftar, out, kolom, sisi=384):
    peta, font = {}, _font()
    ub = [_ubin(d, sisi, peta, font) for d in daftar]
    baris = -(-len(ub) // kolom)
    S = Image.new("RGB", (kolom * sisi, baris * (sisi + 16)), "black")
    for i, u in enumerate(ub):
        S.paste(u, ((i % kolom) * sisi, (i // kolom) * (sisi + 16)))
    S.save(out)
    print(out, S.size, len(ub))


def _crop(data, kelas, out, n=48, kolom=8, sisi=224, konteks=0.6):
    """Potongan kotak satu kelas + konteks di sekelilingnya, kotaknya digambar: untuk menilai batang vs tajuk, segmen vs garis."""
    rng = random.Random(SEED)
    semua = [(d, b) for d in data for b in d["boxes"] if b[0] == kelas]
    S = Image.new("RGB", (kolom * sisi, -(-min(n, len(semua)) // kolom) * sisi), "black")
    for i, (d, (c, x1, y1, x2, y2)) in enumerate(rng.sample(semua, min(n, len(semua)))):
        with buka(d["path"]) as im:
            im = im.convert("RGB")
        m = konteks * max(x2 - x1, y2 - y1)
        a = [max(0, x1 - m), max(0, y1 - m), min(im.width, x2 + m), min(im.height, y2 + m)]
        cr = im.crop(tuple(map(round, a)))
        s = sisi / max(cr.size)
        cr = cr.resize((max(1, round(cr.width * s)), max(1, round(cr.height * s))), Image.BILINEAR)
        ImageDraw.Draw(cr).rectangle([(x1 - a[0]) * s, (y1 - a[1]) * s, (x2 - a[0]) * s, (y2 - a[1]) * s], outline="#ff3b30", width=2)
        S.paste(cr, ((i % kolom) * sisi + (sisi - cr.width) // 2, (i // kolom) * sisi + (sisi - cr.height) // 2))
    S.save(out)
    print(out, S.size)


def sheet():
    rng = random.Random(SEED)
    ot = muat_ot()
    _sheet(rng.sample(ot, 30), IP / "objek-trotoar_sheet.png", 6)
    f = [d for d in ot if any(b[0] in FOKUS["objek-trotoar"] for b in d["boxes"])]
    po = [d for d in f if any(b[0] == "pohon" for b in d["boxes"])]
    ti = [d for d in f if any(b[0] == "tiang" for b in d["boxes"])]
    _sheet(rng.sample(po, 10) + rng.sample(ti, 10), IP / "objek-trotoar_sheet_fokus.png", 5)
    for k in ("pohon", "tiang", "batu", "pot bunga"):
        _crop(ot, k, IP / f"objek-trotoar_crop_{k.replace(' ', '_')}.png")
    sb = muat_sb()
    acak = [d for d in sb if "acak" in d["grup"]]
    _sheet(rng.sample(acak, 30), IP / "sidewalk-barriers_sheet.png", 6)
    fk = []
    for k in FOKUS["sidewalk-barriers"]:
        fk += rng.sample([d for d in sb if k in d["grup"] and d not in fk], 5)
    _sheet(fk, IP / "sidewalk-barriers_sheet_fokus.png", 5)
    for k in ("curb", "pole", "bollard", "cone", "tree_trunk"):
        _crop(sb, k, IP / f"sidewalk-barriers_crop_{k}.png")
        _sheet(rng.sample([d for d in sb if k in d["grup"]], 20), IP / f"sidewalk-barriers_sheet_{k}.png", 5)


if __name__ == "__main__":
    {"statistik": statistik, "sheet": sheet}[sys.argv[1]]()
