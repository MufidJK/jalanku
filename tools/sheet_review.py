"""Sheet review: 6 frame per gambar, tiap frame [permukaan | objek], lebar panel 330 px."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
urut = {x.name: i + 1 for i, x in enumerate(sorted(Path('data/pilot/images').glob('*.jpg')))}
W = {"pilar": (255, 0, 255), "pohon": (0, 128, 255), "tepian": (0, 255, 255), "orang": (0, 255, 0),
     "tanaman_pot": (255, 255, 0), "kursi": (0, 165, 255), "kendaraan": (255, 80, 80), "tangga": (255, 160, 0)}
S = {"jalur_jalan": (80, 220, 80), "jalan_kendaraan": (60, 60, 255), "tangga": (255, 160, 0)}
PW, PH = 330, 586
k = PW / 1080


def frame(j):
    d = json.loads(j.read_text(encoding='utf-8'))
    img = cv2.imread(str(src / d['imagePath']))
    ov = img.copy()
    for s in d['shapes']:
        if s['label'] in S:
            cv2.fillPoly(ov, [np.array(s['points'], np.int32)], S[s['label']])
    a = cv2.resize(cv2.addWeighted(ov, 0.5, img, 0.5, 0), (PW, PH), interpolation=cv2.INTER_AREA)
    b = cv2.resize(img, (PW, PH), interpolation=cv2.INTER_AREA)
    for s in d['shapes']:
        if s['label'] not in W:
            continue
        p = np.array(s['points']) * k
        x1, y1, x2, y2 = (int(v) for v in (p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()))
        c = W[s['label']]
        cv2.rectangle(b, (x1, y1), (x2, y2), c, 1 if s['difficult'] else 2)
        t = f"{s['label'][:3]} {s['score']:.2f}"
        cv2.putText(b, t, (x1 + 2, y1 + 10), 0, 0.3, (0, 0, 0), 2)
        cv2.putText(b, t, (x1 + 2, y1 + 10), 0, 0.3, c, 1)
    v = np.hstack([a, b])
    t = f"{urut.get(d['imagePath'], '?')} {d['imagePath'][:30]}"
    cv2.putText(v, t, (3, 13), 0, 0.42, (0, 0, 0), 3)
    cv2.putText(v, t, (3, 13), 0, 0.42, (255, 255, 255), 1)
    return cv2.copyMakeBorder(v, 0, 3, 0, 3, cv2.BORDER_CONSTANT)


js = sorted(src.glob('*.json'))
for i in range(0, len(js), 6):
    t = [frame(j) for j in js[i:i + 6]]
    while len(t) < 6:
        t.append(np.zeros_like(t[0]))
    cv2.imwrite(str(out / f'r_{i // 6 + 1:02d}.jpg'), np.vstack([np.hstack(t[:3]), np.hstack(t[3:])]), [cv2.IMWRITE_JPEG_QUALITY, 88])
print(len(js))
