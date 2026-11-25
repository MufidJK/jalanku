// Pencocok + pemicu kata bangun "Zanite" (dipakai halaman tes, tes Node, dan replay offline). Tanpa DOM.
//
// Lapis 1, cari(): mendeteksi VARIAN di mana pun dalam kalimat (daftar eksplisit + aturan fuzzy + pasangan).
// Lapis 2, klasifikasi(): aturan BERDIRI SENDIRI (kalibrasi 3). Wake hanya boleh menyala bila:
//   a) transkrip hanya berisi varian (tipe "sendiri"; varian yang diulang, "Janet Janet", dihitung satu), atau
//   b) varian langsung diikuti frasa perintah: jelaskan / jelasin / sekitar (boleh sela "dong", "ya", "deh")
//      (tipe "perintah"; kata setelah frasa perintah boleh ada, ikut jadi teks perintah).
//   Sebelum varian boleh ada sapaan pendek (maks 2 kata dari: eh hei hai halo oi woi oke ok ya nah tolong).
//   Selain itu (kata lain sebelum varian, atau kata lain langsung sesudahnya) = "ditolak".
// Lapis 3, buatPemicu(): mesin ucapan. Satu ucapan dimulai oleh transkrip baru pertama setelah >= 1,5 dtk tanpa
//   transkrip baru. Tipe "sendiri" menyala setelah 800 ms tanpa kata baru, atau saat final datang. Tipe "perintah"
//   menyala langsung. Satu ucapan menyalakan wake paling banyak sekali.
//
// Varian "SENDIRI_SAJA" (jani, janis, janin, janette, dani, danis, danid, danite) hanya dikenali oleh klasifikasi(),
// tidak pernah oleh cari(), sehingga tidak bisa menyala di dalam kalimat panjang. Di antaranya jani, janis, janin,
// dani, danis, danid (VARIAN_LEMAH) menyala dari transkrip final ATAU dari interim yang tidak berubah selama weakMs
// (bawaan 1200 ms); janette, danite, dan varian utama memakai diamMs (bawaan 800 ms). weakMs = Infinity berarti final-saja.
(function (root) {
  const DAFTAR_AWAL = "zanite, zanit, sanit, zenit, zanith, xanit, janit, janet, janite, zanet, sanet, jenit, jenet, zenet";
  const SENDIRI_SAJA_AWAL = "jani, janis, janin, janette, dani, danis, danid, danite";
  // Varian pendek yang sering muncul sebagai kedipan interim awalan kata lain ("Jani" sebelum "janit ..."):
  // menyala dari transkrip final, atau dari interim yang bertahan weakMs (lebih lama dari diamMs).
  const VARIAN_LEMAH = new Set(["jani", "janis", "janin", "dani", "danis", "danid"]);
  const FUZZY = /^(?:z|j|s|x|dz|zh)an[ie][td][eh]?$/;
  const AWAL_PASANGAN = new Set(["za", "ja", "sa", "xa", "dza"]);
  const FILLER = new Set(["dong", "ya", "deh"]);
  const KATA_PERINTAH = new Set(["jelaskan", "jelasin", "sekitar"]);
  const SAPAAN = new Set(["eh", "hei", "hai", "halo", "oi", "woi", "oke", "ok", "ya", "nah", "tolong"]);
  const SAPAAN_MAKS = 2;

  function norm(s) {
    return String(s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9]+/g, " ").trim();
  }
  function parseDaftar(teks) { return String(teks).split(",").map(norm).filter(Boolean); }

  // Varian paling awal di token. Kembalikan {i, len, v, how} atau null.
  // how: "daftar" | "sendiri-saja" | "fuzzy" | "pasangan"
  function lokasi(tok, daftar, fuzzyAktif, sendiriSaja) {
    const frasa = (lst, i) => {
      for (const v of lst) {
        const w = v.split(" ");
        if (w.length && w.every((x, k) => tok[i + k] === x)) return w.length;
      }
      return 0;
    };
    for (let i = 0; i < tok.length; i++) {
      let n = frasa(daftar || [], i);
      if (n) return { i, len: n, v: tok.slice(i, i + n).join(" "), how: "daftar" };
      n = frasa(sendiriSaja || [], i);
      if (n) return { i, len: n, v: tok.slice(i, i + n).join(" "), how: "sendiri-saja" };
      if (fuzzyAktif !== false) {
        if (FUZZY.test(tok[i])) return { i, len: 1, v: tok[i], how: "fuzzy" };
        if (AWAL_PASANGAN.has(tok[i]) && i + 1 < tok.length && FUZZY.test(tok[i] + tok[i + 1])) {
          return { i, len: 2, v: tok[i] + " " + tok[i + 1], how: "pasangan" };
        }
      }
    }
    return null;
  }

  // Lapis 1: varian di mana saja (tanpa SENDIRI_SAJA). Kembalikan {v, how, rest} atau null.
  function cari(raw, daftar, fuzzyAktif) {
    const tok = norm(raw).split(" ").filter(Boolean);
    const L = lokasi(tok, daftar, fuzzyAktif, []);
    return L ? { v: L.v, how: L.how, rest: tok.slice(L.i + L.len).join(" ") } : null;
  }

  // Varian yang diulang di awal token ("Janet Janet") dibuang: pengulangan dihitung satu panggilan.
  function buangUlangan(tok, daftar, fuzzyAktif, sendiriSaja) {
    let sisa = tok, U;
    while (sisa.length && (U = lokasi(sisa, daftar, fuzzyAktif, sendiriSaja)) && U.i === 0) sisa = sisa.slice(U.len);
    return sisa;
  }

  // Lapis 2: aturan berdiri sendiri. null = tidak ada varian.
  function klasifikasi(raw, daftar, fuzzyAktif, sendiriSaja) {
    const tok = norm(raw).split(" ").filter(Boolean);
    const L = lokasi(tok, daftar, fuzzyAktif, sendiriSaja);
    if (!L) return null;
    const dasar = { v: L.v, how: L.how, teks: raw };
    // sapaan pendek (maks 2 kata dari SAPAAN) sebelum varian boleh; kata lain sebelum varian = ditolak
    if (L.i > SAPAAN_MAKS || !tok.slice(0, L.i).every((w) => SAPAAN.has(w))) return Object.assign(dasar, { tipe: "ditolak", alasan: "ada kata lain" });
    const rest = buangUlangan(tok.slice(L.i + L.len), daftar, fuzzyAktif, sendiriSaja);
    if (!rest.length) return Object.assign(dasar, { tipe: "sendiri" });
    let k = 0;
    while (k < rest.length && FILLER.has(rest[k])) k++;
    if (k < rest.length && KATA_PERINTAH.has(rest[k])) {
      return Object.assign(dasar, { tipe: "perintah", cmd: rest.slice(k).join(" ") });
    }
    return Object.assign(dasar, { tipe: "ditolak", alasan: "ada kata lain" });
  }

  // Lapis 3: mesin ucapan. cfg() -> {daftar, sendiriSaja, fuzzy} (dibaca tiap kali, jadi bisa diubah langsung).
  // diamMs / jedaUcapanMs / weakMs boleh angka atau fungsi (dibaca tiap kali, jadi bisa diubah dari halaman).
  function buatPemicu(cfg, diamMsArg, jedaUcapanMsArg, weakMsArg) {
    const nilai = (x, d) => (typeof x === "function" ? x() : x == null ? d : x);
    const diamMs = () => nilai(diamMsArg, 800), jedaUcapanMs = () => nilai(jedaUcapanMsArg, 1500), weakMs = () => nilai(weakMsArg, 1200);
    const S = { cur: null, lastNew: -Infinity, last: new Map(), armed: null, utts: [], nid: 0 };
    const klas = (teks) => { const c = cfg(); return klasifikasi(teks, c.daftar, c.fuzzy, c.sendiriSaja); };
    function mulaiUcapan(t, teks, ev) {
      S.cur = { id: ++S.nid, t0: t, last: teks, outcome: "tanpa-variant", fired: false, kontra: "", fase: "", rejLogged: false };
      S.utts.push(S.cur);
      ev.push({ type: "ucapan", t, utt: S.cur });
    }
    function nyalakan(t, k, teks, ev) {
      S.cur.fired = true; S.cur.outcome = "wake"; S.cur.wakeAt = t; S.armed = null;
      ev.push({ type: "wake", t, tipe: k.tipe, v: k.v, how: k.how, cmd: k.cmd || "", teks, utt: S.cur });
    }
    function tick(t) {
      const ev = [];
      if (S.armed && t >= S.armed.at) {
        const a = S.armed; S.armed = null;
        if (S.cur && !S.cur.fired) nyalakan(a.at, a.k, a.teks, ev);
      }
      return ev;
    }
    function masuk(t, key, teks, final) {
      const ev = tick(t);
      const changed = S.last.get(key) !== teks;
      S.last.set(key, teks);
      if (!changed && !final) return ev;
      if (changed) {
        if (!S.cur || t - S.lastNew >= jedaUcapanMs()) mulaiUcapan(t, teks, ev);
        S.lastNew = t; S.cur.last = teks; S.armed = null;      // kata baru membatalkan hitung mundur 800 ms
      } else if (!S.cur) { mulaiUcapan(t, teks, ev); S.lastNew = t; }
      const k = klas(teks);
      if (!k) return ev;
      const lemah = k.how === "sendiri-saja" && VARIAN_LEMAH.has(k.v);
      const tunggu = lemah ? weakMs() : diamMs();            // Infinity = tidak pernah dari interim
      if (k.tipe === "sendiri") {
        if (!S.cur.fired) {
          if (final) nyalakan(t, k, teks, ev);
          else if (isFinite(tunggu)) S.armed = { at: t + tunggu, k, teks };
        }
      } else if (k.tipe === "perintah") {
        if (!S.cur.fired) {
          if (final || !lemah) nyalakan(t, k, teks, ev);       // varian utama + perintah: langsung
          else if (isFinite(tunggu)) S.armed = { at: t + tunggu, k, teks };
        }
        else ev.push({ type: "perintah-update", t, cmd: k.cmd, utt: S.cur });
      } else if (!S.cur.fired) {
        S.cur.outcome = "ditolak";
        ev.push({ type: "ditolak", t, teks, final, utt: S.cur });
      } else if (final) {
        S.cur.kontra = teks;
        ev.push({ type: "kontradiksi", t, teks, utt: S.cur });
      }
      return ev;
    }
    return { masuk, tick, nextDue: () => (S.armed ? S.armed.at : null), utts: S.utts, selesai: () => tick(Infinity) };
  }

  const api = { DAFTAR_AWAL, SENDIRI_SAJA_AWAL, FUZZY, FILLER, KATA_PERINTAH, SAPAAN, VARIAN_LEMAH, norm, parseDaftar, cari, klasifikasi, buangUlangan, buatPemicu };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ZaniteCocok = api;
})(typeof window !== "undefined" ? window : globalThis);
