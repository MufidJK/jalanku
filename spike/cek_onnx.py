"""Cek ONNX vs .pt untuk spike HP: jumlah deteksi (conf >= 0.25) pada 3 frame val pertama.

Jalankan dengan venv-export, dari root repo:
    venv-export\\Scripts\\python spike\\cek_onnx.py

Baca: models/onnx/*.onnx, models/ronde2/*.pt, data/dataset-gabung-kotak-v4/images/val/ (3 pertama, terurut).
Gambar yang sama (letterbox persegi, pad 114) diberikan ke .pt dan ONNX; ONNX dikenai NMS per kelas
(IoU 0.7), sama seperti yang dikerjakan app.js. Tidak menulis file apa pun.
"""
import glob
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import torch
import torchvision
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent
VAL = ROOT / "data" / "dataset-gabung-kotak-v4" / "images" / "val"
ONNX = ROOT / "models" / "onnx"
MODELS = [("box", "r2-kotak-v3_best.pt"), ("seg", "r2-seg-v3_best.pt")]
SIZES = (640, 416, 320)
CONF, IOU = 0.25, 0.7


def letterbox(im, s):
    h, w = im.shape[:2]
    r = min(s / h, s / w)
    nh, nw = round(h * r), round(w * r)
    out = np.full((s, s, 3), 114, np.uint8)
    top, left = (s - nh) // 2, (s - nw) // 2
    out[top:top + nh, left:left + nw] = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return out


def ringkas(cls, names):
    d = {}
    for c in cls:
        d[names[int(c)]] = d.get(names[int(c)], 0) + 1
    return f"{len(cls)} {dict(sorted(d.items()))}"


def main():
    imgs = sorted(glob.glob(str(VAL / "*.jpg")))[:3]
    for short, pt_name in MODELS:
        pt = YOLO(str(ROOT / "models" / "ronde2" / pt_name))
        names = pt.names
        nc = len(names)
        for sz in SIZES:
            sess = ort.InferenceSession(str(ONNX / f"{short}_{sz}.onnx"), providers=["CPUExecutionProvider"])
            for p in imgs:
                lb = letterbox(cv2.imread(p), sz)  # BGR
                x = np.ascontiguousarray(lb[:, :, ::-1].transpose(2, 0, 1)[None], np.float32) / 255
                ref = pt.predict(lb, imgsz=sz, conf=CONF, iou=IOU, verbose=False)[0].boxes.cls.numpy()
                o = sess.run(None, {"images": x})[0][0]  # [4+nc(+32), N]
                bx, sc = o[:4].T, o[4:4 + nc].T
                conf, cl = sc.max(1), sc.argmax(1)
                k = conf >= CONF
                xyxy = np.c_[bx[:, 0] - bx[:, 2] / 2, bx[:, 1] - bx[:, 3] / 2,
                             bx[:, 0] + bx[:, 2] / 2, bx[:, 1] + bx[:, 3] / 2][k]
                keep = torchvision.ops.batched_nms(torch.tensor(xyxy), torch.tensor(conf[k]),
                                                   torch.tensor(cl[k]), IOU).numpy()
                print(f"{short} {sz} {Path(p).name[:34]:34s} pt: {ringkas(ref, names)} | onnx+NMS: {ringkas(cl[k][keep], names)}")


if __name__ == "__main__":
    main()
