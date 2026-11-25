// Aturan keputusan Zanite yang murni (tanpa DOM, tanpa timer): dipakai zanite.js dan dites di Node
// dengan jam palsu (tests/zanite/tes_aturan.js).
//
//  - siapkanKataSopan(): "tolong, coba, dong, lagi" boleh ada di antara varian dan perintah.
//  - ubahJadi(): Chrome menulis "Zanite" sebagai "jadi"; hanya dihitung bila langsung diikuti perintah penuh.
//  - jenisPerintah(): "jelaskan sekitar" (mengandung sekitar/jelas) atau pertanyaan bebas.
//  - ambilPerintah(): teks transkrip -> teks perintah tanpa kata bangun (null = hanya kata bangun / kosong).
//  - buatPelacakBicara(): kapan app sedang bicara (+ 500 ms sesudahnya) dan teks ucapan yang baru/sedang berbunyi.
//  - sisaSetelahGema(): membuang gema ucapan app dari AWAL transkrip; yang tersisa dianggap suara pengguna.
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
  // oleh teks ucapan app yang baru-baru ini berbunyi; sisanya (suara pengguna) yang diteruskan. Kata sesudah suara
  // pengguna tidak pernah disentuh.
  //  - satu potongan = kata berurutan di dalam SATU teks app; potongan boleh sambung-menyambung;
  //  - potongan pertama boleh mulai di tengah kalimat (mic mulai mendengar di tengah); potongan berikutnya harus
  //    mulai di awal sebuah kalimat app, atau panjangnya >= 2 kata (satu kata yang kebetulan sama tidak ikut dimakan);
  //  - kata terpotong (>= 3 huruf, awalan kata app di posisi itu: "kendara", "terha") ikut dihitung;
  //  - kata bangun SENDIRIAN (potongan 1 kata) hanya dianggap gema selama kalimat yang memuatnya masih berbunyi.
  //    Tanpa ini "Maaf, ... Panggil Zanite lagi." membuat "Zanite" dari pengguna dibuang selama 60 detik.
  const AWALAN_MIN = 3;
  const LOMPAT_MIN = 2;

  const samaKata = (kata, app) => app !== undefined && (kata === app || (kata.length >= AWALAN_MIN && app.startsWith(kata)));
  const adalahVarian = (kata) => { const k = ZC.klasifikasi(kata, DAFTAR, true, SENDIRI_SAJA); return !!k && k.tipe === "sendiri"; };

  // Kata ternormalisasi + posisinya di teks asli, supaya sisanya dikembalikan dengan huruf dan tanda baca asli.
  function pecah(teks) {
    const out = [];
    for (const m of String(teks).matchAll(/[\p{L}\p{M}\p{N}]+/gu)) for (const k of token(m[0])) out.push({ k, i: m.index });
    return out;
  }

  // teksApp: ucapan app 60 detik terakhir. teksSedang: yang masih berbunyi (termasuk ekor). Hasil: sisa transkrip
  // ("" = seluruhnya gema; teks asli tanpa perubahan bila tidak ada yang dibuang).
  function sisaSetelahGema(transkrip, teksApp, teksSedang) {
    const asli = String(transkrip || "");
    const kata = pecah(asli);
    const sedang = new Set(teksSedang || []);
    const app = (teksApp || []).map((t) => ({ w: token(t), sedang: sedang.has(t) })).filter((a) => a.w.length);
    const bisa = new Array(kata.length + 1).fill(false);   // bisa[n]: n kata pertama dapat dijelaskan sebagai gema
    bisa[0] = true;
    let habis = 0;
    for (let i = 0; i < kata.length; i++) {
      if (!bisa[i]) continue;
      for (const a of app) {
        for (let s = 0; s < a.w.length; s++) {
          for (let l = 1; i + l <= kata.length && samaKata(kata[i + l - 1].k, a.w[s + l - 1]); l++) {
            if (i > 0 && s > 0 && l < LOMPAT_MIN) continue;
            if (l === 1 && !a.sedang && adalahVarian(kata[i].k)) continue;
            bisa[i + l] = true;
            habis = Math.max(habis, i + l);
          }
        }
      }
    }
    if (!habis) return asli;
    return habis >= kata.length ? "" : asli.slice(kata[habis].i).trim();
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
        if (cmd !== null && o.gema && o.gema(cmd)) cmd = null;
        if (cmd === null) { entri.delete(key); }   // hanya kata bangun: bukan perintah
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

  // ---- laporan uji untuk "Salin log Zanite". Murni: teks dari angka dan baris yang diberikan pemanggil.
  // info: { header: {nama: nilai}, hitung: {nama: nilai | {kunci: nilai}}, baris: [teks] }
  function susunLaporan(info) {
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
    const baris = (info.baris || []).slice(-300);
    out.push("", "== " + baris.length + " BARIS TERAKHIR ==");
    for (const b of baris) out.push(b);
    return out.join("\n");
  }

  const api = { KATA_SOPAN, siapkanKataSopan, ubahJadi, jenisPerintah, ambilPerintah, buatPelacakBicara, sisaSetelahGema, potonganDari, buatJendela, susunLaporan };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ZaniteAturan = api;
})(typeof window !== "undefined" ? window : globalThis);
