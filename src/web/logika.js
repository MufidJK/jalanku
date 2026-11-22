/*
 * JalanKu - logika peringatan di JavaScript.
 *
 * Port 1:1 dari src/server/logika.py (MesinLogika). Hasilnya harus IDENTIK dengan
 * versi Python (dibuktikan oleh tests/logika/cek_logika.mjs di 11.299 frame rekaman
 * + 42 kasus sintetis). Belum dipakai oleh aplikasi; disiapkan untuk mode "HP saja".
 *
 * Tanpa dependensi, tanpa DOM. Browser: globalThis.MesinLogika. Node: module.exports.
 *
 * PAKAI
 *   const mesin = new MesinLogika(config);      // config = isi src/web/logika-config.json
 *   const hasil = mesin.proses(hasilDeteksi, sesiId, waktuS);
 *
 * hasilDeteksi (sama dengan keluaran MesinDeteksi.prediksi di Python):
 *   {
 *     objek: [{ kelas: "pilar", conf: 0.9, kotak: [x1, y1, x2, y2] }],   // kotak 0..1
 *     mask_seg: null | { n, h, w, data },      // data = Uint8Array (atau Float32Array)
 *                                              // panjang n*h*w, urutan [n][h][w], 1 = piksel
 *                                              // kelas itu (dibandingkan > 0.5). null atau
 *                                              // n = 0 berarti seg tidak mengeluarkan mask.
 *     kelas_seg: [0, 2],                       // id kelas tiap mask (panjang n)
 *     nama_kelas_seg: { "0": "jalur_jalan", "1": "jalan_kendaraan", "2": "tangga" },
 *     waktu_ms: 12.3                           // diteruskan apa adanya
 *   }
 * sesiId : string (default "default"). waktuS: detik (float); null -> jam monotonik.
 *
 * Keluaran: { versi_kontrak: 1, waktu_ms, peringatan: null | {pesan, kelas, posisi,
 *             jarak, tingkat}, objek: [{kelas, conf, kotak, posisi, jarak}],
 *             jalur: {status, persen_jalan} }
 *
 * Jebakan Python vs JS yang ditangani di sini:
 *  - int(x) memotong ke nol -> Math.trunc.
 *  - round(x, n) Python = setengah-genap pada nilai biner persis; toFixed JS membulatkan
 *    seri ke atas -> bulatPy().
 *  - capitalize() Python menurunkan huruf sisanya -> hurufAwalBesar().
 *  - dict.get(k, d) -> ambil() (kunci ada tapi null tetap dikembalikan, seperti Python).
 *  - max(..., key=(tingkat, skor)) mengembalikan yang PERTAMA saat seri -> loop dengan ">".
 *  - dict berurutan (pembuangan sesi tertua) -> Map; deque(maxlen) -> larik dipotong.
 *  - kunci int YAML ("3" di JSON) -> parse ke angka sebelum diurutkan.
 */
(function (akar) {
  "use strict";

  const PESAN_JALUR_TIDAK_TERLIHAT = "Hati-hati, jalur tidak terlihat";
  const PESAN_TANGGA_SEG = "Tangga di depan";

  class ValueError extends Error {
    constructor(pesan) {
      super(pesan);
      this.name = "ValueError";
    }
  }

  const punya = (obj, kunci) => Object.prototype.hasOwnProperty.call(obj, kunci);

  // dict.get(kunci, bawaan)
  function ambil(obj, kunci, bawaan) {
    return obj != null && punya(obj, kunci) ? obj[kunci] : bawaan;
  }

  // dict[kunci] (KeyError kalau tidak ada)
  function wajib(obj, kunci) {
    if (obj == null || !punya(obj, kunci)) throw new Error("KeyError: " + kunci);
    return obj[kunci];
  }

  // bool() Python
  function benarPy(v) {
    if (v == null || v === false || v === 0 || v === "") return false;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === "object") return Object.keys(v).length > 0;
    return true;
  }

  // round(x, nd) Python: setengah-genap pada nilai biner persis.
  // Seri persis hanya terjadi kalau x * 2^(nd+1) bilangan ganjil (x dyadic).
  function bulatPy(x, nd) {
    if (!Number.isFinite(x) || Math.abs(x) >= 1e21) return x;
    const neg = x < 0;
    const a = Math.abs(x);
    const p = 10 ** nd;
    const m = a * 2 ** (nd + 1);
    let hasil;
    if (Number.isInteger(m) && m % 2 === 1) {
      const bawah = (m * 5 ** nd - 1) / 2; // a * p = bawah + 0.5
      hasil = (bawah % 2 === 0 ? bawah : bawah + 1) / p;
    } else {
      hasil = Number(a.toFixed(nd));
    }
    return neg ? -hasil : hasil;
  }

  // str.replace("_", " ").capitalize()
  function hurufAwalBesar(s) {
    if (s.length === 0) return s;
    const pertama = String.fromCodePoint(s.codePointAt(0));
    return pertama.toUpperCase() + s.slice(pertama.length).toLowerCase();
  }

  // deque(maxlen=n).append(v)
  function tambahDeque(deque, nilai, maks) {
    deque.push(nilai);
    while (deque.length > maks) deque.shift();
  }

  function waktuMonotonik() {
    if (typeof performance !== "undefined" && performance.now) return performance.now() / 1000;
    return Date.now() / 1000;
  }

  class MesinLogika {
    constructor(config) {
      this.config = config;

      const stabil = ambil(config, "stabil", {});
      this.jendela_stabil = ambil(stabil, "jendela", 3);
      this.minimal_stabil = ambil(stabil, "minimal", 2);

      // Peringatan "jalur tidak terlihat": harus N frame BERURUTAN tanpa keluaran seg
      this.seg_kosong_minimal = ambil(config, "seg_kosong_minimal", 3);
      if (!(1 <= this.seg_kosong_minimal && this.seg_kosong_minimal <= this.jendela_stabil)) {
        throw new ValueError(
          `seg_kosong_minimal (${this.seg_kosong_minimal}) harus 1..` +
            `stabil.jendela (${this.jendela_stabil})`
        );
      }

      // Aturan C: "Tangga di depan" dari seg butuh lebih banyak frame
      this.seg_tangga_stabil_minimal = ambil(
        config,
        "seg_tangga_stabil_minimal",
        this.minimal_stabil
      );
      if (
        !(1 <= this.seg_tangga_stabil_minimal && this.seg_tangga_stabil_minimal <= this.jendela_stabil)
      ) {
        throw new ValueError(
          `seg_tangga_stabil_minimal (${this.seg_tangga_stabil_minimal}) ` +
            `harus 1..stabil.jendela (${this.jendela_stabil})`
        );
      }

      // Aturan B: objek "jauh" tidak jadi peringatan kalau seg kosong di frame ini
      this.jauh_butuh_seg = benarPy(ambil(config, "jauh_butuh_seg", false));

      // Aturan v1.1 A: tahan peringatan objek tengah+dekat sekian ms (0 = mati)
      this.tahan_dekat_ms = Number(ambil(config, "tahan_dekat_ms", 0));
      // Aturan v1.1 B: objek kiri/kanan dibatasi tingkatnya (3 = mati)
      this.samping_maks_tingkat = Math.trunc(Number(ambil(config, "samping_maks_tingkat", 3)));
      this.samping_masuk_tengah_min = Number(ambil(config, "samping_masuk_tengah_min", 0.1));

      this.riwayat_frame = new Map();
      this.riwayat_seg = new Map();
      this.dekat_terakhir = new Map(); // sesi -> [waktu_s, peringatan]

      // Ambang skor -> tingkat (kunci bisa angka atau string)
      const mentah = ambil(config, "ambang_tingkat", { 3: 2.0, 2: 1.2 });
      const ambang = new Map();
      for (const [k, v] of Object.entries(mentah)) {
        const kunci = Math.trunc(Number(k));
        if (Number.isNaN(kunci)) throw new ValueError(`ambang_tingkat: kunci tidak valid (${k})`);
        ambang.set(kunci, Number(v));
      }
      this.ambang_tingkat = [...ambang.entries()].sort((a, b) => b[0] - a[0]);
    }

    // Membuang sesi tertua sampai muat di bawah maks_sesi (dict berurutan Python).
    _beriRuang(simpanan) {
      const maks = ambil(this.config, "maks_sesi", 200);
      while (simpanan.size >= maks) {
        if (simpanan.size === 0) throw new Error("StopIteration");
        simpanan.delete(simpanan.keys().next().value);
      }
    }

    // Riwayat per sesi; sesi terlama dibuang kalau terlalu banyak.
    _riwayat(simpanan, sesiId) {
      if (!simpanan.has(sesiId)) {
        this._beriRuang(simpanan);
        simpanan.set(sesiId, []);
      }
      return simpanan.get(sesiId);
    }

    static buat_pesan(kelas, posisi, jarak) {
      const nama = hurufAwalBesar(kelas.split("_").join(" "));
      const tempat = posisi === "tengah" ? "di depan" : `di ${posisi}`;
      return `${nama} ${tempat}, ${jarak}`;
    }

    buat_pesan(kelas, posisi, jarak) {
      return MesinLogika.buat_pesan(kelas, posisi, jarak);
    }

    tentukan_posisi(kotak) {
      const [x1, , x2] = kotak;
      const titikTengah = (x1 + x2) / 2;

      const lebarZona = ambil(this.config, "zona_tengah", 0.4);
      const batasKiri = (1 - lebarZona) / 2;
      const batasKanan = 1 - batasKiri;

      if (titikTengah < batasKiri) return "kiri";
      if (titikTengah > batasKanan) return "kanan";
      return "tengah";
    }

    tentukan_jarak(kotak) {
      const y2 = kotak[3];
      const batas = ambil(this.config, "jarak_y2", { dekat: 0.85, sedang: 0.65 });

      if (y2 >= wajib(batas, "dekat")) return "dekat";
      if (y2 >= wajib(batas, "sedang")) return "sedang";
      return "jauh";
    }

    masuk_tengah(kotak) {
      const lebarZona = ambil(this.config, "zona_tengah", 0.4);
      const kiri = 0.5 - lebarZona / 2;
      const kanan = 0.5 + lebarZona / 2;
      return Math.max(0.0, Math.min(kotak[2], kanan) - Math.max(kotak[0], kiri));
    }

    hitung_bahaya(kelas, posisi, jarak, kotak = null) {
      const bobotKelas = ambil(this.config, "bobot_kelas", {});
      const faktorPosisi = ambil(this.config, "faktor_posisi", {});
      const faktorJarak = ambil(this.config, "faktor_jarak", {});

      const bobot = ambil(bobotKelas, kelas, 1);
      const posisiFactor = ambil(faktorPosisi, posisi, 1.0);
      const jarakFactor = ambil(faktorJarak, jarak, 1.0);

      const skor = bobot * posisiFactor * jarakFactor;

      let tingkat = 1;
      for (const [nilaiTingkat, batas] of this.ambang_tingkat) {
        if (skor >= batas) {
          tingkat = nilaiTingkat;
          break;
        }
      }

      // Aturan v1.1 B: benda di samping jalur tidak sampai merah, kecuali
      // kotaknya cukup masuk ke zona tengah.
      if (
        (posisi === "kiri" || posisi === "kanan") &&
        tingkat > this.samping_maks_tingkat &&
        (kotak == null || this.masuk_tengah(kotak) < this.samping_masuk_tengah_min)
      ) {
        tingkat = this.samping_maks_tingkat;
      }

      const peringatanAktif = posisi === "tengah" || jarak === "dekat";

      return {
        skor: bulatPy(skor, 2),
        tingkat,
        peringatan_aktif: peringatanAktif,
      };
    }

    analisis_objek(daftarObjek) {
      const hasil = [];

      for (const objek of daftarObjek) {
        const kelas = objek.kelas;
        const kotak = objek.kotak;

        const posisi = this.tentukan_posisi(kotak);
        const jarak = this.tentukan_jarak(kotak);
        const bahaya = this.hitung_bahaya(kelas, posisi, jarak, kotak);

        hasil.push({
          kelas,
          conf: objek.conf,
          kotak,
          posisi,
          jarak,
          skor: bahaya.skor,
          tingkat: bahaya.tingkat,
          peringatan_aktif: bahaya.peringatan_aktif,
        });
      }

      return hasil;
    }

    pilih_peringatan(daftarAnalisis) {
      let terpilih = null;

      // max(kandidat, key=(tingkat, skor)): seri -> yang pertama
      for (const objek of daftarAnalisis) {
        if (!objek.peringatan_aktif) continue;
        if (
          terpilih === null ||
          objek.tingkat > terpilih.tingkat ||
          (objek.tingkat === terpilih.tingkat && objek.skor > terpilih.skor)
        ) {
          terpilih = objek;
        }
      }

      if (terpilih === null) return null;

      return {
        pesan: this.buat_pesan(terpilih.kelas, terpilih.posisi, terpilih.jarak),
        kelas: terpilih.kelas,
        posisi: terpilih.posisi,
        jarak: terpilih.jarak,
        tingkat: terpilih.tingkat,
      };
    }

    // Mengembalikan [jalur, kandidat]
    analisis_jalur(maskSeg, kelasSeg, namaKelasSeg) {
      if (maskSeg == null || maskSeg.n === 0) {
        return [
          { status: "tidak_jelas", persen_jalan: 0.0 },
          {
            pesan: PESAN_JALUR_TIDAK_TERLIHAT,
            kelas: "jalur_jalan",
            posisi: "tengah",
            jarak: "dekat",
            tingkat: 2,
          },
        ];
      }

      const { h: tinggi, w: lebar, data } = maskSeg;
      const luasMask = tinggi * lebar;

      const lebarZona = ambil(this.config, "zona_tengah", 0.4);
      const x1 = Math.min(Math.max(Math.trunc(((1 - lebarZona) / 2) * lebar), 0), lebar);
      const x2 = Math.min(Math.max(Math.trunc(((1 + lebarZona) / 2) * lebar), 0), lebar);
      const y1 = Math.trunc((tinggi * 2) / 3);

      const barisRoi = Math.max(0, tinggi - y1);
      const kolomRoi = Math.max(0, x2 - x1);
      const ukuranRoi = barisRoi * kolomRoi;

      const persen = (nama) => {
        const pilih = [];
        for (let i = 0; i < kelasSeg.length; i++) {
          const idKelas = String(Math.trunc(Number(kelasSeg[i])));
          if (punya(namaKelasSeg, idKelas) && namaKelasSeg[idKelas] === nama) pilih.push(i);
        }
        if (pilih.length === 0 || ukuranRoi === 0) return 0.0;

        let hitung = 0; // piksel ROI yang dicakup minimal satu mask terpilih (gabungan)
        for (let y = y1; y < tinggi; y++) {
          for (let x = x1; x < x2; x++) {
            const piksel = y * lebar + x;
            for (let k = 0; k < pilih.length; k++) {
              if (data[pilih[k] * luasMask + piksel] > 0.5) {
                hitung++;
                break;
              }
            }
          }
        }
        return hitung / ukuranRoi;
      };

      const persenJalan = persen("jalur_jalan");
      const persenTangga = persen("tangga");
      const persenKendaraan = persen("jalan_kendaraan");

      const minTangga = ambil(this.config, "seg_tangga_min", 0.05);
      const minKendaraan = ambil(this.config, "seg_kendaraan_min", 0.5);
      const ambang = ambil(this.config, "jalur_ambang_terhalang", 0.2);

      let kandidat = null;
      let status;

      if (persenTangga >= minTangga) {
        status = "terhalang";
        kandidat = ["tangga", PESAN_TANGGA_SEG, 3];
      } else if (persenKendaraan >= minKendaraan) {
        status = "tidak_jelas";
        kandidat = ["jalan_kendaraan", "Area kendaraan, hati-hati", 2];
      } else if (persenJalan < ambang) {
        status = "terhalang";
        kandidat = ["jalur_jalan", "Jalur terhalang", 2];
      } else {
        status = "terbuka";
      }

      if (kandidat !== null) {
        const [kelas, pesan, tingkat] = kandidat;
        kandidat = { pesan, kelas, posisi: "tengah", jarak: "dekat", tingkat };
      }

      return [{ status, persen_jalan: bulatPy(persenJalan, 4) }, kandidat];
    }

    stabilkan_seg(kandidat, sesiId = "default") {
      const riwayat = this._riwayat(this.riwayat_seg, sesiId);
      const kunci = kandidat ? kandidat.pesan : null;
      tambahDeque(riwayat, kunci, this.jendela_stabil);

      if (!kandidat) return null;

      if (kunci === PESAN_JALUR_TIDAK_TERLIHAT) {
        const n = this.seg_kosong_minimal;
        const terakhir = riwayat.slice(-n);
        if (terakhir.length === n && terakhir.every((k) => k === kunci)) return kandidat;
        return null;
      }

      let minimal = this.minimal_stabil;
      if (kunci === PESAN_TANGGA_SEG) minimal = this.seg_tangga_stabil_minimal;

      let jumlah = 0;
      for (const k of riwayat) if (k === kunci) jumlah++;
      return jumlah >= minimal ? kandidat : null;
    }

    hitung_iou(kotakA, kotakB) {
      const [ax1, ay1, ax2, ay2] = kotakA;
      const [bx1, by1, bx2, by2] = kotakB;

      const x1 = Math.max(ax1, bx1);
      const y1 = Math.max(ay1, by1);
      const x2 = Math.min(ax2, bx2);
      const y2 = Math.min(ay2, by2);

      const luasIrisan = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
      const luasA = Math.max(0, ax2 - ax1) * Math.max(0, ay2 - ay1);
      const luasB = Math.max(0, bx2 - bx1) * Math.max(0, by2 - by1);
      const luasGabungan = luasA + luasB - luasIrisan;

      if (luasGabungan <= 0) return 0.0;
      return luasIrisan / luasGabungan;
    }

    stabilkan_objek(daftarObjek, sesiId = "default") {
      const riwayat = this._riwayat(this.riwayat_frame, sesiId);

      tambahDeque(
        riwayat,
        daftarObjek.map((objek) => ({ kelas: objek.kelas, kotak: objek.kotak })),
        this.jendela_stabil
      );

      const objekStabil = [];

      for (const objek of daftarObjek) {
        let jumlahFrame = 0;

        for (const frame of riwayat) {
          const ditemukan = frame.some(
            (sebelumnya) =>
              sebelumnya.kelas === objek.kelas &&
              this.hitung_iou(objek.kotak, sebelumnya.kotak) >= 0.3
          );
          if (ditemukan) jumlahFrame++;
        }

        if (jumlahFrame >= this.minimal_stabil) objekStabil.push(objek);
      }

      return objekStabil;
    }

    // Aturan v1.1 A. Hanya peringatan objek asli yang mengisi ulang waktu.
    tahan_dekat(peringatan, sesiId, waktuS) {
      if (this.tahan_dekat_ms <= 0) return peringatan;

      if (peringatan !== null) {
        if (
          peringatan._objek &&
          peringatan.posisi === "tengah" &&
          peringatan.jarak === "dekat"
        ) {
          if (!this.dekat_terakhir.has(sesiId)) this._beriRuang(this.dekat_terakhir);
          this.dekat_terakhir.set(sesiId, [waktuS, { ...peringatan }]);
        }
        return peringatan;
      }

      const simpan = this.dekat_terakhir.get(sesiId);
      if (simpan !== undefined) {
        const selangMs = (waktuS - simpan[0]) * 1000;
        if (0 <= selangMs && selangMs <= this.tahan_dekat_ms) return { ...simpan[1] };
      }

      return null;
    }

    proses(hasilDeteksi, sesiId = "default", waktuS = null) {
      if (waktuS == null) waktuS = waktuMonotonik();

      const hasilObjek = this.analisis_objek(hasilDeteksi.objek);
      let objekStabil = this.stabilkan_objek(hasilObjek, sesiId);

      // Aturan B: tanpa mask seg di frame ini, objek "jauh" tidak boleh jadi peringatan.
      const maskSeg = hasilDeteksi.mask_seg;
      if (this.jauh_butuh_seg && (maskSeg == null || maskSeg.n === 0)) {
        objekStabil = objekStabil.filter((objek) => objek.jarak !== "jauh");
      }

      let peringatan = this.pilih_peringatan(objekStabil);

      const [jalur, kandidatSeg] = this.analisis_jalur(
        maskSeg,
        hasilDeteksi.kelas_seg,
        hasilDeteksi.nama_kelas_seg
      );

      const peringatanSeg = this.stabilkan_seg(kandidatSeg, sesiId);

      if (peringatan !== null) peringatan._objek = true; // penanda internal aturan A

      // SATU peringatan: tingkat tertinggi; seri -> objek kotak
      if (peringatanSeg !== null && (peringatan === null || peringatanSeg.tingkat > peringatan.tingkat)) {
        peringatan = peringatanSeg;
      }

      peringatan = this.tahan_dekat(peringatan, sesiId, waktuS);
      if (peringatan !== null) delete peringatan._objek;

      const objekApi = hasilObjek.map((objek) => ({
        kelas: objek.kelas,
        conf: objek.conf,
        kotak: objek.kotak,
        posisi: objek.posisi,
        jarak: objek.jarak,
      }));

      return {
        versi_kontrak: 1,
        waktu_ms: hasilDeteksi.waktu_ms,
        peringatan,
        objek: objekApi,
        jalur,
      };
    }
  }

  MesinLogika.ValueError = ValueError;
  MesinLogika._bulatPy = bulatPy; // untuk pengujian

  if (typeof module !== "undefined" && module.exports) module.exports = { MesinLogika, ValueError };
  akar.MesinLogika = MesinLogika;
})(typeof globalThis !== "undefined" ? globalThis : this);
