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

let jedaKirimMs = 200;
let stream = null;
let timer = null;
let sibuk = false;
let jumlah = 0;

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
  const W = overlay.width;
  const H = overlay.height;
  ctx.save();
  ctx.strokeStyle = "rgba(255,255,255,0.45)";
  ctx.lineWidth = 2;
  ctx.setLineDash([10, 10]);
  ctx.beginPath();
  ctx.moveTo(W / 3, 0);
  ctx.lineTo(W / 3, H);
  ctx.moveTo((2 * W) / 3, 0);
  ctx.lineTo((2 * W) / 3, H);
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

function tampilkanBalasan(balasan, latensiMs) {
  const p = balasan.peringatan;
  if (p) {
    setStatus(
      p.pesan,
      p.tingkat,
      "Posisi: " + p.posisi + " · Jarak: " + p.jarak
    );
  } else {
    setStatus("Aman.", 0);
  }
  setZona(p ? p.posisi : null, p ? p.tingkat : 0);
  gambarOverlay(balasan);
  ucapkan(p);
  info.className =
    latensiMs < 100 ? "ok" : latensiMs < 300 ? "sedang" : "lambat";
  info.textContent =
    (MODE_MOCK ? "MOCK | " : "") +
    "Frame " + jumlah + " | " + Math.round(latensiMs) + " ms | objek: " +
    balasan.objek.length + " | suara: " + namaSuara;
}

async function siklus() {
  if (sibuk) return; // hanya satu proses dalam satu waktu
  sibuk = true;
  try {
    const jpeg = await ambilJpeg();
    if (!jpeg) return;
    jumlah += 1;
    const t0 = performance.now();
    let balasan;
    if (MODE_MOCK) {
      balasan = await ambilMock();
    } else {
      // Langkah 5: kirim ke POST /api/deteksi (belum dikerjakan)
      info.textContent = "Frame " + jumlah + " (server belum disambung)";
      return;
    }
    tampilkanBalasan(balasan, performance.now() - t0);
  } finally {
    sibuk = false;
  }
}

function jalankanTimer() {
  clearInterval(timer);
  timer = setInterval(siklus, jedaKirimMs);
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
    jalankanTimer();
  } catch (err) {
    setStatus("Kamera gagal: " + err.name, null);
  }
}

function berhentiKamera() {
  clearInterval(timer);
  timer = null;
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
  if (stream) jalankanTimer();
});

document.getElementById("atur-ulang").addEventListener("input", (e) => {
  pengaturanSuara.jedaUlangMs = Number(e.target.value) * 1000;
  document.getElementById("nilai-ulang").textContent = e.target.value;
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