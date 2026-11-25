// Zanite di HP: pengenal suara selalu hidup, kata bangun "Zanite", jendela perintah, kirim ke server, ucapkan jawaban.
// Aturan keputusan murni ada di zanite-aturan.js; pencocok kata bangun di zanite-cocok.js (salinan spike).
//
// Aturan utama: mic TIDAK PERNAH dimatikan agar tidak mendengar suara app sendiri (setiap buka ulang,
// Android membunyikan suara Asisten Google). Dari AWAL tiap transkrip dibuang kata-kata yang cocok dengan ucapan
// app 60 detik terakhir (gema: peringatan, pesan sistem, balasan dan jawaban Zanite); hanya sisanya (suara pengguna)
// yang diteruskan ke pencocok kata bangun dan jendela perintah. Penjaga kedua terhadap bangun sendiri: aturan kata
// bangun yang ketat (varian sendirian, diam 800/1200 ms).
//
// Fokus Zanite: hanya selama pengguna bicara, yaitu sejak kata bangun sampai perintah tertangkap (kirimPerintah
// mulai). Selama itu peringatan tingkat 1 dan 2 tidak diucapkan (tingkat 3 tetap berbunyi dan memotong Zanite),
// dan kata bangun memotong ucapan yang sedang berbunyi kecuali tingkat 3. Sesudah perintah terkirim, peringatan
// berbunyi seperti biasa; jawaban Zanite antre di belakang peringatan yang sedang bicara (tanpa cancel).
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
  const PESAN_TAK_TERDENGAR = "Maaf, tidak terdengar. Panggil Zanite lagi.";
  const PESAN_TUNGGU = "Sebentar.";
  const TUNGGU_JAWAB_MS = 2500;      // belum ada jawaban server sesudah sekian ms: ucapkan "Sebentar." sekali
  const JENDELA_MS = 6000;          // jendela perintah, dihitung dari akhir balasan
  const WAKTU_PERMINTAAN_MS = 10000; // batas klien; jawaban lebih lama dari ini dibuang
  const DIAM_MS = 800;              // kata bangun sendirian: nyala setelah sekian ms tanpa kata baru
  const JEDA_UCAPAN_MS = 1500;      // transkrip baru setelah sekian ms sepi = ucapan baru
  const LEMAH_MS = 1200;            // varian lemah (jani, dani, ...): final atau interim stabil sekian ms
  const TAIL_MS = 500;              // masih "app bicara" sekian ms setelah ucapan selesai
  const CATATAN_MAKS = 300;
  const PANTAU_MS = 250;            // pemantau sintesis: seberapa sering speaking/pending diperiksa
  const CEK_PENGENAL_MS = 5000;    // pemeriksa pengenal: seberapa sering macet dicek
  const DENYUT_MS = 15000;          // baris "pengenal: ..." di log tiap sekian ms selama hidup
  const MACET_MS = 60000;           // tanpa satu pun hasil selama ini (halaman tampak) = pengenal macet, dimulai ulang
  const JEDA_CANCEL_MS = 150;       // jarak minimal antara cancel() dan bip/ucapan Zanite berikutnya (Chrome HP)
  const TUNGGU_T3_MS = 4000;        // balasan menunggu ucapan lain (tingkat 3) paling lama sekian ms
  const FOKUS_MAKS_MS = 12000;      // batas keras fokus Zanite sejak kata bangun (balasan ~3 dtk + jendela 6 dtk + sisa)
  const BARIS_MAKS = 500;             // satu baris log paling panjang sekian karakter
  const UNGGAH_MS = 60000;            // log diunggah ke server tiap sekian ms selama Zanite hidup
  const UNGGAH_JARAK_MS = 20000;      // batas server: 1 unggahan per sekian ms per sesi
  const UNGGAH_MAKS_BYTE = 190000;    // batas server 200 KB
  const BEACON_MAKS_BYTE = 60000;     // sendBeacon/keepalive browser dibatasi 64 KB
  const VERSI = "zanite-app-5";

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
  let fokusAktif = false, fokusId = 0, fokusTimer = null;
  let tTerimaBicara = -Infinity;   // kapan transkrip terakhir diterima saat app bicara
  let tCancelTerakhir = -Infinity; // kapan speechSynthesis.cancel() terakhir dipanggil (lewat sintesisDibatalkan)
  const ditahanDicatat = new Set(); // pesan peringatan yang sudah dicatat di log selama fokus ini
  let tHasil = -Infinity;          // hasil pengenal terakhir (apa pun, termasuk yang dibuang sebagai gema)
  let tMulaiRec = 0;               // pengenal terakhir dimulai/dimulai ulang
  let audioOn = false;             // audiostart sudah datang dan audioend belum
  let hasilDiJendela = 0;          // hasil yang datang sejak jendela perintah dibuka
  let cekPengenalTimer = null, tDenyut = -Infinity;
  const gemaPerKunci = new Map();  // kunci hasil -> waktu: hasil yang dibuang sebagai gema
  let unggahTimer = null, pernahHidup = false;
  const tUnggah = new Map(), unggahTunda = new Map();   // sesi -> waktu unggah terakhir / pengatur waktu tunda
  const catatan = new Map();  // kunci hasil Chrome -> { teks, final, tPertama, tAkhir }
  const log = [];
  // Hitungan untuk "Salin log Zanite". Hanya angka; teks ucapan/jawaban tidak masuk sini.
  const hitung = { wake: {}, gemaDibuang: 0, diterimaSaatBicara: 0, wakeSaatBicara: 0, peringatanDitahan: 0, alasanCadangan: {}, modelJawab: {}, gemaLaluDiterima: 0, restartAlasan: {}, restartPengenal: 0, galatPengenal: {}, permintaan: 0, jawaban: {}, jawabanUsang: 0, bipGagal: 0, gemaDipotong: 0, sebentar: 0, jendelaKosong: 0, unggah: {} };
  const tambah = (obj, k) => { obj[k] = (obj[k] || 0) + 1; };

  function debug(teks) {
    let jamDinding = "";
    try { jamDinding = new Date().toISOString().slice(11, 23) + " "; } catch (e) { /* abaikan */ }
    const isi = String(teks);
    log.push(jamDinding + "+" + Math.round(jam()) + "ms " + (isi.length > BARIS_MAKS ? isi.slice(0, BARIS_MAKS) + "..." : isi));
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

  // label: "balas" | "jawab" (untuk log siklus hidup ucapan). Hasil janji: "end" | "error" | "paksa" | "cancel" |
  // "pengaman" | "gagal" (tidak pernah mulai, sudah diulang sekali) | "lewat".
  function ucapkanZ(teks, label) {
    return typeof ucapkanZanite === "function" ? ucapkanZanite(teks, label) : Promise.resolve("lewat");
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
      if (actx.state !== "running") debug("bip: AudioContext " + actx.state);
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

  // ---- kesehatan pengenal: acara, denyut, dan pemulihan macet
  const statusHalaman = () => { const d = root.document; return (d && d.visibilityState) || "?"; };
  const halamanTampak = () => statusHalaman() !== "hidden";

  // Dimulai ulang (abort + start) karena macet. alasan: "jendela-kosong" | "macet". Bunyi mikrofon Google saat itu
  // dapat diterima. Jam macet diulang dari nol supaya tidak berulang-ulang.
  function mulaiUlangPengenal(alasan) {
    if (!hidup || fatal || jedaPengenal) return;
    tambah(hitung.restartAlasan, alasan);
    debug("restart: " + alasan);
    clearTimeout(restartTimer);
    restartTimer = null;
    const lama = rec;
    rec = null;                          // onend pengenal lama tidak lagi menahan startRec berikutnya
    try { lama && lama.abort(); } catch (e) { /* abaikan */ }
    tMulaiRec = jam();
    restartTimer = setTimeout(startRec, 150);
  }

  function cekPengenal() {
    cekPengenalTimer = null;
    if (!hidup) return;
    const t = jam();
    if (t - tDenyut >= DENYUT_MS) {
      tDenyut = t;
      debug("pengenal: hasil terakhir " + (tHasil === -Infinity ? "belum ada" : Math.round((t - tHasil) / 1000) + " s lalu") +
        ", audio=" + (audioOn ? "on" : "off") + ", visible=" + statusHalaman() + ", hidup=" + hidup + ", rec=" + (rec ? "ada" : "null"));
    }
    if (rec && !fatal && !jedaPengenal && halamanTampak() && t - Math.max(tHasil, tMulaiRec) >= MACET_MS) mulaiUlangPengenal("macet");
    cekPengenalTimer = setTimeout(cekPengenal, CEK_PENGENAL_MS);
  }

  function mulaiPemeriksaPengenal() {
    clearTimeout(cekPengenalTimer);
    tDenyut = -Infinity;
    cekPengenal();
  }

  function berhentiPemeriksaPengenal() {
    clearTimeout(cekPengenalTimer);
    cekPengenalTimer = null;
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
    for (const nama of ["start", "audiostart", "soundstart", "speechstart", "speechend", "soundend", "audioend"]) {
      r["on" + nama] = () => {
        if (nama === "audiostart") audioOn = true;
        if (nama === "audioend") audioOn = false;
        debug("pengenal: " + nama);
      };
    }
    r.onerror = (e) => {
      lastErr = e.error || "?";
      audioOn = false;
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
      audioOn = false;
      debug("pengenal: end");
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
    tMulaiRec = jam();
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
      tHasil = jam();
      hasilDiJendela += 1;
      for (let j = 1; j < r.length; j++) debug("alt" + j + ": " + r[j].transcript);   // alternatif hanya dicatat
      const bicara = sedangBicara();       // juga menyegarkan pelacak sebelum teks app dibaca
      const sisa = ZA.sisaSetelahGema(mentah, pelacak.teksBicara(), pelacak.teksSedang());
      if (!sisa) {
        hitung.gemaDibuang += 1;
        gemaPerKunci.set(key, jam());
        debug("gema dibuang: " + mentah);
        tarikHasil(jam(), key, final);
        continue;
      }
      const dipotong = sisa !== mentah;
      if (dipotong) hitung.gemaDipotong += 1;
      if (bicara) {
        hitung.diterimaSaatBicara += 1;
        tTerimaBicara = jam();
      }
      // Hasil yang sama (kunci sama = ucapan yang sama) sebelumnya dibuang sebagai gema, sekarang diterima.
      if (gemaPerKunci.has(key)) {
        hitung.gemaLaluDiterima += 1;
        gemaPerKunci.delete(key);
        debug("gema dibuang lalu kalimat yang sama diterima: " + sisa);
      }
      for (const [k, v] of gemaPerKunci) if (jam() - v > 15000) gemaPerKunci.delete(k);
      terimaTeks(jam(), key, sisa, final, bicara, dipotong ? mentah : null);
    }
  }

  // Hasil yang tadinya diteruskan ternyata seluruhnya gema (potongan awalnya belum cocok): tarik kembali.
  function tarikHasil(now, key, final) {
    if (!catatan.delete(key)) return;
    if (jendela) jendela.terima(now, key, "", final);
    if (P) proses(P.masuk(now, key, "", final));
    jadwalPemicu();
    jadwalJendela();
  }

  // Satu transkrip (sesudah gema di awalnya dibuang). Dipisah dari onResult supaya mudah dites.
  // asal: transkrip lengkap bila ada gema yang dibuang (hanya untuk log).
  function terimaTeks(now, key, mentah, final, saatBicara, asal) {
    if (!hidup || fatal) return;
    const teks = ZA.ubahJadi(mentah);
    const c = catatan.get(key);
    if (c) { c.teks = teks; c.final = final; c.tAkhir = now; }
    else catatan.set(key, { teks, final, tPertama: now, tAkhir: now });
    for (const [k, v] of catatan) if (now - v.tAkhir > 15000) catatan.delete(k);
    debug((final ? "F " : "I ") + (saatBicara ? "(app bicara) " : "") + teks + (asal ? "   [gema dipotong dari: " + asal + "]" : ""));
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
  // maksMs: batas tunggu. fn(habis): habis = true bila batas terlewati dan masih ada ucapan tercatat.
  function tungguSepi(saya, fn, maksMs) {
    const maksN = Math.round((maksMs || 8000) / 100);
    const coba = (n) => {
      if (saya !== siklus) return;
      if (pelacak.jumlah() > 0) {
        if (n >= maksN) { fn(true); return; }
        setTimeout(() => coba(n + 1), 100);
        return;
      }
      fn(false);
    };
    coba(0);
  }

  // Jalankan fn sesudah JEDA_CANCEL_MS dari cancel() terakhir (Chrome HP bisa membuang suara tepat sesudah cancel).
  function sesudahJedaCancel(fn) {
    const sisa = JEDA_CANCEL_MS - (jam() - tCancelTerakhir);
    if (sisa > 0) setTimeout(fn, sisa); else fn();
  }

  // ---- fokus Zanite
  function mulaiFokus() {
    const id = ++fokusId;
    fokusAktif = true;
    clearTimeout(fokusTimer);
    fokusTimer = setTimeout(() => akhiriFokus(id, "batas " + FOKUS_MAKS_MS / 1000 + " dtk"), FOKUS_MAKS_MS);
    ditahanDicatat.clear();
    debug("fokus mulai");
  }

  // id: hanya mengakhiri fokus milik alur itu (alur lama tidak boleh mengakhiri fokus wake yang lebih baru).
  function akhiriFokus(id, alasan) {
    if (!fokusAktif || (id != null && id !== fokusId)) return;
    fokusAktif = false;
    clearTimeout(fokusTimer);
    fokusTimer = null;
    debug("fokus selesai: " + alasan);
  }

  // Kata bangun memotong ucapan app yang sedang berbunyi, KECUALI peringatan tingkat 3 (dibiarkan selesai;
  // balasan Zanite baru berbunyi sesudahnya).
  function potongUcapan() {
    sedangBicara();                      // segarkan pelacak (menutup ucapan yang onend-nya tidak datang)
    const s = root.speechSynthesis;
    if (pelacak.adaTingkat3()) return;
    if (pelacak.jumlah() > 0 || (s && (s.speaking || s.pending))) {
      debug("wake: cancel() (tercatat=" + pelacak.jumlah() + " speaking=" + !!(s && s.speaking) + " pending=" + !!(s && s.pending) + ")");
      sintesisDibatalkan();
      try { s && s.cancel(); } catch (x) { /* abaikan */ }
    }
  }

  // ---- alur
  function onWake(e) {
    if (fase === "balas") return;     // sedang membalas; ucapan lain diabaikan
    const t0 = e.utt ? e.utt.t0 : e.t;
    const saatBicara = sedangBicara() || tTerimaBicara >= t0;
    tambah(hitung.wake, e.tipe);
    if (saatBicara) hitung.wakeSaatBicara += 1;
    debug("WAKE " + e.tipe + " '" + e.v + "'" + (saatBicara ? " (saat app bicara)" : ""));
    tutupJendela();
    permintaanId += 1;                // jawaban lama (kalau ada) dibuang: pengguna memulai lagi
    mulaiFokus();
    potongUcapan();
    if (e.tipe === "perintah") satuNapas(e);
    else duaLangkah();
  }

  // Alur utama: wake -> bip -> "Iya, ada yang bisa saya bantu?" -> jendela 6 detik setelah balasan selesai.
  function duaLangkah() {
    const saya = ++siklus;
    fase = "balas";
    tampilStatus("");
    // Bila peringatan tingkat 3 sedang bicara (tidak dipotong), bip dan balasan menunggu sampai selesai,
    // paling lama TUNGGU_T3_MS; sesudah itu ucapan yang macet dipotong dan balasan tetap diucapkan.
    if (pelacak.jumlah() > 0) debug("balas: menunggu " + (pelacak.adaTingkat3() ? "t3" : "ucapan lain"));
    tungguSepi(saya, (habis) => {
      if (habis) {
        debug("balas: ucapan lain tidak selesai dalam " + TUNGGU_T3_MS / 1000 + " dtk, dipotong, lanjut");
        sintesisDibatalkan();
        try { root.speechSynthesis && root.speechSynthesis.cancel(); } catch (x) { /* abaikan */ }
      }
      sesudahJedaCancel(() => {
        if (saya !== siklus) return;
        beep(() => {
          if (saya !== siklus) return;
          ucapkanZ(BALAS, "balas").then((hasil) => {
            if (saya !== siklus) return;
            if (hasil === "gagal") {      // suara tidak mau berbunyi: tutup alur, mic tetap mendengar
              debug("balas: gagal, alur ditutup, mic tetap mendengar");
              batalkanAlur();
              return;
            }
            tungguSepi(saya, () => bukaJendela(false));
          });
        });
      });
    }, TUNGGU_T3_MS);
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
    // gema balasan yang menempel di hasil yang sama dengan kata bangun bukan perintah
    jendela = ZA.buatJendela({ t: jam(), bukaMs: JENDELA_MS, inline, gema: (cmd) => ZA.potonganDari(cmd, BALAS, 3) });
    hasilDiJendela = 0;
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
    if (a.aksi === "tutup") {          // 6 detik tanpa perintah: tutup dan beri tahu pengguna sekali
      fase = "diam";
      tampilDiam();
      akhiriFokus(null, "jendela habis tanpa perintah");
      hitung.jendelaKosong += 1;
      ucapkanZ(PESAN_TAK_TERDENGAR, "tutup");
      // Jendela habis dan tidak satu hasil pun datang: pengenal mungkin hidup tetapi tuli. Mulai ulang sekali.
      if (hasilDiJendela === 0) mulaiUlangPengenal("jendela-kosong");
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
    akhiriFokus(null, "perintah tertangkap");   // fokus hanya selama pengguna bicara
    fase = "proses";
    tampilStatus("Zanite memproses");
    if (bip) beep(() => {});
    debug("kirim: " + teks);
    let jawaban = null;
    hitung.permintaan += 1;
    const tunggu = setTimeout(() => {
      if (id !== permintaanId || gen !== appGenerasi()) return;
      hitung.sebentar += 1;
      ucapkanZ(PESAN_TUNGGU, "tunggu");      // jawaban yang datang sesudahnya antre di belakangnya
    }, TUNGGU_JAWAB_MS);
    try { jawaban = await mintaJawaban(teks); } catch (e) { jawaban = null; }
    clearTimeout(tunggu);
    if (!jawaban) jawaban = { teks: PESAN_JARINGAN, jenis: "jaringan", alasan: "galat" };
    // Hanya jenis, alasan (kode pendek), dan waktu; teks jawaban tidak dicatat.
    debug("jawaban: jenis=" + jawaban.jenis + " alasan=" + (jawaban.alasan || "-") + " model=" + (jawaban.model || "-") + " " + Math.round(jam() - t0) + " ms");
    if (id !== permintaanId) return;   // digantikan wake baru atau Berhenti
    tambah(hitung.jawaban, jawaban.jenis);
    if (jawaban.alasan) tambah(hitung.alasanCadangan, jawaban.jenis + ":" + jawaban.alasan);
    if (jawaban.model) tambah(hitung.modelJawab, jawaban.model);
    fase = "diam";
    tampilDiam();
    if (gen !== appGenerasi() || jam() - t0 > WAKTU_PERMINTAAN_MS) {
      hitung.jawabanUsang += 1;
      debug("jawaban usang dibuang");
      return;
    }
    ucapkanZ(jawaban.teks, "jawab");
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
    if (modeMock()) return { teks: (await ambilJawabanZaniteMock()).jawaban, jenis: "mock", alasan: null };
    const jpeg = typeof ambilJpeg === "function" ? await ambilJpeg() : null;
    if (!jpeg) return { teks: PESAN_KAMERA, jenis: "kamera", alasan: "kamera" };
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
      if (data && typeof data.jawaban === "string" && data.jawaban) {
        const a = typeof data.alasan === "string" && /^[A-Za-z0-9_-]{1,40}$/.test(data.alasan) ? data.alasan : (data.alasan ? "?" : null);
        // model yang menjawab (model utama atau cadangan di server); nama saja, disaring seperti alasan
        const m = typeof data.model === "string" && /^[A-Za-z0-9._\/-]{1,60}$/.test(data.model) ? data.model : null;
        return { teks: data.jawaban, jenis: typeof data.jenis === "string" ? data.jenis : "?", alasan: a, model: m };
      }
      return { teks: PESAN_JARINGAN, jenis: "jaringan", alasan: "tanpa-json-http-" + res.status };
    } catch (e) {
      return { teks: PESAN_JARINGAN, jenis: "jaringan", alasan: e && e.name === "AbortError" ? "waktu-klien" : "galat-fetch" };
    } finally {
      clearTimeout(batas);
    }
  }

  function batalkanAlur() {
    ++siklus;
    permintaanId += 1;
    akhiriFokus(null, "alur dibatalkan");
    tutupJendela();
    clearTimeout(tickTimer);
    tickTimer = null;
    fase = "diam";
    tampilDiam();
  }

  // ---- antarmuka untuk app.js / suara.js
  async function mulai(dari) {
    debug("mulai() oleh " + (dari || "?") + (hidup ? " (sudah hidup)" : "") + (memeriksa ? " (sedang memeriksa)" : ""));
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
    mulaiPemeriksaPengenal();
    pernahHidup = true;
    mulaiUnggahBerkala();
  }

  function berhenti(dari) {
    debug("berhenti() oleh " + (dari || "?") + (hidup ? "" : " (sudah mati)"));
    const tadinyaHidup = hidup;
    berhentiPemeriksaPengenal();
    clearTimeout(unggahTimer);
    unggahTimer = null;
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
    if (tadinyaHidup) unggahLog();       // Berhenti dan jedaOtomatis: simpan log di server
  }

  function bisuBerubah(nilai) {
    debug("bisuBerubah(" + nilai + ") oleh Bisu" + (hidup ? "" : " (Zanite mati)"));
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
  // tingkat (opsional): tingkat peringatan; 3 = tidak dipotong oleh kata bangun.
  function bicaraPantau(u, teks, saatPutus, tingkat) {
    const id = pelacak.mulai(15000 + String(teks || "").length * 120, { saatPutus, teks: String(teks || ""), tingkat });   // pengaman: onend kadang tidak datang
    const selesai = () => pelacak.selesai(id);
    u.addEventListener("end", selesai);
    u.addEventListener("error", selesai);
    pantauSintesis();
  }

  // Dipanggil suara.js tepat SEBELUM speechSynthesis.cancel(): semua ucapan yang ada diakhiri sekarang
  // (onend/onerror-nya belum tentu datang). Ucapan baru sesudah cancel punya catatannya sendiri.
  function sintesisDibatalkan() {
    tCancelTerakhir = jam();
    const n = pelacak.selesaiSemua();
    if (n) debug("cancel: " + n + " ucapan diakhiri");
  }

  // ---- log uji: disalin lewat tombol di panel Atur, dan diunggah otomatis ke server app ini sendiri
  // (/api/zanite/log) supaya tidak hilang bila halaman tertutup. Isinya memuat transkrip yang terdengar mic.
  function infoSuara() {
    try {
      const v = typeof pilihSuaraIndonesia === "function" ? pilihSuaraIndonesia() : null;
      return v ? v.name + " (" + v.lang + ")" : "tidak ada suara id/in";
    } catch (e) { return "?"; }
  }

  function laporan(maksBaris) {
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
        "gema dibuang": hitung.gemaDibuang,
        "transkrip diterima saat app bicara": hitung.diterimaSaatBicara,
        "wake saat app bicara": hitung.wakeSaatBicara,
        "peringatan ditahan saat fokus": hitung.peringatanDitahan,
        "selesai-paksa": st.paksa,
        "diakhiri oleh cancel": st.dibatalkan,
        "pengenal restart": hitung.restartPengenal,
        "restart pengenal karena macet, per alasan": hitung.restartAlasan,
        "gema dibuang lalu kalimat yang sama diterima": hitung.gemaLaluDiterima,
        "galat pengenal per jenis": hitung.galatPengenal,
        "permintaan terkirim": hitung.permintaan,
        "jawaban per jenis": hitung.jawaban,
        "alasan cadangan per jenis": hitung.alasanCadangan,
        "model yang menjawab": hitung.modelJawab,
        "jawaban usang dibuang": hitung.jawabanUsang,
        "bip gagal": hitung.bipGagal,
        "gema dipotong dari awal transkrip": hitung.gemaDipotong,
        "'Sebentar.' diucapkan": hitung.sebentar,
        "jendela tutup tanpa perintah": hitung.jendelaKosong,
        "unggah log": hitung.unggah,
      },
      baris: maksBaris === undefined ? log : maksBaris > 0 ? log.slice(-maksBaris) : [],
    });
  }

  function byteUtf8(teks) {
    let n = 0;
    for (const c of teks) { const k = c.codePointAt(0); n += k < 128 ? 1 : k < 2048 ? 2 : k < 65536 ? 3 : 4; }
    return n;
  }

  // Teks yang sama dengan "Salin log Zanite"; baris tertua dibuang bila melebihi batas ukuran.
  function teksUnggah(maksByte) {
    let n = CATATAN_MAKS, teks = laporan();
    while (byteUtf8(teks) > maksByte && n > 0) { n = Math.floor(n * 0.8); teks = laporan(n); }
    return teks;
  }

  const alamatUnggah = (s) => alamatServer() + "/api/zanite/log?sesi=" + encodeURIComponent(s);

  // Gagal diam-diam: hanya dihitung.
  function kirimLog(s, keepalive) {
    tUnggah.set(s, jam());
    const gagal = () => tambah(hitung.unggah, "gagal");
    try {
      const opsi = { method: "POST", headers: { "Content-Type": "text/plain;charset=UTF-8" }, body: teksUnggah(keepalive ? BEACON_MAKS_BYTE : UNGGAH_MAKS_BYTE) };
      if (keepalive) opsi.keepalive = true;
      fetch(alamatUnggah(s), opsi).then((res) => (res.ok ? tambah(hitung.unggah, "ok") : gagal()), gagal);
    } catch (e) { gagal(); }
  }

  // Bila baru saja mengunggah (batas server 20 dtk), unggahan ditunda, bukan dibuang.
  function unggahLog() {
    if (modeMock()) return;
    const s = sesi();
    if (unggahTunda.has(s)) return;      // sudah dijadwalkan; isinya dibaca saat dikirim
    const sisa = UNGGAH_JARAK_MS - (jam() - (tUnggah.has(s) ? tUnggah.get(s) : -Infinity));
    if (sisa <= 0) { kirimLog(s); return; }
    unggahTunda.set(s, setTimeout(() => { unggahTunda.delete(s); kirimLog(s); }, sisa + 500));
  }

  // Halaman ditutup: sendBeacon tetap terkirim sesudah halaman hilang.
  function unggahSaatTutup() {
    if (!pernahHidup || modeMock()) return;
    const s = sesi();
    let antre = false;
    try {
      const nav = root.navigator;
      antre = !!(nav && nav.sendBeacon && nav.sendBeacon(alamatUnggah(s), teksUnggah(BEACON_MAKS_BYTE)));
    } catch (e) { antre = false; }
    if (antre) { tUnggah.set(s, jam()); tambah(hitung.unggah, "beacon"); }
    else kirimLog(s, true);
  }

  function mulaiUnggahBerkala() {
    clearTimeout(unggahTimer);
    unggahTimer = setTimeout(() => {
      if (!hidup) return;
      unggahLog();
      mulaiUnggahBerkala();
    }, UNGGAH_MS);
  }

  try {
    if (typeof root.addEventListener === "function") root.addEventListener("pagehide", unggahSaatTutup);
  } catch (e) { /* abaikan */ }

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

  // Halaman yang tersembunyi/dijeda tampil di log (untuk menyingkirkan dugaan "halaman dijeda").
  try {
    if (root.document && typeof root.document.addEventListener === "function") {
      root.document.addEventListener("visibilitychange", () => debug("halaman: " + statusHalaman()));
    }
  } catch (e) { /* abaikan */ }

  // Untuk suara.js: true selama fokus Zanite. peringatanDitahan() dicatat tiap peringatan tingkat 1/2 yang ditahan.
  const fokus = () => fokusAktif;
  function peringatanDitahan(pesan) {
    hitung.peringatanDitahan += 1;             // dihitung tiap kali; barisnya hanya sekali per pesan per fokus
    if (!ditahanDicatat.has(pesan)) { ditahanDicatat.add(pesan); debug("peringatan ditahan saat fokus: " + pesan); }
  }

  root.Zanite = {
    mulai, berhenti, bisuBerubah, bicaraPantau, sintesisDibatalkan, fokus, peringatanDitahan,
    catat: debug, cancelTerakhir: () => tCancelTerakhir, jam,
    debug: () => log.slice(),
    laporan, salinLog,
    keadaan: () => ({ hidup, fase, fatal, jedaPengenal }),
    _uji: { terimaTeks, sedangBicara, hitung, statistik: () => pelacak.statistik() },
  };
})(typeof window !== "undefined" ? window : globalThis);
