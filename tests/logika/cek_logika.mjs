// Uji paritas: src/web/logika.js harus memberi keluaran SAMA dengan MesinLogika Python.
//
//   1. config: logika-config.json harus sama dengan hasil ekspor config.yaml SEKARANG
//   2. 11.299 frame rekaman, dua kali: aturan v1.1 hidup (config.yaml) dan mati (v1)
//   3. 42 kasus sintetis (semua mesin, semua langkah, seluruh keluaran dibandingkan)
// Keluar dengan kode 1 kalau ada selisih sedikit pun.
//
// Jalankan dari root repo:  node tests/logika/cek_logika.mjs
import { createRequire } from "node:module";
import { createReadStream, readFileSync } from "node:fs";
import { createGunzip, inflateSync } from "node:zlib";
import { createInterface } from "node:readline";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const { MesinLogika } = require(path.join(ROOT, "src/web/logika.js"));
const F_KASUS = path.join(ROOT, "data/logika-js/kasus.jsonl.gz");
const F_SINTETIS = path.join(ROOT, "data/logika-js/sintetis.json");

let ada_selisih = false;
const gagal = (teks) => {
  ada_selisih = true;
  console.log("GAGAL: " + teks);
};

// ---------------------------------------------------------------- pembanding
function samaDalam(a, b) {
  if (a === b) return true;
  if (typeof a === "number" && typeof b === "number") return Object.is(a, b) || (a === b);
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  for (const k of ka) {
    if (!Object.prototype.hasOwnProperty.call(b, k) || !samaDalam(a[k], b[k])) return false;
  }
  return true;
}

// ---------------------------------------------------------------- masukan
function bukaMask(m) {
  if (m === null) return null;
  const { n, h, w, z } = m;
  const bits = inflateSync(Buffer.from(z, "base64"));
  const luas = h * w;
  const bytePerBaris = Math.ceil(luas / 8);
  if (bits.length !== n * bytePerBaris) throw new Error(`ukuran mask salah: ${bits.length} != ${n * bytePerBaris}`);
  const data = new Uint8Array(n * luas);
  for (let i = 0; i < n; i++) {
    const dasar = i * bytePerBaris;
    const tujuan = i * luas;
    for (let p = 0; p < luas; p++) {
      data[tujuan + p] = (bits[dasar + (p >> 3)] >> (7 - (p & 7))) & 1; // numpy packbits: big-endian
    }
  }
  return { n, h, w, data };
}

function bukaMasukan(masukan) {
  return {
    objek: masukan.objek,
    mask_seg: bukaMask(masukan.mask),
    kelas_seg: masukan.kelas_seg,
    nama_kelas_seg: masukan.nama_kelas_seg,
    waktu_ms: masukan.waktu_ms,
  };
}

// ---------------------------------------------------------------- 1. config
function cekConfig(meta) {
  const jsonWeb = JSON.parse(readFileSync(path.join(ROOT, "src/web/logika-config.json"), "utf8"));
  const venvPy = path.join(ROOT, "venv", "Scripts", "python.exe");
  const r = spawnSync(venvPy, ["-I", path.join(ROOT, "src/server/ekspor_config_web.py"), "--cetak"], { encoding: "utf8" });
  if (r.status !== 0) {
    gagal("tidak bisa menjalankan ekspor_config_web.py --cetak: " + (r.stderr || r.error));
    return jsonWeb;
  }
  const dariYaml = JSON.parse(r.stdout);
  let ok = true;
  if (!samaDalam(jsonWeb, dariYaml)) {
    ok = false;
    gagal("src/web/logika-config.json TIDAK sinkron dengan src/server/config.yaml (jalankan ekspor_config_web.py --force)");
  }
  if (!samaDalam(jsonWeb, meta.config_on)) {
    ok = false;
    gagal("logika-config.json beda dengan config saat kasus.jsonl.gz dibuat (buat ulang data dengan buat_kasus.py)");
  }
  console.log(`config: logika-config.json == config.yaml sekarang == config saat data dibuat: ${ok ? "YA" : "TIDAK"}`);
  return jsonWeb;
}

// ---------------------------------------------------------------- 2. frame rekaman
const BAGIAN = ["peringatan", "jalur.status", "jalur.persen_jalan", "objek.jumlah", "objek.posisi", "objek.jarak", "objek.kelas", "objek.kotak", "objek.conf", "waktu_ms", "versi_kontrak"];

function bandingkanFrame(js, py) {
  const hasil = {};
  const pj = py.peringatan;
  const jj = js.peringatan;
  hasil["peringatan"] = pj === null || jj === null ? pj === jj : samaDalam(jj, pj);
  hasil["jalur.status"] = js.jalur.status === py.jalur.status;
  hasil["jalur.persen_jalan"] = js.jalur.persen_jalan === py.jalur.persen_jalan;
  hasil["objek.jumlah"] = js.objek.length === py.objek.length;
  for (const f of ["posisi", "jarak", "kelas", "kotak", "conf"]) {
    hasil["objek." + f] = hasil["objek.jumlah"] && js.objek.every((o, k) => samaDalam(o[f], py.objek[k][f]));
  }
  hasil["waktu_ms"] = js.waktu_ms === py.waktu_ms;
  hasil["versi_kontrak"] = js.versi_kontrak === py.versi_kontrak;
  return hasil;
}

async function cekFrame(meta, configOn) {
  const config = { on: configOn, off: meta.config_off };
  const hitung = { on: { total: 0 }, off: { total: 0 } };
  const selisih = { on: [], off: [] };
  for (const v of ["on", "off"]) for (const b of BAGIAN) hitung[v][b] = 0;
  const mesin = { on: null, off: null };
  const waktu = []; // ms per proses() (varian on)
  let folderIni = null;

  const rl = createInterface({ input: createReadStream(F_KASUS).pipe(createGunzip()), crlfDelay: Infinity });
  let adaMeta = false;
  for await (const baris of rl) {
    if (!baris) continue;
    const k = JSON.parse(baris);
    if (k.tipe === "meta") {
      adaMeta = true;
      continue;
    }
    if (k.folder !== folderIni) {
      folderIni = k.folder;
      mesin.on = new MesinLogika(config.on);
      mesin.off = new MesinLogika(config.off);
    }
    const masukan = bukaMasukan(k.masukan);
    for (const v of ["on", "off"]) {
      const t0 = process.hrtime.bigint();
      const js = mesin[v].proses(masukan, k.sesi, k.waktu_s);
      const t1 = process.hrtime.bigint();
      if (v === "on") waktu.push(Number(t1 - t0) / 1e6);
      const py = v === "on" ? k.keluar : k.keluar_off;
      const hasil = bandingkanFrame(js, py);
      hitung[v].total++;
      const rusak = [];
      for (const b of BAGIAN) {
        if (hasil[b]) hitung[v][b]++;
        else rusak.push(b);
      }
      if (rusak.length && selisih[v].length < 20) {
        selisih[v].push({ i: k.i, folder: k.folder, sesi: k.sesi, bagian: rusak, js: js.peringatan, py: py.peringatan });
      }
    }
  }
  if (!adaMeta) gagal("kasus.jsonl.gz tanpa baris meta");

  for (const v of ["on", "off"]) {
    const judul = v === "on" ? "v1.1 HIDUP (config.yaml)" : "v1.1 MATI (tahan_dekat_ms=0, samping_maks_tingkat=3)";
    console.log(`\nFrame rekaman, ${judul}:`);
    const total = hitung[v].total;
    for (const b of BAGIAN) {
      const n = hitung[v][b];
      console.log(`  ${b.padEnd(20)} ${String(n).padStart(6)} / ${total}${n === total ? "" : "   <-- SELISIH"}`);
      if (n !== total) ada_selisih = true;
    }
    if (total !== 11299) gagal(`jumlah frame ${total} != 11299`);
    for (const s of selisih[v]) console.log("  selisih:", JSON.stringify(s));
  }

  waktu.sort((a, b) => a - b);
  const med = waktu[Math.floor(waktu.length / 2)];
  const p95 = waktu[Math.floor(waktu.length * 0.95)];
  console.log(`\nKecepatan proses() di Node (${waktu.length} panggilan, tanpa decode mask): median ${med.toFixed(4)} ms, p95 ${p95.toFixed(4)} ms, maks ${waktu[waktu.length - 1].toFixed(3)} ms`);
}

// ---------------------------------------------------------------- 3. kasus sintetis
function cekSintetis() {
  const kasus = JSON.parse(readFileSync(F_SINTETIS, "utf8"));
  let lulus = 0;
  console.log("\nKasus sintetis:");
  for (const k of kasus) {
    const masalah = [];
    k.runs.forEach((run, r) => {
      let mesin = null;
      try {
        mesin = new MesinLogika(run.config);
        if (run.error) masalah.push(`mesin ${r}: Python melempar ${run.error.tipe}, JS tidak`);
      } catch (e) {
        if (!run.error) masalah.push(`mesin ${r}: JS melempar ${e.name}: ${e.message}, Python tidak`);
        else if (e.name !== run.error.tipe || e.message !== run.error.pesan) {
          masalah.push(`mesin ${r}: galat beda JS "${e.name}: ${e.message}" vs Python "${run.error.tipe}: ${run.error.pesan}"`);
        }
        return;
      }
      run.steps.forEach((s, j) => {
        const js = mesin.proses(bukaMasukan(s.masukan), s.sesi, s.waktu_s);
        if (!samaDalam(JSON.parse(JSON.stringify(js)), s.keluar)) {
          masalah.push(`mesin ${r} langkah ${j}: JS ${JSON.stringify(js)} != Python ${JSON.stringify(s.keluar)}`);
        }
      });
    });
    if (masalah.length === 0) lulus++;
    else ada_selisih = true;
    console.log(`  ${masalah.length === 0 ? "LULUS" : "GAGAL"} ${k.nomor}. ${k.nama}`);
    for (const m of masalah) console.log("      " + m);
  }
  console.log(`Kasus sintetis: ${lulus}/${kasus.length} lulus`);
  if (kasus.length !== 42) gagal(`jumlah kasus ${kasus.length} != 42`);
}

// ---------------------------------------------------------------- 4. bulatPy vs round() Python
function cekBulat() {
  const kasus = [
    [0.03125, 4, 0.0312], [0.09375, 4, 0.0938], [0.15625, 4, 0.1562], [0.125, 2, 0.12], [0.375, 2, 0.38],
    [0.625, 2, 0.62], [2.675, 2, 2.67], [0.00005, 4, 0.0001], [0.1, 4, 0.1], [1 / 3, 4, 0.3333], [2 / 3, 4, 0.6667], [0, 4, 0],
  ];
  let ok = true;
  for (const [x, nd, mau] of kasus) {
    const r = MesinLogika._bulatPy(x, nd);
    if (r !== mau) {
      ok = false;
      gagal(`bulatPy(${x}, ${nd}) = ${r}, Python round() = ${mau}`);
    }
  }
  console.log(`\nbulatPy (round Python, setengah-genap): ${ok ? "LULUS" : "GAGAL"} (${kasus.length} nilai, termasuk seri biner persis)`);
}

// ---------------------------------------------------------------- utama
const meta = JSON.parse(await new Promise((res, rej) => {
  const rl = createInterface({ input: createReadStream(F_KASUS).pipe(createGunzip()) });
  rl.once("line", (l) => { res(l); rl.close(); });
  rl.once("error", rej);
}));
const configOn = cekConfig(meta);
await cekFrame(meta, configOn);
cekSintetis();
cekBulat();

console.log(ada_selisih ? "\nHASIL: ADA SELISIH" : "\nHASIL: IDENTIK (100%)");
process.exit(ada_selisih ? 1 : 0);
