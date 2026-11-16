from collections import deque


PESAN_JALUR_TIDAK_TERLIHAT = "Hati-hati, jalur tidak terlihat"
PESAN_TANGGA_SEG = "Tangga di depan"


class MesinLogika:
    def __init__(self, config):
        self.config = config

        stabil = config.get("stabil", {})
        self.jendela_stabil = stabil.get("jendela", 3)
        self.minimal_stabil = stabil.get("minimal", 2)

        # Peringatan "jalur tidak terlihat": harus N frame BERURUTAN tanpa keluaran seg
        self.seg_kosong_minimal = config.get("seg_kosong_minimal", 3)
        if not 1 <= self.seg_kosong_minimal <= self.jendela_stabil:
            raise ValueError(
                f"seg_kosong_minimal ({self.seg_kosong_minimal}) harus 1.."
                f"stabil.jendela ({self.jendela_stabil})"
            )

        # Aturan C: "Tangga di depan" dari seg butuh lebih banyak frame (default = stabil.minimal)
        self.seg_tangga_stabil_minimal = config.get(
            "seg_tangga_stabil_minimal", self.minimal_stabil
        )
        if not 1 <= self.seg_tangga_stabil_minimal <= self.jendela_stabil:
            raise ValueError(
                f"seg_tangga_stabil_minimal ({self.seg_tangga_stabil_minimal}) "
                f"harus 1..stabil.jendela ({self.jendela_stabil})"
            )

        # Aturan B: objek "jauh" tidak jadi peringatan kalau seg kosong di frame ini
        self.jauh_butuh_seg = bool(config.get("jauh_butuh_seg", False))

        self.riwayat_frame = {}
        self.riwayat_seg = {}

        # Ambang skor -> tingkat (kunci YAML bisa int atau str)
        ambang = {
            int(k): float(v)
            for k, v in config.get(
                "ambang_tingkat", {3: 2.0, 2: 1.2}
            ).items()
        }
        self.ambang_tingkat = sorted(ambang.items(), reverse=True)

    def _riwayat(self, simpanan, sesi_id):
        """Riwayat per sesi; sesi terlama dibuang kalau terlalu banyak."""

        if sesi_id not in simpanan:
            maks = self.config.get("maks_sesi", 200)
            while len(simpanan) >= maks:
                simpanan.pop(next(iter(simpanan)))
            simpanan[sesi_id] = deque(maxlen=self.jendela_stabil)

        return simpanan[sesi_id]

    @staticmethod
    def buat_pesan(kelas, posisi, jarak):
        """Pesan untuk TTS, contoh: 'Tanaman pot di kanan, dekat'."""

        nama = kelas.replace("_", " ").capitalize()
        tempat = "di depan" if posisi == "tengah" else f"di {posisi}"

        return f"{nama} {tempat}, {jarak}"

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

        tingkat = 1

        for nilai_tingkat, batas in self.ambang_tingkat:
            if skor >= batas:
                tingkat = nilai_tingkat
                break

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
            "pesan": self.buat_pesan(
                objek_terpilih["kelas"],
                objek_terpilih["posisi"],
                objek_terpilih["jarak"],
            ),
            "kelas": objek_terpilih["kelas"],
            "posisi": objek_terpilih["posisi"],
            "jarak": objek_terpilih["jarak"],
            "tingkat": objek_terpilih["tingkat"],
        }

    def analisis_jalur(self, mask_seg, kelas_seg, nama_kelas_seg):
        """
        Menganalisis area bawah-tengah gambar (ROI) dari model seg.

        Menghasilkan (jalur, kandidat):
        - jalur: status terbuka/terhalang/tidak_jelas + persen_jalan
        - kandidat: peringatan dari seg untuk frame ini (belum
          distabilkan), atau None
        """

        # Tidak ada keluaran seg sama sekali (kamera menempel tembok/pintu,
        # gelap, ke langit-langit): tidak_jelas + kandidat peringatan.
        # Kandidat ini hanya keluar kalau kosong N frame berturut-turut
        # (lihat stabilkan_seg).
        if mask_seg is None or len(mask_seg) == 0:
            return {"status": "tidak_jelas", "persen_jalan": 0.0}, {
                "pesan": PESAN_JALUR_TIDAK_TERLIHAT,
                "kelas": "jalur_jalan",
                "posisi": "tengah",
                "jarak": "dekat",
                "tingkat": 2,
            }

        tinggi, lebar = mask_seg.shape[1:]

        # Area tengah gambar: zona_tengah dari lebar
        lebar_zona = self.config.get("zona_tengah", 0.40)
        x1 = int((1 - lebar_zona) / 2 * lebar)
        x2 = int((1 + lebar_zona) / 2 * lebar)

        # Area bawah gambar: sepertiga bagian terbawah
        y1 = int(tinggi * 2 / 3)

        roi = mask_seg[:, y1:tinggi, x1:x2] > 0.5

        def persen(nama):
            pilih = [
                i for i, kelas_id in enumerate(kelas_seg)
                if nama_kelas_seg.get(int(kelas_id)) == nama
            ]
            if not pilih or roi[0].size == 0:
                return 0.0
            return float(roi[pilih].any(axis=0).mean())

        persen_jalan = persen("jalur_jalan")
        persen_tangga = persen("tangga")
        persen_kendaraan = persen("jalan_kendaraan")

        min_tangga = self.config.get("seg_tangga_min", 0.05)
        min_kendaraan = self.config.get("seg_kendaraan_min", 0.50)
        ambang = self.config.get("jalur_ambang_terhalang", 0.20)

        kandidat = None

        if persen_tangga >= min_tangga:
            status = "terhalang"
            kandidat = ("tangga", PESAN_TANGGA_SEG, 3)
        elif persen_kendaraan >= min_kendaraan:
            status = "tidak_jelas"
            kandidat = ("jalan_kendaraan", "Area kendaraan, hati-hati", 2)
        elif persen_jalan < ambang:
            status = "terhalang"
            kandidat = ("jalur_jalan", "Jalur terhalang", 2)
        else:
            status = "terbuka"

        if kandidat is not None:
            kelas, pesan, tingkat = kandidat
            kandidat = {
                "pesan": pesan,
                "kelas": kelas,
                "posisi": "tengah",
                "jarak": "dekat",
                "tingkat": tingkat,
            }

        return {
            "status": status,
            "persen_jalan": round(persen_jalan, 4),
        }, kandidat

    def stabilkan_seg(self, kandidat, sesi_id="default"):
        """
        Peringatan seg hanya keluar kalau muncul minimal N dari N frame terakhir.

        Riwayat dikunci per PESAN (bukan kelas): "Jalur terhalang" dan
        "jalur tidak terlihat" sama-sama berkelas jalur_jalan tapi tidak
        boleh saling membantu. "Jalur tidak terlihat" lebih ketat: semua
        seg_kosong_minimal frame terakhir harus kosong tanpa jeda.
        """

        riwayat = self._riwayat(self.riwayat_seg, sesi_id)
        kunci = kandidat["pesan"] if kandidat else None
        riwayat.append(kunci)

        if kandidat is None:
            return None

        if kunci == PESAN_JALUR_TIDAK_TERLIHAT:
            n = self.seg_kosong_minimal
            terakhir = list(riwayat)[-n:]

            if len(terakhir) == n and all(k == kunci for k in terakhir):
                return kandidat

            return None

        minimal = self.minimal_stabil
        if kunci == PESAN_TANGGA_SEG:
            minimal = self.seg_tangga_stabil_minimal

        if sum(1 for k in riwayat if k == kunci) >= minimal:
            return kandidat

        return None

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

        riwayat = self._riwayat(self.riwayat_frame, sesi_id)

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

        # Aturan B: tanpa mask seg di frame ini, objek "jauh" tetap tergambar
        # di web (ada di daftar objek) tapi tidak boleh jadi peringatan.
        mask_seg = hasil_deteksi["mask_seg"]
        if self.jauh_butuh_seg and (mask_seg is None or len(mask_seg) == 0):
            objek_stabil = [
                objek for objek in objek_stabil if objek["jarak"] != "jauh"
            ]

        peringatan = self.pilih_peringatan(
            objek_stabil
        )

        jalur, kandidat_seg = self.analisis_jalur(
            mask_seg,
            hasil_deteksi["kelas_seg"],
            hasil_deteksi["nama_kelas_seg"],
        )

        peringatan_seg = self.stabilkan_seg(kandidat_seg, sesi_id)

        # SATU peringatan: tingkat tertinggi; seri -> objek kotak
        # (lebih spesifik daripada peringatan seg).
        if peringatan_seg is not None and (
            peringatan is None
            or peringatan_seg["tingkat"] > peringatan["tingkat"]
        ):
            peringatan = peringatan_seg

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
