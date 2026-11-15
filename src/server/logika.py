from collections import deque


class MesinLogika:
    def __init__(self, config):
        self.config = config

        stabil = config.get("stabil", {})
        self.jendela_stabil = stabil.get("jendela", 3)
        self.minimal_stabil = stabil.get("minimal", 2)

        self.riwayat_frame = {}

    def tentukan_posisi(self, kotak):
        """
        Menentukan posisi objek:
        kiri, tengah, atau kanan.

        kotak: [x1, y1, x2, y2]
        Koordinat sudah dinormalisasi 0-1.
        """

        x1, y1, x2, y2 = kotak

        titik_tengah = (x1 + x2) / 2

        lebar_zona = self.config.get("zona_tengah", 0.40)
        batas_kiri = (1 - lebar_zona) / 2
        batas_kanan = 1 - batas_kiri

        if titik_tengah < batas_kiri:
            return "kiri"

        if titik_tengah > batas_kanan:
            return "kanan"

        return "tengah"


    def tentukan_jarak(self, kotak):
        """
        Memperkirakan jarak objek berdasarkan
        koordinat bawah bounding box (y2).

        Hasil: dekat, sedang, atau jauh.
        """

        y2 = kotak[3]

        batas = self.config.get(
            "jarak_y2",
            {
                "dekat": 0.85,
                "sedang": 0.65,
            },
        )

        if y2 >= batas["dekat"]:
            return "dekat"

        if y2 >= batas["sedang"]:
            return "sedang"

        return "jauh"

    def hitung_bahaya(self, kelas, posisi, jarak):
        """
        Menghitung skor bahaya berdasarkan:
        - Bobot kelas objek
        - Posisi objek
        - Perkiraan jarak objek
        """

        bobot_kelas = self.config.get("bobot_kelas", {})
        faktor_posisi = self.config.get("faktor_posisi", {})
        faktor_jarak = self.config.get("faktor_jarak", {})

        bobot = bobot_kelas.get(kelas, 1)
        posisi_factor = faktor_posisi.get(posisi, 1.0)
        jarak_factor = faktor_jarak.get(jarak, 1.0)

        skor = bobot * posisi_factor * jarak_factor

        if skor >= 2.5:
            tingkat = 3
        elif skor >= 1.2:
            tingkat = 2
        else:
            tingkat = 1

        peringatan_aktif = (
            posisi == "tengah" or jarak == "dekat"
        )

        return {
            "skor": round(skor, 2),
            "tingkat": tingkat,
            "peringatan_aktif": peringatan_aktif,
        }

    def analisis_objek(self, daftar_objek):
        """
        Menganalisis seluruh objek hasil deteksi YOLO.
        """

        hasil = []

        for objek in daftar_objek:
            kelas = objek["kelas"]
            kotak = objek["kotak"]

            posisi = self.tentukan_posisi(kotak)
            jarak = self.tentukan_jarak(kotak)

            bahaya = self.hitung_bahaya(
                kelas,
                posisi,
                jarak,
            )

            hasil.append({
                "kelas": kelas,
                "conf": objek["conf"],
                "kotak": kotak,
                "posisi": posisi,
                "jarak": jarak,
                "skor": bahaya["skor"],
                "tingkat": bahaya["tingkat"],
                "peringatan_aktif": bahaya["peringatan_aktif"],
            })

        return hasil

    def pilih_peringatan(self, daftar_analisis):
        """
        Memilih satu objek dengan skor bahaya tertinggi.
        """

        kandidat = [
            objek
            for objek in daftar_analisis
            if objek["peringatan_aktif"]
        ]

        if not kandidat:
            return None

        objek_terpilih = max(
            kandidat,
            key=lambda objek: objek["skor"],
        )

        return {
            "pesan": (
                f"{objek_terpilih['kelas']} di "
                f"{objek_terpilih['posisi']}, "
                f"{objek_terpilih['jarak']}"
            ),
            "kelas": objek_terpilih["kelas"],
            "posisi": objek_terpilih["posisi"],
            "jarak": objek_terpilih["jarak"],
            "tingkat": objek_terpilih["tingkat"],
        }

    def analisis_jalur(self, mask_seg, kelas_seg, nama_kelas_seg):
        """
        Menganalisis jalur pejalan kaki pada area
        bawah-tengah gambar.

        Menghasilkan:
        - status: terbuka, terhalang, tidak_jelas
        - persen_jalan: proporsi jalur pejalan kaki
        """

        if mask_seg is None or len(mask_seg) == 0:
            return {
                "status": "tidak_jelas",
                "persen_jalan": 0.0,
            }

        tinggi, lebar = mask_seg.shape[1:]

        # Area tengah gambar: 40% lebar
        lebar_zona = self.config.get("zona_tengah", 0.40)
        x1 = int((1 - lebar_zona) / 2 * lebar)
        x2 = int((1 + lebar_zona) / 2 * lebar)

        # Area bawah gambar: sepertiga bagian terbawah
        y1 = int(tinggi * 2 / 3)
        y2 = tinggi

        area = (slice(y1, y2), slice(x1, x2))

        nama_jalur = next(
            (kelas_id for kelas_id, nama in nama_kelas_seg.items()
             if nama == "jalur_jalan"),
            None,
        )

        nama_tangga = next(
            (kelas_id for kelas_id, nama in nama_kelas_seg.items()
             if nama == "tangga"),
            None,
        )

        if nama_jalur is None:
            return {
                "status": "tidak_jelas",
                "persen_jalan": 0.0,
            }

        # Gabungkan mask jalur pejalan kaki
        mask_jalan = None
        mask_tangga = None

        for mask, kelas_id in zip(mask_seg, kelas_seg):
            area_mask = mask[area] > 0.5

            if kelas_id == nama_jalur:
                if mask_jalan is None:
                    mask_jalan = area_mask.copy()
                else:
                    mask_jalan |= area_mask

            if kelas_id == nama_tangga:
                if mask_tangga is None:
                    mask_tangga = area_mask.copy()
                else:
                    mask_tangga |= area_mask

        persen_jalan = (
            float(mask_jalan.mean())
            if mask_jalan is not None
            else 0.0
        )

        ambang = self.config.get(
            "jalur_ambang_terhalang",
            0.20,
        )

        ada_tangga = (
            mask_tangga is not None
            and bool(mask_tangga.any())
        )

        if ada_tangga:
            status = "terhalang"
        elif mask_jalan is None:
            status = "tidak_jelas"
        elif persen_jalan < ambang:
            status = "terhalang"
        else:
            status = "terbuka"

        return {
            "status": status,
            "persen_jalan": round(persen_jalan, 4),
        }

    def hitung_iou(self, kotak_a, kotak_b):
        """Menghitung Intersection over Union dua bounding box."""

        ax1, ay1, ax2, ay2 = kotak_a
        bx1, by1, bx2, by2 = kotak_b

        x1 = max(ax1, bx1)
        y1 = max(ay1, by1)
        x2 = min(ax2, bx2)
        y2 = min(ay2, by2)

        luas_irisan = max(0, x2 - x1) * max(0, y2 - y1)

        luas_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        luas_b = max(0, bx2 - bx1) * max(0, by2 - by1)

        luas_gabungan = luas_a + luas_b - luas_irisan

        if luas_gabungan <= 0:
            return 0.0

        return luas_irisan / luas_gabungan

    def stabilkan_objek(self, daftar_objek, sesi_id="default"):
        """Mempertahankan objek yang muncul minimal N dari N frame."""

        riwayat = self.riwayat_frame.setdefault(
            sesi_id,
            deque(maxlen=self.jendela_stabil),
        )

        frame_sekarang = [
            {
                "kelas": objek["kelas"],
                "kotak": objek["kotak"],
            }
            for objek in daftar_objek
        ]

        riwayat.append(frame_sekarang)

        objek_stabil = []

        for objek in daftar_objek:
            jumlah_frame = 0

            for frame in riwayat:
                ditemukan = any(
                    sebelumnya["kelas"] == objek["kelas"]
                    and self.hitung_iou(
                        objek["kotak"],
                        sebelumnya["kotak"],
                    ) >= 0.30
                    for sebelumnya in frame
                )

                if ditemukan:
                    jumlah_frame += 1

            if jumlah_frame >= self.minimal_stabil:
                objek_stabil.append(objek)

        return objek_stabil

    def proses(self, hasil_deteksi, sesi_id='default'):
        """
        Menggabungkan analisis objek dan jalur
        menjadi output navigasi JalanKu.
        """

        hasil_objek = self.analisis_objek(
            hasil_deteksi["objek"]
        )

        objek_stabil = self.stabilkan_objek(
            hasil_objek,
            sesi_id,
        )

        peringatan = self.pilih_peringatan(
            objek_stabil
        )

        jalur = self.analisis_jalur(
            hasil_deteksi["mask_seg"],
            hasil_deteksi["kelas_seg"],
            hasil_deteksi["nama_kelas_seg"],
        )

        objek_api = [
            {
                "kelas": objek["kelas"],
                "conf": objek["conf"],
                "kotak": objek["kotak"],
                "posisi": objek["posisi"],
                "jarak": objek["jarak"],
            }
            for objek in hasil_objek
        ]

        return {
            "versi_kontrak": 1,
            "waktu_ms": hasil_deteksi["waktu_ms"],
            "peringatan": peringatan,
            "objek": objek_api,
            "jalur": jalur,
        }
