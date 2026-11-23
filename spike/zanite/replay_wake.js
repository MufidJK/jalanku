// Replay offline: jalankan pemicu kalibrasi 3 pada blok "TRANSKRIP PER FASE" dari "Salin hasil".
//   node spike/zanite/replay_wake.js data/zanite/mentah_kalibrasi2_retest.txt
// Format baris: hh:mm:ss[.mmm] F|i [*]"teks" (conf) alt: ... <cocok>   dan header [fase nama]
// Baris bertanda * (app sedang bicara) dilewati. Stempel waktu versi lama hanya sampai detik, jadi ada dua mode:
//   tengah: jeda antar baris = kelipatan 1 dtk; >= 1 dtk dianggap >= 800 ms diam, >= 2 dtk dianggap ucapan baru
//   ketat : >= 2 dtk dianggap >= 800 ms diam, >= 3 dtk dianggap ucapan baru (batas bawah pasti)
// Bila stempel punya milidetik (kalibrasi 3 ke atas), dipakai mode "tepat" dengan ambang asli.
const fs = require("fs");
const Z = require("./hp/cocok.js");
const file = process.argv[2];
if (!file) { console.log("pakai: node replay_wake.js <berkas salinan>"); process.exit(1); }
const baris = fs.readFileSync(file, "utf8").split(/\r?\n/);
const mulai = baris.findIndex((b) => /TRANSKRIP PER FASE/.test(b));
if (mulai < 0) { console.log("blok TRANSKRIP PER FASE tidak ditemukan"); process.exit(1); }
const RE = /^(\d\d):(\d\d):(\d\d)(?:\.(\d+))? ([Fi]) (\*?)"(.*?)"(?=$| \(| alt:| <)/;
const data = []; let fase = "?", adaMs = false;
for (let i = mulai + 1; i < baris.length; i++) {
  const b = baris[i];
  if (/^-- /.test(b)) break;
  const h = b.match(/^\[fase (.+)\]$/); if (h) { fase = h[1]; continue; }
  const m = b.match(RE); if (!m) continue;
  if (m[4]) adaMs = true;
  const t = (+m[1] * 3600 + +m[2] * 60 + +m[3]) * 1000 + (m[4] ? +m[4].padEnd(3, "0").slice(0, 3) : 0);
  data.push({ t, fase, final: m[5] === "F", self: m[6] === "*", teks: m[7] });
}
const tanpaArg = process.argv.indexOf("--tanpa");   // contoh: --tanpa jani,dani  (uji pengandaian: buang varian hanya-sendiri ini)
const buang = tanpaArg > 0 ? process.argv[tanpaArg + 1].split(",") : [];
const D = Z.parseDaftar(Z.DAFTAR_AWAL), SS = Z.parseDaftar(Z.SENDIRI_SAJA_AWAL).filter((v) => !buang.includes(v));

function jalankan(diam, jeda, weak) {
  const P = Z.buatPemicu(() => ({ daftar: D, sendiriSaja: SS, fuzzy: true }), diam, jeda, weak);
  let key = 0, faseNow = "?";
  const wake = [], ditolak = [], kontra = [];
  const tampung = (ev) => ev.forEach((e) => {
    if (e.type === "ucapan") e.utt.fase = faseNow;
    if (e.type === "wake") { wake.push(e); e.utt.how = e.how + ":" + e.v; e.utt.tipe = e.tipe; }
    if (e.type === "kontradiksi") kontra.push(e);
  });
  for (const x of data) {
    if (x.self) continue;
    faseNow = x.fase;
    tampung(P.masuk(x.t, "k" + key, x.teks, x.final));
    if (x.final) key++;
  }
  tampung(P.selesai());
  const per = {};
  for (const u of P.utts) {
    const f = per[u.fase] || (per[u.fase] = { ucapan: 0, wake: 0, ditolak: 0, tanpa: 0, kontra: 0, daftar: [] });
    f.ucapan++; if (u.outcome === "wake") f.wake++; else if (u.outcome === "ditolak") f.ditolak++; else f.tanpa++;
    if (u.kontra) f.kontra++;
    if (u.how) { const j = u.how.split(":")[0]; f.jalur = f.jalur || {}; f.jalur[j] = (f.jalur[j] || 0) + 1; }
    f.daftar.push(`  #${u.id} ${u.outcome}${u.how ? " [" + u.how + "]" : ""}${u.kontra ? " (final kemudian: \"" + u.kontra + "\")" : ""}  "${u.last}"`);
  }
  return per;
}
// Tiga aturan varian lemah (jani, janis, janin, dani, danis, danid): lemah@800, lemah@1200, final-saja.
// Pada stempel per detik, ambang "ketat" harus melewati batas bawah pasti: selisih detik d berarti jeda sebenarnya
// antara d-1 dan d+1 dtk, jadi 800 ms pasti terpenuhi bila d >= 2, dan 1200 ms bila d >= 3.
const mode = adaMs
  ? [["tepat (ms asli)", 800, 1500, { "lemah@800": 800, "lemah@1200": 1200, "final-saja": Infinity }]]
  : [["tengah", 800, 1500, { "lemah@800": 800, "lemah@1200": 1200, "final-saja": Infinity }],
     ["ketat", 1800, 2500, { "lemah@800": 1800, "lemah@1200": 2800, "final-saja": Infinity }]];
console.log("baris transkrip dibaca: " + data.length + " (dilewati karena app bicara: " + data.filter((x) => x.self).length + ")");
if (buang.length) console.log("PENGANDAIAN: varian hanya-sendiri dibuang: " + buang.join(", "));
console.log("resolusi waktu: " + (adaMs ? "milidetik" : "detik (perkiraan)"));
for (const [nama, diam, jeda, weaks] of mode) {
  console.log("\n=== mode " + nama + " (diam utama " + diam + " ms, pisah ucapan " + jeda + " ms) ===");
  for (const [pn, weak] of Object.entries(weaks)) {
    console.log("-- aturan " + pn + (isFinite(weak) ? " (varian lemah menyala setelah " + weak + " ms)" : "") + " --");
    const per = jalankan(diam, jeda, weak);
    for (const f of Object.keys(per)) {
      const r = per[f];
      console.log(`[fase ${f}] ucapan ${r.ucapan}: wake ${r.wake}, ditolak ${r.ditolak}, tanpa varian ${r.tanpa}, kontradiksi ${r.kontra}` +
        (r.jalur ? "  jalur: " + Object.keys(r.jalur).map((k) => k + "=" + r.jalur[k]).join(", ") : ""));
      if (process.argv.includes("--rinci")) r.daftar.forEach((l) => console.log(l));
    }
  }
}
