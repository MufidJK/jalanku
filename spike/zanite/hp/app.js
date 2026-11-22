// Spike Zanite, kalibrasi 3: tes kata bangun di Chrome HP (tanpa Gemini, tanpa menyimpan audio/gambar).
// Aturan pemicu ada di cocok.js (berdiri sendiri, hitung per ucapan); berkas ini hanya UI, mic, TTS, bip, log.
"use strict";
const $ = (id) => document.getElementById(id);
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const ZC = window.ZaniteCocok;
const VERSI = "kalibrasi-3";
const KUNCI_A = "zanite_varian_v3", KUNCI_B = "zanite_sendiri_v3";   // kunci baru: daftar lama di HP tidak menimpa
const BALAS = "Iya, ada yang bisa saya bantu?";
const JENDELA_MS = 6000;      // jendela perintah setelah balasan selesai
const TAIL_MS = 900;          // masih dianggap "app bicara" sekian ms setelah TTS/bip selesai
const DIAM_AWAL = 800, WEAK_AWAL = 1200;   // bawaan; bisa diubah di halaman (kotak angka)
const KUNCI_DIAM = "zanite_diam_v3", KUNCI_WEAK = "zanite_weak_v3";
const JEDA_UCAPAN_MS = 1500;  // ucapan baru bila tak ada transkrip baru selama ini
const SELESAI_MAKS_MS = 2500; // tunggu ucapan "satu napas" selesai sebelum membalas
const FASE_TANPA_BALAS = new Set(["diam", "zanite", "kalimat"]);   // hanya menghitung, tidak bip/balas
const KATA_PERINTAH = /\b(jelaskan|jelasin|sekitar)\b/;
const PERINGATAN = [
  "Kursi di depan, dekat", "Tangga di depan",
  "Mode suara aktif. Tekan lama dua detik untuk keluar.",
  "Pilar di kiri, dekat", "Kendaraan di kanan", "Tepian di depan, awas",
  "Orang di depan, dekat", "Tanaman pot di kiri", "Pohon di kanan, jauh",
  "Berhenti, tangga naik di depan",
];

const el = { go: $("go"), app: $("app"), salin: $("salin"), vid: $("vid"), jeda: $("jeda"), fase: $("fase"), fuzzy: $("fuzzy"),
  status: $("status"), live: $("live"), cnt: $("cnt"), log: $("log"), varian: $("varian"), varian2: $("varian2"), diam: $("diam"), weak: $("weak") };

// ---------- state ----------
let running = false, rec = null, recActive = false, micPaused = false, sid = 0;
let stopAt = 0, startAt = 0, listenSince = 0, listenedMs = 0, longestMs = 0, restartTimer = null;
let errStreak = 0, lastErr = null, fatal = false;
let appBicara = false, appTailUntil = 0, lastAppEndAt = 0, voice = null, wakeLock = null, actx = null;
let phaseOverride = null, tickTimer = null, settleTimer = null;
const C = { restart: 0, ends: 0, starts: 0, startFail: 0, jedaMic: 0, finals: 0, selfTranscripts: 0,
  selfWake: { off: 0, on: 0 }, appRuns: { off: 0, on: 0 } };
const errs = {}, finalsByPhase = {};
const wakeList = [], selfList = [], events = [];
const selfKeys = new Set();
const trans = [], lastTeks = new Map();   // semua transkrip (interim + final) untuk kalibrasi
const TRANS_MAKS = 6000;
let pending = null;   // wake menunggu ucapan "satu napas" selesai sebelum dibalas: {rec, t0, lastNew}
let win = null;       // jendela perintah: {rec, caps, first, cmdAt, cmdText, timer}
const recByUtt = new Map();

// ---------- util ----------
const norm = ZC.norm;
const fase = () => phaseOverride || el.fase.value;
const ts = () => { const d = new Date(); return d.toTimeString().slice(0, 8) + "." + String(d.getMilliseconds()).padStart(3, "0"); };
const mmss = (ms) => { const s = Math.floor(ms / 1000); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
const isAppSpeaking = () => appBicara || performance.now() < appTailUntil || (window.speechSynthesis && speechSynthesis.speaking);
const cfg = () => ({ daftar: ZC.parseDaftar(el.varian.value), sendiriSaja: ZC.parseDaftar(el.varian2.value), fuzzy: el.fuzzy.checked });
const klas = (teks) => { const c = cfg(); return ZC.klasifikasi(teks, c.daftar, c.fuzzy, c.sendiriSaja); };
const num = (inp, d) => { const v = parseInt(inp.value, 10); return v >= 0 ? v : d; };
const diamMs = () => num(el.diam, DIAM_AWAL), weakMs = () => num(el.weak, WEAK_AWAL);
// mesin langsung (memakai kotak angka) + tiga mesin bayangan dengan aturan varian lemah tetap, masukan sama
const P = ZC.buatPemicu(cfg, diamMs, JEDA_UCAPAN_MS, weakMs);
const SH = { w800: ZC.buatPemicu(cfg, diamMs, JEDA_UCAPAN_MS, 800), w1200: ZC.buatPemicu(cfg, diamMs, JEDA_UCAPAN_MS, 1200),
  wfinal: ZC.buatPemicu(cfg, diamMs, JEDA_UCAPAN_MS, Infinity) };
const NAMA_SH = { w800: "lemah@800", w1200: "lemah@1200", wfinal: "final-saja" };

try { el.varian.value = localStorage.getItem(KUNCI_A) || ZC.DAFTAR_AWAL; } catch (e) { el.varian.value = ZC.DAFTAR_AWAL; }
try { el.varian2.value = localStorage.getItem(KUNCI_B) || ZC.SENDIRI_SAJA_AWAL; } catch (e) { el.varian2.value = ZC.SENDIRI_SAJA_AWAL; }
el.varian.addEventListener("change", () => { try { localStorage.setItem(KUNCI_A, el.varian.value); } catch (e) {} });
el.varian2.addEventListener("change", () => { try { localStorage.setItem(KUNCI_B, el.varian2.value); } catch (e) {} });
try { el.diam.value = localStorage.getItem(KUNCI_DIAM) || DIAM_AWAL; el.weak.value = localStorage.getItem(KUNCI_WEAK) || WEAK_AWAL; }
catch (e) { el.diam.value = DIAM_AWAL; el.weak.value = WEAK_AWAL; }
el.diam.addEventListener("change", () => { try { localStorage.setItem(KUNCI_DIAM, el.diam.value); } catch (e) {} });
el.weak.addEventListener("change", () => { try { localStorage.setItem(KUNCI_WEAK, el.weak.value); } catch (e) {} });

const lines = new Map();
function logAdd(cls, text, key) {
  let d = key && lines.get(key);
  if (!d) {
    d = document.createElement("div");
    el.log.appendChild(d);
    if (key) lines.set(key, d);
    while (el.log.children.length > 300) el.log.removeChild(el.log.firstChild);
  }
  d.className = cls;
  d.textContent = ts() + "  " + text;
  if (el.log.scrollTop + el.log.clientHeight >= el.log.scrollHeight - 40) el.log.scrollTop = el.log.scrollHeight;
}
function evt(cls, text) {
  logAdd(cls, text);
  events.push(ts() + "  [" + fase() + "] " + text);
  if (events.length > 800) events.shift();
}

// ---------- suara TTS ----------
const LANG_ID = /^(id|in)([-_]|$)/i;     // Android melaporkan bahasa Indonesia sebagai "in-ID" / "in_ID"
function pickVoice() {
  if (!window.speechSynthesis) return;
  const vs = speechSynthesis.getVoices();
  voice = vs.find((v) => /^(id|in)[-_]ID$/i.test(v.lang)) || vs.find((v) => LANG_ID.test(v.lang)) || null;
}
function infoSuara() {
  if (!window.speechSynthesis) return "speechSynthesis tidak ada";
  const vs = speechSynthesis.getVoices();
  const pakai = voice ? "dipakai: " + voice.name + " (" + voice.lang + (voice.localService ? ", lokal" : ", online") + ")" : "TIDAK ada suara id/in";
  return "daftar suara " + vs.length + "; " + pakai;
}
function daftarSuara() {
  if (!window.speechSynthesis) return [];
  return speechSynthesis.getVoices().map((v) => v.name + " | " + v.lang + (v.localService ? " | lokal" : " | online") + (v.default ? " | default" : ""));
}
function tungguSuara(maksMs) {
  return new Promise((res) => {
    if (!window.speechSynthesis) return res();
    pickVoice();
    if (speechSynthesis.getVoices().length) return res();
    let beres = false;
    const f = () => { if (beres) return; beres = true; pickVoice(); res(); };
    speechSynthesis.addEventListener("voiceschanged", f, { once: true });
    setTimeout(f, maksMs);
  });
}
if (window.speechSynthesis) { pickVoice(); speechSynthesis.addEventListener("voiceschanged", pickVoice); }

// info = {started, endedReal, startMs, endMs, voice}; paksaJeda = jeda mic walau kotak jeda tidak dicentang
function appSpeak(text, done, paksaJeda) {
  const info = { started: false, endedReal: false, startMs: null, endMs: null, voice: voice ? voice.name + " (" + voice.lang + ")" : "bawaan (tanpa suara id)" };
  if (!window.speechSynthesis) { appBicara = false; if (done) done(info); return; }
  if (!voice) pickVoice();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = voice ? voice.lang.replace("_", "-") : "id-ID";
  if (voice) u.voice = voice;
  const pause = !!paksaJeda || el.jeda.checked, t0 = performance.now();
  let ended = false;
  const finish = (real) => {
    if (ended) return;
    ended = true; info.endedReal = real; info.endMs = Math.round(performance.now() - t0);
    appBicara = false; appTailUntil = performance.now() + TAIL_MS; lastAppEndAt = performance.now();
    if (pause || micPaused) setTimeout(resumeMic, 300);
    if (done) done(info);
  };
  u.onstart = () => { info.started = true; info.startMs = Math.round(performance.now() - t0); appBicara = true; if (pause) pauseMic(); };
  u.onend = () => finish(true);
  u.onerror = () => finish(false);
  appBicara = true;                       // tandai segera, sebelum onstart
  if (pause) pauseMic();
  speechSynthesis.speak(u);
  setTimeout(() => finish(false), 15000 + text.length * 120);   // pengaman: onend kadang tidak datang di Chrome HP
}

// ---------- bip ----------
function siapAudio() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!actx && AC) actx = new AC();
    if (actx && actx.state === "suspended") actx.resume();
    evt("m", "AudioContext: " + (actx ? actx.state : "tidak ada"));
  } catch (e) { evt("e", "AudioContext gagal: " + (e.name || e)); }
}
function beep(cb) {
  const t0 = performance.now();
  let beres = false;
  const fin = (ok, ket) => { if (beres) return; beres = true; cb({ ok, ket, ms: Math.round(performance.now() - t0) }); };
  try {
    if (!actx) throw new Error("tanpa AudioContext");
    if (actx.state === "suspended") actx.resume();
    const o = actx.createOscillator(), g = actx.createGain();
    o.type = "sine"; o.frequency.value = 880; g.gain.value = 0.25;
    o.connect(g); g.connect(actx.destination);
    o.onended = () => fin(true, "onended");
    o.start(); o.stop(actx.currentTime + 0.15);
    setTimeout(() => fin(false, "onended tidak datang, state " + actx.state), 700);
  } catch (e) { fin(false, e.message || e.name); }
}

// ---------- pengenal suara ----------
function pauseMic() {
  if (micPaused) return;
  micPaused = true; C.jedaMic++;
  if (restartTimer) { clearTimeout(restartTimer); restartTimer = null; }
  try { rec && rec.abort(); } catch (e) {}
}
function resumeMic() {
  if (!micPaused) return;
  if (appBicara) return;       // masih ada ucapan lain
  micPaused = false;
  if (running && !recActive && !restartTimer) startRec();
}

function startRec() {
  if (!running || fatal || recActive || micPaused) return;
  restartTimer = null;
  const r = new SR();
  r.lang = "id-ID"; r.continuous = true; r.interimResults = true; r.maxAlternatives = 3;
  const mySid = ++sid;
  r.onstart = () => {
    recActive = true; listenSince = performance.now(); C.starts++;
    el.status.textContent = "Mendengar...";
    if (lastAppEndAt && performance.now() - lastAppEndAt < 5000) {
      evt("m", "mic hidup lagi " + Math.round(performance.now() - lastAppEndAt) + " ms setelah app selesai bicara");
      lastAppEndAt = 0;
    }
  };
  r.onerror = (e) => {
    lastErr = e.error || "?";
    errs[lastErr] = (errs[lastErr] || 0) + 1;
    evt("e", "ERROR " + lastErr + (e.message ? " (" + e.message + ")" : ""));
    if (lastErr === "not-allowed" || lastErr === "service-not-allowed" || lastErr === "language-not-supported") {
      fatal = true; el.status.textContent = "Berhenti: " + lastErr + " (izin mic / bahasa)";
    }
  };
  r.onend = () => {
    const now = performance.now();
    if (recActive) { const d = now - listenSince; listenedMs += d; longestMs = Math.max(longestMs, d); }
    recActive = false; C.ends++;
    if (rec === r) rec = null;
    if (!running || fatal) return;
    if (micPaused) return;          // dijeda sengaja; resumeMic yang menyalakan lagi
    C.restart++;
    const ringan = !lastErr || lastErr === "no-speech" || lastErr === "aborted";
    errStreak = ringan ? 0 : errStreak + 1;
    const delay = ringan ? 250 : Math.min(300 * Math.pow(2, errStreak), 5000);
    lastErr = null;
    restartTimer = setTimeout(startRec, delay);
  };
  r.onresult = (e) => { errStreak = 0; onResult(e, mySid); };
  rec = r;
  try { r.start(); }
  catch (e) {
    C.startFail++; evt("e", "start() gagal: " + e.name);
    rec = null; restartTimer = setTimeout(startRec, 1000);
  }
}

// ---------- hasil + pemicu ----------
function onResult(e, mySid) {
  for (let i = e.resultIndex; i < e.results.length; i++) {
    const r = e.results[i], key = mySid + ":" + i, final = r.isFinal;
    const now = performance.now();
    const text = r[0].transcript.trim(), conf = r[0].confidence;
    const self = isAppSpeaking();
    el.live.textContent = text || "(kosong)";
    const alts = [];
    for (let j = 1; j < r.length; j++) alts.push(r[j].transcript.trim());
    const k0 = klas(text);
    const tk = { t: ts(), fase: fase(), key, final, text, conf, alts, self, cocok: "" };
    if (k0) tk.cocok = k0.tipe + ":" + k0.how + ":" + k0.v;
    for (let j = 0; j < alts.length; j++) {      // alternatif hanya dicatat untuk kalibrasi, tidak menyalakan wake
      const kj = klas(alts[j]);
      if (kj && kj.tipe !== "ditolak" && !(k0 && k0.tipe !== "ditolak")) tk.cocok += " alt" + (j + 1) + "-saja:" + kj.tipe + ":" + kj.v;
    }
    logAdd(self ? "s" : final ? "f" : "i",
      (final ? "F " : "I ") + (self ? "[APP BICARA] " : "") + '"' + text + '"' + (final ? " (" + conf.toFixed(2) + ")" : "") + (tk.cocok ? " <" + tk.cocok + ">" : ""), key);
    if (final) { C.finals++; finalsByPhase[fase()] = (finalsByPhase[fase()] || 0) + 1; }
    const sebelum = lastTeks.get(key);
    if (final || sebelum !== text) { lastTeks.set(key, text); if (trans.length < TRANS_MAKS) trans.push(tk); else C.transPotong = (C.transPotong || 0) + 1; }

    if (self) {                                   // suara app (atau bip) yang terdengar mic: tidak masuk pemicu
      if (!selfKeys.has(key)) { selfKeys.add(key); C.selfTranscripts++; selfList.push(ts() + " transkrip: " + text); }
      if (k0 && k0.tipe !== "ditolak" && !selfKeys.has(key + "w")) {
        selfKeys.add(key + "w"); const k = el.jeda.checked ? "on" : "off"; C.selfWake[k]++;
        selfList.push(ts() + " SELF-WAKE (jeda " + k.toUpperCase() + ') "' + text + '"');
        evt("s", "SELF-WAKE (jeda " + k + ') "' + text + '"');
      }
      continue;
    }
    if (win) winTerima(key, text, final, now);
    if (pending) { pending.lastNew = now; if (final) balas(pending.rec); else armSettle(); }
    for (const k in SH) SH[k].masuk(now, key, text, final);       // bayangan: masukan sama, hasil hanya dicatat
    proses(P.masuk(now, key, text, final));
  }
}

function proses(evs) {
  for (const e of evs) {
    if (e.type === "ucapan") e.utt.fase = fase();
    else if (e.type === "wake") onWake(e);
    else if (e.type === "ditolak") {
      if (e.final || !e.utt.rejLogged) { e.utt.rejLogged = true; evt("r", 'ditolak: ada kata lain "' + e.teks + '"'); }
    } else if (e.type === "kontradiksi") {
      evt("s", 'PERINGATAN: wake sudah menyala, tapi final ucapan: "' + e.teks + '"');
    } else if (e.type === "perintah-update") {
      const rc = recByUtt.get(e.utt.id);
      if (rc) { rc.inline = e.cmd; evt("m", 'perintah satu napas: "' + e.cmd + '"'); }
    }
  }
  jadwal();
}
function tickSemua() {
  const now = performance.now();
  for (const k in SH) SH[k].tick(now);
  proses(P.tick(now));
}
function jadwal() {
  clearTimeout(tickTimer); tickTimer = null;
  let d = P.nextDue();
  for (const k in SH) { const x = SH[k].nextDue(); if (x != null && (d == null || x < d)) d = x; }
  if (d != null) tickTimer = setTimeout(tickSemua, Math.max(0, d - performance.now()) + 5);
}

function onWake(e) {
  const rc = { n: wakeList.length + 1, t: ts(), fase: fase(), tipe: e.tipe, v: e.v, how: e.how, teks: e.teks, inline: e.cmd || "",
    wakeAt: e.t, utt: e.utt.id, balas: false, beep: "-", tts: "-", ttsInfo: null, replyEndAt: 0,
    cmd: "", cmdOk: false, cmdMs: null, cmdMsBal: null, tutup: "-" };
  wakeList.push(rc); recByUtt.set(e.utt.id, rc);
  evt("w", "WAKE #" + rc.n + " (" + e.tipe + ") '" + e.v + "' [" + e.how + '] dari "' + e.teks + '"');
  el.live.classList.add("wake"); setTimeout(() => el.live.classList.remove("wake"), 1500);
  if (FASE_TANPA_BALAS.has(fase())) return;
  if (win) closeWindow("wake baru");
  pending = { rec: rc, t0: performance.now(), lastNew: performance.now() };
  if (e.tipe === "sendiri") balas(rc); else armSettle();   // "satu napas": tunggu ucapan selesai
}
function armSettle() {
  if (!pending) return;
  clearTimeout(settleTimer);
  const sisa = Math.max(0, Math.min(diamMs() - (performance.now() - pending.lastNew), SELESAI_MAKS_MS - (performance.now() - pending.t0)));
  const rc = pending.rec;
  settleTimer = setTimeout(() => balas(rc), sisa);
}

// bip pendek, lalu TTS "Iya, ..." dengan mic dijeda; semuanya dicatat
function balas(rc) {
  if (rc.balas) return;
  rc.balas = true; clearTimeout(settleTimer); pending = null;
  appBicara = true; pauseMic();
  beep((b) => {
    rc.beep = b.ok ? "ok (" + b.ms + " ms)" : "GAGAL (" + b.ket + ")";
    evt(b.ok ? "m" : "e", "BEEP " + rc.beep);
    appSpeak(BALAS, (info) => {
      rc.ttsInfo = info; rc.replyEndAt = performance.now();
      rc.tts = (info.started ? "onstart " + info.startMs + " ms" : "onstart TIDAK datang") + ", " + (info.endedReal ? "onend " : "selesai lewat pengaman ") + info.endMs + " ms, suara " + info.voice;
      evt(info.started && info.endedReal ? "m" : "e", "TTS " + rc.tts);
      openWindow(rc);
    }, true);
  });
}

function openWindow(rc) {
  if (win) closeWindow("diganti");
  win = { rec: rc, caps: new Map(), first: null, cmdAt: null, cmdText: "", openedAt: performance.now(), timer: null };
  evt("m", "JENDELA PERINTAH " + JENDELA_MS / 1000 + " dtk dibuka" + (rc.inline ? " (sudah ada perintah satu napas)" : ""));
  win.timer = setTimeout(() => closeWindow("habis"), JENDELA_MS);
}
function winTerima(key, text, final, now) {
  if (!text) return;
  win.caps.set(key, text);
  if (!win.first) win.first = { t: now, text };
  if (!win.cmdAt && KATA_PERINTAH.test(norm(text))) { win.cmdAt = now; win.cmdText = text; }
  if (final && KATA_PERINTAH.test(norm(text))) setTimeout(() => { if (win) closeWindow("perintah final"); }, 150);
}
function closeWindow(why) {
  if (!win) return;
  const w = win; win = null; clearTimeout(w.timer);
  const rc = w.rec;
  const caps = [...w.caps.values()];
  rc.tutup = why;
  const adaInline = rc.inline && KATA_PERINTAH.test(norm(rc.inline));
  if (adaInline) { rc.cmd = rc.inline; rc.cmdOk = true; rc.cmdMs = 0; rc.cmdMsBal = null; rc.cmdSumber = "satu napas"; }
  else if (w.cmdAt) { rc.cmd = w.cmdText; rc.cmdOk = true; rc.cmdMs = Math.round(w.cmdAt - rc.wakeAt); rc.cmdMsBal = Math.round(w.cmdAt - rc.replyEndAt); rc.cmdSumber = "jendela"; }
  else { rc.cmd = caps.length ? caps.join(" | ") : (rc.inline || ""); rc.cmdOk = false; rc.cmdSumber = caps.length ? "jendela tanpa kata perintah" : "tidak ada"; }
  evt("m", "PERCOBAAN #" + rc.n + " selesai (" + why + "): wake " + rc.tipe + ", perintah " + (rc.cmdOk ? 'DITANGKAP "' + rc.cmd + '" lewat ' + rc.cmdSumber
    + (rc.cmdMs != null ? ", " + rc.cmdMs + " ms dari wake" + (rc.cmdMsBal != null ? ", " + rc.cmdMsBal + " ms dari akhir balasan" : "") : "")
    : "TIDAK ditangkap" + (rc.cmd ? ' (terdengar: "' + rc.cmd + '")' : "")));
}

// ---------- tes suara app ----------
function putarSuaraApp() {
  const k = el.jeda.checked ? "on" : "off";
  C.appRuns[k]++;
  phaseOverride = "suara"; el.app.disabled = true;
  const w0 = C.selfWake[k], t0 = C.selfTranscripts;
  evt("m", "PUTAR 10 peringatan app, jeda mic " + k.toUpperCase());
  let i = 0;
  const next = () => {
    if (i >= PERINGATAN.length) {
      setTimeout(() => {
        evt("m", "SELESAI putar (jeda " + k + "): self-wake " + (C.selfWake[k] - w0) + ", transkrip saat app bicara " + (C.selfTranscripts - t0));
        phaseOverride = null; el.app.disabled = false;
      }, 2500);
      return;
    }
    appSpeak(PERINGATAN[i++], () => setTimeout(next, 1500), false);
  };
  next();
}

// ---------- mulai / berhenti ----------
async function mulai() {
  siapAudio();                                 // harus di dalam gestur klik
  if (!SR) { el.status.textContent = "Browser ini tidak punya SpeechRecognition."; return; }
  running = true; fatal = false; startAt = performance.now(); stopAt = 0;
  el.go.textContent = "Berhenti"; el.go.classList.add("on");
  evt("m", "MULAI (" + VERSI + ", fuzzy " + (el.fuzzy.checked ? "ON" : "OFF") + ")");
  await tungguSuara(3000);
  evt("m", "suara TTS: " + infoSuara());
  try {
    const s = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
    el.vid.srcObject = s; await el.vid.play(); evt("m", "kamera belakang jalan (video saja)");
  } catch (e) { evt("e", "kamera gagal: " + e.name); }
  try { wakeLock = await navigator.wakeLock.request("screen"); evt("m", "layar dijaga menyala"); }
  catch (e) { evt("e", "wake lock gagal: " + (e.name || e)); }
  startRec();
}
function berhenti() {
  running = false; micPaused = false; stopAt = performance.now();
  if (restartTimer) { clearTimeout(restartTimer); restartTimer = null; }
  try { rec && rec.abort(); } catch (e) {}
  for (const k in SH) SH[k].selesai();
  proses(P.selesai());
  if (win) closeWindow("stop");
  try { wakeLock && wakeLock.release(); } catch (e) {}
  el.go.textContent = "Mulai"; el.go.classList.remove("on");
  el.status.textContent = "Berhenti."; evt("m", "BERHENTI");
}
el.go.onclick = () => (running ? berhenti() : mulai());
el.app.onclick = putarSuaraApp;
document.addEventListener("visibilitychange", () => {
  if (!running) return;
  evt("m", "halaman " + (document.hidden ? "TERSEMBUNYI" : "terlihat lagi"));
  if (!document.hidden && wakeLock && wakeLock.released) navigator.wakeLock.request("screen").then((l) => { wakeLock = l; }).catch(() => {});
});

// ---------- penghitung + salin ----------
function perFase() {
  const out = {};
  for (const u of P.utts) {
    const f = out[u.fase || "?"] || (out[u.fase || "?"] = { ucapan: 0, wake: 0, ditolak: 0, tanpa: 0, kontra: 0, daftar: [] });
    f.ucapan++;
    if (u.outcome === "wake") f.wake++; else if (u.outcome === "ditolak") f.ditolak++; else f.tanpa++;
    if (u.kontra) f.kontra++;
    f.daftar.push(u);
  }
  return out;
}
function ringkas() {
  const now = performance.now(), up = running ? now - startAt : (stopAt ? stopAt - startAt : 0);
  const dengar = listenedMs + (recActive ? now - listenSince : 0);
  const err = Object.keys(errs).map((k) => k + "=" + errs[k]).join(", ") || "tidak ada";
  const pf = perFase();
  const baris = Object.keys(pf).map((f) => "fase " + f + ": ucapan " + pf[f].ucapan + ", wake " + pf[f].wake + ", ditolak " + pf[f].ditolak
    + ", tanpa varian " + pf[f].tanpa + (pf[f].kontra ? ", kontradiksi " + pf[f].kontra : ""));
  const br = wakeList.filter((w) => w.balas);
  const n = (f) => br.filter(f).length;
  return [
    "uptime " + mmss(up) + "  mendengar aktif " + (up ? Math.round((dengar / up) * 100) : 0) + "%  sesi terpanjang " + mmss(Math.max(longestMs, recActive ? now - listenSince : 0)),
    "restart otomatis " + C.restart + "  jeda mic " + C.jedaMic + "  start gagal " + C.startFail + "  end " + C.ends,
    "error: " + err,
    "HITUNGAN PER UCAPAN (ucapan baru = transkrip pertama setelah >= " + JEDA_UCAPAN_MS + " ms sepi; diam utama " + diamMs() + " ms, varian lemah " + weakMs() + " ms):",
    ...(baris.length ? baris : ["(belum ada ucapan)"]),
    "balasan: " + br.length + "  bip ok " + n((w) => /^ok/.test(w.beep)) + "  TTS onstart " + n((w) => w.ttsInfo && w.ttsInfo.started) + "  TTS onend asli " + n((w) => w.ttsInfo && w.ttsInfo.endedReal),
    "self-wake: jeda OFF " + C.selfWake.off + ", jeda ON " + C.selfWake.on + "  transkrip saat app bicara " + C.selfTranscripts,
    "putar suara app: OFF " + C.appRuns.off + "x, ON " + C.appRuns.on + "x",
    "hasil final per fase: " + (Object.keys(finalsByPhase).map((k) => k + "=" + finalsByPhase[k]).join(", ") || "-"),
  ].join("\n");
}
setInterval(() => { el.cnt.textContent = ringkas(); }, 1000);

const hasilU = (u) => (!u ? "?" : u.outcome === "wake" ? "W" + Math.round(u.wakeAt - u.t0) + "ms" : u.outcome === "ditolak" ? "x" : "-");
// aturan bayangan: ucapan ke-i di mesin langsung sejajar dengan ucapan ke-i di tiap mesin bayangan
function bayangan(i) { const o = {}; for (const k in SH) o[k] = SH[k].utts[i]; return o; }
function blokTigaAturan() {
  const out = [], idx = new Map(P.utts.map((u, i) => [u, i]));
  const sejajar = Object.keys(SH).every((k) => SH[k].utts.length === P.utts.length);
  if (!sejajar) out.push("(peringatan: jumlah ucapan mesin bayangan tidak sama dengan mesin langsung)");
  const pf = perFase();
  for (const f of Object.keys(pf)) {
    const baris = ["langsung " + pf[f].wake];
    const lat = [];
    for (const k in SH) {
      const us = pf[f].daftar.map((u) => SH[k].utts[idx.get(u)]).filter(Boolean);
      const w = us.filter((u) => u.outcome === "wake");
      baris.push(NAMA_SH[k] + " " + w.length);
      lat.push(NAMA_SH[k] + " " + (w.length ? Math.round(w.reduce((a, u) => a + (u.wakeAt - u.t0), 0) / w.length) : "-") + " ms");
    }
    out.push("fase " + f + ": ucapan " + pf[f].ucapan + " | nyala: " + baris.join(" | ") + " | rerata nyala dari awal ucapan: " + lat.join(", "));
  }
  return out;
}
function blokUcapan() {
  const out = [], pf = perFase(), idx = new Map(P.utts.map((u, i) => [u, i]));
  for (const f of Object.keys(pf)) {
    out.push("[fase " + f + "] ucapan " + pf[f].ucapan + ": wake " + pf[f].wake + ", ditolak " + pf[f].ditolak + ", tanpa varian " + pf[f].tanpa);
    for (const u of pf[f].daftar) {
      const b = bayangan(idx.get(u));
      out.push("  #" + u.id + " langsung=" + hasilU(u) + " | " + Object.keys(SH).map((k) => NAMA_SH[k] + "=" + hasilU(b[k])).join(" ")
        + (u.kontra ? ' | final kemudian: "' + u.kontra + '"' : "") + '  "' + u.last + '"');
    }
  }
  return out;
}
function blokTranskrip() {
  const out = []; let fp = null;
  for (const x of trans) {
    if (x.fase !== fp) { fp = x.fase; out.push("[fase " + fp + "]"); }
    out.push(x.t + (x.final ? " F " : " i ") + (x.self ? "*" : "") + '"' + x.text + '"'
      + (x.final ? " (" + x.conf.toFixed(2) + ")" : "") + (x.alts.length && x.final ? " alt: " + x.alts.map((a) => '"' + a + '"').join(" ") : "")
      + (x.cocok ? " <" + x.cocok + ">" : ""));
  }
  return out;
}
function blokSalin() {
  const h = wakeList.map((w) => `#${w.n} ${w.t} | fase ${w.fase} | ucapan #${w.utt} | ${w.tipe} '${w.v}' [${w.how}] | "${w.teks}" | satu napas: "${w.inline}"`);
  const pc = wakeList.filter((w) => w.balas).map((w) => `#${w.n} ${w.t} | fase ${w.fase} | wake ${w.tipe} | bip ${w.beep} | TTS ${w.tts} | `
    + (w.cmdOk ? `perintah "${w.cmd}" (${w.cmdSumber}${w.cmdMs != null ? ", " + w.cmdMs + " ms dari wake" : ""}${w.cmdMsBal != null ? ", " + w.cmdMsBal + " ms dari akhir balasan" : ""})`
      : `perintah TIDAK ditangkap${w.cmd ? ' (terdengar: "' + w.cmd + '")' : ""}`) + ` | jendela: ${w.tutup}`);
  const er = events.filter((x) => /ERROR|gagal|GAGAL|TERSEMBUNYI|terlihat lagi|PERINGATAN|tidak datang|TIDAK datang|mic hidup lagi/.test(x)).slice(-60);
  return [
    "== ZANITE TES WAKE ==",
    "UA: " + navigator.userAgent,
    "versi: " + VERSI + "  fuzzy: " + (el.fuzzy.checked ? "ON" : "OFF"),
    "DIAM_MS (utama): " + diamMs() + "  WEAK_MS (varian lemah jani/janis/janin/dani/danis/danid): " + weakMs() + "  pisah ucapan: " + JEDA_UCAPAN_MS + "  bayangan: lemah@800, lemah@1200, final-saja",
    "suara TTS: " + infoSuara(),
    "varian: " + el.varian.value,
    "varian hanya-sendiri: " + el.varian2.value,
    "waktu salin: " + new Date().toString(),
    "", ringkas(),
    "", "-- RINGKASAN TIGA ATURAN VARIAN LEMAH (bayangan, masukan sama; W<ms>=menyala dari awal ucapan, x=ditolak, -=tanpa varian) --", ...blokTigaAturan(),
    "", "-- UCAPAN PER FASE (langsung + tiga aturan bayangan) --", ...blokUcapan(),
    "", "-- WAKE (" + wakeList.length + ", satu per ucapan) --", ...h,
    "", "-- PERCOBAAN DENGAN BALASAN (bip + TTS + jendela perintah) --", ...pc,
    "", "-- SELF (app bicara) --", ...selfList.slice(-60),
    "", "-- ERROR / GANGGUAN --", ...er,
    "", "-- TRANSKRIP PER FASE (semua interim dan final; F=final, i=interim, *=app bicara, <cocok>=jenis:jalur:varian; alt = alternatif lain Chrome) --"
      + (C.transPotong ? " [terpotong " + C.transPotong + "]" : ""), ...blokTranskrip(),
    "", "-- DAFTAR SUARA TTS --", ...daftarSuara(),
  ].join("\n");
}
el.salin.onclick = async () => {
  const t = blokSalin();
  try { await navigator.clipboard.writeText(t); el.status.textContent = "Hasil disalin."; }
  catch (e) {
    const ta = document.createElement("textarea"); ta.value = t; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); el.status.textContent = "Hasil disalin (cadangan)."; }
    catch (e2) { el.status.textContent = "Gagal menyalin; teks ada di kotak bawah."; }
  }
};
if (!SR) el.status.textContent = "Browser ini tidak punya SpeechRecognition (pakai Chrome Android).";
