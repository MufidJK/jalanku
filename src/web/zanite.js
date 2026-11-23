// Zanite di HP: pengenal suara selalu hidup, kata bangun "Zanite", jendela perintah, kirim ke server, ucapkan jawaban.
// Aturan keputusan murni ada di zanite-aturan.js; pencocok kata bangun di zanite-cocok.js (salinan spike).
//
// Aturan utama: mic TIDAK PERNAH dimatikan agar tidak mendengar suara app sendiri (setiap buka ulang,
// Android membunyikan suara Asisten Google). Sebagai gantinya transkrip yang datang saat app bicara dan
// 500 ms sesudahnya dibuang. Berlaku untuk semua ucapan app: peringatan, pesan sistem, jawaban Zanite.
//
// Tanpa SpeechRecognition, atau /api/status bilang zanite:false -> berkas ini tidak melakukan apa-apa.
(function (root) {
  "use strict";
  const ZC = root.ZaniteCocok;
  const ZA = root.ZaniteAturan;
  const SR = root.SpeechRecognition || root.webkitSpeechRecognition;

  const BALAS = "Iya, ada yang bisa saya bantu?";
  const PESAN_JARINGAN = "Zanite butuh internet atau server sedang bermasalah.";
  const PESAN_KAMERA = "Maaf, kamera belum siap.";
  const PESAN_IZIN = "Izin mikrofon ditolak, Zanite mati.";
  const JENDELA_MS = 6000;          // jendela perintah, dihitung dari akhir balasan
  const WAKTU_PERMINTAAN_MS = 10000; // batas klien; jawaban lebih lama dari ini dibuang
  const DIAM_MS = 800;              // kata bangun sendirian: nyala setelah sekian ms tanpa kata baru
  const JEDA_UCAPAN_MS = 1500;      // transkrip baru setelah sekian ms sepi = ucapan baru
  const LEMAH_MS = 1200;            // varian lemah (jani, dani, ...): final atau interim stabil sekian ms
  const TAIL_MS = 500;              // masih "app bicara" sekian ms setelah ucapan selesai
  const CATATAN_MAKS = 150;
  const PANTAU_MS = 250;            // pemantau sintesis: seberapa sering speaking/pending diperiksa
  const VERSI = "zanite-app-1";

  const daftar = ZC.parseDaftar(ZC.DAFTAR_AWAL);
  const sendiriSaja = ZC.parseDaftar(ZC.SENDIRI_SAJA_AWAL);
  const cfg = () => ({ daftar, sendiriSaja, fuzzy: true });
  const jam = () => root.performance.now();
  const pelacak = ZA.buatPelacakBicara(jam, TAIL_MS, { catat: (t) => debug(t) });

  // ---- state
  let hidup = false;          // pengenal harus hidup (kamera jalan dan Zanite tersedia)
  let memeriksa = false;      // sedang menunggu /api/status
  let tokenMulai = 0;
  let fatal = false;          // izin ditolak dll: tidak mencoba lagi
  let jedaPengenal = false;   // Bisu: sengaja tidak mendengar
  let izinDiucap = false;
  let rec = null, restartTimer = null, errBeruntun = 0, lastErr = null, sid = 0;
  let P = null, tickTimer = null;
  let fase = "diam";          // diam | balas | jendela | proses
  let siklus = 0;             // naik tiap alur dibatalkan; callback lama membandingkan
  let jendela = null, jendelaTimer = null;
  let permintaanId = 0;
  let actx = null;
  const catatan = new Map();  // kunci hasil Chrome -> { teks, final, tPertama, tAkhir }
  const log = [];
  // Hitungan untuk "Salin log Zanite". Hanya angka; teks ucapan/jawaban tidak masuk sini.
  const hitung = { wake: {}, dibuangSaatBicara: 0, restartPengenal: 0, galatPengenal: {}, permintaan: 0, jawaban: {}, jawabanUsang: 0, bipGagal: 0 };
  const tambah = (obj, k) => { obj[k] = (obj[k] || 0) + 1; };

  function debug(teks) {
    let jamDinding = "";
    try { jamDinding = new Date().toISOString().slice(11, 23) + " "; } catch (e) { /* abaikan */ }
    log.push(jamDinding + "+" + Math.round(jam()) + "ms " + teks);
    if (log.length > CATATAN_MAKS) log.shift();
  }

  // ---- akses ke state app.js / server.js / suara.js (variabel global, dibaca saat dipakai, bukan saat dimuat)
  const appGenerasi = () => (typeof generasi === "undefined" ? 0 : generasi);
  const appBisu = () => (typeof bisu === "undefined" ? false : bisu);
  const modeMock = () => (typeof MODE_MOCK === "undefined" ? false : MODE_MOCK);
  const alamatServer = () => (typeof ALAMAT_SERVER === "undefined" ? "" : ALAMAT_SERVER);
  const sesi = () => (typeof SESI === "undefined" ? "default" : SESI);
  // speechSynthesis.speaking sendiri tidak dipercaya (bisa macet true); hanya dipakai bersama catatan pelacak.
  const sedangBicara = () => {
    const s = root.speechSynthesis;
    return pelacak.sedangBicara(!!(s && s.speaking), !!(s && s.pending));
  };
  let pemantauTimer = null;
  function pantauSintesis() {
    if (pemantauTimer) return;
    pemantauTimer = setTimeout(() => {
      pemantauTimer = null;
      sedangBicara();                       // memperbarui pelacak (dan menutup ucapan yang onend-nya tidak datang)
      if (pelacak.jumlah() > 0) pantauSintesis();
    }, PANTAU_MS);
  }

  function ucapkanZ(teks) {
    return typeof ucapkanZanite === "function" ? ucapkanZanite(teks) : Promise.resolve();
  }

  function tampilStatus(teks, redup) {
    try {
      const el = root.document && root.document.getElementById("zanite-status");
      if (!el) return;
      el.textContent = teks || "";
      el.hidden = !teks;
      if (el.classList) el.classList.toggle("redup", !!redup);
    } catch (e) { /* tidak penting */ }
  }

  // Keadaan diam: redup "Zanite aktif" selama mendengarkan kata bangun; kosong bila Zanite mati/Bisu/izin ditolak.
  function tampilDiam() {
    tampilStatus(hidup && !fatal && !jedaPengenal ? "Zanite aktif" : "", true);
  }

  // ---- bunyi bip (WebAudio). onended kadang tidak datang, jadi ada batas waktu; bip gagal tidak menahan balasan.
  function siapAudio() {
    try {
      const AC = root.AudioContext || root.webkitAudioContext;
      if (!actx && AC) actx = new AC();
      if (actx && actx.state === "suspended") actx.resume();
    } catch (e) { debug("AudioContext gagal: " + (e && e.name)); }
  }

  function beep(selesai) {
    const id = pelacak.mulai(900, { tanpaSintesis: true });   // bip juga bunyi yang tidak boleh didengar mic sendiri
    let beres = false;
    const fin = () => {
      if (beres) return;
      beres = true;
      pelacak.selesai(id);
      selesai();
    };
    try {
      if (!actx) throw new Error("tanpa AudioContext");
      if (actx.state === "suspended") actx.resume();
      const o = actx.createOscillator(), g = actx.createGain();
      o.type = "sine";
      o.frequency.value = 880;
      g.gain.value = 0.25;
      o.connect(g);
      g.connect(actx.destination);
      o.onended = fin;
      o.start();
      o.stop(actx.currentTime + 0.15);
      setTimeout(fin, 700);
    } catch (e) {
      hitung.bipGagal += 1;
      debug("bip gagal: " + (e && (e.message || e.name)));
      fin();
    }
  }

  // ---- status server
  async function cekStatus() {
    if (modeMock()) return typeof ambilStatusMock === "function" ? !!ambilStatusMock().zanite : false;
    const kontrol = new AbortController();
    const batas = setTimeout(() => kontrol.abort(), 3000);
    try {
      const res = await fetch(alamatServer() + "/api/status", { signal: kontrol.signal });
      if (!res.ok) return false;
      return (await res.json()).zanite === true;
    } catch (e) {
      return false;
    } finally {
      clearTimeout(batas);
    }
  }

  // ---- pengenal suara
  function berhentiPengenal() {
    jedaPengenal = true;
    clearTimeout(restartTimer);
    restartTimer = null;
    try { rec && rec.abort(); } catch (e) { /* abaikan */ }
    rec = null;                         // onend pengenal lama tidak lagi menahan startRec berikutnya
  }

  function startRec() {
    if (!hidup || fatal || jedaPengenal || rec) return;
    restartTimer = null;
    const r = new SR();
    r.lang = "id-ID";
    r.continuous = true;
    r.interimResults = true;
    r.maxAlternatives = 3;
    const mySid = ++sid;
    r.onerror = (e) => {
      lastErr = e.error || "?";
      tambah(hitung.galatPengenal, lastErr);
      debug("ERROR " + lastErr);
      if (lastErr === "not-allowed" || lastErr === "service-not-allowed") {
        fatal = true;
        batalkanAlur();
        if (!izinDiucap) { izinDiucap = true; ucapkanZ(PESAN_IZIN); }
      } else if (lastErr === "language-not-supported") {
        fatal = true;
        batalkanAlur();
      }
    };
    r.onend = () => {
      if (rec === r) rec = null;
      if (!hidup || fatal || jedaPengenal) return;
      hitung.restartPengenal += 1;
      const ringan = !lastErr || lastErr === "no-speech" || lastErr === "aborted";
      errBeruntun = ringan ? 0 : errBeruntun + 1;
      const tunda = ringan ? 250 : Math.min(300 * Math.pow(2, errBeruntun), 5000);
      lastErr = null;
      restartTimer = setTimeout(startRec, tunda);
    };
    r.onresult = (e) => { errBeruntun = 0; onResult(e, mySid); };
    rec = r;
    try {
      r.start();
    } catch (e) {
      debug("start() gagal: " + (e && e.name));
      rec = null;
      restartTimer = setTimeout(startRec, 1000);
    }
  }

  function onResult(e, mySid) {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i], key = mySid + ":" + i, final = r.isFinal;
      const mentah = String((r[0] && r[0].transcript) || "").trim();
      if (!mentah) continue;
      for (let j = 1; j < r.length; j++) debug("alt" + j + ": " + r[j].transcript);   // alternatif hanya dicatat
      if (sedangBicara()) { hitung.dibuangSaatBicara += 1; debug("dibuang (app bicara): " + mentah); continue; }
      terimaTeks(jam(), key, mentah, final);
    }
  }

  // Satu transkrip yang lolos penyaringan. Dipisah dari onResult supaya mudah dites.
  function terimaTeks(now, key, mentah, final) {
    if (!hidup || fatal) return;
    const teks = ZA.ubahJadi(mentah);
    const c = catatan.get(key);
    if (c) { c.teks = teks; c.final = final; c.tAkhir = now; }
    else catatan.set(key, { teks, final, tPertama: now, tAkhir: now });
    for (const [k, v] of catatan) if (now - v.tAkhir > 15000) catatan.delete(k);
    debug((final ? "F " : "I ") + teks);
    if (jendela) jendela.terima(now, key, teks, final);
    if (P) proses(P.masuk(now, key, teks, final));
    jadwalPemicu();
    jadwalJendela();
  }

  function proses(evs) {
    for (const e of evs) {
      if (e.type === "wake") onWake(e);
      else if (e.type === "ditolak") debug('ditolak: "' + e.teks + '"');
    }
  }

  function jadwalPemicu() {
    clearTimeout(tickTimer);
    tickTimer = null;
    if (!P) return;
    const d = P.nextDue();
    if (d == null) return;
    tickTimer = setTimeout(() => {
      tickTimer = null;
      if (P) proses(P.tick(jam()));
      jadwalPemicu();
      jadwalJendela();
    }, Math.max(0, d - jam()) + 5);
  }

  // Menjalankan fn setelah tidak ada ucapan app yang masih tercatat (maks. 8 dtk). Dipakai sesudah balasan: bila
  // balasan dipotong peringatan tingkat 3, jendela perintah baru dibuka sesudah peringatan itu selesai.
  function tungguSepi(saya, fn) {
    const coba = (n) => {
      if (saya !== siklus) return;
      if (pelacak.jumlah() > 0 && n < 80) { setTimeout(() => coba(n + 1), 100); return; }
      fn();
    };
    coba(0);
  }

  // ---- alur
  function onWake(e) {
    if (fase === "balas") return;     // sedang membalas; ucapan lain diabaikan
    tambah(hitung.wake, e.tipe);
    debug("WAKE " + e.tipe + " '" + e.v + "'");
    tutupJendela();
    permintaanId += 1;                // jawaban lama (kalau ada) dibuang: pengguna memulai lagi
    if (e.tipe === "perintah") satuNapas(e);
    else duaLangkah();
  }

  // Alur utama: wake -> bip -> "Iya, ada yang bisa saya bantu?" -> jendela 6 detik setelah balasan selesai.
  function duaLangkah() {
    const saya = ++siklus;
    fase = "balas";
    tampilStatus("");
    beep(() => {
      if (saya !== siklus) return;
      ucapkanZ(BALAS).then(() => {
        if (saya !== siklus) return;
        tungguSepi(saya, () => bukaJendela(false));
      });
    });
  }

  // "Zanite jelaskan sekitar" dalam satu napas: tidak ada "Iya, ...". Tunggu ucapannya selesai (jendela diisi
  // dari transkrip ucapan yang sama), lalu bip + kirim. Bip tidak dibunyikan sebelum itu supaya sisa kalimat
  // tidak ikut terbuang oleh penyaring "app bicara".
  function satuNapas(e) {
    ++siklus;
    const w = bukaJendela(true);
    const t0 = e.utt ? e.utt.t0 : e.t;
    for (const [key, c] of catatan) if (c.tPertama >= t0) w.terima(c.tAkhir, key, c.teks, c.final);
    jadwalJendela();
  }

  function bukaJendela(inline) {
    tutupJendela();
    jendela = ZA.buatJendela({ t: jam(), bukaMs: JENDELA_MS, inline });
    fase = "jendela";
    tampilStatus("Zanite mendengar");
    jadwalJendela();
    return jendela;
  }

  function jadwalJendela() {
    clearTimeout(jendelaTimer);
    jendelaTimer = null;
    if (!jendela) return;
    const d = jendela.jatuhTempo();
    if (d == null) return;
    jendelaTimer = setTimeout(cekJendela, Math.max(0, d - jam()) + 5);
  }

  function cekJendela() {
    jendelaTimer = null;
    if (!jendela) return;
    const a = jendela.periksa(jam());
    if (!a) { jadwalJendela(); return; }
    const inline = jendela.inline;
    jendela = null;
    if (a.aksi === "tutup") {          // 6 detik tanpa suara: tutup diam-diam
      fase = "diam";
      tampilDiam();
      return;
    }
    kirimPerintah(a.teks, inline);
  }

  function tutupJendela() {
    clearTimeout(jendelaTimer);
    jendelaTimer = null;
    if (jendela) jendela.tutup();
    jendela = null;
    if (fase === "jendela") { fase = "diam"; tampilDiam(); }
  }

  async function kirimPerintah(teks, bip) {
    const id = ++permintaanId, gen = appGenerasi(), t0 = jam();
    fase = "proses";
    tampilStatus("Zanite memproses");
    if (bip) beep(() => {});
    debug("kirim: " + teks);
    let jawaban = null;
    hitung.permintaan += 1;
    try { jawaban = await mintaJawaban(teks); } catch (e) { jawaban = null; }
    if (!jawaban) jawaban = { teks: PESAN_JARINGAN, jenis: "jaringan" };
    if (id !== permintaanId) return;   // digantikan wake baru atau Berhenti
    tambah(hitung.jawaban, jawaban.jenis);
    fase = "diam";
    tampilDiam();
    if (gen !== appGenerasi() || jam() - t0 > WAKTU_PERMINTAAN_MS) { hitung.jawabanUsang += 1; debug("jawaban usang dibuang"); return; }
    ucapkanZ(jawaban.teks);
  }

  function blobKeBase64(blob) {
    return new Promise((res, rej) => {
      const fr = new root.FileReader();
      fr.onload = () => res(String(fr.result).split(",")[1] || "");
      fr.onerror = () => rej(fr.error);
      fr.readAsDataURL(blob);
    });
  }

  // { teks, jenis } untuk diucapkan, atau null kalau jaringan/server gagal. Hanya jenisnya yang dihitung di log.
  async function mintaJawaban(teks) {
    if (modeMock()) return { teks: (await ambilJawabanZaniteMock()).jawaban, jenis: "mock" };
    const jpeg = typeof ambilJpeg === "function" ? await ambilJpeg() : null;
    if (!jpeg) return { teks: PESAN_KAMERA, jenis: "kamera" };
    const gambar = await blobKeBase64(jpeg);
    const kontrol = new AbortController();
    const batas = setTimeout(() => kontrol.abort(), WAKTU_PERMINTAAN_MS);
    try {
      const res = await fetch(alamatServer() + "/api/zanite", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Sesi": sesi() },
        body: JSON.stringify({ teks, gambar }),
        signal: kontrol.signal,
      });
      let data = null;
      try { data = await res.json(); } catch (e) { data = null; }
      // Kalimat dari server (juga untuk 429/400/403) diucapkan apa adanya; tanpa JSON = masalah jaringan/server.
      return data && typeof data.jawaban === "string" && data.jawaban
        ? { teks: data.jawaban, jenis: typeof data.jenis === "string" ? data.jenis : "?" } : null;
    } catch (e) {
      return null;
    } finally {
      clearTimeout(batas);
    }
  }

  function batalkanAlur() {
    ++siklus;
    permintaanId += 1;
    tutupJendela();
    clearTimeout(tickTimer);
    tickTimer = null;
    fase = "diam";
    tampilDiam();
  }

  // ---- antarmuka untuk app.js / suara.js
  async function mulai() {
    if (hidup || memeriksa || !SR) return;
    const token = ++tokenMulai;
    memeriksa = true;
    siapAudio();
    const ada = await cekStatus();
    memeriksa = false;
    if (token !== tokenMulai) return;   // Berhenti dipanggil saat menunggu
    if (!ada) { debug("Zanite tidak tersedia di server"); return; }
    hidup = true;
    fatal = false;
    izinDiucap = false;
    P = ZC.buatPemicu(cfg, DIAM_MS, JEDA_UCAPAN_MS, LEMAH_MS);
    jedaPengenal = appBisu();           // Bisu menyala: tidak mendengar (tidak ada jawaban diam-diam)
    if (!jedaPengenal) startRec();
    tampilDiam();
  }

  function berhenti() {
    tokenMulai += 1;
    memeriksa = false;
    hidup = false;
    batalkanAlur();
    clearTimeout(restartTimer);
    restartTimer = null;
    try { rec && rec.abort(); } catch (e) { /* abaikan */ }
    rec = null;
    P = null;
    catatan.clear();
  }

  function bisuBerubah(nilai) {
    if (!hidup) return;
    if (nilai) {
      berhentiPengenal();
      batalkanAlur();                   // sesudah jedaPengenal menyala: status jadi kosong
    } else {
      jedaPengenal = false;
      if (!rec) startRec();             // kalau pengenal lama masih berakhir, onend yang menyalakan lagi
      tampilDiam();
    }
  }

  // Dipanggil suara.js untuk SETIAP ucapan app, tepat sebelum speak().
  // saatPutus (opsional): dipanggil bila ucapan diakhiri tanpa onend (cancel / selesai-paksa / pengaman).
  function bicaraPantau(u, teks, saatPutus) {
    const id = pelacak.mulai(15000 + String(teks || "").length * 120, { saatPutus });   // pengaman: onend kadang tidak datang
    const selesai = () => pelacak.selesai(id);
    u.addEventListener("end", selesai);
    u.addEventListener("error", selesai);
    pantauSintesis();
  }

  // Dipanggil suara.js tepat SEBELUM speechSynthesis.cancel(): semua ucapan yang ada diakhiri sekarang
  // (onend/onerror-nya belum tentu datang). Ucapan baru sesudah cancel punya catatannya sendiri.
  function sintesisDibatalkan() {
    const n = pelacak.selesaiSemua();
    if (n) debug("cancel: " + n + " ucapan diakhiri");
  }

  // ---- log uji: disalin lewat tombol di panel Atur. Tidak ada yang dikirim ke mana pun.
  function infoSuara() {
    try {
      const v = typeof pilihSuaraIndonesia === "function" ? pilihSuaraIndonesia() : null;
      return v ? v.name + " (" + v.lang + ")" : "tidak ada suara id/in";
    } catch (e) { return "?"; }
  }

  function laporan() {
    const st = pelacak.statistik();
    let waktu = "?";
    try { waktu = new Date().toISOString(); } catch (e) { /* abaikan */ }
    return ZA.susunLaporan({
      header: {
        versi: VERSI,
        waktu,
        userAgent: root.navigator && root.navigator.userAgent,
        suara: infoSuara(),
        TAIL_MS, DIAM_MS, LEMAH_MS,
      },
      hitung: {
        "wake per tipe": hitung.wake,
        "transkrip dibuang saat app bicara": hitung.dibuangSaatBicara,
        "selesai-paksa": st.paksa,
        "diakhiri oleh cancel": st.dibatalkan,
        "pengenal restart": hitung.restartPengenal,
        "galat pengenal per jenis": hitung.galatPengenal,
        "permintaan terkirim": hitung.permintaan,
        "jawaban per jenis": hitung.jawaban,
        "jawaban usang dibuang": hitung.jawabanUsang,
        "bip gagal": hitung.bipGagal,
      },
      baris: log,
    });
  }

  // Salin ke papan klip; kalau API-nya gagal, tampilkan teksnya di <textarea> supaya bisa dipilih manual.
  async function salinLog() {
    const teks = laporan();
    let ok = false;
    try {
      const nav = root.navigator;
      if (nav && nav.clipboard && nav.clipboard.writeText) { await nav.clipboard.writeText(teks); ok = true; }
    } catch (e) { ok = false; }
    const doc = root.document;
    const area = doc && doc.getElementById("teks-log-zanite");
    const tombol = doc && doc.getElementById("salin-log-zanite");
    if (area) {
      area.hidden = ok;
      if (!ok) {
        area.value = teks;
        try { area.focus(); area.select(); } catch (e) { /* abaikan */ }
      }
    }
    if (tombol) {
      tombol.textContent = ok ? "Log tersalin" : "Salin manual dari kotak";
      setTimeout(() => { tombol.textContent = "Salin log Zanite"; }, 2500);
    }
    return ok;
  }

  function pasangTombolLog() {
    try {
      const tombol = root.document && root.document.getElementById("salin-log-zanite");
      if (!tombol) return;
      tombol.hidden = false;
      tombol.addEventListener("click", () => { salinLog(); });
    } catch (e) { /* abaikan */ }
  }
  pasangTombolLog();

  root.Zanite = {
    mulai, berhenti, bisuBerubah, bicaraPantau, sintesisDibatalkan,
    debug: () => log.slice(),
    laporan, salinLog,
    keadaan: () => ({ hidup, fase, fatal, jedaPengenal }),
    _uji: { terimaTeks, sedangBicara, hitung, statistik: () => pelacak.statistik() },
  };
})(typeof window !== "undefined" ? window : globalThis);
