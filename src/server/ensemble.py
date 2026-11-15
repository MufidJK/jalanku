"""Weighted Boxes Fusion (WBF) per kelas untuk ensemble model kotak.

Salinan persis iou_matriks / wbf_kelas / wbf_gambar dari tools/ensemble_val.py
(pilihan final yang dikunci, lihat data/test-final/LOG.md). Jangan diubah di sini
tanpa mengubah keduanya: hasil server harus sama dengan hasil evaluasi.

Aturan conf: rata-rata atas SEMUA anggota dari conf tertinggi tiap anggota di
klaster; anggota yang tidak punya kotak di klaster itu dihitung 0.
"""
import numpy as np

WBF_IOU = 0.55


def iou_matriks(a, b):
    """a (n,4), b (m,4) -> (n,m)."""
    if not len(a) or not len(b):
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    la = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    lb = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(la[:, None] + lb[None, :] - inter, 1e-9)


def wbf_kelas(kotak, conf, mdl, n_model, thr=WBF_IOU):
    """Satu kelas, satu gambar. kotak (n,4), conf (n,), mdl (n,) indeks model. -> kotak gabungan (k,4), conf (k,)."""
    urut = np.argsort(-conf, kind="stable")
    gab = np.zeros((0, 4))
    sw, sxy, mx = [], [], []  # jumlah bobot, jumlah bobot*kotak, conf tertinggi per model
    for i in urut:
        k = -1
        if len(gab):
            v = iou_matriks(kotak[i][None], gab)[0]
            j = int(v.argmax())
            if v[j] > thr:
                k = j
        if k < 0:
            sw.append(0.0)
            sxy.append(np.zeros(4))
            mx.append(np.zeros(n_model))
            gab = np.vstack([gab, kotak[i][None]])
            k = len(sw) - 1
        sw[k] += conf[i]
        sxy[k] = sxy[k] + conf[i] * kotak[i]
        mx[k][mdl[i]] = max(mx[k][mdl[i]], conf[i])
        gab[k] = sxy[k] / sw[k]
    return gab, np.array([m.sum() / n_model for m in mx])


def wbf_gambar(daftar, thr=WBF_IOU):
    """daftar: prediksi satu gambar dari tiap model (dict cls/conf/xyxy). -> dict format prediksi."""
    n = len(daftar)
    cls = np.concatenate([d["cls"] for d in daftar])
    conf = np.concatenate([d["conf"] for d in daftar])
    xy = np.concatenate([d["xyxy"].reshape(-1, 4) for d in daftar])
    mdl = np.concatenate([np.full(len(d["cls"]), i) for i, d in enumerate(daftar)]).astype(int)
    oc, of, ox = [], [], []
    for c in np.unique(cls):
        s = cls == c
        g, f = wbf_kelas(xy[s], conf[s], mdl[s], n, thr)
        oc.append(np.full(len(f), c))
        of.append(f)
        ox.append(g)
    return dict(w=daftar[0]["w"], h=daftar[0]["h"], cls=np.concatenate(oc).astype(int) if oc else np.zeros(0, int),
                conf=np.concatenate(of) if of else np.zeros(0), xyxy=np.concatenate(ox) if ox else np.zeros((0, 4)), poly=None)
