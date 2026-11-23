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
    get pending() { return this.antre.length > 0 || !!this.pendingMacet; },
    getVoices: () => [{ lang: "in-ID", name: "Suara Indonesia" }],
    jatuh: 0, macet: null,
    speak(u) {
      if (this.tCancel !== undefined) D.jedaCancelSpeakMin = Math.min(D.jedaCancelSpeakMin === undefined ? Infinity : D.jedaCancelSpeakMin, now - this.tCancel);
      if (this.jatuh > 0) { this.jatuh--; if (this.jatuhPending) this.pendingMacet = true; return; }                 // Chrome HP: speak() sesudah cancel() dibuang diam-diam
      this.antre.push(u); if (!this.sedang) this.lanjut();
    },
    lanjut() {
      const u = this.antre.shift();
      if (!u) { this.sedang = null; this.speaking = false; return; }
      this.sedang = u; this.speaking = true; D.diucap.push(u.text); u.fire("start");
      if (this.macet && u.text === this.macet) return;              // ucapan yang tidak pernah selesai
      this.timer = setT(() => { this.sedang = null; if (!o.tanpaEnd) u.fire("end"); this.lanjut(); }, DURASI_BICARA);
    },
    cancel() {
      this.tCancel = now; this.pendingMacet = false;
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
    document: { visibilityState: undefined, _ls: {}, addEventListener(k, f) { this._ls[k] = f; }, getElementById: (id) => (id === "zanite-status" ? elStatus : id === "salin-log-zanite" ? elTombolLog : id === "teks-log-zanite" ? elAreaLog : null) },
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
    // jendela habis tanpa satu hasil pun: pengenal dimulai ulang SEKALI (lihat tes "pengenal macet")
    cek("jendela kosong: pengenal dimulai ulang sekali", d.SRs.length === 2 && d.SRs[0].aborted === true, d.SRs.length);
    // sesudah itu wake baru bisa lagi (pengenal baru)
    d.ucap("Janit"); await d.maju(800 + 150 + 30);
    cek("wake lagi sesudah jendela tutup", d.diucap.filter((x) => x === BALAS).length === 2, d.diucap);
  });

  // [CHECKPOINT 5] Tes lama "transkrip dibuang saat app bicara dan 500 ms sesudahnya" diganti: aturannya sekarang
  // penyaring gema (buang hanya yang mirip teks ucapan app), bukan membuang semuanya.
  await tes("penyaring gema selama balasan dan ekornya: gema dibuang, suara pengguna diterima", async () => {
    const d = buatDunia();
    await d.mulai();
    d.ucap("Zanite", true);
    await d.maju(150);                               // bip selesai, balasan mulai
    d.ucap("iya ada yang bisa saya bantu");           // gema balasan sendiri: dibuang
    const U = d.ctx.Zanite._uji.hitung;
    cek("gema balasan dibuang, dihitung", U.gemaDibuang === 1 && U.diterimaSaatBicara === 0, [U.gemaDibuang, U.diterimaSaatBicara]);
    d.ucap("Zanite jelaskan sekitar");               // suara pengguna saat balasan: diterima (tetapi wake saat 'balas' diabaikan)
    cek("suara pengguna saat balasan diterima", U.diterimaSaatBicara === 1, U.diterimaSaatBicara);
    await d.maju(DURASI_BICARA - 1);
    cek("selama balasan: tidak jadi perintah (wake ditahan fase balas)", d.zanite().length === 0);
    await d.maju(1);                                 // balasan selesai
    cek("jendela terbuka", d.status.textContent === "Zanite mendengar");
    await d.maju(100);                               // masih dalam ekor 500 ms
    d.ucap("iya ada yang bisa saya bantu", false);   // gema yang telat masih dibuang (ucapan baru selesai < 1,5 dtk)
    cek("gema dalam ekor 500 ms juga dibuang", U.gemaDibuang === 2, U.gemaDibuang);
    d.ucap("itu apa di depan", false);               // suara pengguna dalam ekor: diterima
    cek("suara pengguna dalam ekor diterima", U.diterimaSaatBicara === 2, U.diterimaSaatBicara);
    await d.maju(1190);
    cek("belum dikirim sebelum jeda 1,2 dtk", d.zanite().length === 0);
    await d.maju(20);
    cek("dikirim: teks pengguna saja", d.zanite().length === 1 && JSON.parse(d.zanite()[0].init.body).teks === "itu apa di depan", d.zanite().map((c) => c.init.body));
    cek("mic tidak di-abort", d.tidakPernahAbort());
  });

  await tes("peringatan tingkat 2: gema dibuang, 'Hati-hati, jalur tidak terlihat' diulang tiap 4 dtk tidak menulikan Zanite", async () => {
    const d = buatDunia();
    await d.mulai();
    const U = d.ctx.Zanite._uji.hitung;
    d.jalankan(`ucapkan({ pesan: "Hati-hati, jalur tidak terlihat", tingkat: 2, kelas: "jalur" })`);
    await d.maju(100);
    cek("peringatan diucapkan", d.diucap[0] === "Hati-hati, jalur tidak terlihat" && d.synth.speaking);
    d.ucap("hati hati jalur tidak terlihat");           // gema persis: dibuang
    d.ucap("hati hati jalur", false);                   // gema sebagian (3/3 kata ada di teks): dibuang
    d.ucap("jalur", false);                             // 1 kata yang ada di teks app: dibuang
    cek("tiga gema dibuang", U.gemaDibuang === 3 && U.diterimaSaatBicara === 0, [U.gemaDibuang, U.diterimaSaatBicara]);
    d.ucap("di depan ada apa", false);                  // suara pengguna: diterima
    cek("'di depan ada apa' diterima saat peringatan bicara", U.gemaDibuang === 3 && U.diterimaSaatBicara === 1, [U.gemaDibuang, U.diterimaSaatBicara]);
    cek("dan tampil di log dengan penanda", d.ctx.Zanite.debug().some((x) => /\(app bicara\) di depan ada apa/.test(x)));
    cek("gema dicatat di log dengan teksnya", d.ctx.Zanite.debug().some((x) => /gema dibuang: hati hati jalur tidak terlihat/.test(x)));
    cek("bukan kata bangun: tidak ada bip", d.bips === 0);
    cek("mic tidak di-abort", d.tidakPernahAbort());

    // pesan sistem: gema dibuang, suara pengguna diterima
    const e = buatDunia();
    await e.mulai();
    e.jalankan(`ucapkanSistem("Kamera dijeda.")`);
    await e.maju(100);
    e.ucap("kamera dijeda");
    e.ucap("depan ada apa");
    const V = e.ctx.Zanite._uji.hitung;
    cek("pesan sistem: gema dibuang, pengguna diterima", V.gemaDibuang === 1 && V.diterimaSaatBicara === 1, [V.gemaDibuang, V.diterimaSaatBicara]);
  });

  await tes("kata bangun saat peringatan tingkat 2 berbunyi: peringatan dipotong, Zanite membalas", async () => {
    for (const katanya of ["Janet", "Zanite"]) {
      const d = buatDunia();
      await d.mulai();
      d.jalankan(`ucapkan({ pesan: "Hati-hati, jalur tidak terlihat", tingkat: 2, kelas: "jalur" })`);
      await d.maju(100);
      const c0 = d.cancelPanggil;
      d.ucap(katanya, true);
      await d.maju(10);
      cek(katanya + ": peringatan dipotong (cancel)", d.cancelPanggil === c0 + 1 && d.synth.sedang === null, [d.cancelPanggil, c0]);
      cek(katanya + ": bip menunggu jeda 150 ms sesudah cancel", d.bips === 0, d.bips);
      await d.maju(145);
      cek(katanya + ": bip lalu 'Iya, ...' sebagai ucapan berikutnya", d.bips === 1, d.bips);
      await d.maju(150);
      cek(katanya + ": balasan diucapkan, peringatan tidak diulang", d.diucap.length === 2 && d.diucap[1] === BALAS, d.diucap);
      cek(katanya + ": dihitung 'wake saat app bicara'", d.ctx.Zanite._uji.hitung.wakeSaatBicara === 1, d.ctx.Zanite._uji.hitung.wakeSaatBicara);
      cek(katanya + ": pelacak mencatat cancel", d.ctx.Zanite._uji.statistik().dibatalkan === 1);
    }
  });

  await tes("fokus (hanya selama pengguna bicara): t1/t2 ditahan, t3 tetap berbunyi dan memotong; berakhir saat perintah tertangkap, jendela habis, batal, atau 12 dtk", async () => {
    const pesan2 = `ucapkan({ pesan: "Pilar di kiri, dekat", tingkat: 2, kelas: "pilar" })`;
    const pesan1 = `ucapkan({ pesan: "Kursi di kanan, jauh", tingkat: 1, kelas: "kursi" })`;
    const pesan3 = `ucapkan({ pesan: "Tangga di depan", tingkat: 3, kelas: "tangga" })`;

    // a) fokus mulai di wake; t1/t2 ditahan (tidak diucapkan, tidak dicatat); t3 berbunyi dan memotong
    const d = buatDunia();
    await d.mulai();
    cek("sebelum wake: tidak ada fokus", d.ctx.Zanite.fokus() === false);
    d.ucap("Zanite", true); await d.maju(10);
    cek("sesudah wake: fokus", d.ctx.Zanite.fokus() === true);
    d.jalankan(pesan2); d.jalankan(pesan1);
    cek("t1/t2 saat fokus: tidak diucapkan", d.diucap.every((x) => x !== "Pilar di kiri, dekat" && x !== "Kursi di kanan, jauh"), d.diucap);
    cek("dihitung 'peringatan ditahan saat fokus'", d.ctx.Zanite._uji.hitung.peringatanDitahan === 2, d.ctx.Zanite._uji.hitung.peringatanDitahan);
    await d.maju(150 + 200);                                  // balasan 'Iya...' sedang bicara
    const c0 = d.cancelPanggil;
    d.jalankan(pesan3);
    cek("t3 saat fokus: berbunyi dan memotong Zanite", d.cancelPanggil === c0 + 1 && d.diucap[d.diucap.length - 1] === "Tangga di depan", [d.cancelPanggil, c0, d.diucap]);
    await d.maju(DURASI_BICARA + 150);                        // t3 selesai; jendela dibuka sesudahnya
    cek("fokus masih ada selama jendela terbuka", d.ctx.Zanite.fokus() === true && d.status.textContent === "Zanite mendengar", d.status.textContent);
    // b) jalur keluar 1: jendela habis tanpa perintah -> fokus berakhir; t2 yang sama berbunyi (tidak tercatat sebelumnya)
    await d.maju(6100);
    cek("jendela habis tanpa perintah: fokus berakhir", d.ctx.Zanite.fokus() === false, d.status.textContent);
    const n = d.diucap.length;
    d.jalankan(pesan2);
    cek("sesudah fokus: pesan t2 yang tadi ditahan berbunyi (tidak dicatat sebagai sudah diucapkan)", d.diucap.length === n + 1 && d.diucap[n] === "Pilar di kiri, dekat", d.diucap);

    // c) jalur keluar 2: perintah tertangkap (kirimPerintah mulai) -> fokus berakhir; t2 saat menunggu server berbunyi
    const e = buatDunia({ tundaJawab: 1000 });
    await e.mulai();
    e.ucap("Zanite jelasin sekitar"); await e.maju(699);
    cek("perintah belum tertangkap: masih fokus", e.ctx.Zanite.fokus() === true && e.zanite().length === 0);
    await e.maju(10);
    cek("perintah tertangkap (dikirim): fokus berakhir", e.zanite().length === 1 && e.ctx.Zanite.fokus() === false, e.zanite().length);
    cek("tercatat di log", /fokus selesai: perintah tertangkap/.test(e.ctx.Zanite.debug().join(" | ")));
    await e.maju(390);                                         // t~1100: masih menunggu server
    e.jalankan(pesan2);
    cek("menunggu server: t2 berbunyi lagi seperti biasa", e.diucap.includes("Pilar di kiri, dekat") && e.ctx.Zanite._uji.hitung.peringatanDitahan === 0, e.diucap);
    const cE = e.cancelPanggil;
    await e.maju(650);                                         // t~1750: jawaban sudah tiba saat t2 masih bicara
    cek("jawaban tiba saat t2 bicara: antre di belakang t2, tanpa cancel", e.cancelPanggil === cE && e.synth.sedang.text === "Pilar di kiri, dekat" && e.synth.antre.length === 1 && e.synth.antre[0].text.startsWith("Di kiri"), [e.diucap, e.synth.antre.length]);
    await e.maju(DURASI_BICARA);
    cek("jawaban diucapkan sesudah t2 selesai", e.diucap[e.diucap.length - 1].startsWith("Di kiri ada pilar"), e.diucap);
    e.jalankan(pesan1);
    cek("t1 tidak memotong jawaban yang sedang berbunyi", !e.diucap.includes("Kursi di kanan, jauh") && e.cancelPanggil === cE, e.diucap);

    // d) jawaban dibuang (kamera dijeda): fokus sudah berakhir sejak perintah tertangkap
    const f = buatDunia({ tundaJawab: 2000 });
    await f.mulai();
    f.ucap("Zanite jelasin sekitar"); await f.maju(700 + 100);
    cek("fokus sudah berakhir saat menunggu", f.ctx.Zanite.fokus() === false);
    f.jalankan("generasi += 1");
    await f.maju(2500);
    cek("jawaban dibuang: tidak diucapkan, fokus tetap berakhir", f.ctx.Zanite.fokus() === false && f.diucap.length === 0, f.diucap);

    // e) gagal jaringan: fokus sudah berakhir saat kirim
    const g = buatDunia({ galatJaringan: true });
    await g.mulai();
    g.ucap("Zanite jelasin sekitar"); await g.maju(700 + 10);
    cek("saat kirim: fokus berakhir", g.ctx.Zanite.fokus() === false);
    await g.maju(200);
    cek("gagal jaringan: pesan diucapkan", g.diucap[0] === PESAN_JARINGAN);

    // f) jalur keluar 5: Bisu dan Berhenti
    const h = buatDunia();
    await h.mulai();
    h.ucap("Zanite", true); await h.maju(10);
    cek("fokus ada", h.ctx.Zanite.fokus() === true);
    h.jalankan("setBisu(true)"); await h.maju(10);
    cek("Bisu: fokus berakhir", h.ctx.Zanite.fokus() === false);

    // g) batas keras 12 dtk: pengguna mulai bicara terlambat dan terus bicara (perintah belum tertangkap)
    const k = buatDunia({ tundaJawab: 30000 });
    await k.mulai();
    k.ucap("Zanite", true); await k.maju(10 + 150 + DURASI_BICARA + 100);   // jendela terbuka (~1,1 dtk)
    await k.maju(5000);                                                       // diam hampir 6 dtk
    const idx = k.ucap("apa", false);
    let kata = 0;
    const bicaraSampai = async (batas) => { while (k.waktu() + 500 < batas) { await k.maju(500); k.ucap("apa " + "itu ".repeat(++kata), false, idx); } };
    await bicaraSampai(10000);
    cek("sebelum batas: fokus masih ada, t2 ditahan", k.ctx.Zanite.fokus() === true && k.waktu() < 12000 && k.zanite().length === 0, k.waktu());
    k.jalankan(pesan2);
    cek("t2 ditahan", !k.diucap.includes("Pilar di kiri, dekat"));
    await bicaraSampai(11900); await k.maju(12000 - k.waktu() - 1); k.ucap("apa " + "itu ".repeat(++kata), false, idx);
    cek("11,999 dtk sejak wake: masih fokus", k.ctx.Zanite.fokus() === true && k.zanite().length === 0, k.waktu());
    await k.maju(60);
    cek("batas 12 dtk: fokus berakhir walau perintah belum tertangkap", k.ctx.Zanite.fokus() === false && /fokus selesai: batas 12 dtk/.test(k.ctx.Zanite.debug().join(" | ")), k.ctx.Zanite.debug().slice(-4));
    const n2 = k.diucap.length;
    k.jalankan(pesan1);
    cek("sesudah batas: t1 berbunyi lagi", k.diucap.length === n2 + 1 && k.diucap[n2] === "Kursi di kanan, jauh", k.diucap);
  });

  await tes("kata bangun saat peringatan tingkat 3 berbunyi: tidak dipotong, balasan menunggu", async () => {
    const d = buatDunia();
    await d.mulai();
    d.jalankan(`ucapkan({ pesan: "Tangga di depan", tingkat: 3, kelas: "tangga" })`);
    await d.maju(100);
    const c0 = d.cancelPanggil;
    d.ucap("Zanite", true); await d.maju(50);
    cek("t3 tidak dipotong oleh kata bangun", d.cancelPanggil === c0 && d.synth.sedang && d.synth.sedang.text === "Tangga di depan", [d.cancelPanggil, c0]);
    cek("bip belum berbunyi selama t3 bicara", d.bips === 0, d.bips);
    cek("fokus sudah aktif", d.ctx.Zanite.fokus() === true);
    await d.maju(DURASI_BICARA);                             // t3 selesai (800 ms sejak mulai) + polling 100 ms
    await d.maju(250);
    cek("sesudah t3 selesai: bip dan balasan", d.bips === 1 && d.diucap[d.diucap.length - 1] === BALAS, [d.bips, d.diucap]);
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
    cek("speaking macet true tanpa catatan: wake tetap menyala", a.bips === 1 && a.ctx.Zanite._uji.hitung.gemaDibuang === 0, [a.bips, a.ctx.Zanite._uji.hitung.gemaDibuang]);

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

    // 3) selama ucapan benar-benar berbunyi: gema dibuang (tidak menyalakan apa-apa), suara pengguna diterima
    const c = buatDunia({ tanpaEnd: true });
    await c.mulai();
    c.jalankan(`ucapkan({ pesan: "Pilar di kiri, dekat", tingkat: 2, kelas: "pilar" })`);
    await c.maju(400);
    c.ucap("pilar di kiri dekat", true); await c.maju(2000);
    cek("selama sintesis berbunyi: gema dibuang", c.bips === 0 && c.ctx.Zanite._uji.hitung.gemaDibuang === 1, [c.bips, c.ctx.Zanite._uji.hitung.gemaDibuang]);

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
    d.ucap("tangga di depan", true); await d.maju(50);                // saat ucapan tingkat 3 masih bicara (600 < 800): gema dibuang
    cek("ucapan tingkat 3 (catatan sendiri): gema dibuangnya tetap berlaku", d.bips === bip0 && d.ctx.Zanite._uji.hitung.gemaDibuang === 1, [d.bips, bip0]);
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

  await tes("speak() dibuang Chrome sesudah cancel: diulang SEKALI lalu mulai; dibuang dua kali: menyerah, alur ditutup, mic tetap mendengar", async () => {
    const lifecycle = (d) => d.ctx.Zanite.debug().filter((x) => /(balas|jawab):/.test(x)).map((x) => x.replace(/^\S+ \+\d+ms /, ""));
    // 1) dibuang sekali -> diulang sekali dan berbunyi
    const d = buatDunia();
    await d.mulai();
    d.jalankan(`ucapkan({ pesan: "Hati-hati, jalur tidak terlihat", tingkat: 2, kelas: "jalur" })`);
    await d.maju(100);
    d.synth.jatuh = 1;                                        // speak() berikutnya (balasan) dibuang diam-diam
    d.ucap("Zanite", true);
    await d.maju(10 + 150 + 150);                             // cancel, jeda 150, bip 150, balasan di-speak (dibuang)
    cek("balasan dibuang: tidak ada suara dan tidak ada event", d.diucap.length === 1 && d.synth.sedang === null, d.diucap);
    cek("belum diulang sebelum 1,5 dtk", !lifecycle(d).some((x) => /ulang/.test(x)), lifecycle(d));
    await d.maju(1500);
    cek("tanpa start 1,5 dtk: dicatat 'ulang (tanpa start)'", lifecycle(d).some((x) => /^balas: ulang \(tanpa start\) \d+ ms$/.test(x)), lifecycle(d));
    await d.maju(200);
    cek("balasan terdengar sesudah diulang", d.diucap.filter((x) => x === BALAS).length === 1 && d.synth.sedang && d.synth.sedang.text === BALAS, d.diucap);
    cek("jeda >= 150 ms antara cancel() dan setiap speak() sesudahnya", d.jedaCancelSpeakMin >= 150, d.jedaCancelSpeakMin);
    await d.maju(DURASI_BICARA + 50);
    const L = lifecycle(d).map((x) => x.replace(/ \d+ ms$/, "").replace(/ \(tanpa start\)/, ""));
    cek("siklus hidup tercatat berurutan: speak, ulang, speak (ulang), start, end", JSON.stringify(L) === JSON.stringify(["balas: speak", "balas: ulang", "balas: speak (ulang)", "balas: start", "balas: end"]), L);
    cek("alur lanjut: jendela terbuka", d.status.textContent === "Zanite mendengar", d.status.textContent);
    cek("pelacak tidak menunggu pengaman", d.waktu() < 6000, d.waktu());

    // 2) dibuang dua kali -> menyerah: fokus berakhir, alur ditutup, mic tetap mendengar
    const e = buatDunia();
    await e.mulai();
    e.synth.jatuh = 2;
    e.ucap("Zanite", true);
    await e.maju(10 + 150 + 150);
    cek("fokus aktif saat menunggu balasan", e.ctx.Zanite.fokus() === true);
    await e.maju(1500 + 150 + 1500 + 100);                    // percobaan 1 gagal, percobaan 2 gagal
    const Le = lifecycle(e);
    cek("dicatat: ulang lalu gagal", Le.some((x) => /ulang \(tanpa start\)/.test(x)) && Le.some((x) => /^balas: gagal \d+ ms$/.test(x)), Le);
    cek("tidak ada balasan terdengar", e.diucap.length === 0, e.diucap);
    cek("fokus berakhir", e.ctx.Zanite.fokus() === false);
    cek("alur ditutup: status kembali 'Zanite aktif', tidak ada jendela", e.status.textContent === "Zanite aktif" && e.ctx.Zanite.keadaan().fase === "diam", [e.status.textContent, e.ctx.Zanite.keadaan()]);
    cek("dicatat di log Zanite", e.ctx.Zanite.debug().some((x) => /balas: gagal, alur ditutup, mic tetap mendengar/.test(x)));
    cek("mic tidak di-abort dan tetap hanya satu pengenal", e.tidakPernahAbort() && e.SRs.length === 1);
    e.synth.jatuh = 0;
    e.ucap("Janit", true); await e.maju(10 + 150 + 150 + 100);
    cek("wake berikutnya berhasil membalas", e.diucap.length === 1 && e.diucap[0] === BALAS, e.diucap);

    // 2b) dibuang tetapi speechSynthesis.pending macet true: pelacak tidak bisa memaksa selesai, hanya pengawas yang menangkap
    const m = buatDunia();
    await m.mulai();
    m.synth.jatuh = 1; m.synth.jatuhPending = true;
    m.ucap("Zanite", true);
    await m.maju(10 + 150 + 150 + 1500 + 300);
    cek("pending macet: pengawas mengulang (bukan pelacak)", lifecycle(m).some((x) => /ulang \(tanpa start\)/.test(x)) && m.diucap.includes(BALAS) && m.ctx.Zanite._uji.statistik().paksa === 0, [lifecycle(m), m.ctx.Zanite._uji.statistik()]);

    // 3) jawaban (bukan balasan) yang dibuang sekali: juga diulang sekali
    const g = buatDunia({ tundaJawab: 100 });
    await g.mulai();
    g.synth.jatuh = 1;
    g.ucap("Zanite jelasin sekitar"); await g.maju(700 + 100 + 1500 + 150 + 200);
    cek("jawaban dibuang sekali: diulang dan terdengar", g.diucap.length === 1 && g.diucap[0].startsWith("Di kiri"), g.diucap);
    cek("siklus hidup 'jawab:' tercatat", g.ctx.Zanite.debug().some((x) => /jawab: ulang \(tanpa start\)/.test(x)) && g.ctx.Zanite.debug().some((x) => /jawab: speak \(ulang\)/.test(x)));
  });

  await tes("balasan menunggu t3 yang tidak pernah selesai: paling lama 4 dtk, lalu dipotong dan membalas", async () => {
    const d = buatDunia();
    await d.mulai();
    d.synth.macet = "Tangga di depan";                        // t3 ini tidak pernah selesai, tidak ada end
    d.jalankan(`ucapkan({ pesan: "Tangga di depan", tingkat: 3, kelas: "tangga" })`);
    await d.maju(2000);
    cek("t3 macet: speaking tetap true", d.synth.speaking === true && d.synth.sedang && d.synth.sedang.text === "Tangga di depan");
    const c0 = d.cancelPanggil;
    d.ucap("Zanite", true); await d.maju(10);
    cek("wake: t3 tidak dipotong, tercatat 'menunggu t3'", d.cancelPanggil === c0 && d.ctx.Zanite.debug().some((x) => /balas: menunggu t3/.test(x)), d.ctx.Zanite.debug().slice(-3));
    await d.maju(3500);                                       // 3,5 dtk sesudah wake
    cek("3,5 dtk: masih menunggu (belum bip, belum balasan)", d.bips === 0 && !d.diucap.includes(BALAS), [d.bips, d.diucap]);
    await d.maju(1000);                                       // lewat 4 dtk + jeda cancel 150 + bip 150
    cek("sesudah 4 dtk: t3 macet dipotong (cancel)", d.cancelPanggil === c0 + 1 && d.ctx.Zanite.debug().some((x) => /tidak selesai dalam 4 dtk/.test(x)), [d.cancelPanggil, c0]);
    cek("balasan diucapkan sesudah itu (bukan menunggu pengaman 15+ dtk)", d.diucap.includes(BALAS) && d.waktu() < 8000, [d.diucap, d.waktu()]);
    d.synth.macet = null;
    await d.maju(DURASI_BICARA + 50);
    cek("jendela terbuka sesudah balasan", d.status.textContent === "Zanite mendengar", d.status.textContent);
    cek("mic tidak di-abort", d.tidakPernahAbort());
  });

  await tes("alasan di log HP: jenis, alasan, waktu round-trip, hitungan per jenis; tanpa teks jawaban", async () => {
    const d = buatDunia({ tundaJawab: 1234, badanJawab: { jawaban: "TEKSRAHASIAJAWABAN di kiri", jenis: "cadangan", alasan: "waktu-habis" } });
    await d.mulai();
    d.ucap("Zanite jelasin sekitar"); await d.maju(700 + 1300);
    const log = d.ctx.Zanite.debug().join(" | ");
    cek("baris 'jawaban:' memuat jenis, alasan, ms", /jawaban: jenis=cadangan alasan=waktu-habis 12\d\d ms/.test(log), d.ctx.Zanite.debug().filter((x) => /jawaban:/.test(x)));
    const L = d.ctx.Zanite.laporan();
    cek("hitungan 'alasan cadangan per jenis'", /alasan cadangan per jenis: cadangan:waktu-habis=1/.test(L), L.split("\n").filter((x) => /alasan/.test(x)));
    cek("teks jawaban tidak ikut di log/laporan", !log.includes("TEKSRAHASIAJAWABAN") && !L.includes("TEKSRAHASIAJAWABAN"));
    // jawaban normal: alasan null -> '-', tidak masuk hitungan
    const e = buatDunia({ tundaJawab: 500, badanJawab: { jawaban: "Di kiri ada pilar, sedang.", jenis: "jawaban", alasan: null } });
    await e.mulai(); e.ucap("Zanite jelasin sekitar"); await e.maju(700 + 600);
    cek("jawaban normal: alasan=-", /jawaban: jenis=jawaban alasan=- 5\d\d ms/.test(e.ctx.Zanite.debug().join(" | ")), e.ctx.Zanite.debug().slice(-4));
    cek("jawaban normal: tidak masuk hitungan alasan", /alasan cadangan per jenis: -/.test(e.ctx.Zanite.laporan()));
    // alasan aneh dari server (bukan kode) diganti, tidak disalin ke log
    const f = buatDunia({ tundaJawab: 100, badanJawab: { jawaban: "x", jenis: "cadangan", alasan: "ini pesan galat dengan spasi <b>" } });
    await f.mulai(); f.ucap("Zanite jelasin sekitar"); await f.maju(700 + 200);
    cek("alasan bukan kode: diganti '?'", /alasan=\? /.test(f.ctx.Zanite.debug().join(" | ")) && !f.ctx.Zanite.debug().join(" | ").includes("pesan galat"));
    // kegagalan sisi HP
    const g = buatDunia({ galatJaringan: true });
    await g.mulai(); g.ucap("Zanite jelasin sekitar"); await g.maju(700 + 200);
    cek("fetch gagal: jenis=jaringan alasan=galat-fetch", /jawaban: jenis=jaringan alasan=galat-fetch \d+ ms/.test(g.ctx.Zanite.debug().join(" | ")), g.ctx.Zanite.debug().slice(-3));
    const h = buatDunia({ kodeJawab: 502, tanpaJson: true });
    await h.mulai(); h.ucap("Zanite jelasin sekitar"); await h.maju(700 + 1100);
    cek("tanpa JSON: alasan=tanpa-json-http-502", /alasan=tanpa-json-http-502/.test(h.ctx.Zanite.debug().join(" | ")), h.ctx.Zanite.debug().slice(-3));
    const i = buatDunia({ tundaJawab: 12000 });
    await i.mulai(); i.ucap("Zanite jelasin sekitar"); await i.maju(700 + 10500);
    cek("klien menyerah: alasan=waktu-klien", /alasan=waktu-klien 10\d\d\d ms/.test(i.ctx.Zanite.debug().join(" | ")), i.ctx.Zanite.debug().slice(-3));
  });

  await tes("'peringatan ditahan saat fokus': dihitung tiap kali, baris log hanya sekali per pesan per fokus", async () => {
    const d = buatDunia();
    await d.mulai();
    d.ucap("Zanite", true); await d.maju(10);
    const pesanA = `ucapkan({ pesan: "Hati-hati, jalur tidak terlihat", tingkat: 2, kelas: "jalur" })`;
    const pesanB = `ucapkan({ pesan: "Kursi di kanan, jauh", tingkat: 1, kelas: "kursi" })`;
    for (let i = 0; i < 6; i++) d.jalankan(pesanA);           // tiap frame: diulang
    d.jalankan(pesanB); d.jalankan(pesanB);
    const ditahan = () => d.ctx.Zanite.debug().filter((x) => /peringatan ditahan saat fokus: /.test(x));
    cek("hitungan: tiap peringatan dihitung (8)", d.ctx.Zanite._uji.hitung.peringatanDitahan === 8, d.ctx.Zanite._uji.hitung.peringatanDitahan);
    cek("baris log: hanya satu per pesan (2 baris)", ditahan().length === 2 && ditahan().some((x) => /jalur tidak terlihat/.test(x)) && ditahan().some((x) => /Kursi di kanan/.test(x)), ditahan());
    cek("laporan memuat hitungan 8", /peringatan ditahan saat fokus: 8/.test(d.ctx.Zanite.laporan()));
    // fokus baru: dicatat lagi sekali
    await d.maju(13000);
    cek("fokus lama sudah berakhir", d.ctx.Zanite.fokus() === false);
    d.ucap("Janit", true); await d.maju(10);
    d.jalankan(pesanB); d.jalankan(pesanB);
    cek("fokus baru: pesan yang sama dicatat lagi, sekali", ditahan().filter((x) => /Kursi di kanan/.test(x)).length === 2, ditahan());
  });

  await tes("pengenal macet (hidup tetapi tuli): jendela habis tanpa satu hasil pun -> mulai ulang sekali; 60 dtk tanpa hasil -> mulai ulang", async () => {
    const ulangAlasan = (d) => d.ctx.Zanite._uji.hitung.restartAlasan;
    // (a) jendela habis tanpa hasil: abort + start sekali; pengenal baru dipakai sesudahnya
    const a = buatDunia();
    await a.mulai();
    a.ucap("Zanite", true);
    await a.maju(150 + DURASI_BICARA + 100);
    cek("jendela terbuka, belum ada restart", a.status.textContent === "Zanite mendengar" && a.SRs.length === 1 && a.SRs[0].aborted === false);
    await a.maju(6100);
    cek("jendela habis tanpa hasil: pengenal lama di-abort, baru dibuat dan dimulai", a.SRs[0].aborted === true && a.SRs.length === 2 && a.sr().started, [a.SRs.length, a.SRs[0].aborted]);
    cek("tercatat: restart: jendela-kosong, dihitung per alasan", a.ctx.Zanite.debug().some((x) => /restart: jendela-kosong/.test(x)) && ulangAlasan(a)["jendela-kosong"] === 1, ulangAlasan(a));
    cek("restart hanya sekali", a.SRs.length === 2);
    await a.maju(3000);
    cek("tidak restart lagi sesudahnya", a.SRs.length === 2 && ulangAlasan(a)["jendela-kosong"] === 1);
    a.ucap("Janit", true); await a.maju(10 + 150 + 150 + 50);
    cek("pengenal baru bekerja: wake berikutnya membalas", a.diucap.filter((x) => x === BALAS).length === 2, a.diucap);
    cek("laporan memuat restart per alasan", /restart pengenal karena macet, per alasan: jendela-kosong=1/.test(a.ctx.Zanite.laporan()));

    // (a2) jendela yang ADA hasilnya (perintah diucapkan) tidak memicu restart; begitu pula pengguna yang bicara tetapi bukan perintah
    const b = buatDunia();
    await b.mulai();
    b.ucap("Zanite", true); await b.maju(150 + DURASI_BICARA + 600);
    b.ucap("itu apa di depan"); await b.maju(1300 + 1100 + DURASI_BICARA);
    cek("jendela berisi perintah: tidak restart", b.SRs.length === 1 && b.tidakPernahAbort() && Object.keys(ulangAlasan(b)).length === 0, [b.SRs.length, ulangAlasan(b)]);
    const c = buatDunia();
    await c.mulai();
    c.ucap("Zanite", true); await c.maju(150 + DURASI_BICARA + 600);
    c.ucap("hmm", false); await c.maju(7000);                // ada hasil (walau bukan perintah penuh): bukan tuli
    cek("jendela dengan hasil apa pun: tidak restart", c.SRs.length === 1 && Object.keys(ulangAlasan(c)).length === 0, [c.SRs.length, ulangAlasan(c)]);

    // (a3) jendela habis tanpa perintah, tetapi pengenal MENDENGAR (gema balasan sendiri dalam ekor 500 ms): bukan tuli
    const c3 = buatDunia();
    await c3.mulai();
    c3.ucap("Zanite", true); await c3.maju(150 + DURASI_BICARA + 100);
    c3.ucap("iya ada yang bisa saya bantu", false);          // terdengar dalam ekor: dibuang sebagai gema, tetapi tetap hasil
    cek("gema itu dibuang, tidak jadi perintah", c3.ctx.Zanite._uji.hitung.gemaDibuang === 1 && c3.zanite().length === 0);
    await c3.maju(6100);
    cek("jendela habis dengan hasil (gema) di dalamnya: pengenal sehat, tidak restart", c3.SRs.length === 1 && c3.tidakPernahAbort() && Object.keys(ulangAlasan(c3)).length === 0, [c3.SRs.length, ulangAlasan(c3)]);

    // (b) 60 dtk tanpa hasil sama sekali, halaman tampak: mulai ulang sekali
    const d = buatDunia();
    await d.mulai();
    await d.maju(59000);
    cek("59 dtk tanpa hasil: belum restart", d.SRs.length === 1 && d.tidakPernahAbort(), d.SRs.length);
    await d.maju(7000);                                       // pemeriksa berjalan tiap 5 dtk
    cek("sesudah 60 dtk tanpa hasil: restart: macet", d.SRs.length === 2 && d.SRs[0].aborted && ulangAlasan(d).macet === 1 && d.ctx.Zanite.debug().some((x) => /restart: macet/.test(x)), [d.SRs.length, ulangAlasan(d)]);
    await d.maju(30000);
    cek("30 dtk kemudian: belum restart lagi (jam diulang dari nol)", d.SRs.length === 2 && ulangAlasan(d).macet === 1, [d.SRs.length, ulangAlasan(d)]);
    await d.maju(40000);
    cek("60 dtk sesudah restart tanpa hasil: restart lagi, dihitung 2", d.SRs.length === 3 && ulangAlasan(d).macet === 2, [d.SRs.length, ulangAlasan(d)]);

    // (b2) masa sepi NORMAL yang berisi hasil: tidak restart
    const e = buatDunia();
    await e.mulai();
    for (let i = 0; i < 12; i++) { await e.maju(20000); e.ucap("ngomong sama teman " + i, true); }       // hasil tiap 20 dtk, 4 menit
    cek("hasil tiap 20 dtk selama 4 menit: tidak pernah restart", e.SRs.length === 1 && e.tidakPernahAbort() && Object.keys(ulangAlasan(e)).length === 0, [e.SRs.length, ulangAlasan(e)]);
    // pengenal yang berakhir/dimulai ulang secara normal (Chrome HP) mereset jam: tanpa hasil pun tidak dianggap macet
    const f = buatDunia();
    await f.mulai();
    for (let i = 0; i < 8; i++) { await f.maju(20000); f.sr().onend(); await f.maju(300); }               // mulai ulang normal tiap 20 dtk
    cek("pengenal yang hidup-mati normal tanpa hasil: bukan macet", Object.keys(ulangAlasan(f)).length === 0 && f.SRs.length === 9, [f.SRs.length, ulangAlasan(f)]);

    // (b3) halaman tersembunyi: tidak restart; Bisu dan fatal: tidak restart
    const g = buatDunia();
    await g.mulai();
    g.ctx.document.visibilityState = "hidden";
    await g.maju(120000);
    cek("halaman tersembunyi 2 menit: tidak restart", g.SRs.length === 1 && g.tidakPernahAbort() && Object.keys(ulangAlasan(g)).length === 0, [g.SRs.length, ulangAlasan(g)]);
    const h = buatDunia();
    await h.mulai();
    h.jalankan("setBisu(true)"); await h.maju(120000);
    cek("Bisu: tidak restart sendiri", h.SRs.length === 1 && Object.keys(ulangAlasan(h)).length === 0, [h.SRs.length, ulangAlasan(h)]);
  });

  await tes("peristiwa pengenal, denyut 15 dtk, dan pemanggil mulai/berhenti tercatat di log", async () => {
    const d = buatDunia();
    await d.mulai();
    const r = d.sr();
    for (const n of ["start", "audiostart", "soundstart", "speechstart", "speechend", "soundend", "audioend"]) r["on" + n] && r["on" + n]({});
    r.onend();
    const log = d.ctx.Zanite.debug().join(" | ");
    for (const n of ["start", "audiostart", "soundstart", "speechstart", "speechend", "soundend", "audioend", "end"])
      cek("peristiwa dicatat: " + n, new RegExp("pengenal: " + n + "( |$)").test(d.ctx.Zanite.debug().map((x) => x.replace(/^\S+ \+\d+ms /, "")).join("\n").replace(/\n/g, " ") + " ") || log.includes("pengenal: " + n), n);
    cek("peristiwa dicatat dengan cap waktu", d.ctx.Zanite.debug().some((x) => /^\d\d:\d\d:\d\d\.\d{3} \+\d+ms pengenal: speechstart$/.test(x)));
    r.onerror({ error: "no-speech" });
    cek("error dicatat dengan waktu", d.ctx.Zanite.debug().some((x) => /^\S+ \+\d+ms ERROR no-speech$/.test(x)));
    // denyut tiap 15 dtk
    const e = buatDunia();
    await e.mulai();
    e.sr().onaudiostart && e.sr().onaudiostart({});
    await e.maju(31000);
    const denyut = e.ctx.Zanite.debug().filter((x) => /pengenal: hasil terakhir/.test(x));
    cek("denyut tiap 15 dtk (2 baris dalam 31 dtk)", denyut.length >= 2 && denyut.length <= 3, denyut);
    cek("isi denyut: hasil terakhir, audio, visible, hidup, rec", /hasil terakhir belum ada, audio=off, visible=\?, hidup=true, rec=ada/.test(denyut[0]) && /hasil terakhir belum ada, audio=on, visible=\?, hidup=true, rec=ada/.test(denyut[1]), denyut);
    e.ucap("halo teman", true); await e.maju(16000);
    const d2 = e.ctx.Zanite.debug().filter((x) => /pengenal: hasil terakhir/.test(x)).pop();
    cek("denyut sesudah ada hasil: 'X s lalu'", /hasil terakhir (1[4-6]) s lalu/.test(d2), d2);
    e.ctx.document.visibilityState = "hidden"; await e.maju(16000);
    cek("denyut mencatat visible=hidden", /visible=hidden/.test(e.ctx.Zanite.debug().filter((x) => /pengenal: hasil terakhir/.test(x)).pop()));
    e.ctx.Zanite.berhenti("uji"); const n = e.ctx.Zanite.debug().filter((x) => /pengenal: hasil terakhir/.test(x)).length;
    await e.maju(60000);
    cek("sesudah Berhenti: denyut berhenti", e.ctx.Zanite.debug().filter((x) => /pengenal: hasil terakhir/.test(x)).length === n);

    // halaman tersembunyi/tampil tercatat
    const v = buatDunia();
    await v.mulai();
    v.ctx.document.visibilityState = "hidden"; v.ctx.document._ls.visibilitychange();
    v.ctx.document.visibilityState = "visible"; v.ctx.document._ls.visibilitychange();
    cek("visibilitychange tercatat di log", v.ctx.Zanite.debug().filter((x) => /halaman: (hidden|visible)$/.test(x)).length === 2);

    // pemanggil
    const f = buatDunia();
    f.ctx.Zanite.mulai("mulaiKamera"); await f.maju(10);
    f.ctx.Zanite.berhenti("jedaOtomatis");
    f.ctx.Zanite.mulai("lanjutOtomatis"); await f.maju(10);
    f.jalankan("setBisu(true)");
    f.ctx.Zanite.berhenti("berhentiKamera (Berhenti)");
    const lf = f.ctx.Zanite.debug().map((x) => x.replace(/^\S+ \+\d+ms /, ""));
    cek("pemanggil mulai/berhenti dan Bisu tercatat berurutan", ["mulai() oleh mulaiKamera", "berhenti() oleh jedaOtomatis", "mulai() oleh lanjutOtomatis", "bisuBerubah(true)", "berhenti() oleh berhentiKamera (Berhenti)"].every((k, i) => lf.filter((x) => x.startsWith(k.split(" oleh")[0]) && x.includes(k.includes(" oleh") ? k.split(" oleh ")[1] : "")).length >= 1), lf);
  });

  await tes("'gema dibuang lalu kalimat yang sama diterima': dihitung per hasil", async () => {
    const d = buatDunia();
    await d.mulai();
    const U = d.ctx.Zanite._uji.hitung;
    d.jalankan(`ucapkan({ pesan: "Pilar di depan, dekat", tingkat: 2, kelas: "pilar" })`);
    await d.maju(100);
    const idx = d.ucap("di", false);                          // 1 kata ada di teks app: dibuang
    d.ucap("di depan", false, idx);                           // 100% kata ada di teks app: dibuang
    d.ucap("di depan ada", false, idx);                       // 2 dari 3 kata (67%): dibuang
    cek("tiga potongan dibuang sebagai gema", U.gemaDibuang === 3 && U.gemaLaluDiterima === 0, [U.gemaDibuang, U.gemaLaluDiterima]);
    d.ucap("di depan ada apa", true, idx);                    // 2 dari 4 (50%): diterima, hasil yang sama
    cek("kalimat final yang sama diterima: dihitung sekali", U.gemaLaluDiterima === 1 && U.diterimaSaatBicara === 1, [U.gemaLaluDiterima, U.diterimaSaatBicara]);
    cek("tercatat di log", d.ctx.Zanite.debug().some((x) => /gema dibuang lalu kalimat yang sama diterima: di depan ada apa/.test(x)));
    d.ucap("di depan ada apa lagi", true, idx);
    cek("tidak dihitung dua kali untuk hasil yang sama", U.gemaLaluDiterima === 1, U.gemaLaluDiterima);
    // hasil lain (kunci lain) yang diterima tanpa pernah dibuang: tidak dihitung
    d.ucap("depan ada apa", false);
    cek("hasil lain tanpa gema sebelumnya: tidak dihitung", U.gemaLaluDiterima === 1, U.gemaLaluDiterima);
    cek("laporan memuat hitungan", /gema dibuang lalu kalimat yang sama diterima: 1/.test(d.ctx.Zanite.laporan()));
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
    cek("header: versi, userAgent, suara + bahasa, TAIL/DIAM/LEMAH", /versi: zanite-app-4/.test(L) && /userAgent: UA-uji/.test(L) && /suara: Suara Indonesia \(in-ID\)/.test(L) && /TAIL_MS: 500/.test(L) && /DIAM_MS: 800/.test(L) && /LEMAH_MS: 1200/.test(L), L.slice(0, 400));
    cek("hitungan: wake per tipe", /wake per tipe: .*=\d/.test(L), L);
    for (const k of ["gema dibuang", "transkrip diterima saat app bicara", "wake saat app bicara", "peringatan ditahan saat fokus", "selesai-paksa", "pengenal restart", "galat pengenal per jenis", "permintaan terkirim: 1", "jawaban per jenis: jawaban=1", "jawaban usang dibuang: 0", "bip gagal: 0"])
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
    cek("maksimal 300 baris", bagian.length <= 300 && f.ctx.Zanite.debug().length <= 300, bagian.length);
    cek("yang terbaru dipertahankan", /kata 399/.test(Lf) && !/ kata 10\b/.test(Lf));
  });

  console.log("alur zanite: " + (total - gagal) + "/" + total + " lulus");
  console.log(gagal ? "GAGAL " + gagal : "semua lulus");
  process.exit(gagal ? 1 : 0);
})();
