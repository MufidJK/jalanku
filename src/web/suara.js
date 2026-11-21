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
  return daftar.find((v) => v.lang.toLowerCase().startsWith("id")) || null;
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
  if (bisu && "speechSynthesis" in window) window.speechSynthesis.cancel();
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
    synth.speak(u);
  }

  pesanTerakhir = peringatan.pesan;
  waktuTerakhir = sekarang;
  if (peringatan.tingkat === 1) waktuKelasRingan[peringatan.kelas] = sekarang;
}

if ("speechSynthesis" in window) {
  window.speechSynthesis.onvoiceschanged = () => {
    const v = pilihSuaraIndonesia();
    namaSuara = v ? v.name : "bawaan (tanpa id-ID)";
  };
}