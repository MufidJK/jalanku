// Tes alur Zanite di HP, tanpa browser dan tanpa jaringan: node tests/zanite/tes_alur.js
// Memuat berkas web ASLI (suara.js, zanite-cocok.js, zanite-aturan.js, zanite.js, mock.js) ke dalam konteks vm dengan
// pengenal suara, TTS, WebAudio, fetch, dan jam palsu. app.js tidak dimuat; variabel yang dibacanya dari luar
// (generasi, SESI, ambilJpeg, ...) disediakan oleh prelude di bawah.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const WEB = path.join(__dirname, "..", "..", "src", "web");
let total = 0, gagal = 0;
const cek = (nama, ok, info) => { total++; if (!ok) { gagal++; console.log("GAGAL:", nama, info === undefined ? "" : JSON.stringify(info)); } };

const BALAS = "Iya, ada yang bisa saya bantu?";
const PESAN_JARINGAN = "Zanite butuh internet atau server sedang bermasalah.";
const DURASI_BICARA = 800;

function buatDunia(opsi = {}) {
  const o = Object.assign({ sr: true, mock: false, statusZanite: true, jawaban: "Di kiri ada pilar, jaraknya sedang.", tundaJawab: 1000, kodeJawab: 200 }, opsi);
  let now = 0, nid = 0;
  const timers = [];
  const setT = (fn, ms) => { const id = ++nid; timers.push({ id, at: now + (ms || 0), fn }); return id; };
  const clearT = (id) => { const i = timers.findIndex((t) => t.id === id); if (i >= 0) timers.splice(i, 1); };
  const tick = () => new Promise((r) => setImmediate(r));
  async function maju(ms) {
    const akhir = now + ms;
    for (;;) {
      const t = timers.filter((x) => x.at <= akhir).sort((a, b) => a.at - b.at || a.id - b.id)[0];
      if (!t) break;
      now = Math.max(now, t.at);
      timers.splice(timers.indexOf(t), 1);
      t.fn();
      await tick();
    }
    now = akhir;
    await tick();
  }

  const D = { SRs: [], diucap: [], cancelPanggil: 0, fetchCalls: [], statusLog: [], bips: 0, papanKlip: [] };

  class FakeSR {
    constructor() { D.SRs.push(this); this.aborted = false; this.started = false; this.results = []; }
    start() { this.started = true; }
    abort() { this.aborted = true; setT(() => { this.onerror && this.onerror({ error: "aborted" }); this.onend && this.onend(); }, 0); }
  }
  class FakeUtterance {
    constructor(text) { this.text = text; this.ls = {}; }
    addEventListener(t, f) { (this.ls[t] = this.ls[t] || []).push(f); }
    fire(t) { (this.ls[t] || []).forEach((f) => f({})); }
  }
  const synth = {
    antre: [], sedang: null, speaking: false, timer: null,
    get pending() { return this.antre.length > 0; },
    getVoices: () => [{ lang: "in-ID", name: "Suara Indonesia" }],
    speak(u) { this.antre.push(u); if (!this.sedang) this.lanjut(); },
    lanjut() {
      const u = this.antre.shift();
      if (!u) { this.sedang = null; this.speaking = false; return; }
      this.sedang = u; this.speaking = true; D.diucap.push(u.text); u.fire("start");
      this.timer = setT(() => { this.sedang = null; if (!o.tanpaEnd) u.fire("end"); this.lanjut(); }, DURASI_BICARA);
    },
    cancel() {
      D.cancelPanggil++;
      const semua = [this.sedang].concat(this.antre).filter(Boolean);
      clearT(this.timer); this.antre = []; this.sedang = null; this.speaking = false;
      if (!o.cancelTanpaEvent) semua.forEach((u) => u.fire("error"));
    },
  };
  class FakeAudioContext {
    constructor() { this.state = "running"; this.currentTime = 0; }
    resume() {}
    createGain() { return { gain: {}, connect() {} }; }
    createOscillator() {
      const osc = { frequency: {}, connect() {}, start() { D.bips++; }, stop() { setT(() => osc.onended && osc.onended(), 150); } };
      return osc;
    }
    get destination() { return {}; }
  }
  function fakeFetch(url, init) {
    const p = typeof url === "string" ? url : "";
    D.fetchCalls.push({ url: p, init });
    return new Promise((resolve, reject) => {
      let beres = false;
      const sig = init && init.signal;
      if (sig) sig.addEventListener("abort", () => { if (!beres) { beres = true; reject(Object.assign(new Error("abort"), { name: "AbortError" })); } });
      if (p.endsWith("/api/status")) {
        if (o.statusGagal) return setT(() => { beres = true; reject(new TypeError("Failed to fetch")); }, 0);
        return setT(() => { beres = true; resolve({ ok: true, json: async () => ({ siap: true, versi_kontrak: 1, zanite: o.statusZanite }) }); }, 0);
      }
      if (o.galatJaringan) return setT(() => { if (!beres) { beres = true; reject(new TypeError("Failed to fetch")); } }, 50);
      setT(() => {
        if (beres) return;
        beres = true;
        resolve({
          ok: o.kodeJawab === 200,
          status: o.kodeJawab,
          json: async () => { if (o.tanpaJson) throw new Error("bukan json"); return o.badanJawab || { jawaban: o.jawaban, jenis: "jawaban" }; },
        });
      }, o.tundaJawab);
    });
  }
  const elStatus = { _t: "", hidden: true, redup: false, set textContent(v) { this._t = v; D.statusLog.push(v); }, get textContent() { return this._t; },
    classList: { toggle(k, on) { if (k === "redup") elStatus.redup = !!on; } } };
  const fakeEl = () => ({ hidden: true, value: "", _t: "", ls: {}, set textContent(v) { this._t = v; }, get textContent() { return this._t; },
    addEventListener(t, f) { this.ls[t] = f; }, focus() { this.fokus = true; }, select() { this.terpilih = true; } });
  const elTombolLog = fakeEl(), elAreaLog = fakeEl();
  elTombolLog._t = "Salin log Zanite";

  const ctx = {
    console, AbortController, Promise, setTimeout: setT, clearTimeout: clearT,
    performance: { now: () => now },
    fetch: fakeFetch,
    FileReader: class { readAsDataURL() { setT(() => this.onload && (this.result = "data:image/jpeg;base64,QUJD", this.onload()), 0); } },
    AudioContext: FakeAudioContext,
    SpeechSynthesisUtterance: FakeUtterance, speechSynthesis: synth,
    navigator: { userAgent: "UA-uji", clipboard: { writeText: async (t) => { if (o.klipGagal) throw new Error("ditolak"); D.papanKlip.push(t); } } },
    document: { getElementById: (id) => (id === "zanite-status" ? elStatus : id === "salin-log-zanite" ? elTombolLog : id === "teks-log-zanite" ? elAreaLog : null) },
  };
  if (o.sr) ctx.SpeechRecognition = FakeSR;
  ctx.window = ctx;
  vm.createContext(ctx);
  const muat = (kode, nama) => vm.runInContext(kode, ctx, { filename: nama });
  muat(`let generasi = 0; let SESI = "sesi-uji"; const MODE_MOCK = ${o.mock ? "true" : "false"}; const ALAMAT_SERVER = "";
        function ambilJpeg() { return Promise.resolve({ blobPalsu: true }); }`, "prelude");
  for (const f of ["suara.js", "mock.js", "zanite-cocok.js", "zanite-aturan.js", "zanite.js"]) muat(fs.readFileSync(path.join(WEB, f), "utf8"), f);

  const sr = () => D.SRs[D.SRs.length - 1];
  D.ctx = ctx; D.maju = maju; D.synth = synth; D.status = elStatus; D.tombolLog = elTombolLog; D.areaLog = elAreaLog;
  D.waktu = () => now;
  D.jalankan = (kode) => vm.runInContext(kode, ctx);
  D.mulai = async () => { const p = ctx.Zanite.mulai(); await maju(1); await p; await maju(1); };
  // satu hasil pengenal: idx baru = ucapan baru; idx lama = pembaruan hasil yang sama
  D.ucap = (teks, final = false, idx = null) => {
    const r = sr();
    if (idx === null) idx = r.results.length;
    r.results[idx] = { isFinal: final, length: 1, 0: { transcript: teks, confidence: 0.9 } };
    r.onresult({ resultIndex: idx, results: r.results });
    return idx;
  };
  D.sr = sr;
  D.zanite = () => D.fetchCalls.filter((c) => c.url.endsWith("/api/zanite"));
  D.tidakPernahAbort = () => D.SRs.every((r) => !r.aborted);
  return D;
}

async function tes(nama, fn) {
  const sebelum = total;
  try { await fn(); }
  catch (e) { gagal++; total++; console.log("GALAT di", nama, e && e.stack || e); }
  console.log("  " + nama + ": " + (total - sebelum) + " pemeriksaan");
}

(async () => {
  await tes("dua langkah: wake -> bip -> balasan -> jendela -> kirim -> jawaban", async () => {
    const d = buatDunia();
    await d.mulai();
    cek("pengenal dibuat dan dimulai", d.SRs.length === 1 && d.sr().started && d.sr().lang === "id-ID" && d.sr().continuous && d.sr().interimResults && d.sr().maxAlternatives === 3);
    cek("status server dicek", d.fetchCalls.length === 1 && d.fetchCalls[0].url === "/api/status");
    d.ucap("Janet");
    await d.maju(799);
    cek("belum menyala di 799 ms", d.diucap.length === 0 && d.synth.sedang === null && d.bips === 0);
    await d.maju(11);
    cek("menyala sesudah 800 ms: bip", d.bips === 1, d.bips);
    cek("belum bicara sebelum bip selesai", d.diucap.length === 0);
    await d.maju(150);
    cek("setelah bip: 'Iya, ada yang bisa saya bantu?'", d.diucap.length === 1 && d.diucap[0] === BALAS, d.diucap);
    cek("status belum 'mendengar' saat membalas", d.status.textContent === "" && d.status.hidden === true);
    await d.maju(DURASI_BICARA);
    cek("jendela terbuka setelah balasan selesai", d.status.textContent === "Zanite mendengar" && d.status.hidden === false, d.status.textContent);
    await d.maju(600);
    const idx = d.ucap("itu apa di depan?");
    await d.maju(1199);
    cek("pertanyaan bebas: belum dikirim di 1199 ms", d.zanite().length === 0);
    await d.maju(10);
    const z = d.zanite();
    cek("dikirim sekali ke /api/zanite", z.length === 1, z.length);
    const body = z[0] && JSON.parse(z[0].init.body);
    cek("badan: teks apa adanya + gambar base64", body && body.teks === "itu apa di depan?" && body.gambar === "QUJD", body);
    cek("header: JSON + X-Sesi sesi sekarang, method POST", z[0].init.method === "POST" && z[0].init.headers["Content-Type"] === "application/json" && z[0].init.headers["X-Sesi"] === "sesi-uji");
    cek("status 'memproses', tanpa ucapan 'memuat'", d.status.textContent === "Zanite memproses" && d.diucap.length === 1);
    await d.maju(1000);
    cek("jawaban diucapkan", d.diucap.length === 2 && d.diucap[1] === "Di kiri ada pilar, jaraknya sedang.", d.diucap);
    cek("sesudahnya kembali ke 'Zanite aktif' redup", d.status.textContent === "Zanite aktif" && d.status.hidden === false && d.status.redup === true, [d.status.textContent, d.status.redup]);
    cek("mic tidak pernah di-abort selama alur", d.tidakPernahAbort());
    cek("hanya SATU pengenal selama seluruh alur", d.SRs.length === 1, d.SRs.length);
  });

  await tes("satu napas: tanpa 'Iya', bip saat kirim", async () => {
    const d = buatDunia();
    await d.mulai();
    d.ucap("Zanite jelasin sekitar");
    await d.maju(0);
    cek("tidak ada bip/ucapan sebelum perintah selesai", d.bips === 0 && d.diucap.length === 0);
    await d.maju(699);
    cek("belum dikirim di 699 ms", d.zanite().length === 0);
    await d.maju(10);
    cek("dikirim sesudah 700 ms dengan perintah tanpa kata bangun", d.zanite().length === 1 && JSON.parse(d.zanite()[0].init.body).teks === "jelasin sekitar", d.zanite().map((c) => c.init.body));
    cek("bip saat kirim, tanpa 'Iya, ...'", d.bips === 1 && d.diucap.length === 0, [d.bips, d.diucap]);
    await d.maju(1000);
    cek("jawaban diucapkan", d.diucap.length === 1 && d.diucap[0] === "Di kiri ada pilar, jaraknya sedang.", d.diucap);
  });

  await tes("satu napas: kalimat tumbuh, kata sopan, 'jadi'", async () => {
    const d = buatDunia();
    await d.mulai();
    const i = d.ucap("Zanite jelaskan");          // interim pertama
    await d.maju(300);
    d.ucap("Zanite jelaskan sekitar gue dong", false, i);
    await d.maju(699); cek("kalimat tumbuh: menunggu sampai selesai", d.zanite().length === 0);
    await d.maju(10);
    cek("kalimat lengkap yang dikirim", d.zanite().length === 1 && JSON.parse(d.zanite()[0].init.body).teks === "jelaskan sekitar gue dong", d.zanite().map((c) => c.init.body));
    await d.maju(3000);
    // kata sopan
    d.ucap("Zanite tolong jelaskan sekitar"); await d.maju(800);
    cek("'tolong' di antara varian dan perintah", d.zanite().length === 2 && JSON.parse(d.zanite()[1].init.body).teks === "jelaskan sekitar", d.zanite().map((c) => c.init.body));
    await d.maju(3000);
    // "jadi" + perintah penuh
    d.ucap("jadi jelasin sekitar"); await d.maju(800);
    cek("'jadi' + perintah penuh = wake", d.zanite().length === 3 && JSON.parse(d.zanite()[2].init.body).teks === "jelasin sekitar", d.zanite().map((c) => c.init.body));
    await d.maju(3000);
    const n = d.zanite().length, bip = d.bips;
    d.ucap("jadi apa itu"); await d.maju(3000);
    d.ucap("jadi jelaskan"); await d.maju(3000);
    cek("'jadi' tanpa perintah penuh bukan wake", d.zanite().length === n && d.bips === bip && d.diucap.filter((x) => x === BALAS).length === 0, d.diucap);
    cek("mic tidak pernah di-abort", d.tidakPernahAbort());
  });

  await tes("jendela 6 detik: diam-diam tertutup", async () => {
    const d = buatDunia();
    await d.mulai();
    d.ucap("Zanite", true);
    await d.maju(150 + DURASI_BICARA + 100);
    cek("jendela terbuka", d.status.textContent === "Zanite mendengar");
    await d.maju(5800);
    cek("belum tertutup di 5,9 dtk", d.status.textContent === "Zanite mendengar");
    await d.maju(300);
    cek("tertutup sesudah 6 dtk, tanpa suara", d.status.textContent === "Zanite aktif" && d.diucap.length === 1 && d.zanite().length === 0, d.diucap);
    cek("mic tidak di-abort", d.tidakPernahAbort());
    // sesudah itu wake baru bisa lagi
    d.ucap("Janit"); await d.maju(800 + 150 + 30);
    cek("wake lagi sesudah jendela tutup", d.diucap.filter((x) => x === BALAS).length === 2, d.diucap);
  });

  await tes("transkrip dibuang saat app bicara dan 500 ms sesudahnya", async () => {
    const d = buatDunia();
    await d.mulai();
    d.ucap("Zanite", true);
    await d.maju(150);                               // bip selesai, balasan mulai
    d.ucap("Zanite jelaskan sekitar");               // terdengar mic saat balasan: harus dibuang
    await d.maju(DURASI_BICARA - 1);
    cek("selama balasan: dibuang, tidak jadi perintah", d.zanite().length === 0);
    await d.maju(1);                                 // balasan selesai
    cek("jendela terbuka", d.status.textContent === "Zanite mendengar");
    await d.maju(499);
    d.ucap("lalu apa", false);                       // 499 ms sesudah selesai: masih dibuang
    await d.maju(1);
    const idx = d.ucap("itu apa di depan", false);   // tepat 500 ms sesudah selesai: diterima
    await d.maju(1190);
    cek("499 ms dibuang: belum ada yang dikirim sebelum jeda 1,2 dtk dari yang diterima", d.zanite().length === 0);
    await d.maju(20);
    cek("dikirim: teks yang diterima saja", d.zanite().length === 1 && JSON.parse(d.zanite()[0].init.body).teks === "itu apa di depan", d.zanite().map((c) => c.init.body));
    cek("mic tidak di-abort", d.tidakPernahAbort());
  });

  await tes("peringatan (ucapkan) dan pesan sistem: transkrip dibuang, mic hidup", async () => {
    const d = buatDunia();
    await d.mulai();
    d.jalankan(`ucapkan({ pesan: "Pilar di kiri, dekat", tingkat: 2, kelas: "pilar" })`);
    await d.maju(100);
    cek("peringatan diucapkan", d.diucap[0] === "Pilar di kiri, dekat" && d.synth.speaking);
    d.ucap("Zanite", true);                          // terdengar saat peringatan
    await d.maju(DURASI_BICARA + 400);               // peringatan selesai + 400 ms (< 500)
    cek("kata bangun saat peringatan tidak menyalakan Zanite", d.bips === 0 && d.diucap.length === 1);
    d.jalankan(`ucapkanSistem("Lanjut.")`);
    await d.maju(100);
    d.ucap("Janit", true);
    await d.maju(DURASI_BICARA + 2000);
    cek("saat pesan sistem juga dibuang", d.bips === 0 && !d.diucap.includes(BALAS), d.diucap);
    await d.maju(600);
    d.ucap("Zanite", true);
    await d.maju(10);
    cek("sesudahnya Zanite mendengar lagi", d.bips === 1);
    cek("pengenal tidak pernah di-abort karena app bicara", d.tidakPernahAbort() && d.SRs.length === 1);
  });

  await tes("tingkat 3 memotong Zanite; jawaban Zanite tidak memotong peringatan", async () => {
    const d = buatDunia({ tundaJawab: 200 });
    await d.mulai();
    d.ucap("Zanite jelasin sekitar"); await d.maju(700 + 220);        // jawaban datang dan sedang diucapkan
    cek("jawaban sedang diucapkan", d.synth.sedang && d.synth.sedang.text === "Di kiri ada pilar, jaraknya sedang.", d.diucap);
    const c0 = d.cancelPanggil;
    d.jalankan(`ucapkan({ pesan: "Tangga di depan", tingkat: 3, kelas: "tangga" })`);
    cek("tingkat 3 memotong jawaban Zanite", d.cancelPanggil === c0 + 1 && d.diucap[d.diucap.length - 1] === "Tangga di depan", d.diucap);
    d.jalankan(`ucapkan({ pesan: "Kursi di kiri, dekat", tingkat: 1, kelas: "kursi" })`);
    cek("tingkat 1 tidak memotong dan tidak antre", d.diucap[d.diucap.length - 1] === "Tangga di depan");
    await d.maju(DURASI_BICARA + 600);

    // jawaban yang datang SAAT peringatan tingkat 3 bicara: antre di belakangnya, tanpa cancel
    const e = buatDunia({ tundaJawab: 300 });
    await e.mulai();
    e.ucap("Zanite jelasin sekitar"); await e.maju(700 + 100);        // menunggu jawaban
    e.jalankan(`ucapkan({ pesan: "Tangga di depan", tingkat: 3, kelas: "tangga" })`);
    const cancelSebelum = e.cancelPanggil;
    await e.maju(300);                                                // jawaban tiba saat peringatan bicara
    cek("jawaban tidak memanggil cancel", e.cancelPanggil === cancelSebelum);
    cek("peringatan selesai dulu, lalu jawaban", e.diucap[e.diucap.length - 1] === "Tangga di depan" && e.synth.antre.length === 1, e.diucap);
    await e.maju(DURASI_BICARA);
    cek("jawaban diucapkan sesudah peringatan", e.diucap[e.diucap.length - 1] === "Di kiri ada pilar, jaraknya sedang.", e.diucap);
  });

  await tes("jawaban usang dibuang: kamera dijeda/berhenti, atau > 10 detik", async () => {
    const d = buatDunia({ tundaJawab: 3000 });
    await d.mulai();
    d.ucap("Zanite jelasin sekitar"); await d.maju(700 + 100);
    d.jalankan("generasi += 1");                       // jedaOtomatis / Berhenti
    await d.maju(4000);
    cek("generasi berubah: jawaban dibuang", d.zanite().length === 1 && d.diucap.length === 0, d.diucap);
    cek("status kembali 'Zanite aktif'", d.status.textContent === "Zanite aktif");

    const e = buatDunia({ tundaJawab: 9000 });
    await e.mulai();
    e.ucap("Zanite jelasin sekitar"); await e.maju(700 + 9000 + 50);
    cek("9 detik: masih diucapkan", e.diucap.length === 1 && e.diucap[0].startsWith("Di kiri"), e.diucap);

    const f = buatDunia({ tundaJawab: 12000 });
    await f.mulai();
    f.ucap("Zanite jelasin sekitar"); await f.maju(700 + 11000);
    cek("klien menyerah di 10 dtk dan mengucapkan pesan jaringan", f.diucap.length === 1 && f.diucap[0] === PESAN_JARINGAN, f.diucap);
    await f.maju(5000);
    cek("jawaban server yang terlambat tidak diucapkan lagi", f.diucap.length === 1);
  });

  await tes("kegagalan jaringan/server dan kalimat dari server", async () => {
    const a = buatDunia({ galatJaringan: true });
    await a.mulai(); a.ucap("Zanite jelasin sekitar"); await a.maju(700 + 200);
    cek("fetch gagal: pesan jaringan sekali", a.diucap.length === 1 && a.diucap[0] === PESAN_JARINGAN, a.diucap);
    const b = buatDunia({ kodeJawab: 502, tanpaJson: true });
    await b.mulai(); b.ucap("Zanite jelasin sekitar"); await b.maju(700 + 1100);
    cek("502 tanpa JSON: pesan jaringan", b.diucap.length === 1 && b.diucap[0] === PESAN_JARINGAN, b.diucap);
    const c = buatDunia({ kodeJawab: 429, badanJawab: { jawaban: "Tunggu sebentar, Zanite baru saja menjawab.", jenis: "batas" } });
    await c.mulai(); c.ucap("Zanite jelasin sekitar"); await c.maju(700 + 1100);
    cek("429 dengan JSON: kalimat server diucapkan", c.diucap.length === 1 && c.diucap[0] === "Tunggu sebentar, Zanite baru saja menjawab.", c.diucap);
    const e = buatDunia({ kodeJawab: 200, badanJawab: { aneh: 1 } });
    await e.mulai(); e.ucap("Zanite jelasin sekitar"); await e.maju(700 + 1100);
    cek("JSON tanpa 'jawaban': pesan jaringan", e.diucap.length === 1 && e.diucap[0] === PESAN_JARINGAN, e.diucap);
  });

  await tes("kata bangun lemah, ditolak, sapaan", async () => {
    const d = buatDunia();
    await d.mulai();
    d.ucap("jani", false); await d.maju(1199);
    cek("varian lemah interim: belum di 1199 ms", d.bips === 0);
    await d.maju(10);
    cek("varian lemah interim: menyala sesudah 1200 ms", d.bips === 1);
    await d.maju(150 + DURASI_BICARA + 6100);
    const n = d.bips;
    d.ucap("janit itu teman saya", true); await d.maju(3000);
    cek("kata lain sesudah varian: ditolak", d.bips === n);
    d.ucap("halo zanite", true); await d.maju(10);
    cek("sapaan + zanite menyala", d.bips === n + 1);
  });

  await tes("pengenal: restart otomatis, backoff, izin ditolak", async () => {
    const d = buatDunia();
    await d.mulai();
    d.sr().onend(); await d.maju(249);
    cek("berakhir biasa: belum restart di 249 ms", d.SRs.length === 1);
    await d.maju(1);
    cek("restart di 250 ms", d.SRs.length === 2 && d.sr().started);
    d.sr().onerror({ error: "network" }); d.sr().onend(); await d.maju(599);
    cek("error network: backoff 600 ms", d.SRs.length === 2);
    await d.maju(1);
    cek("restart sesudah backoff", d.SRs.length === 3);
    d.sr().onerror({ error: "network" }); d.sr().onend(); await d.maju(1199);
    cek("backoff berlipat (1200 ms)", d.SRs.length === 3);
    await d.maju(1);
    cek("restart ke-3", d.SRs.length === 4);
    d.sr().onerror({ error: "not-allowed" }); d.sr().onend(); await d.maju(30000);
    cek("izin ditolak: diucapkan sekali", d.diucap.length === 1 && d.diucap[0] === "Izin mikrofon ditolak, Zanite mati.", d.diucap);
    cek("izin ditolak: tidak restart", d.SRs.length === 4);
    d.ucap("Zanite", true); await d.maju(2000);
    cek("izin ditolak: Zanite mati total", d.bips === 0);
  });

  await tes("Bisu: tidak mendengar; Berhenti; mulai lagi", async () => {
    const d = buatDunia();
    await d.mulai();
    d.jalankan("setBisu(true)"); await d.maju(10);
    cek("Bisu menyala: pengenal dihentikan", d.SRs[0].aborted);
    d.sr().onend && d.sr().onend(); await d.maju(5000);
    cek("Bisu: tidak restart sendiri", d.SRs.length === 1);
    d.jalankan("setBisu(false)"); await d.maju(10);
    cek("Bisu dimatikan: mendengar lagi", d.SRs.length === 2 && d.sr().started && !d.sr().aborted);
    d.ucap("Zanite", true); await d.maju(100);
    cek("dan menyala lagi", d.bips === 1);
    // Berhenti membuang alur dan jawaban
    await d.maju(3000);
    d.ucap("Zanite jelasin sekitar"); await d.maju(900);
    d.ctx.Zanite.berhenti(); await d.maju(3000);
    cek("Berhenti: pengenal di-abort, tidak restart", d.sr().aborted && d.SRs.length === 2);
    cek("Berhenti: jawaban yang datang sesudahnya tidak diucapkan", d.diucap.filter((x) => x.startsWith("Di kiri")).length === 0);
    const ada = d.diucap.length;
    d.ctx.Zanite.mulai(); await d.maju(10);
    cek("mulai lagi sesudah Berhenti: pengenal baru", d.SRs.length === 3 && d.sr().started);
    // Bisu menyala saat mulai
    const e = buatDunia(); e.jalankan("bisu = true");
    await e.mulai();
    cek("mulai dalam keadaan Bisu: tidak mendengar", e.SRs.length === 0 || !e.sr().started, e.SRs.length);
    e.jalankan("setBisu(false)"); await e.maju(10);
    cek("Bisu dimatikan sesudahnya: mendengar", e.SRs.length === 1 && e.sr().started);
  });

  await tes("tidak aktif: server bilang zanite:false, tanpa SpeechRecognition, status gagal", async () => {
    const a = buatDunia({ statusZanite: false });
    await a.mulai();
    a.ctx.Zanite.mulai(); await a.maju(10);
    cek("zanite:false: tidak ada pengenal, tidak ada suara", a.SRs.length === 0 && a.diucap.length === 0 && a.bips === 0);
    const b = buatDunia({ sr: false });
    await b.mulai();
    cek("tanpa SpeechRecognition: tidak melakukan apa-apa, tidak memanggil server", b.SRs.length === 0 && b.fetchCalls.length === 0);
    const c = buatDunia({ statusGagal: true });
    await c.mulai();
    cek("status gagal: Zanite mati diam-diam", c.SRs.length === 0 && c.diucap.length === 0);
    // suara.js tanpa Zanite tetap bekerja (window.Zanite tidak ada)
    const d = buatDunia({ sr: false });
    d.jalankan(`ucapkan({ pesan: "Pilar di kiri, dekat", tingkat: 2, kelas: "pilar" }); setBisu(true); setBisu(false);`);
    cek("suara.js tetap jalan tanpa pengenal", d.diucap[0] === "Pilar di kiri, dekat");
  });

  await tes("mock: status true, jawaban tetap sesudah ~1,2 dtk, tanpa jaringan", async () => {
    const d = buatDunia({ mock: true });
    await d.mulai();
    cek("mock: pengenal hidup tanpa memanggil /api/status", d.SRs.length === 1 && d.fetchCalls.length === 0);
    d.ucap("Zanite jelasin sekitar"); await d.maju(710);
    cek("mock: tidak ada fetch", d.fetchCalls.length === 0 && d.status.textContent === "Zanite memproses");
    await d.maju(1190);
    cek("mock: belum menjawab sebelum 1,2 dtk", d.diucap.length === 0);
    await d.maju(20);
    cek("mock: jawaban tetap diucapkan sesudah 1,2 dtk", d.diucap.length === 1 && d.diucap[0].startsWith("Ini jawaban contoh dari Zanite"), d.diucap);
  });

  await tes("pilihSuaraIndonesia: id dan in", async () => {
    const d = buatDunia();
    const pilih = (daftar) => { d.synth.getVoices = () => daftar; return d.jalankan("pilihSuaraIndonesia()"); };
    cek("in-ID dipilih", (pilih([{ lang: "en-US", name: "e" }, { lang: "in-ID", name: "x" }]) || {}).name === "x");
    cek("in_ID dipilih", (pilih([{ lang: "in_ID", name: "y" }]) || {}).name === "y");
    cek("id-ID dipilih", (pilih([{ lang: "id-ID", name: "z" }]) || {}).name === "z");
    cek("'id' saja dipilih", (pilih([{ lang: "id", name: "w" }]) || {}).name === "w");
    cek("bahasa lain tidak dipilih (mis. 'ind', 'it-IT', 'inh')", pilih([{ lang: "it-IT", name: "a" }, { lang: "ind-XX", name: "b" }, { lang: "inh", name: "c" }]) === null);
  });

  await tes("risiko tuli: speaking macet tanpa catatan, onend tidak datang, cancel tingkat 3", async () => {
    // 1) speechSynthesis.speaking macet true, tidak ada ucapan app: Zanite tetap mendengar
    const a = buatDunia();
    await a.mulai();
    a.synth.speaking = true;                          // macet: tidak ada utterance app yang tercatat
    a.ucap("Janit", true);
    await a.maju(820);
    cek("speaking macet true tanpa catatan: wake tetap menyala", a.bips === 1 && a.ctx.Zanite._uji.hitung.dibuangSaatBicara === 0, [a.bips, a.ctx.Zanite._uji.hitung.dibuangSaatBicara]);

    // 2) onend tidak pernah datang: diakhiri paksa ~1 dtk sesudah sintesis diam; tidak menunggu pengaman 15-20 dtk
    const b = buatDunia({ tanpaEnd: true });
    await b.mulai();
    b.jalankan(`ucapkan({ pesan: "Pilar di kiri, dekat", tingkat: 2, kelas: "pilar" })`);
    await b.maju(DURASI_BICARA);                      // sintesis selesai tanpa onend; terakhir terlihat aktif di ~750
    cek("sintesis diam tanpa onend", b.synth.speaking === false && b.ctx.Zanite._uji.statistik().paksa === 0);
    await b.maju(900);                                // t=1700: belum 1000 ms sejak terakhir aktif
    cek("belum dipaksa < 1 dtk sesudah sintesis diam", b.ctx.Zanite._uji.statistik().paksa === 0, b.ctx.Zanite._uji.statistik());
    await b.maju(150);                                // t=1850
    cek("dipaksa selesai ~1 dtk sesudah speaking/pending false", b.ctx.Zanite._uji.statistik().paksa === 1, b.ctx.Zanite._uji.statistik());
    cek("tercatat di log uji", b.ctx.Zanite.debug().some((x) => /selesai-paksa/.test(x)));
    b.ucap("Zanite", true);                           // sesudahnya didengar lagi, jauh sebelum 15-20 dtk
    await b.maju(810);
    cek("sesudah selesai-paksa Zanite mendengar lagi (tanpa menunggu 15-20 dtk)", b.bips === 1 && b.waktu() < 4000, [b.bips, b.waktu()]);

    // 3) transkrip selama ucapan benar-benar berbunyi tetap dibuang
    const c = buatDunia({ tanpaEnd: true });
    await c.mulai();
    c.jalankan(`ucapkan({ pesan: "Pilar di kiri, dekat", tingkat: 2, kelas: "pilar" })`);
    await c.maju(400);
    c.ucap("Zanite", true); await c.maju(2000);
    cek("selama sintesis berbunyi: dibuang", c.bips === 0 && c.ctx.Zanite._uji.hitung.dibuangSaatBicara === 1, [c.bips, c.ctx.Zanite._uji.hitung.dibuangSaatBicara]);

    // 4) tingkat 3 memanggil cancel() yang tidak mengirim onend/onerror: catatan lama diakhiri, bukan menunggu
    const d = buatDunia({ tundaJawab: 200, cancelTanpaEvent: true });
    await d.mulai();
    d.ucap("Zanite jelasin sekitar"); await d.maju(700 + 220);      // jawaban Zanite sedang diucapkan
    cek("jawaban Zanite sedang diucapkan", d.synth.sedang && d.synth.sedang.text.startsWith("Di kiri"));
    d.jalankan(`ucapkan({ pesan: "Tangga di depan", tingkat: 3, kelas: "tangga" })`);
    const st = d.ctx.Zanite._uji.statistik(), bip0 = d.bips;          // bip0: bip saat kirim (satu napas)
    cek("cancel tingkat 3: catatan lama diakhiri oleh cancel (bukan selesai-paksa, bukan pengaman)", st.dibatalkan === 1 && st.paksa === 0, st);
    cek("tercatat di log", d.ctx.Zanite.debug().some((x) => /cancel: 1 ucapan diakhiri/.test(x)));
    await d.maju(600);
    d.ucap("Zanite", true); await d.maju(50);                         // saat ucapan tingkat 3 masih bicara (600 < 800): dibuang
    cek("ucapan tingkat 3 (catatan sendiri) tetap membuang transkrip", d.bips === bip0 && d.ctx.Zanite._uji.hitung.dibuangSaatBicara === 1, [d.bips, bip0]);
    await d.maju(150 + 600);                                          // tingkat 3 selesai (800) + > 500 ms
    d.ucap("Janit", true); await d.maju(820);
    cek("sesudah ucapan tingkat 3 selesai: Zanite mendengar lagi", d.bips === bip0 + 1, [d.bips, bip0]);
    cek("pengenal tidak pernah di-abort", d.tidakPernahAbort());
  });

  await tes("balasan 'Iya, ...' dipotong tingkat 3 / dipaksa selesai: jendela terbuka sesudahnya, bukan setelah pengaman 20 dtk", async () => {
    // 1) dipotong peringatan tingkat 3, cancel() tidak mengirim event apa pun
    const d = buatDunia({ cancelTanpaEvent: true });
    await d.mulai();
    d.ucap("Zanite", true); await d.maju(10 + 150 + 300);              // bip selesai, BALAS sedang diucapkan
    cek("balasan sedang diucapkan", d.synth.sedang && d.synth.sedang.text === BALAS, d.diucap);
    d.jalankan(`ucapkan({ pesan: "Tangga di depan", tingkat: 3, kelas: "tangga" })`);
    await d.maju(DURASI_BICARA - 100);                                   // peringatan masih bicara
    cek("selama peringatan tingkat 3 bicara: jendela belum dibuka", d.status.textContent !== "Zanite mendengar", d.status.textContent);
    await d.maju(100 + 150);                                             // peringatan selesai
    cek("sesudah peringatan selesai: jendela terbuka (tanpa menunggu pengaman 20 dtk)", d.status.textContent === "Zanite mendengar" && d.waktu() < 3000, [d.status.textContent, d.waktu()]);
    await d.maju(600);
    d.ucap("itu apa di depan?"); await d.maju(1300);
    cek("perintah sesudah peringatan diterima dan dikirim", d.zanite().length === 1 && JSON.parse(d.zanite()[0].init.body).teks === "itu apa di depan?", d.zanite().map((c) => c.init.body));

    // 2) onend balasan tidak pernah datang: dipaksa selesai, jendela terbuka sekitar 1 dtk sesudah suara berhenti
    const e = buatDunia({ tanpaEnd: true });
    await e.mulai();
    e.ucap("Zanite", true); await e.maju(10 + 150);
    cek("balasan diucapkan", e.diucap[0] === BALAS);
    await e.maju(DURASI_BICARA);                                         // suara berhenti, onend tidak datang
    cek("belum terbuka tepat saat suara berhenti", e.status.textContent !== "Zanite mendengar");
    await e.maju(2200);
    cek("terbuka sesudah selesai-paksa, jauh sebelum 20 dtk", e.status.textContent === "Zanite mendengar" && e.waktu() < 5000 && e.ctx.Zanite._uji.statistik().paksa === 1, [e.status.textContent, e.waktu(), e.ctx.Zanite._uji.statistik()]);

    // 3) alur normal tidak terlambat: jendela terbuka tepat saat balasan selesai
    const f = buatDunia();
    await f.mulai();
    f.ucap("Zanite", true); await f.maju(10 + 150 + DURASI_BICARA + 5);
    cek("normal: jendela terbuka segera sesudah balasan selesai", f.status.textContent === "Zanite mendengar", f.status.textContent);
  });

  await tes("status 'Zanite aktif' redup saat menunggu kata bangun", async () => {
    const d = buatDunia();
    cek("sebelum mulai: kosong", d.status.textContent === "" && d.status.hidden === true);
    await d.mulai();
    cek("mendengarkan kata bangun: 'Zanite aktif' redup", d.status.textContent === "Zanite aktif" && d.status.hidden === false && d.status.redup === true);
    d.ucap("Zanite", true); await d.maju(810);
    cek("saat membalas: kosong", d.status.textContent === "" && d.status.hidden === true, d.status.textContent);
    await d.maju(150 + DURASI_BICARA);
    cek("jendela: 'Zanite mendengar' tidak redup", d.status.textContent === "Zanite mendengar" && d.status.redup === false);
    await d.maju(6100);
    cek("jendela tutup: kembali 'Zanite aktif'", d.status.textContent === "Zanite aktif" && d.status.redup === true);
    d.jalankan("setBisu(true)"); await d.maju(10);
    cek("Bisu: tidak mendengar, status kosong", d.status.textContent === "" && d.status.hidden === true, d.status.textContent);
    d.jalankan("setBisu(false)"); await d.maju(10);
    cek("Bisu mati: 'Zanite aktif' lagi", d.status.textContent === "Zanite aktif");
    d.ctx.Zanite.berhenti(); await d.maju(10);
    cek("Berhenti: kosong", d.status.textContent === "");
    const e = buatDunia(); await e.mulai();
    e.sr().onerror({ error: "not-allowed" }); e.sr().onend(); await e.maju(10);
    cek("izin ditolak: status kosong", e.status.textContent === "");
    const f = buatDunia({ statusZanite: false }); await f.mulai();
    cek("Zanite tidak tersedia di server: tidak ada status", f.status.textContent === "");
  });

  await tes("Salin log Zanite: isi, hitungan, papan klip, cadangan <textarea>", async () => {
    const d = buatDunia();
    cek("tombol disiapkan oleh zanite.js (terlihat, ada pendengar klik)", d.tombolLog.hidden === false && typeof d.tombolLog.ls.click === "function");
    await d.mulai();
    d.ucap("Janit"); await d.maju(800 + 150 + DURASI_BICARA + 600);     // dua langkah, sesudah ekor 500 ms balasan
    d.ucap("itu apa di depan?"); await d.maju(1300 + 1000);                // jawaban
    const L = d.ctx.Zanite.laporan();
    cek("header: versi, userAgent, suara + bahasa, TAIL/DIAM/LEMAH", /versi: zanite-app-1/.test(L) && /userAgent: UA-uji/.test(L) && /suara: Suara Indonesia \(in-ID\)/.test(L) && /TAIL_MS: 500/.test(L) && /DIAM_MS: 800/.test(L) && /LEMAH_MS: 1200/.test(L), L.slice(0, 400));
    cek("hitungan: wake per tipe", /wake per tipe: .*=\d/.test(L), L);
    for (const k of ["transkrip dibuang saat app bicara", "selesai-paksa", "pengenal restart", "galat pengenal per jenis", "permintaan terkirim: 1", "jawaban per jenis: jawaban=1", "jawaban usang dibuang: 0", "bip gagal: 0"])
      cek("hitungan memuat: " + k, L.includes(k), k);
    cek("baris log: ada cap waktu dan isi", /\d\d:\d\d:\d\d\.\d{3} \+\d+ms WAKE/.test(L) && /kirim: itu apa di depan\?/.test(L));
    cek("teks jawaban TIDAK ikut di log", !L.includes("Di kiri ada pilar"));
    cek("memanggil laporan tidak menyentuh jaringan", d.fetchCalls.filter((c) => !c.url.endsWith("/api/status") && !c.url.endsWith("/api/zanite")).length === 0);
    const sebelum = d.fetchCalls.length;
    const ok = await d.ctx.Zanite.salinLog();
    cek("salin ke papan klip berhasil, tanpa fetch baru", ok === true && d.papanKlip.length === 1 && d.papanKlip[0].startsWith("== LOG ZANITE ==") && d.fetchCalls.length === sebelum);
    cek("textarea tetap tersembunyi saat berhasil", d.areaLog.hidden === true);
    cek("tombol memberi umpan balik", d.tombolLog.textContent === "Log tersalin");
    await d.maju(2600);
    cek("tombol kembali", d.tombolLog.textContent === "Salin log Zanite");
    // klik tombol memanggil salin
    d.tombolLog.ls.click(); await d.maju(1);
    cek("klik tombol menyalin", d.papanKlip.length === 2);

    // clipboard gagal: teks tampil di <textarea> supaya bisa dipilih
    const e = buatDunia({ klipGagal: true });
    await e.mulai();
    const ok2 = await e.ctx.Zanite.salinLog();
    cek("clipboard gagal: textarea tampil berisi log, terpilih", ok2 === false && e.areaLog.hidden === false && e.areaLog.value.startsWith("== LOG ZANITE ==") && e.areaLog.terpilih === true);
    cek("tombol menunjuk kotak", e.tombolLog.textContent === "Salin manual dari kotak");

    // log dibatasi 150 baris, terbaru yang dipertahankan
    const f = buatDunia();
    await f.mulai();
    for (let i = 0; i < 400; i++) f.ucap("kata " + i, false, 0);
    const Lf = f.ctx.Zanite.laporan();
    const bagian = Lf.split("== ")[3].split("\n").slice(1);
    cek("maksimal 150 baris", bagian.length <= 150 && f.ctx.Zanite.debug().length <= 150, bagian.length);
    cek("yang terbaru dipertahankan", /kata 399/.test(Lf) && !/ kata 10\b/.test(Lf));
  });

  console.log("alur zanite: " + (total - gagal) + "/" + total + " lulus");
  console.log(gagal ? "GAGAL " + gagal : "semua lulus");
  process.exit(gagal ? 1 : 0);
})();
