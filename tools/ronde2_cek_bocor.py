"""Cek kebocoran lokasi TEST taman-ubm ke frame training (ronde 2 + train v2).

Embedding GENERIK (ResNet50 ImageNet torchvision, bukan model JalanKu). Atas izin Jeka (review
ronde 2, 14 Nov 2026) frame mentah taman-ubm di data/frame-blur dibaca untuk cek kebocoran saja.
Tidak ada model JalanKu yang dijalankan di frame test, tidak ada berkas yang diubah/dihapus.

Skor per kandidat:
  global  = cosine maksimum embedding frame (avgpool layer4) ke frame taman-ubm mana pun.
  patch   = rata-rata 8 patch teratas dari (mirip_taman - mirip_referensi), di mana
            mirip_taman = cosine maks patch layer4 ke semua patch taman-ubm,
            mirip_referensi = cosine maks ke patch frame train v2 dari LOKASI LAIN
            (menekan kemiripan generik: lantai, plafon, kaca).
Kontrol positif: frame yang sudah dikeluarkan (data/ronde2/dikeluarkan/).

Keluaran: data/ronde2/bocor/ (skor.csv, lorong_lt3_waktu.csv, sheet_*.png).

  python tools/ronde2_cek_bocor.py
"""
import csv
import glob
import os
import re

import cv2
import numpy as np
import torch
import torchvision

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "ronde2", "bocor")
W, H = 448, 800  # input jaringan (rasio 9:16), peta layer4 = 14 x 25
TOPK = 8


def lokasi(stem):
    return re.split(r"_\d{4}-\d{2}-\d{2}_", stem)[0]


def video(stem):
    return stem.rsplit("_t", 1)[0]


def waktu(stem):
    return int(stem.rsplit("_t", 1)[1]) / 1000.0


def kumpulkan():
    kand = {}  # stem -> (path, sumber)
    for p in glob.glob(os.path.join(ROOT, "data", "dataset-kampus-kotak-v2", "images", "train", "*.jpg")):
        kand[os.path.splitext(os.path.basename(p))[0]] = (p, "train-v2")
    for p in glob.glob(os.path.join(ROOT, "data", "ronde2-review", "*.jpg")):
        kand[os.path.splitext(os.path.basename(p))[0]] = (p, "ronde2")
    for p in glob.glob(os.path.join(ROOT, "data", "ronde2", "dikeluarkan", "*.jpg")):
        kand[os.path.splitext(os.path.basename(p))[0]] = (p, "KONTROL-dikeluarkan")
    for s in kand:
        assert not lokasi(s).startswith(("selasar-lt11", "pot-lt11", "taman-ubm")), s
    taman = sorted(glob.glob(os.path.join(ROOT, "data", "frame-blur", "taman-ubm*", "*.jpg")))
    lt3 = sorted(glob.glob(os.path.join(ROOT, "data", "frame-blur", "lorong-lt3-eskalator-alfa-tower*", "*.jpg")))
    return kand, taman, lt3


class Fitur:
    def __init__(self):
        m = torchvision.models.resnet50(weights=torchvision.models.ResNet50_Weights.IMAGENET1K_V2)
        self.net = torch.nn.Sequential(*list(m.children())[:-2]).eval().cuda().half()
        self.mean = torch.tensor([0.485, 0.456, 0.406], device="cuda").view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], device="cuda").view(1, 3, 1, 1)

    @torch.no_grad()
    def __call__(self, paths, bs=16):
        G, P = [], []
        for i in range(0, len(paths), bs):
            ims = [cv2.cvtColor(cv2.resize(cv2.imread(p), (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
                   for p in paths[i:i + bs]]
            x = torch.from_numpy(np.stack(ims)).cuda().permute(0, 3, 1, 2).float() / 255
            x = ((x - self.mean) / self.std).half()
            f = self.net(x).float()  # B,2048,25,14
            G.append(torch.nn.functional.normalize(f.mean((2, 3)), dim=1))
            P.append(torch.nn.functional.normalize(f.flatten(2).transpose(1, 2), dim=2))  # B,350,2048
        return torch.cat(G), torch.cat(P)


def maks_ke_bank(Pq, bank, chunk=8192):
    """Pq: (n,2048), bank: (m,2048) -> (best sim (n,), idx (n,))"""
    best = torch.full((Pq.shape[0],), -1.0, device="cuda")
    idx = torch.zeros(Pq.shape[0], dtype=torch.long, device="cuda")
    q = Pq.half()
    for j in range(0, bank.shape[0], chunk):
        s = (q @ bank[j:j + chunk].T).float()
        v, k = s.max(1)
        upd = v > best
        best[upd], idx[upd] = v[upd], k[upd] + j
    return best, idx


def skor(stems, Gc, Pc, Gt, Pt_bank, ref_P, ref_lok, lok_of):
    hasil = []
    npp = Pc.shape[1]
    for i, s in enumerate(stems):
        gs = (Gc[i:i + 1] @ Gt.T).squeeze(0)
        g_best, g_idx = gs.max(0)
        st, it = maks_ke_bank(Pc[i], Pt_bank)
        mask = torch.tensor([l != lok_of(s) for l in ref_lok], device="cuda")
        rb = ref_P[mask].reshape(-1, ref_P.shape[-1])
        sr, _ = maks_ke_bank(Pc[i], rb)
        d = st - sr
        top = torch.topk(d, TOPK)
        frame_taman = (it[top.indices] // npp).mode().values.item()
        hasil.append(dict(stem=s, glob=g_best.item(), glob_taman=g_idx.item(), patch=top.values.mean().item(),
                          patch_taman=frame_taman, mirip_taman_top=st[top.indices].mean().item(),
                          patch_idx=top.indices.cpu().numpy()))
    return hasil


def thumb(p, w=216, h=384, patches=None, teks=None, warna=(0, 0, 255)):
    im = cv2.resize(cv2.imread(p), (w, h), interpolation=cv2.INTER_AREA)
    if patches is not None:
        gw, gh = 14, 25
        for k in patches:
            r, c = divmod(int(k), gw)
            x0, y0 = int(c * w / gw), int(r * h / gh)
            cv2.rectangle(im, (x0, y0), (int((c + 1) * w / gw), int((r + 1) * h / gh)), warna, 2)
    if teks:
        for j, t in enumerate(teks):
            y = 16 + 16 * j
            cv2.putText(im, t, (4, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(im, t, (4, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
    return im


def main():
    os.makedirs(OUT, exist_ok=True)
    kand, taman, lt3 = kumpulkan()
    stems = sorted(kand)
    print(f"kandidat {len(stems)}, taman-ubm {len(taman)}, lorong-lt3 mentah {len(lt3)}")
    F = Fitur()
    Gc, Pc = F([kand[s][0] for s in stems])
    Gt, Pt = F(taman)
    Pt_bank = Pt.reshape(-1, Pt.shape[-1]).half()
    tr = [s for s in stems if kand[s][1] == "train-v2"]
    ref_P = Pc[[stems.index(s) for s in tr]].half()
    ref_lok = [lokasi(s) for s in tr]

    H1 = skor(stems, Gc, Pc, Gt, Pt_bank, ref_P, ref_lok, lokasi)
    for h in H1:
        h["sumber"] = kand[h["stem"]][1]
    # peringkat gabungan: rata-rata peringkat patch dan global
    for key in ("patch", "glob"):
        for r, h in enumerate(sorted(H1, key=lambda h: -h[key])):
            h["rank_" + key] = r + 1
    for h in H1:
        h["rank_gab"] = (h["rank_patch"] + h["rank_glob"]) / 2
    H1.sort(key=lambda h: h["rank_gab"])
    with open(os.path.join(OUT, "skor.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["urut", "stem", "sumber", "lokasi", "skor_patch", "skor_global", "rank_patch", "rank_global",
                     "taman_terdekat_patch", "taman_terdekat_global"])
        for i, h in enumerate(H1):
            wr.writerow([i + 1, h["stem"], h["sumber"], lokasi(h["stem"]), f"{h['patch']:.4f}", f"{h['glob']:.4f}",
                         h["rank_patch"], h["rank_glob"], os.path.basename(taman[h["patch_taman"]]),
                         os.path.basename(taman[h["glob_taman"]])])

    # lorong-lt3 mentah: profil waktu (konteks; frame ini belum tentu dipakai training)
    lt3_stems = [os.path.splitext(os.path.basename(p))[0] for p in lt3]
    Gl, Pl = F(lt3)
    H2 = skor(lt3_stems, Gl, Pl, Gt, Pt_bank, ref_P, ref_lok, lokasi)
    with open(os.path.join(OUT, "lorong_lt3_waktu.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["stem", "pov", "t", "skor_patch", "skor_global", "dipakai"])
        for h in H2:
            s = h["stem"]
            dip = kand[s][1] if s in kand else ""
            wr.writerow([s, "mata" if "_mata_" in s else "dada", f"{waktu(s):.1f}", f"{h['patch']:.4f}",
                         f"{h['glob']:.4f}", dip])

    # contact sheet kandidat: pasangan [kandidat | taman terdekat], 4 pasang per baris, 20 per sheet
    per, kol = 20, 4
    for n, a in enumerate(range(0, min(len(H1), 60), per)):
        tiles = []
        for i, h in enumerate(H1[a:a + per]):
            s = h["stem"]
            lab = [f"#{a + i + 1} {h['sumber']}", lokasi(s)[:24], s.rsplit('_', 2)[1] + " t=" + f"{waktu(s):.0f}s",
                   f"patch {h['patch']:.3f} (r{h['rank_patch']})", f"global {h['glob']:.3f} (r{h['rank_glob']})"]
            warna = (0, 0, 255) if h["sumber"].startswith("KONTROL") else (0, 255, 255)
            c = thumb(kand[s][0], patches=h["patch_idx"], teks=lab, warna=warna)
            tp = taman[h["patch_taman"]]
            t = thumb(tp, teks=["taman-ubm (TEST)", os.path.basename(tp).rsplit("_", 2)[1] + " t=" +
                                f"{waktu(os.path.splitext(os.path.basename(tp))[0]):.0f}s"])
            tiles.append(cv2.copyMakeBorder(np.hstack([c, t]), 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=(40, 40, 40)))
        while len(tiles) % kol:
            tiles.append(np.full_like(tiles[0], 40))
        sheet = np.vstack([np.hstack(tiles[r:r + kol]) for r in range(0, len(tiles), kol)])
        cv2.imwrite(os.path.join(OUT, f"sheet_{n + 1}_urut{a + 1}-{a + per}.png"), sheet)

    # sheet lorong-lt3 mentah t=170-250 s, kedua POV, tiap ~4 s
    for pov in ("dada", "mata"):
        hs = [h for h in H2 if f"_{pov}_" in h["stem"] and 170 <= waktu(h["stem"]) <= 250]
        hs = hs[::2]
        tiles = [thumb(lt3[lt3_stems.index(h["stem"])], w=162, h=288, patches=h["patch_idx"],
                       teks=[f"t={waktu(h['stem']):.0f}s", f"p {h['patch']:.3f}", f"g {h['glob']:.3f}",
                             kand[h['stem']][1] if h["stem"] in kand else ""]) for h in hs]
        kol2 = 10
        while len(tiles) % kol2:
            tiles.append(np.full_like(tiles[0], 40))
        sheet = np.vstack([np.hstack(tiles[r:r + kol2]) for r in range(0, len(tiles), kol2)])
        cv2.imwrite(os.path.join(OUT, f"lorong_lt3_{pov}_170-250s.png"), sheet)

    print("10 teratas:")
    for i, h in enumerate(H1[:15]):
        print(f"{i + 1:3d} {h['sumber']:20s} {h['stem']:70s} patch {h['patch']:.3f} r{h['rank_patch']:<4d} "
              f"glob {h['glob']:.3f} r{h['rank_glob']}")


if __name__ == "__main__":
    main()
