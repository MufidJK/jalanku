// Tes aturan keputusan Zanite yang murni (src/web/zanite-aturan.js), jam palsu, tanpa browser:
//   node tests/zanite/tes_aturan.js
const ZC = require("../../src/web/zanite-cocok.js");
const ZA = require("../../src/web/zanite-aturan.js");

let total = 0, gagal = 0;
const cek = (nama, ok, info) => { total++; if (!ok) { gagal++; console.log("GAGAL:", nama, info === undefined ? "" : JSON.stringify(info)); } };
const D = ZC.parseDaftar(ZC.DAFTAR_AWAL), SS = ZC.parseDaftar(ZC.SENDIRI_SAJA_AWAL);
const kl = (t) => ZC.klasifikasi(t, D, true, SS);

// ---- "jadi": hanya bila langsung diikuti perintah penuh jelas(kan|in) ... sekitar
for (const [t, h] of [
  ["jadi jelaskan sekitar", "zanite jelaskan sekitar"],
  ["Jadi, jelasin sekitar gue dong", "zanite jelasin sekitar gue dong"],
  ["halo jadi jelaskan sekitar", "halo zanite jelaskan sekitar"],
  ["eh hei jadi jelasin sekitar", "eh hei zanite jelasin sekitar"],
  ["jadi jelaskan apa yang ada di sekitar saya", "zanite jelaskan apa yang ada di sekitar saya"],
]) cek("jadi diubah: " + t, ZA.ubahJadi(t) === h, ZA.ubahJadi(t));
for (const t of ["jadi", "jadi jelaskan", "jadi jelasin dong", "jadi sekitar", "jadi dong jelaskan sekitar", "jadi apa itu",
  "kamu jadi jelaskan sekitar", "eh hei halo jadi jelaskan sekitar", "jelaskan sekitar jadi", "ya sudah jadi jelaskan sekitar",
  "jelaskan sekitar", "saya jadi bingung di sekitar sini", "jadi jelaskan lagi nanti"])
  cek("jadi TIDAK diubah: " + t, ZA.ubahJadi(t) === t, ZA.ubahJadi(t));
{ const k = kl(ZA.ubahJadi("jadi jelaskan sekitar")); cek("jadi -> wake perintah", k && k.tipe === "perintah" && k.cmd === "jelaskan sekitar", k); }
cek("jadi tanpa perintah penuh bukan wake", kl(ZA.ubahJadi("jadi jelaskan")) === null && kl("jadi jelaskan sekitar") === null);

// ---- kata sopan antara varian dan perintah
for (const [t, c] of [
  ["zanite tolong jelaskan sekitar", "jelaskan sekitar"], ["Zanite, coba jelasin sekitar", "jelasin sekitar"],
  ["janit dong jelaskan", "jelaskan"], ["zanite lagi jelaskan sekitar", "jelaskan sekitar"],
  ["zanite tolong coba jelasin sekitar gue", "jelasin sekitar gue"], ["zanite ya jelasin", "jelasin"],     // "ya" bawaan spike tetap
  ["halo zanite tolong sekitar", "sekitar"],
]) { const k = kl(t); cek("sopan: " + t, k && k.tipe === "perintah" && k.cmd === c, k); }
for (const t of ["zanite tolong", "zanite coba", "zanite lagi", "zanite lagi di mana", "zanite tolong ambilkan air", "zanite coba tebak"])
  { const k = kl(t); cek("sopan tanpa perintah ditolak: " + t, k && k.tipe === "ditolak", k); }
cek("kata sopan didaftarkan", ZA.KATA_SOPAN.every((w) => ZC.FILLER.has(w)));

// ---- jenis perintah
for (const t of ["jelaskan sekitar", "jelasin sekitar gue dong", "sekitar", "jelas", "jelasin", "Apa yang ada di sekitar saya?", "tolong jelaskan"])
  cek("jelaskan: " + t, ZA.jenisPerintah(t) === "jelaskan");
for (const t of ["itu apa di depan?", "ada tangga nggak", "apakah jalannya aman", "warna bajunya apa", "baca tulisan itu", ""])
  cek("tanya: " + t, ZA.jenisPerintah(t) === "tanya");

// ---- ambilPerintah: kata bangun dibuang
for (const [t, h] of [
  ["zanite jelaskan sekitar", "jelaskan sekitar"], ["Zanite itu apa di depan", "itu apa di depan"], ["eh zanite apa itu", "apa itu"],
  ["jelaskan sekitar zanite", "jelaskan sekitar"], ["itu apa di depan?", "itu apa di depan?"], ["Zanite, jelasin dong", "jelasin dong"],
  ["itu janet temanku", "itu janet temanku"],
]) cek("ambilPerintah: " + t, ZA.ambilPerintah(t) === h, ZA.ambilPerintah(t));
for (const t of ["", "   ", "Zanite", "janet", "jani", "Danis", "eh zanite", "za nit"]) cek("ambilPerintah null: " + t, ZA.ambilPerintah(t) === null, ZA.ambilPerintah(t));

// ---- pelacak "app bicara": transkrip dibuang selama bicara + 500 ms.
// Sumber kebenaran = ucapan yang TERCATAT; speechSynthesis.speaking sendiri tidak cukup (bisa macet true).
{ // alur normal: ucapan tercatat + sintesis aktif, selesai lewat onend
  let t = 0; const jam = () => t;
  const p = ZA.buatPelacakBicara(jam, 500);
  cek("diam di awal", !p.sedangBicara(false, false));
  t = 100; const a = p.mulai(15000);
  cek("bicara mulai", p.sedangBicara(true, false));
  t = 5000; cek("masih bicara (sintesis aktif)", p.sedangBicara(true, false));
  t = 5200; p.selesai(a);
  cek("tepat selesai: masih dibuang (ekor)", p.sedangBicara(false, false));
  t = 5699; cek("499 ms sesudah selesai: masih dibuang", p.sedangBicara(false, false));
  t = 5700; cek("500 ms sesudah selesai: diterima", !p.sedangBicara(false, false));
  p.selesai(a); p.selesai(999); t = 9000; cek("selesai ganda / id asing aman", !p.sedangBicara(false, false));
  cek("tanpa selesai-paksa pada alur normal", p.statistik().paksa === 0 && p.statistik().dibatalkan === 0);
}
{ // speechSynthesis.speaking macet true TANPA catatan = bukan "app bicara"
  let t = 50000; const jam = () => t;
  const p = ZA.buatPelacakBicara(jam, 500);
  cek("speaking macet true tanpa catatan: tidak bicara", !p.sedangBicara(true, false));
  t = 80000; cek("tetap tidak bicara 30 dtk kemudian", !p.sedangBicara(true, false));
  cek("pending macet true tanpa catatan: tidak bicara", !p.sedangBicara(false, true));
  // sesudah ucapan tercatat selesai, speaking yang masih macet true tidak memperpanjang apa pun
  const a = p.mulai(15000); t = 80300; p.selesai(a);
  t = 80800; cek("catatan selesai + speaking macet: diterima sesudah ekor 500 ms", !p.sedangBicara(true, false));
}
{ // ucapan baru (belum ada speaking) dihitung 1500 ms; sesudahnya hanya bila sintesis speaking/pending
  let t = 0; const jam = () => t; const cat = [];
  const p = ZA.buatPelacakBicara(jam, 500, { catat: (x) => cat.push(x) });
  p.mulai(15000);
  t = 1; cek("baru mulai: dihitung bicara walau speaking belum true", p.sedangBicara(false, false));
  t = 1499; cek("1499 ms: masih dihitung", p.sedangBicara(false, false));
  t = 1500; cek("1500 ms tanpa speaking/pending: ekor 500 ms masih berlaku", p.sedangBicara(false, false));
  t = 1500; cek("... dan ucapan diakhiri paksa (tidak pernah mulai)", p.statistik().paksa === 1 && p.jumlah() === 0 && cat.length === 1, [p.statistik(), cat]);
  t = 1998; cek("ekor 500 ms dari sampel bicara terakhir (1499): 1998 masih", p.sedangBicara(false, false));
  t = 1999; cek("1999: diterima", !p.sedangBicara(false, false));
}
{ // pending (antre) saja cukup menjaga ucapan tetap dihitung
  let t = 0; const jam = () => t;
  const p = ZA.buatPelacakBicara(jam, 500);
  p.mulai(15000);
  t = 3000; cek("pending=true, speaking=false: tetap bicara", p.sedangBicara(false, true));
  t = 9000; cek("pending terus true: tetap bicara", p.sedangBicara(false, true) && p.statistik().paksa === 0);
}
{ // onend tidak pernah datang: diakhiri paksa ~1 dtk sesudah speaking & pending sama-sama false
  let t = 0; const jam = () => t; const cat = [];
  const p = ZA.buatPelacakBicara(jam, 500, { catat: (x) => cat.push(x) });
  p.mulai(15000);
  for (t = 0; t <= 3000; t += 250) p.sedangBicara(true, false);        // sintesis bicara sampai t=3000
  t = 3000; cek("sintesis berhenti di 3000 tanpa onend", p.jumlah() === 1);
  for (t = 3250; t < 4000; t += 250) p.sedangBicara(false, false);
  cek("750 ms sesudah sintesis diam: belum dipaksa", p.jumlah() === 1 && p.statistik().paksa === 0);
  t = 3999; p.sedangBicara(false, false); cek("999 ms: belum dipaksa", p.statistik().paksa === 0);
  t = 4000; const r = p.sedangBicara(false, false);
  cek("1000 ms: selesai-paksa tercatat", p.statistik().paksa === 1 && p.jumlah() === 0 && cat.length === 1 && /selesai-paksa/.test(cat[0]), [p.statistik(), cat]);
  cek("sesudah dipaksa: ekor dihitung dari akhir sintesis (3000), jadi sudah lewat", r === false);
  // tidak menunggu pengaman 15 dtk
  t = 4100; cek("tidak menunggu pengaman 15-20 dtk", !p.sedangBicara(false, false));
}
{ // sintesis hidup lagi (utterance antre berikutnya) sebelum 1000 ms: tidak dipaksa
  let t = 0; const jam = () => t;
  const p = ZA.buatPelacakBicara(jam, 500);
  p.mulai(15000);
  for (t = 0; t <= 2000; t += 250) p.sedangBicara(true, false);
  t = 2500; p.sedangBicara(false, false);
  t = 2900; p.sedangBicara(true, false);
  t = 3800; p.sedangBicara(false, false);
  cek("jeda sintesis < 1000 ms tidak dipaksa", p.jumlah() === 1 && p.statistik().paksa === 0);
}
{ // synth.cancel(): semua catatan lama diakhiri; ucapan baru punya catatan sendiri
  let t = 1000; const jam = () => t;
  const p = ZA.buatPelacakBicara(jam, 500);
  const a = p.mulai(15000), b = p.mulai(15000);
  cek("dua catatan sebelum cancel", p.jumlah() === 2 && p.sedangBicara(true, false));
  const n = p.selesaiSemua();
  const baru = p.mulai(15000);               // ucapan tingkat 3 yang di-speak() sesudah cancel
  cek("selesaiSemua mengakhiri semua yang lama, melaporkan jumlahnya", n === 2 && p.jumlah() === 1 && p.statistik().dibatalkan === 2, [n, p.jumlah()]);
  p.selesai(a); p.selesai(b);                // onerror/onend lama (kalau datang) tidak berpengaruh pada yang baru
  cek("event lama yang telat tidak menghapus catatan baru", p.jumlah() === 1);
  t = 1500; cek("ucapan baru dihitung bicara", p.sedangBicara(true, false));
  t = 2300; p.selesai(baru);
  t = 2799; cek("ekor 500 ms dari ucapan baru", p.sedangBicara(false, false));
  t = 2800; cek("selesai", !p.sedangBicara(false, false));
  // cancel tanpa ucapan baru: ekor 500 ms dari saat cancel, tidak menunggu pengaman
  let u = 100; const q = ZA.buatPelacakBicara(() => u, 500);
  q.mulai(15000); u = 4000; q.selesaiSemua();
  u = 4499; cek("cancel saja: ekor 500 ms", q.sedangBicara(true, false));
  u = 4500; cek("cancel saja: sesudah ekor diterima (speaking macet pun tidak dihitung)", !q.sedangBicara(true, false));
  cek("selesaiSemua tanpa catatan: 0, tidak mengubah ekor", ZA.buatPelacakBicara(jam, 500).selesaiSemua() === 0);
}
{ // batas pengaman: mati bila lewat batas, sekalipun sintesis dilaporkan masih true
  let t = 10000; const jam = () => t;
  const p = ZA.buatPelacakBicara(jam, 500);
  p.mulai(15000);
  t = 24999; cek("pengaman: belum habis", p.sedangBicara(true, false));
  t = 25000; cek("pengaman habis, ekor 500 ms masih berlaku", p.sedangBicara(true, false));
  t = 25500; cek("pengaman: sesudah ekor diterima lagi (speaking macet diabaikan)", !p.sedangBicara(true, false));
}
{ // bip (tanpaSintesis): dihitung sampai selesai atau pengaman, tidak dipaksa selesai
  let t = 0; const jam = () => t;
  const p = ZA.buatPelacakBicara(jam, 500);
  const b = p.mulai(900, { tanpaSintesis: true });
  t = 600; cek("bip: dihitung walau sintesis diam", p.sedangBicara(false, false) && p.statistik().paksa === 0);
  t = 700; p.selesai(b);
  t = 1199; cek("ekor 500 ms sesudah bip", p.sedangBicara(false, false));
  t = 1200; cek("bip selesai", !p.sedangBicara(false, false));
}
{ // dua ucapan bertumpuk: selesai satu belum cukup
  let t = 7000; const jam = () => t;
  const p = ZA.buatPelacakBicara(jam, 500);
  const b = p.mulai(15000), c = p.mulai(15000);
  t = 7500; p.selesai(b); t = 8300; cek("satu selesai, satu masih jalan", p.sedangBicara(true, false));
  t = 8400; p.selesai(c); t = 8899; cek("ekor dihitung dari yang TERAKHIR selesai", p.sedangBicara(false, false));
  t = 8900; cek("ekor habis", !p.sedangBicara(false, false));
}

{ // saatPutus: pemilik janji ucapan diberi tahu bila ucapan berakhir TANPA onend (cancel, paksa, pengaman)
  let t = 0; const jam = () => t; const kabar = [];
  const p = ZA.buatPelacakBicara(jam, 500);
  const mk = (nama, opsi) => p.mulai(15000, Object.assign({ saatPutus: (alasan) => kabar.push(nama + ":" + alasan) }, opsi || {}));
  const a = mk("a"); t = 100; p.selesai(a);
  cek("selesai normal (onend) tidak memanggil saatPutus", kabar.length === 0, kabar);
  mk("b"); mk("c");
  t = 200; p.selesaiSemua();
  cek("cancel: semua pemilik diberi tahu saat itu juga", kabar.join() === "b:cancel,c:cancel", kabar);
  kabar.length = 0; t = 1000;
  mk("d"); for (t = 1000; t <= 1500; t += 250) p.sedangBicara(true, false);
  for (t = 1750; t <= 2500; t += 250) p.sedangBicara(false, false);
  cek("selesai-paksa: pemilik diberi tahu", kabar.join() === "d:paksa", kabar);
  kabar.length = 0; t = 10000; mk("e"); t = 25000; p.sedangBicara(true, false);
  cek("pengaman: pemilik diberi tahu", kabar.join() === "e:pengaman", kabar);
  // pemanggil yang melempar galat tidak merusak pelacak
  t = 30000; p.mulai(15000, { saatPutus: () => { throw new Error("x"); } }); p.selesaiSemua();
  cek("galat di saatPutus tidak merusak pelacak", p.jumlah() === 0);
}

// ---- jendela perintah (jam palsu)
{
  const w = ZA.buatJendela({ t: 0 });
  cek("jendela: jatuh tempo 6000", w.jatuhTempo() === 6000);
  cek("jendela: 5999 belum", w.periksa(5999) === null);
  const a = w.periksa(6000); cek("jendela: 6000 tutup diam-diam", a && a.aksi === "tutup" && a.alasan === "habis", a);
  cek("jendela: sesudah selesai tidak ada aksi", w.periksa(7000) === null && w.jatuhTempo() === null);
}
{ // pertanyaan bebas: kirim setelah 1200 ms diam, diperbarui oleh kata baru
  const w = ZA.buatJendela({ t: 0 });
  w.terima(1000, "a", "itu apa", false);
  cek("tanya: jatuh tempo 2200", w.jatuhTempo() === 2200, w.jatuhTempo());
  w.terima(1800, "a", "itu apa di depan", false);
  cek("tanya: kata baru menggeser ke 3000", w.jatuhTempo() === 3000 && w.periksa(2999) === null);
  const a = w.periksa(3000);
  cek("tanya: dikirim apa adanya", a && a.aksi === "kirim" && a.teks === "itu apa di depan" && a.jenis === "tanya", a);
  w.terima(3100, "a", "lagi", true); cek("sesudah kirim, masukan diabaikan", w.periksa(9999) === null);
}
{ // transkrip yang sama diulang tanpa perubahan tidak menggeser hitung mundur
  const w = ZA.buatJendela({ t: 0 }); w.terima(1000, "a", "itu apa", false); w.terima(1500, "a", "itu apa", false);
  cek("tanya: ulangan sama tidak menggeser", w.jatuhTempo() === 2200, w.jatuhTempo());
}
{ // perintah jelaskan lebih cepat (700 ms)
  const w = ZA.buatJendela({ t: 0 });
  w.terima(1000, "a", "jelasin sekitar", false);
  cek("jelaskan: 1699 belum", w.periksa(1699) === null);
  const a = w.periksa(1700); cek("jelaskan: 1700 kirim", a && a.aksi === "kirim" && a.jenis === "jelaskan" && a.teks === "jelasin sekitar", a);
}
{ // final: kirim 200 ms sesudahnya
  const w = ZA.buatJendela({ t: 0 });
  w.terima(1000, "a", "itu apa di depan?", true);
  cek("final: 1199 belum", w.periksa(1199) === null);
  const a = w.periksa(1200); cek("final: 1200 kirim", a && a.aksi === "kirim" && a.teks === "itu apa di depan?", a);
}
{ // beberapa hasil Chrome digabung berurutan
  const w = ZA.buatJendela({ t: 0 });
  w.terima(1000, "a", "jelasin", true); w.terima(1500, "b", "sekitar", false);
  cek("gabung dua hasil", w.teks() === "jelasin sekitar", w.teks());
  cek("gabung: belum final karena yang kedua belum", w.jatuhTempo() === 2200, w.jatuhTempo());
}
{ // hanya kata bangun (mis. final "Zanite" yang terlambat) bukan perintah
  const w = ZA.buatJendela({ t: 0 });
  w.terima(1000, "k0", "Zanite", true);
  cek("hanya kata bangun: jendela tetap menunggu", w.jatuhTempo() === 6000 && w.periksa(5999) === null);
  w.terima(2000, "k1", "jelaskan sekitar", false);
  w.terima(2300, "k0", "Zanite", true);                        // final terlambat untuk ucapan lama
  cek("kata bangun terlambat tidak mengotori perintah", w.teks() === "jelaskan sekitar", w.teks());
  const w2 = ZA.buatJendela({ t: 0 }); w2.terima(2400, "k2", "zanite jelaskan sekitar", false);   // wake + perintah di dalam jendela
  cek("kata bangun di depan perintah dibuang", w2.teks() === "jelaskan sekitar", w2.teks());
}
{ // batas atas lamanya bicara
  const w = ZA.buatJendela({ t: 0 }); let t = 1000, i = 0;
  for (; t < 11500; t += 500) w.terima(t, "a", "kata " + (i++), false);
  const a = w.periksa(11000); cek("bicara terlalu lama: dikirim di 10 dtk", a && a.aksi === "kirim", a);
}
{ const w = ZA.buatJendela({ t: 0, inline: true }); cek("jendela: penanda inline", w.inline === true && ZA.buatJendela({ t: 0 }).inline === false); }
{ // jendela yang dipakai untuk satu napas: diisi dari transkrip yang sudah ada
  const w = ZA.buatJendela({ t: 5000, inline: true });
  w.terima(4800, "1:0", "Zanite jelasin sekitar", false);
  cek("satu napas: perintah diambil dari ucapan wake", w.teks() === "jelasin sekitar" && w.jatuhTempo() === 5500, [w.teks(), w.jatuhTempo()]);
}

// ---- laporan log uji (murni)
{
  const baris = []; for (let i = 0; i < 200; i++) baris.push("12:00:00.000 +" + i + "ms baris " + i);
  const L = ZA.susunLaporan({ header: { versi: "v-uji", userAgent: "UA", TAIL_MS: 500, kosong: "" }, hitung: { "wake per tipe": { perintah: 2, sendiri: 1 }, kosong: {}, angka: 7 }, baris });
  cek("laporan: judul + header", /^== LOG ZANITE ==\nversi: v-uji\nuserAgent: UA\nTAIL_MS: 500\nkosong: -\n/.test(L), L.slice(0, 120));
  cek("laporan: hitungan (objek diurutkan, kosong = -)", /wake per tipe: perintah=2, sendiri=1\nkosong: -\nangka: 7/.test(L), L);
  const b = L.split("== ")[3].split("\n").slice(1);
  cek("laporan: hanya 150 baris terakhir", b.length === 150 && b[0].endsWith("baris 50") && b[149].endsWith("baris 199"), [b.length, b[0], b[b.length - 1]]);
  cek("laporan: tanpa masukan tidak error", typeof ZA.susunLaporan({}) === "string" && /0 BARIS TERAKHIR/.test(ZA.susunLaporan({})));
}

console.log("aturan zanite: " + (total - gagal) + "/" + total + " lulus");
console.log(gagal ? "GAGAL " + gagal : "semua lulus");
process.exit(gagal ? 1 : 0);
