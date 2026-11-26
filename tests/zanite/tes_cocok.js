// Tes pencocok + pemicu kata bangun: node tests/zanite/tes_cocok.js
const Z = require("../../src/web/zanite-cocok.js");
const daftar = Z.parseDaftar(Z.DAFTAR_AWAL);
const harus = ["Zanite", "zanite, jelaskan sekitar", "Janet", "janit", "Janit jelasin sekitar gua", "zanet", "sanet", "jenit",
  "zanith", "xanit", "dzanit", "zanid", "Janite!", "hei janet apa itu", "ja nit", "za nit jelaskan", "Zanite.", "janete"];
const tidak = ("granit depan|janji|jenis|kantin|sanitasi|jahit|genit|kenit|sunat|zaman|zakat|senin|santai|sanksi|janda|jantan|jangan|jalan|jelas|" +
  "jelaskan|jelasin|janin|jamin|zahid|jani|janis|deni|dani|ani|sini|sana|nyanyi|zamrud|sanggup|senang|sehat|zat|sanat|janur|jatuh|" +
  "saya mau ke kantin|tolong ambilkan air|kursinya di sebelah sana|saya janji besok datang|sanitasi di kampus bersih|" +
  "jenis kendaraan apa itu|ada tangga di depan|granit|panit|tanit|manit|danit|ganit|kanit|banit|ranit|lanit|sunit|" +
  "sanad|sanjung|jalan ini|jenius|jelang|senat|seniman|zenith lagi|saniter|sani|zani|jani|ja ni|sa ni te|jangan nit|za gitu|ja gitu|sa kit|ja ne").split("|");
let gagal = 0;
for (const t of harus) { const m = Z.cari(t, daftar); if (!m) { gagal++; console.log("HARUS COCOK, TIDAK:", t); } }
for (const t of tidak) { const m = Z.cari(t, daftar); if (m) { gagal++; console.log("SEHARUSNYA TIDAK, COCOK:", t, JSON.stringify(m)); } }
const r = Z.cari("Zanite, jelaskan sekitar", daftar); if (r.rest !== "jelaskan sekitar") { gagal++; console.log("rest salah", r); }
console.log("lapis 1 (cari): " + (harus.length + tidak.length + 1 - gagal) + "/" + (harus.length + tidak.length + 1) + " lulus");
// ---------- Kalibrasi 3: aturan berdiri sendiri + mesin ucapan ----------
const D = Z.parseDaftar(Z.DAFTAR_AWAL), SS = Z.parseDaftar(Z.SENDIRI_SAJA_AWAL);
const kl = (t) => Z.klasifikasi(t, D, true, SS);
let total = 0, lulus = 0;
const cek = (nama, ok, info) => { total++; if (ok) lulus++; else { gagal++; console.log("GAGAL:", nama, info || ""); } };

// berdiri sendiri -> "sendiri"
for (const t of ["janit", "Janet", "janette", "Danis", "dani", "danid", "danite", "jani", "janis", "janin", "Zanite", "Zanite.", "za nit", "xanit"]) {
  const k = kl(t); cek("sendiri: " + t, k && k.tipe === "sendiri", JSON.stringify(k));
}
// varian + perintah -> "perintah"
const perintah = [["Zanite jelaskan sekitar", "jelaskan sekitar"], ["Zanite, jelasin dong", "jelasin dong"], ["janit dong jelaskan", "jelaskan"],
  ["Janet jelasin sekitar gua", "jelasin sekitar gua"], ["zanet sekitar", "sekitar"], ["Danis jelaskan sekitar", "jelaskan sekitar"], ["janit ya jelasin", "jelasin"]];
for (const [t, c] of perintah) { const k = kl(t); cek("perintah: " + t, k && k.tipe === "perintah" && k.cmd === c, JSON.stringify(k)); }
// sapaan pendek (maks 2 kata dari daftar) sebelum varian: menyala
for (const t of ["halo zanite", "eh zanite", "Hei, Janet", "oke janit", "tolong danis", "eh hei zanite", "ya nah janet"]) {
  const k = kl(t); cek("sapaan sendiri: " + t, k && k.tipe === "sendiri", JSON.stringify(k));
}
for (const [t, c] of [["eh zanite jelasin", "jelasin"], ["halo zanite jelaskan sekitar", "jelaskan sekitar"], ["tolong janet jelasin dong", "jelasin dong"]]) {
  const k = kl(t); cek("sapaan perintah: " + t, k && k.tipe === "perintah" && k.cmd === c, JSON.stringify(k));
}
// sapaan terlalu panjang atau kata lain sebelum varian: ditolak
for (const t of ["teman saya janit", "eh hei halo janit", "halo kamu janit", "eh teman zanite", "saya janit", "tolong ya eh janet jelaskan", "lagi janit jelaskan sekitar"]) {
  const k = kl(t); cek("ditolak (awalan): " + t, k && k.tipe === "ditolak", JSON.stringify(k));
}
// ditolak: ada kata lain
for (const t of ["janit itu teman saya", "janit Lagi di mana", "Danis lagi di mana", "hei janet apa itu", "teman saya janit", "janit ya",
  "jani di sekitar sini", "janin itu bayi", "dani lagi makan", "janet di sekitar", "zanite tolong"]) {
  const k = kl(t); cek("ditolak: " + t, k && k.tipe === "ditolak", JSON.stringify(k));
}
// tidak ada varian -> null
for (const t of ["saya mau ke kantin", "granit", "ganteng", "danite ganteng nih"].slice(0, 3).concat(["jelaskan sekitar", "sanitasi", "kantin janji", "tolong ambilkan air"])) cek("null: " + t, kl(t) === null);
// varian SENDIRI_SAJA tidak boleh dikenali lapis 1 (cari)
for (const t of ["jani", "janis", "janin", "janette", "dani", "danis", "danid", "danite", "ganteng"]) cek("cari tidak kenal: " + t, Z.cari(t, D, true) === null);

// ---- mesin ucapan ----
const mesin = () => Z.buatPemicu(() => ({ daftar: D, sendiriSaja: SS, fuzzy: true }));
const jenis = (ev) => ev.map((e) => e.type + (e.tipe ? ":" + e.tipe : "")).join(",");
{ // interim sendiri: menyala tepat setelah 800 ms
  const m = mesin(); let ev = m.masuk(0, "k1", "janit", false);
  cek("interim sendiri belum menyala", !ev.some((e) => e.type === "wake"));
  cek("tick 799 belum", m.tick(799).length === 0);
  ev = m.tick(800); cek("tick 800 menyala", ev.length === 1 && ev[0].type === "wake" && ev[0].tipe === "sendiri" && ev[0].t === 800, jenis(ev));
}
{ // kata baru membatalkan -> ditolak
  const m = mesin(); m.masuk(0, "k1", "janit", false);
  const ev = m.masuk(300, "k1", "janit itu teman saya", false);
  cek("kata baru -> ditolak", jenis(ev).includes("ditolak") && !ev.some((e) => e.type === "wake"), jenis(ev));
  cek("tidak menyala sesudahnya", m.tick(5000).length === 0 && m.utts[0].outcome === "ditolak");
}
{ // final sendiri langsung menyala
  const m = mesin(); const ev = m.masuk(0, "k1", "Janet", true);
  cek("final sendiri langsung", ev.some((e) => e.type === "wake" && e.tipe === "sendiri"), jenis(ev));
}
{ // perintah menyala langsung, lalu diperbarui
  const m = mesin(); let ev = m.masuk(0, "k1", "zanite jelaskan", false);
  cek("perintah langsung", ev.some((e) => e.type === "wake" && e.tipe === "perintah" && e.cmd === "jelaskan"), jenis(ev));
  ev = m.masuk(200, "k1", "zanite jelaskan sekitar", false);
  cek("perintah diperbarui", ev.some((e) => e.type === "perintah-update" && e.cmd === "jelaskan sekitar") && !ev.some((e) => e.type === "wake"), jenis(ev));
}
{ // satu ucapan, satu wake: interim 'janit' menyala, final 'Janit' tidak menyala lagi
  const m = mesin(); m.masuk(0, "k1", "janit", false); const a = m.tick(800);
  const b = m.masuk(900, "k1", "Janit", true);
  cek("sekali per ucapan", a.length === 1 && !b.some((e) => e.type === "wake") && m.utts.length === 1 && m.utts[0].fired, jenis(a) + " | " + jenis(b));
}
{ // kontradiksi: sudah menyala, final menunjukkan kalimat lain
  const m = mesin(); m.masuk(0, "k1", "janit", false); m.tick(800);
  const ev = m.masuk(1000, "k1", "janit itu teman saya", true);
  cek("kontradiksi tercatat", ev.some((e) => e.type === "kontradiksi") && m.utts[0].kontra === "janit itu teman saya", jenis(ev));
}
{ // pemisahan ucapan: jeda < 1,5 dtk satu ucapan, >= 1,5 dtk ucapan baru
  const m = mesin(); m.masuk(0, "k1", "janit", false); m.masuk(500, "k1", "janit lagi", false);
  m.masuk(3000, "k2", "Janet", true); m.masuk(4400, "k3", "saya mau ke kantin", true); m.masuk(6000, "k4", "kantin", true);
  cek("jumlah ucapan", m.utts.length === 3, m.utts.map((u) => u.id + ":" + u.outcome).join(" "));
  cek("hasil per ucapan", m.utts.map((u) => u.outcome).join() === "ditolak,wake,tanpa-variant", m.utts.map((u) => u.outcome).join());
}
{ // varian lemah (jani, janis, janin, dani, danis, danid): final, atau interim stabil weakMs (bawaan 1200)
  for (const v of ["Jani", "Janis", "janin", "Dani", "Danis", "danid"]) {
    const m = mesin(); let ev = m.masuk(0, "k1", v, false);
    cek("lemah: interim tidak langsung menyala: " + v, !ev.some((e) => e.type === "wake") && m.nextDue() === 1200, String(m.nextDue()));
    cek("lemah: belum menyala di 800 dan 1199: " + v, m.tick(800).length === 0 && m.tick(1199).length === 0);
    ev = m.tick(1200);
    cek("lemah: menyala tepat di 1200: " + v, ev.length === 1 && ev[0].type === "wake" && ev[0].t === 1200, jenis(ev));
    const m2 = mesin(); m2.masuk(0, "k1", v, false);
    ev = m2.masuk(300, "k1", v, true);
    cek("lemah: final menyala langsung: " + v, ev.some((e) => e.type === "wake" && e.t === 300), jenis(ev));
  }
  { // kata baru membatalkan hitung mundur lemah
    const m = mesin(); m.masuk(0, "k1", "Jani", false); m.masuk(1000, "k1", "janit itu teman saya", false);
    cek("lemah: Jani 1 dtk lalu kalimat: tidak menyala", m.tick(20000).length === 0 && m.utts[0].outcome === "ditolak", m.utts[0].outcome);
    const m2 = mesin(); m2.masuk(0, "k1", "Jani", false); m2.masuk(2000, "k1", "janit itu teman saya", false);
    cek("lemah: Jani bertahan 2 dtk lalu kalimat: menyala di 1200 (risiko yang diterima)", m2.utts[0].fired && m2.utts[0].wakeAt === 1200, String(m2.utts[0].wakeAt));
    const m3 = mesin(); m3.masuk(0, "k1", "ja", false); m3.masuk(100, "k1", "Jani", false); m3.masuk(300, "k1", "janit itu teman saya", false);
    cek("lemah: kedipan cepat ja, Jani, kalimat: tidak menyala", m3.tick(20000).length === 0 && m3.utts[0].outcome === "ditolak");
  }
  { // lemah + perintah
    const m = mesin(); let ev = m.masuk(0, "k1", "dani jelaskan", false);
    cek("lemah + perintah interim: belum langsung", !ev.some((e) => e.type === "wake") && m.nextDue() === 1200, String(m.nextDue()));
    ev = m.tick(1200);
    cek("lemah + perintah menyala di 1200 dengan perintah", ev.length === 1 && ev[0].tipe === "perintah" && ev[0].cmd === "jelaskan", jenis(ev));
    const m2 = mesin(); m2.masuk(0, "k1", "dani jelaskan", false);
    ev = m2.masuk(400, "k1", "dani jelaskan sekitar", true);
    cek("lemah + perintah final langsung", ev.some((e) => e.type === "wake" && e.tipe === "perintah" && e.cmd === "jelaskan sekitar"), jenis(ev));
  }
  // varian sendiri-saja bukan lemah (janette, danite) dan varian utama tetap diamMs 800
  for (const v of ["janette", "danite", "Janit", "Janet"]) {
    const m = mesin(); m.masuk(0, "k1", v, false); const ev = m.tick(800);
    cek("bukan lemah: menyala di 800 ms: " + v, ev.length === 1 && ev[0].type === "wake" && ev[0].t === 800, jenis(ev));
  }
  // dapat diubah: diamMs dan weakMs sebagai fungsi / angka
  { let dm = 500, wk = 2000; const m = Z.buatPemicu(() => ({ daftar: D, sendiriSaja: SS, fuzzy: true }), () => dm, 1500, () => wk);
    m.masuk(0, "k1", "Janit", false); cek("diamMs dapat diubah (500)", m.nextDue() === 500, String(m.nextDue()));
    m.masuk(5000, "k2", "Jani", false); cek("weakMs dapat diubah (2000)", m.nextDue() === 7000, String(m.nextDue()));
    dm = 300; m.masuk(9000, "k3", "Janit", false); cek("diamMs berubah di tengah jalan (300)", m.nextDue() === 9300, String(m.nextDue())); }
  // weakMs = Infinity: final-saja
  { const m = Z.buatPemicu(() => ({ daftar: D, sendiriSaja: SS, fuzzy: true }), 800, 1500, Infinity);
    let ev = m.masuk(0, "k1", "Jani", false);
    cek("final-saja (Infinity): tidak ada hitung mundur", m.nextDue() === null && m.tick(60000).length === 0);
    ev = m.masuk(61000, "k1", "Jani", true); cek("final-saja (Infinity): final menyala", ev.some((e) => e.type === "wake"), jenis(ev)); }
  // tiga aturan bayangan menerima masukan sama, hasil beda
  { const mk = (w) => Z.buatPemicu(() => ({ daftar: D, sendiriSaja: SS, fuzzy: true }), 800, 1500, w);
    const R = { w800: mk(800), w1200: mk(1200), wfinal: mk(Infinity) };
    for (const k in R) R[k].masuk(0, "k1", "Jani", false);
    for (const k in R) R[k].tick(1000);
    const hasil = (k) => (R[k].utts[0].fired ? "W" : "-");
    cek("bayangan di 1000 ms: 800=W 1200=- final=-", hasil("w800") + hasil("w1200") + hasil("wfinal") === "W--", hasil("w800") + hasil("w1200") + hasil("wfinal"));
    for (const k in R) R[k].tick(1300);
    cek("bayangan di 1300 ms: 800=W 1200=W final=-", hasil("w800") + hasil("w1200") + hasil("wfinal") === "WW-");
    for (const k in R) R[k].masuk(1400, "k1", "Jani", true);
    cek("bayangan setelah final: semua W", hasil("w800") + hasil("w1200") + hasil("wfinal") === "WWW");
    cek("bayangan: id ucapan sejajar", R.w800.utts[0].id === R.wfinal.utts[0].id); }
}
{ // akhir data: hitung mundur yang menggantung menyala saat selesai()
  const m = mesin(); m.masuk(0, "k1", "janit", false); const ev = m.selesai();
  cek("selesai() menyalakan sisa", ev.some((e) => e.type === "wake"), jenis(ev));
}
console.log("kalibrasi 3: " + lulus + "/" + total + " lulus");
console.log(gagal ? "GAGAL " + gagal : "semua lulus");
process.exit(gagal ? 1 : 0);
