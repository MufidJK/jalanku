const pengaturanSuara = {
  jedaUlangMs: 4000,
  jedaKelasRinganMs: 8000, // benda ringan (tingkat 1) berkelas sama tidak diucapkan ulang; 0 = mati
  jedaSampingMs: 10000, // pesan samping (" di kiri"/" di kanan") yang SAMA baru diulang sesudah jeda ini; 0 = mati (v1). Aturan v1.1 B, lihat data/aturan-v1-1/hasil_ablasi.md
  rate: 1,
  volume: 1,
};

let bisu = false;
let pesanTerakhir = "";
let waktuTerakhir = 0;
const waktuKelasRingan = {}; // kelas -> waktu terakhir diucapkan (khusus tingkat 1)
let namaSuara = "belum dibuka";

function pilihSuaraIndonesia() {
  const daftar = window.speechSynthesis.getVoices();
  // Android melaporkan bahasa Indonesia sebagai "in-ID" / "in_ID", jadi terima "id" DAN "in".
  return daftar.find((v) => /^(id|in)([-_]|$)/i.test(v.lang)) || null;
}

// Dipanggil saat tombol Mulai ditekan: "membuka" suara di HP.
function bukaSuara() {
  if (!("speechSynthesis" in window)) {
    namaSuara = "tidak didukung";
    return;
  }
  const kosong = new SpeechSynthesisUtterance(" ");
  kosong.volume = 0;
  window.speechSynthesis.speak(kosong);
  const v = pilihSuaraIndonesia();
  namaSuara = v ? v.name : "bawaan (tanpa id-ID)";
}

function setBisu(nilai) {
  bisu = nilai;
  if (bisu && "speechSynthesis" in window) {
    sintesisDibatalkan();
    window.speechSynthesis.cancel();
  }
  if (window.Zanite) window.Zanite.bisuBerubah(bisu); // Bisu = Zanite tidak mendengar
}

function ucapkan(peringatan) {
  if (!peringatan) return;

  const sekarang = Date.now();
  const sama = peringatan.pesan === pesanTerakhir;
  const samping = / di (kiri|kanan)/.test(peringatan.pesan);
  const jedaSama =
    samping && pengaturanSuara.jedaSampingMs > 0
      ? Math.max(pengaturanSuara.jedaUlangMs, pengaturanSuara.jedaSampingMs)
      : pengaturanSuara.jedaUlangMs;
  if (sama && sekarang - waktuTerakhir < jedaSama) return;

  // Benda ringan (tingkat 1): kelas yang sama tidak diucapkan lagi dalam jeda ini,
  // walau teksnya berbeda (kanan/depan, dekat/sedang). Tingkat 2 dan 3 tidak terpengaruh.
  const jedaRingan = pengaturanSuara.jedaKelasRinganMs;
  if (
    peringatan.tingkat === 1 &&
    jedaRingan > 0 &&
    sekarang - (waktuKelasRingan[peringatan.kelas] ?? -Infinity) < jedaRingan
  ) {
    return;
  }

  // Getar: tingkat 3, tetap jalan walau Bisu (Bisu hanya mematikan suara).
  if (peringatan.tingkat === 3 && navigator.vibrate) {
    navigator.vibrate([200, 100, 200]);
  }

  // Fokus Zanite (sejak kata bangun sampai alurnya selesai): tingkat 1 dan 2 tidak diucapkan, dan tidak dicatat
  // sebagai sudah diucapkan, jadi berulang seperti biasa sesudah fokus selesai. Layar tetap diperbarui oleh app.js.
  if (peringatan.tingkat !== 3 && window.Zanite && window.Zanite.fokus()) {
    window.Zanite.peringatanDitahan(peringatan.pesan);
    return;
  }

  if ("speechSynthesis" in window && !bisu) {
    const synth = window.speechSynthesis;
    if (peringatan.tingkat === 3) {
      sintesisDibatalkan();
      synth.cancel(); // memotong suara yang sedang bicara
    } else if (synth.speaking) {
      return; // tingkat rendah tidak memotong dan tidak menumpuk antrean
    }

    const u = new SpeechSynthesisUtterance(peringatan.pesan);
    u.lang = "id-ID";
    u.rate = pengaturanSuara.rate;
    u.volume = pengaturanSuara.volume;
    const v = pilihSuaraIndonesia();
    if (v) u.voice = v;
    pantauBicara(u, peringatan.pesan, undefined, peringatan.tingkat);
    synth.speak(u);
  }

  pesanTerakhir = peringatan.pesan;
  waktuTerakhir = sekarang;
  if (peringatan.tingkat === 1) waktuKelasRingan[peringatan.kelas] = sekarang;
}

// Pesan aplikasi (bukan peringatan): selalu memotong suara yang sedang bicara
// dan tidak menyentuh catatan jeda ulang peringatan.
function ucapkanSistem(teks) {
  if (!("speechSynthesis" in window) || bisu) return;
  const synth = window.speechSynthesis;
  sintesisDibatalkan();
  synth.cancel();
  const u = new SpeechSynthesisUtterance(teks);
  u.lang = "id-ID";
  u.rate = pengaturanSuara.rate;
  u.volume = pengaturanSuara.volume;
  const v = pilihSuaraIndonesia();
  if (v) u.voice = v;
  pantauBicara(u, teks);
  synth.speak(u);
}

// Zanite: beri tahu kapan app sedang bicara. Mic Zanite tidak pernah dimatikan; transkrip yang datang
// selama app bicara (dan sebentar sesudahnya) dibuang oleh zanite.js.
function pantauBicara(u, teks, saatPutus, tingkat) {
  if (window.Zanite) window.Zanite.bicaraPantau(u, teks, saatPutus, tingkat);
}

// Tepat sebelum speechSynthesis.cancel(): ucapan yang dibatalkan belum tentu mengirim end/error, jadi Zanite
// diberi tahu supaya tidak menunggu pengaman 15-20 detik.
function sintesisDibatalkan() {
  if (window.Zanite) window.Zanite.sintesisDibatalkan();
}

// Jawaban/balasan Zanite. TIDAK memotong suara lain: peringatan tingkat 3 yang sedang bicara selesai dulu, ucapan
// masuk antrean di belakangnya. Peringatan tingkat 3 berikutnya tetap memotongnya (synth.cancel di ucapkan).
// label: "balas" | "jawab" (untuk log siklus hidup). Janji selesai (dengan alasannya) bila ucapan habis ("end"),
// gagal ("error"), dibatalkan ("cancel"), dipaksa selesai oleh pelacak ("paksa"), lewat batas pengaman ("pengaman"),
// atau tidak pernah mulai walau sudah diulang sekali ("gagal").
//
// Chrome HP kadang membuang speak() yang datang tepat sesudah cancel() tanpa event apa pun. Karena itu:
//  - speak() diberi jarak JEDA_SESUDAH_CANCEL_MS dari cancel() terakhir;
//  - pengawas: bila tidak ada event "start" dan sintesis tidak sedang bicara selama BATAS_START_MS sesudah speak(),
//    ucapan dibatalkan dan diulang SEKALI; bila tetap tidak mulai, menyerah ("gagal") dan alur ditutup oleh pemanggil.
const JEDA_SESUDAH_CANCEL_MS = 150;
const BATAS_START_MS = 1500;
const PERIODE_PENGAWAS_MS = 250;

function ucapkanZanite(teks, label) {
  return new Promise((selesai) => {
    if (!("speechSynthesis" in window) || bisu || !teks) return selesai("lewat");
    const nama = label || "jawab";
    const synth = window.speechSynthesis;
    const Z = window.Zanite;
    const log = (t) => { if (Z && Z.catat) Z.catat(nama + ": " + t); };
    const kini = () => performance.now();
    const t0 = kini();
    const ms = () => Math.round(kini() - t0) + " ms";
    let beres = false, percobaan = 0, token = 0, sudahMulai = false, tSpeak = 0, tSibuk = 0, pengawas = null;
    let uKini = null;                        // ucapan yang sedang dicoba (untuk pendar tepi layar)
    const lepasPendar = () => { if (uKini && Z && Z.pendarSelesai) Z.pendarSelesai(uKini); };
    const akhir = (alasan) => {
      if (beres) return;
      beres = true;
      lepasPendar();
      clearTimeout(pengawas);
      clearTimeout(pengaman);
      log(alasan + " " + ms());
      selesai(alasan);
    };
    const pengaman = setTimeout(() => akhir("pengaman"), 20000 + teks.length * 120);

    function awasi(saya) {
      const periksa = () => {
        if (beres || saya !== token || sudahMulai) return;
        const t = kini();
        if (synth.speaking) tSibuk = t;                    // ada ucapan lain yang bicara: giliran kita belum tiba
        if (t - Math.max(tSpeak, tSibuk) >= BATAS_START_MS) { tanpaStart(saya); return; }
        pengawas = setTimeout(periksa, PERIODE_PENGAWAS_MS);
      };
      pengawas = setTimeout(periksa, PERIODE_PENGAWAS_MS);
    }

    // saya: percobaan yang dinilai gagal; panggilan dari percobaan lama (atau sesudah selesai) diabaikan.
    function tanpaStart(saya) {
      if (beres || saya !== token) return;
      token += 1;                                          // event dari ucapan lama tidak dihiraukan lagi
      sintesisDibatalkan();
      synth.cancel();
      if (percobaan >= 2) { log("gagal " + ms()); akhir("gagal"); return; }
      log("ulang (tanpa start) " + ms());
      coba();
    }

    function coba() {
      percobaan += 1;
      const saya = ++token;
      sudahMulai = false;
      const u = new SpeechSynthesisUtterance(teks);
      u.lang = "id-ID";
      u.rate = pengaturanSuara.rate;
      u.volume = pengaturanSuara.volume;
      const v = pilihSuaraIndonesia();
      if (v) u.voice = v;
      lepasPendar();                         // ucapan percobaan sebelumnya (bila ada) tidak dihitung lagi
      uKini = u;
      if (Z && Z.pendarPantau) Z.pendarPantau(u);
      u.addEventListener("start", () => { if (saya === token) { sudahMulai = true; log("start " + ms()); } });
      u.addEventListener("end", () => { if (saya === token) akhir("end"); });
      u.addEventListener("error", () => { if (saya === token) akhir("error"); });
      // saatPutus: dipotong cancel / dipaksa selesai oleh pelacak -> janji selesai saat itu juga, bukan setelah pengaman
      // Dipaksa selesai oleh pelacak padahal event "start" tidak pernah datang = ucapan dibuang, BUKAN selesai:
      // diperlakukan sebagai tanpa-start (diulang sekali), bukan membuka jendela perintah dalam diam.
      pantauBicara(u, teks, (alasan) => {
        if (saya !== token) return;
        if (alasan === "paksa" && !sudahMulai) setTimeout(() => tanpaStart(saya), 0);
        else akhir(alasan);
      });
      const bicara = () => {
        if (beres || saya !== token) return;
        tSpeak = tSibuk = kini();
        log("speak" + (percobaan > 1 ? " (ulang)" : "") + " " + ms());
        synth.speak(u);
        awasi(saya);
      };
      const sisa = JEDA_SESUDAH_CANCEL_MS - (Z && Z.cancelTerakhir ? kini() - Z.cancelTerakhir() : Infinity);
      if (sisa > 0) setTimeout(bicara, sisa); else bicara();
    }

    coba();
  });
}

if ("speechSynthesis" in window) {
  window.speechSynthesis.onvoiceschanged = () => {
    const v = pilihSuaraIndonesia();
    namaSuara = v ? v.name : "bawaan (tanpa id-ID)";
  };
}