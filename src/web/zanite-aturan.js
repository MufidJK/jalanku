// Aturan keputusan Zanite yang murni (tanpa DOM, tanpa timer): dipakai zanite.js dan dites di Node
// dengan jam palsu (tests/zanite/tes_aturan.js).
//
//  - siapkanKataSopan(): "tolong, coba, dong, lagi" boleh ada di antara varian dan perintah.
//  - ubahJadi(): Chrome menulis "Zanite" sebagai "jadi"; hanya dihitung bila langsung diikuti perintah penuh.
//  - jenisPerintah(): "jelaskan sekitar" (mengandung sekitar/jelas) atau pertanyaan bebas.
//  - ambilPerintah(): teks transkrip -> teks perintah tanpa kata bangun (null = hanya kata bangun / kosong).
//  - buatPelacakBicara(): kapan app sedang bicara (+ 500 ms sesudahnya) dan teks ucapan yang baru/sedang berbunyi.
//  - sisaSetelahGema(): membuang gema ucapan app (di awal, potongan >= 3 kata di mana pun, ekor sesudah kata
//    bangun); yang tersisa dianggap suara pengguna.
//  - buatJendela(): jendela perintah 6 detik dan kapan perintah dianggap selesai diucapkan.
(function (root) {
  const ZC = typeof module !== "undefined" && module.exports ? require("./zanite-cocok.js") : root.ZaniteCocok;

  const KATA_SOPAN = ["tolong", "coba", "dong", "lagi"];
  const DAFTAR = ZC.parseDaftar(ZC.DAFTAR_AWAL);
  const SENDIRI_SAJA = ZC.parseDaftar(ZC.SENDIRI_SAJA_AWAL);
  const SAPAAN_MAKS = 2;

  // cocok.js tidak diubah: FILLER-nya adalah Set yang dibaca klasifikasi(), jadi kata sopan ditambahkan di sini.
  function siapkanKataSopan() {
    for (const k of KATA_SOPAN) ZC.FILLER.add(k);
  }
  siapkanKataSopan();

  function token(teks) {
    return ZC.norm(teks).split(" ").filter(Boolean);
  }

  // "jadi" = kata bangun hanya bila langsung diikuti jelas(kan|in) dan "sekitar" muncul sesudahnya.
  // Sapaan pendek (maks 2 kata) sebelum "jadi" boleh. Hasil: teks dengan "jadi" diganti "zanite", selain itu teks asli.
  function ubahJadi(teks) {
    const tok = token(teks);
    const i = tok.indexOf("jadi");
    if (i < 0 || i > SAPAAN_MAKS) return teks;
    if (!tok.slice(0, i).every((w) => ZC.SAPAAN.has(w))) return teks;
    if (!/^jelas(kan|in)$/.test(tok[i + 1] || "")) return teks;
    if (!tok.slice(i + 2).includes("sekitar")) return teks;
    return tok.slice(0, i).concat(["zanite"], tok.slice(i + 1)).join(" ");
  }

  // "jelaskan" = perintah jelaskan sekitar (mengandung "sekitar" atau "jelas"); selain itu pertanyaan bebas.
  function jenisPerintah(teks) {
    const n = ZC.norm(teks);
    return n.includes("sekitar") || n.includes("jelas") ? "jelaskan" : "tanya";
  }

  // Teks perintah dari satu transkrip. Kata bangun di awal (atau di akhir) dibuang.
  // null = tidak ada isi perintah (kosong, atau hanya kata bangun).
  function ambilPerintah(teks) {
    const mentah = String(teks || "").trim();
    if (!mentah) return null;
    const k = ZC.klasifikasi(mentah, DAFTAR, true, SENDIRI_SAJA);
    if (k && k.tipe === "sendiri") return null;
    if (k && k.tipe === "perintah") return k.cmd;
    const c = ZC.cari(mentah, DAFTAR, true);
    if (c) {
      const tok = token(mentah);
      const sisa = c.rest ? c.rest.split(" ").length : 0;
      const awal = tok.length - sisa - c.v.split(" ").length;
      const depan = tok.slice(0, awal);
      c.rest = ZC.buangUlangan(tok.slice(tok.length - sisa), DAFTAR, true, SENDIRI_SAJA).join(" ");   // "Janet Janet ..."
      if (!c.rest) return depan.join(" ") || null;                 // kata bangun di ujung kalimat
      if (awal <= SAPAAN_MAKS && depan.every((w) => ZC.SAPAAN.has(w))) return c.rest;   // di awal, setelah sapaan
    }
    return mentah;
  }

  // ---- penyaring gema. Chrome menggabung ucapan app dan ucapan pengguna ke SATU hasil yang terus tumbuh, jadi
  // gema tidak bisa dinilai per transkrip utuh. Gema dibuang kata demi kata dari AWAL transkrip selama bisa dijelaskan
  // oleh teks ucapan app yang baru-baru ini berbunyi; sisanya (suara pengguna) yang diteruskan. App yang terus bicara
  // juga menempel SESUDAH suara pengguna, jadi di sisa itu dibuang pula (zanite-app-10): potongan >= 3 kata berurutan
  // dari satu ucapan app di mana pun, dan ekor sesudah kata bangun bila seluruhnya ucapan app. Potongan 1-2 kata di
  // tengah perintah tetap. Dipakai pemanggil HANYA untuk hasil yang kata pertamanya datang saat app bicara
  // (atau dalam ekornya); hasil yang mulai saat hening tidak pernah dipotong.
  //  - satu potongan = kata berurutan di dalam SATU teks app; potongan boleh sambung-menyambung;
  //  - kata dicocokkan dengan toleransi salah dengar Chrome: lihat samaKata();
  //  - di dalam satu potongan SATU kata boleh tidak cocok, asal kata tepat sebelum dan sesudahnya cocok dengan kata
  //    app pada posisinya ("jalur pindah terlihat" untuk "jalur tidak terlihat");
  //  - kata bangun (daftar zanite dan sendiri-saja, termasuk bentuk fuzzy) tidak pernah dianggap gema kecuali teks app
  //    memang memuat kata itu (persis, atau awalannya saat kata masih tumbuh);
  //  - potongan pertama boleh mulai di tengah kalimat (mic mulai mendengar di tengah); potongan berikutnya harus
  //    mulai di awal sebuah kalimat app, atau panjangnya >= 2 kata (satu kata yang kebetulan sama tidak ikut dimakan);
  //  - kata terpotong (>= 3 huruf, awalan kata app di posisi itu: "kendara", "terha") ikut dihitung;
  //  - kata bangun SENDIRIAN (potongan 1 kata) hanya dianggap gema selama kalimat yang memuatnya masih berbunyi.
  //    Tanpa ini "Maaf, ... Panggil Zanite lagi." membuat "Zanite" dari pengguna dibuang selama 60 detik.
  const AWALAN_MIN = 3;
  const LOMPAT_MIN = 2;

  // Pasangan ejaan baku/tidak baku: Chrome sering menulis ejaan yang berbeda dari teks yang diucapkan.
  const PASANGAN_EJAAN = [["cokelat", "coklat"], ["silahkan", "silakan"], ["antri", "antre"], ["praktek", "praktik"],
    ["apotik", "apotek"], ["aktifitas", "aktivitas"], ["telpon", "telepon"], ["trotoir", "trotoar"]];
  // tanpa tanda hubung, huruf yang berulang dirapatkan ("maaf" -> "maf")
  const rapatkan = (kata) => kata.replace(/-/g, "").replace(/(.)\1+/g, "$1");
  const EJAAN = new Map(PASANGAN_EJAAN.map(([a, b]) => [rapatkan(a), rapatkan(b)]));
  const ingatanBentuk = new Map();   // disimpan: dipakai berkali-kali untuk tiap hasil interim
  function bentuk(kata) {
    let b = ingatanBentuk.get(kata);
    if (b === undefined) {
      const r = rapatkan(kata);
      b = EJAAN.get(r) || r;
      if (ingatanBentuk.size >= 2000) ingatanBentuk.clear();
      ingatanBentuk.set(kata, b);
    }
    return b;
  }

  const ingatanVarian = new Map();   // kata -> boolean (dipanggil berkali-kali untuk tiap hasil interim)
  function adalahVarian(kata) {
    let v = ingatanVarian.get(kata);
    if (v === undefined) {
      const k = ZC.klasifikasi(kata, DAFTAR, true, SENDIRI_SAJA);
      v = !!k && k.tipe === "sendiri";
      if (ingatanVarian.size >= 2000) ingatanVarian.clear();
      ingatanVarian.set(kata, v);
    }
    return v;
  }

  // jarak edit (Levenshtein) <= maks?
  function dekatEjaan(a, b, maks) {
    if (Math.abs(a.length - b.length) > maks) return false;
    let lalu = Array.from({ length: b.length + 1 }, (_, j) => j);
    for (let i = 1; i <= a.length; i++) {
      const kini = [i];
      for (let j = 1; j <= b.length; j++) kini[j] = Math.min(lalu[j] + 1, kini[j - 1] + 1, lalu[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (Math.min(...kini) > maks) return false;
      lalu = kini;
    }
    return lalu[b.length] <= maks;
  }

  // Kata dari pengenal sama dengan kata app? Persis, awalan (>= 3 huruf), sama sesudah dinormalkan, atau jarak edit
  // <= 1 (kata 4-6 huruf) / <= 2 (7 huruf ke atas), dihitung dari kata yang lebih pendek. Kata bangun: persis/awalan saja.
  function samaKata(kata, app) {
    if (app === undefined) return false;
    if (kata === app || (kata.length >= AWALAN_MIN && app.startsWith(kata))) return true;
    if (adalahVarian(kata)) return false;
    const a = bentuk(kata), b = bentuk(app);
    if (a === b || (kata.length >= AWALAN_MIN && b.startsWith(a))) return true;
    const pendek = Math.min(kata.length, app.length);
    const maks = pendek >= 7 ? 2 : pendek >= 4 ? 1 : 0;
    return maks > 0 && dekatEjaan(a, b, maks);
  }
  // satu kata di satu sisi = dua kata di sisi lain ("tempatsampah" / "tempat sampah")
  const samaGabung = (satu, x, y) => x !== undefined && y !== undefined && !adalahVarian(satu) && bentuk(satu) === bentuk(x + y);

  // Kata ternormalisasi + posisinya di teks asli, supaya sisanya dikembalikan dengan huruf dan tanda baca asli.
  function pecah(teks) {
    const out = [];
    for (const m of String(teks).matchAll(/[\p{L}\p{M}\p{N}]+/gu)) {
      for (const k of token(m[0])) out.push({ k, i: m.index, j: m.index + m[0].length, n: out.length });
    }
    return out;
  }

  // Telusuri satu potongan: kata transkrip k mulai i dicocokkan dengan teks app a mulai posisi s.
  // sampai(t) dipanggil untuk tiap t sehingga k[i..t) cocok.
  function telusur(k, i, a, s, sampai) {
    const n = k.length;
    const antre = [[i, s, false]];      // [posisi transkrip, posisi app, sudah memakai satu kata tak cocok]
    const maju = (t, p, lompat) => { antre.push([t, p, lompat]); sampai(t); };
    while (antre.length) {
      const [t, p, lompat] = antre.pop();
      if (t >= n || p >= a.w.length) continue;
      let cocok = false;
      if (samaKata(k[t], a.w[p])) { cocok = true; maju(t + 1, p + 1, lompat); }
      if (samaGabung(k[t], a.w[p], a.w[p + 1])) { cocok = true; maju(t + 1, p + 2, lompat); }
      if (t + 1 < n && samaGabung(a.w[p], k[t], k[t + 1])) { cocok = true; maju(t + 2, p + 1, lompat); }
      // satu kata tak cocok, diapit kata yang cocok; kata bangun tidak pernah dilewati begini
      if (!cocok && !lompat && t > i && t + 1 < n && !adalahVarian(k[t]) && samaKata(k[t + 1], a.w[p + 1])) maju(t + 2, p + 2, true);
    }
  }

  // Berapa kata pertama k yang dapat dijelaskan sebagai gema (potongan sambung-menyambung).
  function awalanGema(k, app) {
    const bisa = new Array(k.length + 1).fill(false);   // bisa[n]: n kata pertama dapat dijelaskan sebagai gema
    bisa[0] = true;
    let habis = 0;
    for (let i = 0; i < k.length; i++) {
      if (!bisa[i]) continue;
      for (const a of app) {
        for (let s = 0; s < a.w.length; s++) {
          telusur(k, i, a, s, (t) => {
            if (i > 0 && s > 0 && t - i < LOMPAT_MIN) return;
            if (t - i === 1 && !a.sedang && adalahVarian(k[i])) return;
            bisa[t] = true;
            habis = Math.max(habis, t);
          });
        }
      }
    }
    return { habis, semua: bisa[k.length] };
  }

  // Potongan >= POTONGAN_MIN kata berurutan dari SATU ucapan app dibuang di mana pun (tidak disambung lintas ucapan).
  const POTONGAN_MIN = 3;
  function tanpaPotonganPanjang(kata, app) {
    const k = kata.map((x) => x.k), buang = new Array(k.length).fill(false);
    for (let i = 0; i < k.length; i++) {
      let jauh = i;
      for (const a of app) for (let s = 0; s < a.w.length; s++) telusur(k, i, a, s, (t) => { jauh = Math.max(jauh, t); });
      if (jauh - i >= POTONGAN_MIN) buang.fill(true, i, jauh);
    }
    return kata.filter((x, i) => !buang[i]);
  }

  // Sesudah kata bangun: bila SELURUH sisanya ucapan app (berapa pun katanya), sisanya dibuang. Sisa yang memuat
  // kata lain tidak disentuh, supaya perintah pengguna tidak terpotong ujungnya.
  function tanpaEkorSesudahBangun(kata, app) {
    const k = kata.map((x) => x.k);
    for (let v = 0; v < k.length; v++) {
      for (let p = 1; p <= 2; p++) {                    // varian satu kata, atau pasangan ("za net")
        if (v + p >= k.length || !adalahVarian(k.slice(v, v + p).join(" "))) continue;
        if (awalanGema(k.slice(v + p), app).semua) return kata.slice(0, v + p);
      }
    }
    return kata;
  }

  // teksApp: ucapan app 60 detik terakhir. teksSedang: yang masih berbunyi (termasuk ekor). Hasil: sisa transkrip
  // ("" = seluruhnya gema; teks asli tanpa perubahan bila tidak ada yang dibuang).
  // Urutan: (1) gema di awal, (2) potongan panjang di mana pun, (3) ekor sesudah kata bangun.
  function sisaSetelahGema(transkrip, teksApp, teksSedang) {
    const asli = String(transkrip || "");
    const kata = pecah(asli);
    const sedang = new Set(teksSedang || []);
    const app = (teksApp || []).map((t) => ({ w: token(t), sedang: sedang.has(t) })).filter((a) => a.w.length);
    let sisa = kata.slice(awalanGema(kata.map((x) => x.k), app).habis);
    sisa = tanpaEkorSesudahBangun(tanpaPotonganPanjang(sisa, app), app);
    if (sisa.length === kata.length) return asli;
    // rangkai lagi dari teks asli: tiap blok kata yang berurutan diambil utuh (huruf dan tanda baca dipertahankan)
    const blok = [];
    for (let a = 0, b; a < sisa.length; a = b) {
      for (b = a + 1; b < sisa.length && sisa[b].n === sisa[b - 1].n + 1;) b++;
      const akhir = sisa[b - 1];
      blok.push(asli.slice(sisa[a].i, akhir.n === kata.length - 1 ? asli.length : akhir.j).trim());
    }
    return blok.join(" ");
  }

  // true bila teks (>= min kata) seluruhnya potongan berurutan dari kalimat app itu.
  function potonganDari(teks, kalimat, min) {
    const a = token(teks), b = token(kalimat);
    if (a.length < min) return false;
    for (let s = 0; s + a.length <= b.length; s++) if (a.every((w, i) => samaKata(w, b[s + i]))) return true;
    return false;
  }

  // ---- pelacak "app sedang bicara". Mic tidak pernah dimatikan; transkrip yang datang saat app bicara
  // dan tailMs sesudahnya dibuang. Tiap ucapan punya batas pengaman (onend kadang tidak datang di Chrome HP).
  //
  // Sumber kebenaran: ucapan app yang TERCATAT di pelacak. speechSynthesis.speaking sendiri tidak cukup
  // (bisa macet true di Chrome Android -> Zanite tuli). Satu ucapan dihitung "bicara" selama tercatat DAN
  // (sintesis speaking/pending ATAU baru mulai < mulaiMs lalu). Bila sintesis sudah tidak speaking/pending
  // selama paksaMs tetapi onend tidak datang, ucapan itu diakhiri paksa ("selesai-paksa").
  // opsi: mulaiMs (1500), paksaMs (1000), gemaMs (60000: teks ucapan yang sudah selesai masih dihitung untuk
  // penyaring gema), catat(teks) untuk log.
  function buatPelacakBicara(jam, tailMs, opsi) {
    const tail = tailMs == null ? 500 : tailMs;
    const o = Object.assign({ mulaiMs: 1500, paksaMs: 1000, gemaMs: 60000, catat: null }, opsi || {});
    const aktif = new Map();   // id -> { mati (batas pengaman), tMulai, tAktif (terakhir sintesis terlihat aktif), sintesis }
    let n = 0, akhir = -Infinity, terakhirBicara = -Infinity, paksa = 0, dibatalkan = 0;
    const baruSelesai = [];    // { teks, t }: ucapan yang baru berakhir (untuk penyaring gema)
    const catatSelesai = (e, t) => { if (e.teks) baruSelesai.push({ teks: e.teks, t }); };
    const lapor = (t) => { if (o.catat) o.catat(t); };
    // Ucapan yang berakhir tanpa onend/onerror (cancel, selesai-paksa, pengaman): pemilik janji ucapannya diberi tahu
    // saat itu juga supaya tidak menunggu pengaman 15-20 detik.
    const putus = (e, alasan) => { if (e.saatPutus) { try { e.saatPutus(alasan); } catch (x) { /* abaikan */ } } };

    // Perbarui keadaan dari pengamatan sintesis. Dipanggil tiap sedangBicara() dan oleh pemantau berkala.
    function segarkan(speaking, pending) {
      const t = jam(), sint = !!(speaking || pending);
      for (const [id, e] of aktif) {
        if (t >= e.mati) { aktif.delete(id); akhir = Math.max(akhir, e.mati); catatSelesai(e, e.mati); putus(e, "pengaman"); continue; }
        if (!e.sintesis) continue;
        if (sint) { e.tAktif = t; continue; }
        if (t - e.tAktif >= o.paksaMs && t - e.tMulai >= o.mulaiMs) {
          aktif.delete(id);
          akhir = Math.max(akhir, e.tAktif);   // ekor dihitung dari akhir sintesis terakhir yang terlihat
          catatSelesai(e, e.tAktif);
          paksa += 1;
          lapor("selesai-paksa: onend tidak datang, sintesis diam " + Math.round(t - e.tAktif) + " ms");
          putus(e, "paksa");
        }
      }
    }

    return {
      // opsi.tanpaSintesis: bunyi yang bukan speechSynthesis (bip): dihitung sampai selesai() atau batas pengaman
      mulai(batasMs, opsiUcapan) {
        const id = ++n, t = jam();
        const ou = opsiUcapan || {};
        aktif.set(id, { mati: t + batasMs, tMulai: t, tAktif: t, sintesis: !ou.tanpaSintesis, saatPutus: ou.saatPutus, teks: ou.teks || "", tingkat: ou.tingkat });
        return id;
      },
      selesai(id) {
        const e = aktif.get(id);
        if (!e) return;
        aktif.delete(id);
        akhir = Math.max(akhir, jam());
        catatSelesai(e, jam());
      },
      // synth.cancel() memutus semua ucapan yang ada; onend/onerror-nya belum tentu datang. Ucapan baru
      // sesudahnya (yang di-speak() setelah cancel) mendapat catatannya sendiri.
      selesaiSemua() {
        const jumlah = aktif.size;
        if (jumlah) {
          const lama = [...aktif.values()];
          aktif.clear();
          akhir = Math.max(akhir, jam());
          dibatalkan += jumlah;
          for (const e of lama) catatSelesai(e, jam());
          for (const e of lama) putus(e, "cancel");
        }
        return jumlah;
      },
      // speaking / pending: speechSynthesis.speaking dan .pending (boleh kosong)
      sedangBicara(speaking, pending) {
        segarkan(speaking, pending);
        const t = jam(), sint = !!(speaking || pending);
        let bicara = false;
        for (const e of aktif.values()) if (!e.sintesis || sint || t - e.tMulai < o.mulaiMs) { bicara = true; break; }
        if (bicara) terakhirBicara = t;
        return bicara || t < Math.max(akhir, terakhirBicara) + tail;
      },
      jumlah: () => aktif.size,
      // peringatan tingkat 3 yang masih tercatat berbunyi: tidak boleh dipotong oleh kata bangun
      adaTingkat3: () => { for (const e of aktif.values()) if (e.tingkat === 3) return true; return false; },
      // teks ucapan yang sedang berbunyi + yang selesai < gemaMs lalu (bahan penyaring gema), tanpa duplikat
      teksBicara() {
        const t = jam(), out = new Set();
        for (const e of aktif.values()) if (e.teks) out.add(e.teks);
        for (let i = baruSelesai.length - 1; i >= 0; i--) if (t - baruSelesai[i].t >= o.gemaMs) baruSelesai.splice(i, 1);
        for (const b of baruSelesai) out.add(b.teks);
        return [...out];
      },
      // teks yang masih berbunyi: ucapan tercatat + yang selesai di dalam ekor tailMs
      teksSedang() {
        const t = jam(), out = new Set();
        for (const e of aktif.values()) if (e.teks) out.add(e.teks);
        for (const b of baruSelesai) if (t - b.t < tail) out.add(b.teks);
        return [...out];
      },
      statistik: () => ({ paksa, dibatalkan }),
    };
  }

  // Kata seru / pengisi: "perintah" yang isinya hanya ini diabaikan, jendela terus menunggu.
  const PENGISI = new Set(["oh", "eh", "hmm", "ya", "nah", "oke", "ok", "hah", "ha"]);
  const hanyaPengisi = (teks) => token(teks).every((w) => PENGISI.has(w));

  // ---- jendela perintah. Tanpa timer: pemanggil menjadwalkan jatuhTempo() lalu memanggil periksa().
  // opsi: t (waktu buka), bukaMs (6000), diamTanyaMs, diamJelaskanMs, setelahFinalMs, maksBicaraMs,
  // gema(cmd) -> true bila "perintah" itu hanya gema balasan app (diabaikan)
  function buatJendela(opsi) {
    const o = Object.assign({ t: 0, bukaMs: 6000, diamTanyaMs: 1200, diamJelaskanMs: 700, setelahFinalMs: 200, maksBicaraMs: 10000, inline: false }, opsi || {});
    const entri = new Map();   // kunci hasil Chrome -> { cmd, final }
    const S = { pertama: null, ubah: null, cmd: "", final: false, selesai: false };

    function gabung() { return [...entri.values()].map((e) => e.cmd).join(" ").replace(/\s+/g, " ").trim(); }
    function diam() { return S.final ? o.setelahFinalMs : jenisPerintah(S.cmd) === "jelaskan" ? o.diamJelaskanMs : o.diamTanyaMs; }

    return {
      inline: o.inline,
      terima(t, key, teks, final) {
        if (S.selesai) return;
        let cmd = ambilPerintah(teks);
        if (cmd !== null && (hanyaPengisi(cmd) || (o.gema && o.gema(cmd)))) cmd = null;
        if (cmd === null) { entri.delete(key); }   // hanya kata bangun / pengisi / gema balasan: bukan perintah
        else entri.set(key, { cmd, final: !!final });
        const baru = gabung();
        if (!baru) { S.cmd = ""; S.pertama = null; S.ubah = null; return; }   // ditarik kembali: jangan kirim kosong
        if (S.pertama === null) S.pertama = t;
        if (baru !== S.cmd) S.ubah = t;
        S.cmd = baru;
        S.final = [...entri.values()].every((e) => e.final);
      },
      // null | {aksi:"kirim", teks, jenis} | {aksi:"tutup", alasan:"habis"}
      periksa(t) {
        if (S.selesai) return null;
        if (S.pertama === null) return t - o.t >= o.bukaMs ? (S.selesai = true, { aksi: "tutup", alasan: "habis" }) : null;
        if (t - S.ubah >= diam() || t - S.pertama >= o.maksBicaraMs) {
          S.selesai = true;
          return { aksi: "kirim", teks: S.cmd, jenis: jenisPerintah(S.cmd) };
        }
        return null;
      },
      jatuhTempo() {
        if (S.selesai) return null;
        if (S.pertama === null) return o.t + o.bukaMs;
        return Math.min(S.ubah + diam(), S.pertama + o.maksBicaraMs);
      },
      tutup() { S.selesai = true; },
      teks: () => S.cmd,
    };
  }

  // ---- laporan uji untuk "Salin log Zanite" dan unggahan log. Murni: teks dari angka dan baris yang diberikan pemanggil.
  // info: { header: {nama: nilai}, hitung: {nama: nilai | {kunci: nilai}}, baris: [teks] }
  function susunKepala(info) {
    const out = [];
    const nilai = (v) => {
      if (v && typeof v === "object") {
        const k = Object.keys(v).sort();
        return k.length ? k.map((x) => x + "=" + v[x]).join(", ") : "-";
      }
      return v === undefined || v === null || v === "" ? "-" : String(v);
    };
    out.push("== LOG ZANITE ==");
    for (const [k, v] of Object.entries(info.header || {})) out.push(k + ": " + nilai(v));
    out.push("", "== HITUNGAN ==");
    for (const [k, v] of Object.entries(info.hitung || {})) out.push(k + ": " + nilai(v));
    return out.join("\n");
  }

  function susunLaporan(info) {
    const baris = (info.baris || []).slice(-300);
    return [susunKepala(info), "", "== " + baris.length + " BARIS TERAKHIR ==", ...baris].join("\n");
  }

  const api = { KATA_SOPAN, siapkanKataSopan, ubahJadi, jenisPerintah, ambilPerintah, buatPelacakBicara, sisaSetelahGema, potonganDari, buatJendela, susunKepala, susunLaporan };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ZaniteAturan = api;
})(typeof window !== "undefined" ? window : globalThis);
