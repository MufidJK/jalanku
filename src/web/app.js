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
const ctx = overlay.getContext("2d");

const LEBAR_KIRIM = 640;
const KUALITAS_JPEG = 0.7;
const MODE_MOCK = new URLSearchParams(location.search).get("mock") === "1";
const WARNA = { 0: "#1b7f3b", 1: "#1565c0", 2: "#f9a825", 3: "#c62828" };
const IKON = { 0: "✔", 1: "ℹ", 2: "⚠", 3: "⛔" };

let jedaKirimMs = 200; // jeda MINIMUM antar pengiriman
let stream = null;
let timer = null; // setTimeout berikutnya (maksimal satu yang menunggu)
let jalan = false; // loop kirim sedang aktif
let sibuk = false;
let jumlah = 0;

// Banner "tanpa peringatan": ganti hanya setelah 2 balasan berturut-turut.
const BALASAN_BERTURUT = 2;
let bannerTanpaPeringatan = null; // "terbuka" | "tidak_jelas" | "terhalang" | null
let hitungTerbuka = 0;
let hitungTidakTerbuka = 0;

// --- Status dan zona ---
function setStatus(teks, tingkat, detail) {
  statusTeks.textContent = teks;
  statusIkon.textContent = tingkat === null ? "" : IKON[tingkat];
  status.className = tingkat === null ? "" : "t" + tingkat;
  statusDetail.textContent = detail || "";
  statusDetail.hidden = !detail;
}

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
  const H = overlay.height;
  // Zona server: kiri 30% / tengah 40% / kanan 30% dari lebar GAMBAR.
  const x1 = petaKotak([0.3, 0, 0.3, 1])[0];
  const x2 = petaKotak([0.7, 0, 0.7, 1])[0];
  ctx.save();
  ctx.strokeStyle = "rgba(255,255,255,0.45)";
  ctx.lineWidth = 2;
  ctx.setLineDash([10, 10]);
  ctx.beginPath();
  ctx.moveTo(x1, 0);
  ctx.lineTo(x1, H);
  ctx.moveTo(x2, 0);
  ctx.lineTo(x2, H);
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
    ctx.font = "bold 18px sans-serif";
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
  let berhasil = false;
  try {
    const jpeg = await ambilJpeg();
    if (!jpeg || !jalan) return;
    jumlah += 1;
    const t0 = performance.now();
    let balasan;
    if (MODE_MOCK) {
      balasan = await ambilMock();
    } else {
      balasan = await kirimKeServer(jpeg);
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

async function mulaiKamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
    kamera.srcObject = stream;
    await kamera.play();
    layarAwal.hidden = true;
    setStatus("Kamera aktif.", null);
    tombolMulai.textContent = "Berhenti";
    tombolMulai.classList.add("jalan");
    bukaSuara();
    sesuaikanOverlay();
    gambarOverlay(null);
    jumlah = 0;
    jalankanLoop();
    mintaKunciLayar();
  } catch (err) {
    setStatus("Kamera gagal: " + err.name, null);
  }
}

function berhentiKamera() {
  hentikanLoop();
  lepasKunciLayar();
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }
  kamera.srcObject = null;
  setStatus("Tekan Mulai.", null);
  setZona(null, 0);
  info.textContent = "";
  info.className = "";
  tombolMulai.textContent = "Mulai";
  tombolMulai.classList.remove("jalan");
  layarAwal.hidden = false;
  bersihkanOverlay();
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

// Browser melepas kunci otomatis saat tab tersembunyi: minta lagi saat muncul.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && stream) mintaKunciLayar();
});

window.addEventListener("resize", () => {
  sesuaikanOverlay();
  if (!stream) bersihkanOverlay();
});

tombolMulai.addEventListener("click", () => {
  if (stream) {
    berhentiKamera();
  } else {
    mulaiKamera();
  }
});

// --- Bisu ---
tombolBisu.addEventListener("click", () => {
  setBisu(!bisu);
  tombolBisu.textContent = bisu ? "Suara nyala" : "Bisu";
  tombolBisu.classList.toggle("aktif", bisu);
  tombolBisu.setAttribute("aria-pressed", String(bisu));
});

// --- Pengaturan ---
tombolAtur.addEventListener("click", () => {
  panel.hidden = !panel.hidden;
  tombolAtur.setAttribute("aria-expanded", String(!panel.hidden));
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