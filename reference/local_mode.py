import cv2
from inference import get_model

from config import API_KEY, MODEL_ID, CONFIDENCE, KAMERA_INDEX, KELAS_DIPAKAI
from rules import buat_pesan
from speech import Pembicara


def main():
    print("Memuat model (pertama kali butuh internet)...")
    model = get_model(model_id=MODEL_ID, api_key=API_KEY)
    bicara = Pembicara()

    cap = cv2.VideoCapture(KAMERA_INDEX)
    if not cap.isOpened():
        raise SystemExit("Kamera tidak terbaca. Coba ganti KAMERA_INDEX di config.py")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]

        hasil = model.infer(frame, confidence=CONFIDENCE)[0]

        deteksi = []
        for p in hasil.predictions:
            if p.class_name not in KELAS_DIPAKAI:
                continue
            deteksi.append({
                "kelas": p.class_name, "x": p.x, "y": p.y,
                "w": p.width, "h": p.height, "conf": p.confidence,
            })
            x1, y1 = int(p.x - p.width / 2), int(p.y - p.height / 2)
            x2, y2 = int(p.x + p.width / 2), int(p.y + p.height / 2)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{p.class_name} {p.confidence:.2f}", (x1, max(y1 - 8, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        pesan = buat_pesan(deteksi, w, h)
        if pesan:
            kunci, teks, urgent = pesan
            bicara.ucapkan(kunci, teks, urgent)
            cv2.putText(frame, teks, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (0, 0, 255), 2)

        cv2.imshow("JalanKu (tekan q untuk keluar)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
