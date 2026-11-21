"use strict";
// JalanKu spike HP: ukur FPS box + seg (YOLO26n, ONNX) yang jalan di browser HP.
// Throw-away: bukan app v2. Mask seg TIDAK didekode (itu kerja Stage 3).

const ORT_VERSION = "1.31.1";
const CONF = 0.25;
const IOU = 0.7;
const WINDOW = 30; // median dari N frame terakhir
const BOX_NAMES = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"];
const SEG_NAMES = ["jalur_jalan", "jalan_kendaraan", "tangga"];

const $ = (id) => document.getElementById(id);
const el = { sz: $("sz"), be: $("be"), useBox: $("useBox"), useSeg: $("useSeg"), go: $("go"),
  copy: $("copy"), msg: $("msg"), vid: $("vid"), ov: $("ov"), fps: $("fps"), stats: $("stats"), out: $("out") };
const params = new URLSearchParams(location.search);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const median = (a) => { if (!a.length) return NaN; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const fmt = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d) : "-");

// ---------- onnxruntime-web ----------
const isolated = !!self.crossOriginIsolated;
const threads = params.get("threads") ? +params.get("threads")
  : isolated ? Math.min(4, navigator.hardwareConcurrency || 4) : 1;
ort.env.wasm.wasmPaths = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`;
ort.env.wasm.numThreads = threads;
ort.env.wasm.simd = true;

// ---------- state ----------
let running = false, stream = null, wakeLock = null;
let loaded = null;   // { key, backend, sessions:{box,seg}, loadMs, warmMs }
let sample = [];     // satu entri per frame: {pre, box, boxNms, seg, segNms, draw, total, nBox, nSeg, end}
let lastRes = { w: 0, h: 0 };
let lastNBox = 0, lastNSeg = 0;

// buffer preprocess (dipakai ulang)
const lb = document.createElement("canvas");
const lbCtx = lb.getContext("2d", { willReadFrequently: true });
let inBuf = null;

function setMsg(t) { el.msg.textContent = t || ""; }

// ---------- preprocess: letterbox ala Ultralytics (rasio tetap, pad 114) -> float32 NCHW 0..1 ----------
function preprocess(video, sz) {
  const w = video.videoWidth, h = video.videoHeight;
  const r = Math.min(sz / h, sz / w);
  const nw = Math.round(w * r), nh = Math.round(h * r);
  const left = Math.round((sz - nw) / 2 - 0.1), top = Math.round((sz - nh) / 2 - 0.1);
  if (lb.width !== sz) { lb.width = sz; lb.height = sz; inBuf = new Float32Array(3 * sz * sz); }
  lbCtx.fillStyle = "rgb(114,114,114)";
  lbCtx.fillRect(0, 0, sz, sz);
  lbCtx.drawImage(video, left, top, nw, nh);
  const d = lbCtx.getImageData(0, 0, sz, sz).data, n = sz * sz;
  for (let i = 0, j = 0; i < n; i++, j += 4) {
    inBuf[i] = d[j] / 255;
    inBuf[n + i] = d[j + 1] / 255;
    inBuf[2 * n + i] = d[j + 2] / 255;
  }
  return { r, left, top, w, h };
}

// ---------- decode + NMS (per kelas, IoU 0.7, conf 0.25) ----------
// output0: [1, 4+nc(+32), N], channel-major; kotak = cx,cy,w,h dalam piksel input; skor sudah sigmoid.
function decode(data, nc, N) {
  const c = []; // kandidat
  for (let i = 0; i < N; i++) {
    let best = -1, bs = 0;
    for (let k = 0; k < nc; k++) { const s = data[(4 + k) * N + i]; if (s > bs) { bs = s; best = k; } }
    if (bs < CONF) continue;
    const cx = data[i], cy = data[N + i], w = data[2 * N + i], h = data[3 * N + i];
    c.push({ x1: cx - w / 2, y1: cy - h / 2, x2: cx + w / 2, y2: cy + h / 2, s: bs, c: best });
  }
  return c;
}
function nms(cands) {
  cands.sort((a, b) => b.s - a.s);
  const keep = [];
  for (const a of cands) {
    const areaA = (a.x2 - a.x1) * (a.y2 - a.y1);
    let ok = true;
    for (const b of keep) {
      if (b.c !== a.c) continue;
      const iw = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1);
      const ih = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1);
      if (iw <= 0 || ih <= 0) continue;
      const inter = iw * ih;
      if (inter / (areaA + (b.x2 - b.x1) * (b.y2 - b.y1) - inter) > IOU) { ok = false; break; }
    }
    if (ok) keep.push(a);
  }
  return keep;
}
function postprocess(out0, nc) {
  const N = out0.dims[2];
  return nms(decode(out0.data, nc, N));
}

// ---------- load model ----------
async function createSession(name, sz, backend) {
  const buf = await (await fetch(`/models/${name}_${sz}.onnx`)).arrayBuffer();
  return ort.InferenceSession.create(buf, { executionProviders: [backend], graphOptimizationLevel: "all" });
}
async function warmup(session, sz) {
  const t = new ort.Tensor("float32", new Float32Array(3 * sz * sz).fill(0.45), [1, 3, sz, sz]);
  await session.run({ images: t });
}
async function loadBackend(backend, sz, wantBox, wantSeg) {
  const sessions = {};
  const t0 = performance.now();
  if (wantBox) sessions.box = await createSession("box", sz, backend);
  if (wantSeg) sessions.seg = await createSession("seg", sz, backend);
  const loadMs = performance.now() - t0;
  const t1 = performance.now();
  for (const k of Object.keys(sessions)) await warmup(sessions[k], sz); // kompilasi shader (webgpu) / init thread
  return { sessions, loadMs, warmMs: performance.now() - t1 };
}
async function releaseLoaded() {
  if (!loaded) return;
  for (const s of Object.values(loaded.sessions)) { try { await s.release(); } catch (e) {} }
  loaded = null;
}
async function ensureLoaded(sz, wantBox, wantSeg, pref) {
  const key = `${pref}|${sz}|${wantBox}|${wantSeg}`;
  if (loaded && loaded.key === key) return;
  await releaseLoaded();
  const order = pref === "auto" ? (navigator.gpu ? ["webgpu", "wasm"] : ["wasm"]) : [pref];
  let lastErr = null;
  for (const be of order) {
    try {
      setMsg(`memuat model (${be}) ...`);
      const r = await loadBackend(be, sz, wantBox, wantSeg);
      loaded = { key, backend: be, ...r };
      setMsg(be !== order[0] ? `webgpu gagal (${lastErr && lastErr.message ? lastErr.message.slice(0, 80) : lastErr}), pakai wasm` : "");
      return;
    } catch (e) {
      lastErr = e; console.error(be, e);
      for (const s of Object.values(e.sessions || {})) { try { await s.release(); } catch (_) {} }
    }
  }
  throw new Error("semua backend gagal: " + (lastErr && lastErr.message ? lastErr.message : lastErr));
}

// ---------- gambar ----------
function colorOf(c) { return `hsl(${(c * 47) % 360} 90% 55%)`; }
function drawBoxes(dets, g) {
  const ov = el.ov, vw = g.w, vh = g.h;
  if (ov.width !== vw || ov.height !== vh) { ov.width = vw; ov.height = vh; }
  const ctx = ov.getContext("2d");
  ctx.clearRect(0, 0, vw, vh);
  const lw = Math.max(2, vw / 200), fs = Math.max(12, Math.round(vw / 32));
  ctx.lineWidth = lw; ctx.font = `${fs}px sans-serif`; ctx.textBaseline = "top";
  for (const d of dets) {
    const x1 = Math.max(0, (d.x1 - g.left) / g.r), y1 = Math.max(0, (d.y1 - g.top) / g.r);
    const x2 = Math.min(vw, (d.x2 - g.left) / g.r), y2 = Math.min(vh, (d.y2 - g.top) / g.r);
    ctx.strokeStyle = colorOf(d.c);
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    const label = `${BOX_NAMES[d.c]} ${d.s.toFixed(2)}`, tw = ctx.measureText(label).width;
    ctx.fillStyle = colorOf(d.c);
    ctx.fillRect(x1, y1, tw + 6, fs + 4);
    ctx.fillStyle = "#000";
    ctx.fillText(label, x1 + 3, y1 + 2);
  }
}

// ---------- loop ----------
async function loop(sz) {
  const S = loaded.sessions;
  while (running) {
    const v = el.vid;
    if (v.readyState < 2 || !v.videoWidth) { await sleep(20); continue; }
    const t0 = performance.now();
    const g = preprocess(v, sz);
    lastRes = { w: g.w, h: g.h };
    const t1 = performance.now();
    const input = new ort.Tensor("float32", inBuf, [1, 3, sz, sz]);
    let boxMs = NaN, boxNms = NaN, segMs = NaN, segNms = NaN, dets = [];
    if (S.box) {
      const a = performance.now();
      const o = await S.box.run({ images: input });
      const b = performance.now();
      dets = postprocess(o[S.box.outputNames[0]], BOX_NAMES.length);
      boxMs = b - a; boxNms = performance.now() - b;
      lastNBox = dets.length;
    }
    if (S.seg) {
      const a = performance.now();
      const o = await S.seg.run({ images: input });
      const b = performance.now();
      const segDets = postprocess(o[S.seg.outputNames[0]], SEG_NAMES.length); // 32 koef mask diabaikan
      segMs = b - a; segNms = performance.now() - b;
      lastNSeg = segDets.length;
    }
    const d0 = performance.now();
    drawBoxes(dets, g);
    const end = performance.now();
    sample.push({ pre: t1 - t0, box: boxMs, boxNms, seg: segMs, segNms, draw: end - d0, total: end - t0, end });
    if (sample.length > WINDOW) sample.shift();
    await sleep(0); // lepas ke browser (render video / UI)
  }
}

// ---------- statistik ----------
function snapshot() {
  const col = (k) => median(sample.map((s) => s[k]).filter(Number.isFinite));
  let fps = NaN;
  if (sample.length >= 2) fps = ((sample.length - 1) * 1000) / (sample[sample.length - 1].end - sample[0].end);
  return { n: sample.length, pre: col("pre"), box: col("box"), boxNms: col("boxNms"), seg: col("seg"),
    segNms: col("segNms"), draw: col("draw"), total: col("total"), fps };
}
function resultLine() {
  const s = snapshot(), L = loaded;
  const on = (x) => (x ? "on" : "off");
  return [
    `JalanKuSpike ort=${ORT_VERSION}`,
    `backend=${L ? L.backend : "-"}`, `threads=${threads}`, `isolated=${isolated}`,
    `imgsz=${el.sz.value}`, `box=${on(L && L.sessions.box)} seg=${on(L && L.sessions.seg)}`,
    `cam=${lastRes.w}x${lastRes.h}`,
    `load_ms=${fmt(L && L.loadMs, 0)} warmup_ms=${fmt(L && L.warmMs, 0)}`,
    `med${WINDOW}: pre=${fmt(s.pre)} box=${fmt(s.box)} boxNMS=${fmt(s.boxNms)} seg=${fmt(s.seg)} segNMS=${fmt(s.segNms)} draw=${fmt(s.draw)} total=${fmt(s.total)} ms`,
    `fps=${fmt(s.fps)}`, `nBox=${lastNBox} nSeg=${lastNSeg}`,
    `UA=${navigator.userAgent}`,
  ].join(" | ");
}
function render() {
  const s = snapshot(), L = loaded;
  el.fps.textContent = `${fmt(s.fps)} fps`;
  el.stats.textContent =
`backend      : ${L ? L.backend : "-"}   (wasm threads ${threads}, crossOriginIsolated ${isolated})
imgsz        : ${el.sz.value}   kamera ${lastRes.w}x${lastRes.h}
load model   : ${fmt(L && L.loadMs, 0)} ms (+ warm-up ${fmt(L && L.warmMs, 0)} ms), sekali
--- median ${WINDOW} frame terakhir (n=${s.n}) ---
preprocess   : ${fmt(s.pre)} ms
box model    : ${fmt(s.box)} ms    box NMS : ${fmt(s.boxNms)} ms    (${lastNBox} deteksi)
seg model    : ${fmt(s.seg)} ms    seg NMS : ${fmt(s.segNms)} ms    (${lastNSeg} deteksi, tanpa mask)
gambar       : ${fmt(s.draw)} ms
TOTAL/frame  : ${fmt(s.total)} ms`;
}
setInterval(() => { if (running) render(); }, 1000);

// ---------- wake lock ----------
async function takeWake() {
  try { if (navigator.wakeLock) wakeLock = await navigator.wakeLock.request("screen"); } catch (e) { console.warn("wakeLock", e); }
}
document.addEventListener("visibilitychange", () => { if (running && document.visibilityState === "visible") takeWake(); });

// ---------- start / stop ----------
function lockControls(b) { for (const k of ["sz", "be", "useBox", "useSeg"]) el[k].disabled = b; }
async function start() {
  if (!el.useBox.checked && !el.useSeg.checked) { setMsg("pilih minimal satu model (box/seg)"); return; }
  lockControls(true); el.go.disabled = true;
  try {
    const sz = +el.sz.value;
    await ensureLoaded(sz, el.useBox.checked, el.useSeg.checked, el.be.value);
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
    el.vid.srcObject = stream;
    await el.vid.play();
    await takeWake();
    sample = []; running = true;
    el.go.textContent = "Stop"; el.go.classList.add("on");
    loop(sz);
  } catch (e) {
    console.error(e); setMsg("gagal: " + (e && e.message ? e.message : e)); lockControls(false);
  }
  el.go.disabled = false;
}
async function stop() {
  running = false;
  await sleep(50);
  render();
  el.out.value = resultLine();
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
  el.vid.srcObject = null;
  if (wakeLock) { try { await wakeLock.release(); } catch (e) {} wakeLock = null; }
  el.go.textContent = "Start"; el.go.classList.remove("on");
  lockControls(false);
}
el.go.addEventListener("click", () => (running ? stop() : start()));
el.copy.addEventListener("click", async () => {
  const line = running || !el.out.value ? resultLine() : el.out.value;
  el.out.value = line;
  try { await navigator.clipboard.writeText(line); setMsg("tersalin ke clipboard"); }
  catch (e) { el.out.select(); document.execCommand("copy"); setMsg("tersalin (cara lama); kalau gagal, salin teks di kotak bawah"); }
});

// ---------- mode otomatis untuk tes di laptop: ?auto=DETIK&sz=320&be=wasm&box=1&seg=1 ----------
(async function auto() {
  if (!params.get("auto")) return;
  if (params.get("sz")) el.sz.value = params.get("sz");
  if (params.get("be")) el.be.value = params.get("be");
  el.useBox.checked = params.get("box") !== "0";
  el.useSeg.checked = params.get("seg") !== "0";
  await start();
  if (!running) { await fetch("/report", { method: "POST", body: "AUTO GAGAL: " + el.msg.textContent }); return; }
  await sleep(+params.get("auto") * 1000);
  await stop();
  await fetch("/report", { method: "POST", body: resultLine() });
  document.title = "DONE";
})();
