const pengaturanSuara = {
  jedaUlangMs: 4000,
  rate: 1,
  volume: 1,
};

let bisu = false;
let pesanTerakhir = "";
let waktuTerakhir = 0;
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
  if (!peringatan || bisu) return;
  if (!("speechSynthesis" in window)) return;

  const sekarang = Date.now();
  const sama = peringatan.pesan === pesanTerakhir;
  if (sama && sekarang - waktuTerakhir < pengaturanSuara.jedaUlangMs) return;

  const synth = window.speechSynthesis;
  if (peringatan.tingkat === 3) {
    synth.cancel(); // memotong suara yang sedang bicara
    if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
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

  pesanTerakhir = peringatan.pesan;
  waktuTerakhir = sekarang;
}