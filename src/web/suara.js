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
    pantauBicara(u, peringatan.pesan);
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
function pantauBicara(u, teks, saatPutus) {
  if (window.Zanite) window.Zanite.bicaraPantau(u, teks, saatPutus);
}

// Tepat sebelum speechSynthesis.cancel(): ucapan yang dibatalkan belum tentu mengirim end/error, jadi Zanite
// diberi tahu supaya tidak menunggu pengaman 15-20 detik.
function sintesisDibatalkan() {
  if (window.Zanite) window.Zanite.sintesisDibatalkan();
}

// Jawaban Zanite. TIDAK memotong suara lain: peringatan tingkat 3 yang sedang bicara selesai dulu, jawaban
// masuk antrean di belakangnya. Peringatan tingkat 3 berikutnya tetap memotongnya (synth.cancel di ucapkan).
// Janji selesai bila ucapan habis, gagal, dibatalkan, atau lewat batas pengaman (onend kadang tidak datang).
function ucapkanZanite(teks) {
  return new Promise((selesai) => {
    if (!("speechSynthesis" in window) || bisu || !teks) return selesai();
    const u = new SpeechSynthesisUtterance(teks);
    u.lang = "id-ID";
    u.rate = pengaturanSuara.rate;
    u.volume = pengaturanSuara.volume;
    const v = pilihSuaraIndonesia();
    if (v) u.voice = v;
    let beres = false;
    const akhir = () => {
      if (beres) return;
      beres = true;
      selesai();
    };
    u.addEventListener("end", akhir);
    u.addEventListener("error", akhir);
    setTimeout(akhir, 20000 + teks.length * 120);
    // saatPutus: dipotong cancel / dipaksa selesai oleh pelacak -> janji selesai saat itu juga, bukan setelah pengaman
    pantauBicara(u, teks, akhir);
    window.speechSynthesis.speak(u);
  });
}

if ("speechSynthesis" in window) {
  window.speechSynthesis.onvoiceschanged = () => {
    const v = pilihSuaraIndonesia();
    namaSuara = v ? v.name : "bawaan (tanpa id-ID)";
  };
}