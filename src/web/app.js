const kamera = document.getElementById("kamera");
const overlay = document.getElementById("overlay");
const status = document.getElementById("status");
const statusIkon = document.getElementById("status-ikon");
const statusTeks = document.getElementById("status-teks");
const statusDetail = document.getElementById("status-detail");
const zonaEl = document.getElementById("zona");
const layarAwal = document.getElementById("layar-awal");
const info = document.getElementById("info");
const kanvas = document.getElementById("kanvas");
const tombolMulai = document.getElementById("tombol-mulai");
const tombolBisu = document.getElementById("tombol-bisu");
const tombolAtur = document.getElementById("tombol-atur");
const panel = document.getElementById("panel");
const tombolModeSuara = document.getElementById("tombol-mode-suara");
const layarSuara = document.getElementById("layar-suara");
const teksTahan = document.getElementById("teks-tahan");
const utama = document.querySelector("main");
const ctx = overlay.getContext("2d");

const LEBAR_KIRIM = 640;
const KUALITAS_JPEG = 0.7;
const MODE_MOCK = new URLSearchParams(location.search).get("mock") === "1";
const WARNA = { 0: "#14773A", 1: "#1565C0", 2: "#F5C400", 3: "#C62828" };
// Ikon SVG konstan (bukan data pengguna), warna ikut teks lewat currentColor.
const SVG_IKON =
  '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">';
const IKON = {
  0: SVG_IKON + '<path d="M4.5 12.5l5 5L19.5 7" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  1: SVG_IKON + '<circle cx="12" cy="12" r="9.5" stroke="currentColor" stroke-width="2.5"/><path d="M12 11v6" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/><circle cx="12" cy="7.5" r="1.5" fill="currentColor"/></svg>',
  2: SVG_IKON + '<path d="M12 3.5L21.5 20H2.5L12 3.5Z" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round"/><path d="M12 10v4.5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/><circle cx="12" cy="17.2" r="1.4" fill="currentColor"/></svg>',
  3: SVG_IKON + '<circle cx="12" cy="12" r="9.5" stroke="currentColor" stroke-width="2.5"/><path d="M7.5 12h9" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>',
};
const UKURAN_JUDUL = 26;
const UKURAN_JUDUL_MIN = 16;

let jedaKirimMs = 200; // jeda MINIMUM antar pengiriman
let stream = null;
let timer = null; // setTimeout berikutnya (maksimal satu yang menunggu)
let jalan = false; // loop kirim sedang aktif
let sibuk = false;
let jumlah = 0;

// State jalan (bukan lagi "stream ada atau tidak"):
let aktif = false; // Mulai/Mode suara ditekan dan belum Berhenti
let modeSuara = false; // lapisan hitam tampil
let dijeda = false; // dijeda otomatis karena halaman tersembunyi
let sedangMulai = false; // getUserMedia dari Mulai/Mode suara masih menunggu
// Naik setiap Berhenti atau halaman tersembunyi. Kamera atau balasan yang
// datang dengan generasi lama sudah usang dan dibuang.
let generasi = 0;
let generasiSiklus = 0; // generasi saat siklus kirim yang sedang jalan dimulai

// Banner "tanpa peringatan": ganti hanya setelah 2 balasan berturut-turut.
const BALASAN_BERTURUT = 2;
let bannerTanpaPeringatan = null; // "terbuka" | "tidak_jelas" | "terhalang" | null
let hitungTerbuka = 0;
let hitungTidakTerbuka = 0;

// --- Status dan zona ---
function setStatus(teks, tingkat, detail) {
  statusTeks.textContent = teks;
  statusIkon.innerHTML = tingkat === null ? "" : IKON[tingkat];
  status.className = tingkat === null ? "" : "t" + tingkat;
  status.classList.toggle("dua-baris", teks.startsWith("Kamera gagal:"));
  statusDetail.textContent = detail || "";
  statusDetail.hidden = !detail;
  pasJudul();
  requestAnimationFrame(pasJudul); // ukur ulang sesudah tata letak selesai
}

// Judul status satu baris: mulai 26px, kecilkan 1px sampai muat (min 16px).
function pasJudul() {
  statusTeks.style.fontSize = "";
  if (status.classList.contains("dua-baris")) return;
  let ukuran = UKURAN_JUDUL;
  while (judulMeluap() && ukuran > UKURAN_JUDUL_MIN) {
    ukuran -= 1;
    statusTeks.style.fontSize = ukuran + "px";
  }
}

// scrollWidth/clientWidth dibulatkan ke px bulat, jadi luapan di bawah 1px
// lolos (dan elipsis tetap muncul). Bandingkan juga lebar pecahan teks.
function judulMeluap() {
  if (statusTeks.scrollWidth > statusTeks.clientWidth) return true;
  const rentang = document.createRange();
  rentang.selectNodeContents(statusTeks);
  const lebarTeks = rentang.getBoundingClientRect().width;
  return lebarTeks > statusTeks.getBoundingClientRect().width + 0.01;
}

// Lebar kartu berubah (rotasi, ukuran jendela, DevTools): ukur ulang judul.
let lebarStatus = 0;
new ResizeObserver((entri) => {
  const lebar = entri[0].contentRect.width;
  if (lebar === lebarStatus) return; // abaikan perubahan tinggi saja
  lebarStatus = lebar;
  pasJudul();
}).observe(status);

function setZona(posisi, tingkat) {
  for (const z of zonaEl.children) {
    z.className = posisi && z.dataset.z === posisi ? "aktif t" + tingkat : "";
  }
}

// --- Overlay kotak ---
function sesuaikanOverlay() {
  overlay.width = window.innerWidth;
  overlay.height = window.innerHeight;
}

function garisZona() {
  // Sebelum kamera jalan, ukuran video belum diketahui: jangan gambar garis.
  if (!kamera.videoWidth || !kamera.videoHeight) return;
  // Garis hanya di area kamera yang bersih: 16px di bawah blok atas
  // sampai 12px di atas tombol kecil (overlay dalam px CSS).
  const yAtas = document.getElementById("atas").getBoundingClientRect().bottom + 16;
  const yBawah =
    document.getElementById("baris-kecil").getBoundingClientRect().top - 12;
  if (yBawah <= yAtas) return;
  // Zona server: kiri 30% / tengah 40% / kanan 30% dari lebar GAMBAR.
  const x1 = petaKotak([0.3, 0, 0.3, 1])[0];
  const x2 = petaKotak([0.7, 0, 0.7, 1])[0];
  ctx.save();
  ctx.strokeStyle = "rgba(255,255,255,0.4)";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([6, 8]);
  ctx.beginPath();
  ctx.moveTo(x1, yAtas);
  ctx.lineTo(x1, yBawah);
  ctx.moveTo(x2, yAtas);
  ctx.lineTo(x2, yBawah);
  ctx.stroke();
  ctx.restore();
}

function bersihkanOverlay() {
  ctx.clearRect(0, 0, overlay.width, overlay.height);
}

function jalurBulat(x, y, w, h, r) {
  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(x, y, w, h, r);
  } else {
    ctx.rect(x, y, w, h);
  }
}

// Kotak dari server skala 0-1 terhadap gambar penuh. Video ditampilkan
// dengan object-fit: cover, jadi perhitungannya harus ikut terpotong.
function petaKotak(k) {
  const vw = kamera.videoWidth;
  const vh = kamera.videoHeight;
  const W = overlay.width;
  const H = overlay.height;
  const skala = Math.max(W / vw, H / vh);
  const offX = (W - vw * skala) / 2;
  const offY = (H - vh * skala) / 2;
  return [
    offX + k[0] * vw * skala,
    offY + k[1] * vh * skala,
    offX + k[2] * vw * skala,
    offY + k[3] * vh * skala,
  ];
}

function gambarOverlay(balasan) {
  bersihkanOverlay();
  if (modeSuara) return; // tertutup lapisan hitam: tidak perlu menggambar
  garisZona();
  if (!balasan) return;
  const p = balasan.peringatan;
  for (const o of balasan.objek) {
    const [x1, y1, x2, y2] = petaKotak(o.kotak);
    const utama = p && p.kelas === o.kelas && p.posisi === o.posisi;
    const warna = utama ? WARNA[p.tingkat] : "#ffffff";

    // isi transparan + garis tepi bersudut bulat
    jalurBulat(x1, y1, x2 - x1, y2 - y1, 12);
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = warna;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.lineWidth = utama ? 6 : 3;
    ctx.strokeStyle = warna;
    ctx.stroke();

    // label berbentuk pil
    const teks = o.kelas + " " + Math.round(o.conf * 100) + "%";
    ctx.font = "700 18px 'Plus Jakarta Sans', sans-serif";
    const lebar = ctx.measureText(teks).width + 16;
    const yLabel = Math.max(y1 - 30, 0);
    jalurBulat(x1, yLabel, lebar, 26, 8);
    ctx.fillStyle = warna;
    ctx.fill();
    const teksGelap = !utama || p.tingkat === 2;
    ctx.fillStyle = teksGelap ? "#000" : "#fff";
    ctx.fillText(teks, x1 + 8, yLabel + 19);
  }
}

// --- Ambil frame ---
function ambilJpeg() {
  return new Promise((resolve) => {
    const w = kamera.videoWidth;
    const h = kamera.videoHeight;
    if (!w || !h) return resolve(null);
    kanvas.width = LEBAR_KIRIM;
    kanvas.height = Math.round((h * LEBAR_KIRIM) / w);
    kanvas
      .getContext("2d")
      .drawImage(kamera, 0, 0, kanvas.width, kanvas.height);
    kanvas.toBlob(resolve, "image/jpeg", KUALITAS_JPEG);
  });
}

const TEKS_JALUR = {
  terhalang: {
    teks: "Jalur terhalang",
    detail: "Jalur tertutup, tanpa peringatan suara",
  },
  tidak_jelas: {
    teks: "Jalur tidak jelas",
    detail: "Kamera belum melihat jalan",
  },
};

function resetBanner() {
  bannerTanpaPeringatan = null;
  hitungTerbuka = 0;
  hitungTidakTerbuka = 0;
}

function tampilkanTanpaPeringatan(statusJalur) {
  bannerTanpaPeringatan = statusJalur;
  if (statusJalur === "terbuka") {
    setStatus("Aman.", 0);
  } else {
    // Jalur tidak terbuka tapi tanpa peringatan: jangan bilang "Aman.",
    // tapi pakai gaya info (biru) supaya tidak mirip peringatan sungguhan.
    const t = TEKS_JALUR[statusJalur] || TEKS_JALUR.tidak_jelas;
    setStatus(t.teks, 1, t.detail);
  }
}

function tampilkanBalasan(balasan, latensiMs) {
  const p = balasan.peringatan;
  const j = balasan.jalur || { status: "tidak_jelas", persen_jalan: 0 };
  const statusJalur = j.status || "tidak_jelas";

  if (p) {
    // Peringatan tidak pernah ditunda: tampil langsung, hitungan diulang.
    resetBanner();
    const detail = [
      p.posisi ? "Posisi: " + p.posisi : "",
      p.jarak ? "Jarak: " + p.jarak : "",
    ]
      .filter(Boolean)
      .join(" · ");
    setStatus(p.pesan, p.tingkat, detail);
  } else if (statusJalur === "terbuka") {
    hitungTerbuka += 1;
    hitungTidakTerbuka = 0;
    if (bannerTanpaPeringatan === null || hitungTerbuka >= BALASAN_BERTURUT) {
      tampilkanTanpaPeringatan("terbuka");
    }
  } else {
    hitungTidakTerbuka += 1;
    hitungTerbuka = 0;
    if (
      bannerTanpaPeringatan === null ||
      hitungTidakTerbuka >= BALASAN_BERTURUT
    ) {
      tampilkanTanpaPeringatan(statusJalur);
    }
  }
  setZona(p ? p.posisi : null, p ? p.tingkat : 0);
  gambarOverlay(balasan);
  ucapkan(p); // p null: tidak ada suara

  info.className =
    latensiMs < 100 ? "ok" : latensiMs < 300 ? "sedang" : "lambat";
  const persen = Math.round((j.persen_jalan || 0) * 100);
  const spanJalur = document.createElement("span");
  spanJalur.className = "jalur " + statusJalur;
  spanJalur.textContent =
    "jalur: " + statusJalur.replace("_", " ") + " " + persen + "%";
  info.textContent = "";
  info.append(
    (MODE_MOCK ? "MOCK | " : "") +
      "Frame " + jumlah + " | " + Math.round(latensiMs) + " ms | objek: " +
      balasan.objek.length + " | ",
    spanJalur,
    " | suara: " + namaSuara
  );
}

// Loop menjadwalkan dirinya sendiri: frame berikutnya dikirim begitu balasan
// tiba, tapi tidak lebih cepat dari jedaKirimMs sejak siklus dimulai.
function jadwalkan(tungguMs) {
  clearTimeout(timer); // pastikan tidak pernah ada dua jadwal sekaligus
  timer = jalan ? setTimeout(siklus, Math.max(0, tungguMs)) : null;
}

async function siklus() {
  timer = null;
  if (sibuk) return; // hanya satu proses dalam satu waktu
  sibuk = true;
  const tMulai = performance.now();
  const gen = generasi;
  generasiSiklus = gen;
  let berhasil = false;
  try {
    const jpeg = await ambilJpeg();
    if (!jpeg || !jalan) return;
    jumlah += 1;
    const t0 = performance.now();
    let balasan;
    if (MODE_MOCK) {
      balasan = await ambilMock();
      if (gen !== generasi) return; // usang (dari sebelum jeda/Berhenti): buang
    } else {
      balasan = await kirimKeServer(jpeg);
      if (gen !== generasi) return; // usang (dari sebelum jeda/Berhenti): buang
      if (!balasan) {
        resetBanner(); // banner "Server bermasalah" tampil; mulai bersih saat pulih
        return;
      }
    }
    if (!jalan) return; // dihentikan saat menunggu balasan
    tampilkanBalasan(balasan, performance.now() - t0);
    berhasil = true;
  } finally {
    sibuk = false;
    // Berhasil: kurangi jeda dengan lamanya siklus. Gagal: tunggu jeda penuh.
    if (jalan) jadwalkan(berhasil ? jedaKirimMs - (performance.now() - tMulai) : jedaKirimMs);
  }
}

function jalankanLoop() {
  jalan = true;
  resetBanner();
  jadwalkan(0);
}

function hentikanLoop() {
  jalan = false;
  clearTimeout(timer);
  timer = null;
}

// server.js memanggil tandaiServerBermasalah() dari dalam kirimKeServer().
// Permintaan usang (dikirim sebelum jeda/Berhenti) tidak boleh menampilkan
// atau mengucapkan "Server bermasalah". server.js tidak diubah: bungkus di sini.
// Aman karena hanya ada satu siklus kirim dalam satu waktu (sibuk).
const tandaiServerBermasalahAsli = tandaiServerBermasalah;
tandaiServerBermasalah = function (alasan) {
  if (generasiSiklus !== generasi) return;
  tandaiServerBermasalahAsli(alasan);
};

function lepasStream() {
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }
  kamera.srcObject = null;
}

// Ambil kamera dan putar videonya. Dipakai Mulai, Mode suara, lanjut otomatis.
// true: kamera jalan. false: permintaan usang (Berhenti atau halaman
// tersembunyi lagi saat menunggu), track baru sudah dihentikan.
// Gagal sungguhan: melempar error.
async function ambilKamera() {
  const gen = generasi;
  let s;
  try {
    s = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
  } catch (err) {
    if (gen !== generasi) return false;
    throw err;
  }
  if (gen !== generasi) {
    s.getTracks().forEach((t) => t.stop());
    return false;
  }
  stream = s;
  kamera.srcObject = s;
  try {
    await kamera.play();
  } catch (err) {
    if (gen !== generasi) return false; // jeda/Berhenti sudah melepas kamera
    lepasStream();
    throw err;
  }
  if (gen !== generasi) return false;
  // Riwayat frame server per X-Sesi tidak kedaluwarsa: setiap kamera mulai
  // (Mulai, Mode suara, lanjut otomatis) memakai sesi baru.
  sesiBaru();
  return true;
}

// Hasil: "jalan", "gagal" (status "Kamera gagal: ..." sudah tampil), "usang".
async function mulaiKamera() {
  if (sedangMulai) return "usang"; // ketukan ganda saat masih menunggu
  sedangMulai = true;
  try {
    if (!(await ambilKamera())) return "usang";
    aktif = true;
    layarAwal.hidden = true;
    perbaruiTombolModeSuara();
    setStatus("Kamera aktif.", null);
    tombolMulai.textContent = "Berhenti";
    tombolMulai.classList.add("jalan");
    bukaSuara();
    sesuaikanOverlay();
    gambarOverlay(null);
    jumlah = 0;
    jalankanLoop();
    mintaKunciLayar();
    zaniteHidup("mulaiKamera"); // dari gestur Mulai / Mode suara: izin mikrofon diminta di sini
    return "jalan";
  } catch (err) {
    setStatus("Kamera gagal: " + err.name, null);
    return "gagal";
  } finally {
    sedangMulai = false;
  }
}

function berhentiKamera() {
  generasi += 1; // kamera/balasan yang masih menunggu jadi usang
  aktif = false;
  dijeda = false;
  if (modeSuara) keluarModeSuara(false);
  perbaruiTombolModeSuara();
  hentikanLoop();
  zaniteMati("berhentiKamera (Berhenti)");
  lepasKunciLayar();
  lepasStream();
  setStatus("Tekan Mulai.", null);
  setZona(null, 0);
  info.textContent = "";
  info.className = "";
  tombolMulai.textContent = "Mulai";
  tombolMulai.classList.remove("jalan");
  layarAwal.hidden = false;
  bersihkanOverlay();
}

// --- Zanite (zanite.js): hanya jalan selama kamera jalan ---
// dari: siapa yang memanggil (dicatat di log Zanite untuk uji di HP)
function zaniteHidup(dari) {
  if (window.Zanite) window.Zanite.mulai(dari);
}

function zaniteMati(dari) {
  if (window.Zanite) window.Zanite.berhenti(dari);
}

// --- Wake Lock: layar tidak mati selama jalan ---
let kunciLayar = null;

async function mintaKunciLayar() {
  if (kunciLayar || !("wakeLock" in navigator)) return;
  try {
    kunciLayar = await navigator.wakeLock.request("screen");
    kunciLayar.addEventListener("release", () => {
      kunciLayar = null;
    });
  } catch (err) {
    // Tidak didukung atau ditolak: abaikan, halaman tetap jalan.
  }
}

async function lepasKunciLayar() {
  if (!kunciLayar) return;
  try {
    await kunciLayar.release();
  } catch (err) {
    // abaikan
  }
  kunciLayar = null;
}

// --- Mode suara: lapisan hitam, peringatan tetap lewat suara dan getar ---
const TEKS_KELUAR = "Tekan lama 2 detik untuk keluar";
const TAHAN_MS = 2000;
const GESER_MAKS_PX = 24;
let tahan = null; // { id, x, y, timer } untuk pointer pertama saja

function perbaruiTombolModeSuara() {
  tombolModeSuara.hidden = aktif || !panel.hidden;
}

function masukModeSuara() {
  modeSuara = true;
  teksTahan.textContent = TEKS_KELUAR;
  layarSuara.hidden = false;
  utama.inert = true; // TalkBack tidak ikut membaca status di bawah lapisan
  bersihkanOverlay();
  layarSuara.focus();
  ucapkanSistem("Mode suara aktif. Tekan lama dua detik untuk keluar.");
}

// suara=false dipakai Berhenti dan kamera gagal: tanpa getar dan ucapan.
function keluarModeSuara(suara) {
  batalTahan();
  modeSuara = false;
  layarSuara.hidden = true;
  utama.inert = false;
  if (!suara) return;
  gambarOverlay(null);
  tombolMulai.focus();
  ucapkanSistem("Mode suara mati.");
}

function batalTahan() {
  if (!tahan) return;
  clearTimeout(tahan.timer);
  tahan = null;
  teksTahan.textContent = TEKS_KELUAR;
}

function selesaiTahan() {
  tahan = null;
  navigator.vibrate?.(60);
  keluarModeSuara(true);
}

layarSuara.addEventListener("pointerdown", (e) => {
  if (tahan) return;
  tahan = {
    id: e.pointerId,
    x: e.clientX,
    y: e.clientY,
    timer: setTimeout(selesaiTahan, TAHAN_MS),
  };
  teksTahan.textContent = "Tahan...";
});

layarSuara.addEventListener("pointermove", (e) => {
  if (!tahan || e.pointerId !== tahan.id) return;
  if (Math.hypot(e.clientX - tahan.x, e.clientY - tahan.y) > GESER_MAKS_PX) {
    batalTahan();
  }
});

for (const jenis of ["pointerup", "pointercancel", "pointerleave"]) {
  layarSuara.addEventListener(jenis, (e) => {
    if (tahan && e.pointerId === tahan.id) batalTahan();
  });
}

layarSuara.addEventListener("contextmenu", (e) => e.preventDefault());

// --- Lanjut otomatis: kamera dilepas saat tersembunyi, diambil lagi saat muncul ---
function jedaOtomatis() {
  generasi += 1; // juga membatalkan getUserMedia yang masih menunggu
  if (!aktif) return;
  dijeda = true;
  batalTahan();
  hentikanLoop();
  zaniteMati("jedaOtomatis");
  lepasStream();
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  // aktif dan modeSuara tetap: pengguna kembali ke mode yang sama.
}

async function lanjutOtomatis() {
  dijeda = false;
  let jalanLagi;
  try {
    jalanLagi = await ambilKamera();
  } catch (err) {
    ucapkanSistem("Kamera gagal.");
    berhentiKamera();
    setStatus("Kamera gagal: " + err.name, null);
    return;
  }
  if (!jalanLagi) return; // tersembunyi lagi atau Berhenti saat menunggu
  sesuaikanOverlay();
  gambarOverlay(null);
  jalankanLoop(); // juga mereset banner
  mintaKunciLayar();
  zaniteHidup("lanjutOtomatis");
  ucapkanSistem("Lanjut."); // baru sesudah kamera benar-benar diputar
}

// Browser melepas kunci layar dan memutus kamera saat tab tersembunyi.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    jedaOtomatis();
    return;
  }
  if (!aktif) return;
  if (dijeda) {
    lanjutOtomatis();
  } else {
    mintaKunciLayar();
  }
});

window.addEventListener("resize", () => {
  sesuaikanOverlay();
  if (!stream) bersihkanOverlay();
});

// Lebar judul berubah begitu font lokal selesai dimuat: ukur ulang.
if (document.fonts) {
  document.fonts.ready.then(pasJudul);
  document.fonts.addEventListener("loadingdone", pasJudul);
}

tombolMulai.addEventListener("click", () => {
  if (aktif) {
    berhentiKamera();
  } else {
    mulaiKamera();
  }
});

tombolModeSuara.addEventListener("click", async () => {
  if (aktif || sedangMulai) return;
  // Mode suara tidak pernah mulai dalam keadaan bisu.
  setBisu(false);
  perbaruiTombolBisu();
  const hasil = await mulaiKamera();
  if (hasil === "jalan") {
    masukModeSuara();
  } else if (hasil === "gagal") {
    bukaSuara();
    ucapkanSistem("Kamera gagal.");
  }
});

// --- Bisu ---
function perbaruiTombolBisu() {
  tombolBisu.textContent = bisu ? "Suara nyala" : "Bisu";
  tombolBisu.classList.toggle("aktif", bisu);
  tombolBisu.setAttribute("aria-pressed", String(bisu));
}

tombolBisu.addEventListener("click", () => {
  setBisu(!bisu);
  perbaruiTombolBisu();
});

// --- Pengaturan ---
tombolAtur.addEventListener("click", () => {
  panel.hidden = !panel.hidden;
  tombolAtur.setAttribute("aria-expanded", String(!panel.hidden));
  perbaruiTombolModeSuara(); // panel menutupi posisi tombol Mode suara
});

document.getElementById("atur-kirim").addEventListener("input", (e) => {
  jedaKirimMs = Number(e.target.value);
  document.getElementById("nilai-kirim").textContent = jedaKirimMs;
  // Tidak perlu menyentuh loop: jeda baru dipakai pada penjadwalan berikutnya.
});

document.getElementById("atur-ulang").addEventListener("input", (e) => {
  pengaturanSuara.jedaUlangMs = Number(e.target.value) * 1000;
  document.getElementById("nilai-ulang").textContent = e.target.value;
});

document.getElementById("atur-ringan").addEventListener("input", (e) => {
  pengaturanSuara.jedaKelasRinganMs = Number(e.target.value) * 1000;
  document.getElementById("nilai-ringan").textContent = e.target.value;
});

document.getElementById("atur-rate").addEventListener("input", (e) => {
  pengaturanSuara.rate = Number(e.target.value);
  document.getElementById("nilai-rate").textContent =
    pengaturanSuara.rate.toFixed(1);
});

document.getElementById("atur-volume").addEventListener("input", (e) => {
  pengaturanSuara.volume = Number(e.target.value) / 100;
  document.getElementById("nilai-volume").textContent = e.target.value;
});

sesuaikanOverlay();