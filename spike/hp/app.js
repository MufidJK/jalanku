"use strict";
// JalanKu Tahap 5a/5b: halaman UKUR (bukan app). box tiap frame + seg tiap N frame, fp32/fp16, WebGPU (wasm cadangan).
// Mask seg TIDAK didekode dan logika peringatan TIDAK ada: angka di sini batas bawah biaya per frame.
// 5b: pilihan model (lama latih 640 / latih ulang hp-*) dan tombol "Tes 5 menit" (ketahanan, tidak ada yang diubah di mode 5a).

const ORT_VERSION = "1.31.1";
const CONF = 0.25;
const IOU = 0.7;
const WINDOW = 30; // median dari N frame terakhir
const TEST_MS = 300000; // tes ketahanan: 5 menit
const MODEL_PREFIX = { lama: "", baru: "hp_" }; // lama: box_320.onnx ; baru: hp_box_320.onnx
const BOX_NAMES = ["pilar", "pohon", "tepian", "orang", "tanaman_pot", "kursi", "kendaraan", "tangga"];
const SEG_NAMES = ["jalur_jalan", "jalan_kendaraan", "tangga"];
const INV255 = 1 / 255;

const $ = (id) => document.getElementById(id);
const el = { sz: $("sz"), be: $("be"), prec: $("prec"), segN: $("segN"), pre: $("pre"), mdl: $("mdl"), useBox: $("useBox"), useSeg: $("useSeg"),
  go: $("go"), copy: $("copy"), msg: $("msg"), vid: $("vid"), ov: $("ov"), fps: $("fps"), stats: $("stats"), out: $("out"),
  tes: $("tes"), copy5: $("copy5"), cd: $("cd"), out5: $("out5") };
const params = new URLSearchParams(location.search);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const median = (a) => { if (!a.length) return NaN; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const fmt = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d) : "-");
const errText = (e) => String(e && e.message ? e.message : e).replace(/\s+/g, " ").slice(0, 160);

// ---------- onnxruntime-web ----------
const isolated = !!self.crossOriginIsolated;
const threads = params.get("threads") ? +params.get("threads")
  : isolated ? Math.min(4, navigator.hardwareConcurrency || 4) : 1;
ort.env.wasm.wasmPaths = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`;
ort.env.wasm.numThreads = threads;
ort.env.wasm.simd = true;

let gpuF16 = null; // adapter WebGPU punya fitur shader-f16? (null = tidak diketahui / tidak ada WebGPU)
if (navigator.gpu) navigator.gpu.requestAdapter().then((a) => { gpuF16 = a ? a.features.has("shader-f16") : null; }).catch(() => {});

// ---------- state ----------
let running = false, stream = null, wakeLock = null;
let loaded = null;   // { key, backend, precRun, precNote, sessions:{box,seg}, loadMs, warmMs }
let sample = [];     // satu entri per frame
let lastRes = { w: 0, h: 0 };
let lastNBox = 0, lastNSeg = 0, frameIdx = 0, preRun = "-";
// tes ketahanan (5b): rec = satu entri per frame sepanjang tes (bukan hanya 30 terakhir)
let rec = [], recOn = false, recT0 = null, errCount = 0, lastErr = "", hiddenCount = 0, testRunning = false;
let batStart = null;

// ---------- preprocess: letterbox ala Ultralytics (rasio tetap, pad 114) -> float32 NCHW 0..1 ----------
// Geometri sama persis dengan versi spike pertama: r = min(sz/h, sz/w), offset Math.round((sz - n)/2 - 0.1).
function geom(w, h, sz) {
  const r = Math.min(sz / h, sz / w);
  const nw = Math.round(w * r), nh = Math.round(h * r);
  return { r, nw, nh, left: Math.round((sz - nw) / 2 - 0.1), top: Math.round((sz - nh) / 2 - 0.1), w, h, sz };
}
const P = { g: null, inBuf: null, tensor: null, c2d: null, ctx2d: null, gl: null, px: null };

function ensureBuffers(sz) {
  if (P.inBuf && P.inBuf.length === 3 * sz * sz) return;
  P.inBuf = new Float32Array(3 * sz * sz);
  P.tensor = new ort.Tensor("float32", P.inBuf, [1, 3, sz, sz]); // satu tensor, dipakai ulang tiap frame
  P.px = new Uint8Array(4 * sz * sz);
  P.g = null;
}
function rgbaToNchw(d, n) {
  const b = P.inBuf, n2 = 2 * n;
  for (let i = 0, j = 0; i < n; i++, j += 4) {
    b[i] = d[j] * INV255;
    b[n + i] = d[j + 1] * INV255;
    b[n2 + i] = d[j + 2] * INV255;
  }
}

// (a) "lama": kode spike pertama apa adanya (fillRect penuh + getImageData + Tensor baru tiap frame). Hanya ?pre=lama, untuk banding.
const lamaCv = document.createElement("canvas");
const lamaCtx = lamaCv.getContext("2d", { willReadFrequently: true });
let lamaBuf = null;
function preLama(video, sz) {
  const w = video.videoWidth, h = video.videoHeight;
  const r = Math.min(sz / h, sz / w);
  const nw = Math.round(w * r), nh = Math.round(h * r);
  const left = Math.round((sz - nw) / 2 - 0.1), top = Math.round((sz - nh) / 2 - 0.1);
  if (lamaCv.width !== sz) { lamaCv.width = sz; lamaCv.height = sz; lamaBuf = new Float32Array(3 * sz * sz); }
  lamaCtx.fillStyle = "rgb(114,114,114)";
  lamaCtx.fillRect(0, 0, sz, sz);
  lamaCtx.drawImage(video, left, top, nw, nh);
  const d = lamaCtx.getImageData(0, 0, sz, sz).data, n = sz * sz;
  for (let i = 0, j = 0; i < n; i++, j += 4) {
    lamaBuf[i] = d[j] / 255;
    lamaBuf[n + i] = d[j + 1] / 255;
    lamaBuf[2 * n + i] = d[j + 2] / 255;
  }
  return { g: { r, left, top, w, h }, tensor: new ort.Tensor("float32", lamaBuf, [1, 3, sz, sz]) };
}

// (b) "2d": canvas 2D, pad diisi sekali saat geometri berubah, tensor + buffer float dipakai ulang.
//     getImageData tetap mengalokasikan satu ImageData per frame (tidak bisa dihindari di API 2D).
function pre2d(video, sz) {
  const w = video.videoWidth, h = video.videoHeight;
  ensureBuffers(sz);
  if (!P.c2d) { P.c2d = document.createElement("canvas"); P.ctx2d = P.c2d.getContext("2d", { willReadFrequently: true }); }
  if (!P.g || P.g.w !== w || P.g.h !== h || P.g.sz !== sz || P.g.mode !== "2d") {
    P.g = { ...geom(w, h, sz), mode: "2d" };
    P.c2d.width = sz; P.c2d.height = sz;
    P.ctx2d.fillStyle = "rgb(114,114,114)";
    P.ctx2d.fillRect(0, 0, sz, sz);
  }
  const g = P.g;
  P.ctx2d.drawImage(video, g.left, g.top, g.nw, g.nh); // hanya area dalam; pad 114 tidak pernah tertimpa
  rgbaToNchw(P.ctx2d.getImageData(0, 0, sz, sz).data, sz * sz);
  return { g, tensor: P.tensor };
}

// (c) "webgl": WebGL2, video -> tekstur (LINEAR) -> quad di viewport letterbox, clear 114 -> readPixels ke Uint8Array yang dipakai ulang.
//     Tidak ada alokasi per frame.
function initGL() {
  const c = document.createElement("canvas");
  const gl = c.getContext("webgl2", { antialias: false, depth: false, stencil: false, alpha: true, premultipliedAlpha: false,
    preserveDrawingBuffer: false, powerPreference: "high-performance" });
  if (!gl) throw new Error("WebGL2 tidak tersedia");
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
  const prog = gl.createProgram();
  // uv.y = 0 (baris atas video) di bawah framebuffer, karena readPixels membaca dari bawah: hasilnya baris 0 = atas gambar.
  gl.attachShader(prog, sh(gl.VERTEX_SHADER, `#version 300 es
    in vec2 p; out vec2 uv; void main() { uv = vec2(p.x * 0.5 + 0.5, p.y * 0.5 + 0.5); gl_Position = vec4(p, 0.0, 1.0); }`));
  gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, `#version 300 es
    precision highp float; uniform sampler2D t; in vec2 uv; out vec4 o; void main() { o = vec4(texture(t, uv).rgb, 1.0); }`));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
  gl.useProgram(prog);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "p");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR],
    [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
  gl.pixelStorei(gl.PACK_ALIGNMENT, 1);
  gl.clearColor(114 / 255, 114 / 255, 114 / 255, 1);
  P.gl = { c, gl };
}
function preWebgl(video, sz) {
  const w = video.videoWidth, h = video.videoHeight;
  ensureBuffers(sz);
  if (!P.gl) initGL();
  const { c, gl } = P.gl;
  if (!P.g || P.g.w !== w || P.g.h !== h || P.g.sz !== sz || P.g.mode !== "webgl") {
    P.g = { ...geom(w, h, sz), mode: "webgl" };
    c.width = sz; c.height = sz;
  }
  const g = P.g;
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
  gl.viewport(0, 0, sz, sz);
  gl.clear(gl.COLOR_BUFFER_BIT);
  gl.viewport(g.left, g.top, g.nw, g.nh); // koordinat framebuffer = baris buffer hasil readPixels (sudah dibalik di shader)
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  gl.readPixels(0, 0, sz, sz, gl.RGBA, gl.UNSIGNED_BYTE, P.px);
  rgbaToNchw(P.px, sz * sz);
  return { g, tensor: P.tensor };
}

let preFn = null;
function pickPre(mode) {
  if (mode === "lama") { preRun = "lama"; return preLama; }
  if (mode === "webgl") {
    try { if (!P.gl) initGL(); preRun = "webgl"; return preWebgl; }
    catch (e) { setMsg("WebGL2 gagal (" + errText(e) + "), preprocess pakai 2d"); }
  }
  preRun = "2d"; return pre2d;
}

// ---------- decode + NMS (per kelas, IoU 0.7, conf 0.25) ----------
// output0: [1, 4+nc(+32), N], channel-major; kotak = cx,cy,w,h dalam piksel input; skor sudah sigmoid.
function decode(data, nc, N) {
  const c = [];
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
function postprocess(out0, nc) { return nms(decode(out0.data, nc, out0.dims[2])); }

// ---------- load model ----------
function setMsg(t) { el.msg.textContent = t || ""; }
async function createSession(name, sz, backend, prec, mdl, files) {
  const url = `/models/${MODEL_PREFIX[mdl]}${name}_${sz}${prec === "fp16" ? "_fp16" : ""}.onnx`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} tidak ada (HTTP ${res.status})`);
  const s = await ort.InferenceSession.create(await res.arrayBuffer(), { executionProviders: [backend], graphOptimizationLevel: "all" });
  files.push(url.slice("/models/".length)); // hanya dicatat kalau benar-benar termuat
  return s;
}
async function warmup(session, sz) {
  const t = new ort.Tensor("float32", new Float32Array(3 * sz * sz).fill(0.45), [1, 3, sz, sz]);
  for (let i = 0; i < 2; i++) await session.run({ images: t }); // kompilasi shader (webgpu) / init thread
}
async function loadOnce(backend, sz, wantBox, wantSeg, prec, mdl) {
  const sessions = {}, files = [];
  try {
    const t0 = performance.now();
    if (wantBox) sessions.box = await createSession("box", sz, backend, prec, mdl, files);
    if (wantSeg) sessions.seg = await createSession("seg", sz, backend, prec, mdl, files);
    const loadMs = performance.now() - t0;
    const t1 = performance.now();
    for (const k of Object.keys(sessions)) await warmup(sessions[k], sz);
    return { sessions, files, loadMs, warmMs: performance.now() - t1 };
  } catch (e) {
    for (const s of Object.values(sessions)) { try { await s.release(); } catch (_) {} }
    throw e;
  }
}
async function releaseLoaded() {
  if (!loaded) return;
  for (const s of Object.values(loaded.sessions)) { try { await s.release(); } catch (e) {} }
  loaded = null;
}
async function ensureLoaded(sz, wantBox, wantSeg, pref, prec, mdl) {
  const key = `${pref}|${sz}|${wantBox}|${wantSeg}|${prec}|${mdl}`;
  if (loaded && loaded.key === key) return;
  await releaseLoaded();
  const order = pref === "auto" ? (navigator.gpu ? ["webgpu", "wasm"] : ["wasm"]) : [pref];
  const notes = [];
  for (const be of order) {
    const precs = prec === "fp16" ? ["fp16", "fp32"] : ["fp32"];
    for (const p of precs) {
      try {
        setMsg(`memuat model (${be}, ${p}) ...`);
        const r = await loadOnce(be, sz, wantBox, wantSeg, p, mdl);
        loaded = { key, backend: be, backendWanted: pref, precWanted: prec, precRun: p, precNote: notes.join("; "), ...r };
        setMsg(notes.length ? "CATATAN: " + loaded.precNote : "");
        return;
      } catch (e) {
        console.error(be, p, e);
        notes.push(`${be} ${p} gagal: ${errText(e)}`);
      }
    }
  }
  throw new Error("semua backend gagal: " + notes.join("; "));
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
// Satu frame = preprocess + box (tiap frame) + seg (hanya frame ke-0, N, 2N, ...) + gambar. FPS menghitung SEMUA frame.
async function loop(sz, segN) {
  const S = loaded.sessions;
  frameIdx = 0;
  while (running) {
    const v = el.vid;
    if (v.readyState < 2 || !v.videoWidth) { await sleep(20); continue; }
    try {
      const t0 = performance.now();
      const { g, tensor } = preFn(v, sz);
      lastRes = { w: g.w, h: g.h };
      const t1 = performance.now();
      let boxMs = NaN, boxNms = NaN, segMs = NaN, segNms = NaN, dets = [];
      if (S.box) {
        const a = performance.now();
        const o = await S.box.run({ images: tensor });
        const b = performance.now();
        dets = postprocess(o[S.box.outputNames[0]], BOX_NAMES.length);
        boxMs = b - a; boxNms = performance.now() - b;
        lastNBox = dets.length;
      }
      const segNow = S.seg && frameIdx % segN === 0;
      if (segNow) {
        const a = performance.now();
        const o = await S.seg.run({ images: tensor });
        const b = performance.now();
        lastNSeg = postprocess(o[S.seg.outputNames[0]], SEG_NAMES.length).length; // 32 koef mask diabaikan
        segMs = b - a; segNms = performance.now() - b;
      }
      const d0 = performance.now();
      drawBoxes(dets, g);
      const end = performance.now();
      sample.push({ pre: t1 - t0, box: boxMs, boxNms, seg: segMs, segNms, draw: end - d0, total: end - t0,
        totalSeg: segNow ? end - t0 : NaN, totalNoSeg: segNow ? NaN : end - t0, end });
      if (sample.length > WINDOW) sample.shift();
      if (recOn) {
        if (recT0 === null) recT0 = t0; // jam tes mulai di frame pertama (model dan kamera sudah siap)
        rec.push({ end, pre: t1 - t0, box: boxMs, seg: segMs });
      }
      frameIdx++;
    } catch (e) { // 5b: galat per frame dihitung, loop tidak mati diam-diam
      errCount++; lastErr = errText(e); console.error(e);
      await sleep(50);
    }
    await sleep(0); // lepas ke browser (render video / UI)
  }
}

// ---------- statistik ----------
function snapshot() {
  const col = (k) => median(sample.map((s) => s[k]).filter(Number.isFinite));
  let fps = NaN;
  if (sample.length >= 2) fps = ((sample.length - 1) * 1000) / (sample[sample.length - 1].end - sample[0].end);
  const nSeg = sample.filter((s) => Number.isFinite(s.seg)).length;
  return { n: sample.length, nSeg, pre: col("pre"), box: col("box"), boxNms: col("boxNms"), seg: col("seg"), segNms: col("segNms"),
    draw: col("draw"), total: col("total"), totalSeg: col("totalSeg"), totalNoSeg: col("totalNoSeg"), fps };
}
function resultLine() {
  const s = snapshot(), L = loaded;
  const on = (x) => (x ? "on" : "off");
  return [
    `JalanKu5b ort=${ORT_VERSION}`,
    `model=${el.mdl.value} file=${L ? L.files.join(",") : "-"}`,
    `imgsz=${el.sz.value}`, `presisi=${el.prec.value}->${L ? L.precRun : "-"}`, `backend=${L ? L.backend : "-"}`,
    `segN=${el.segN.value}`, `pre=${preRun}`, `box=${on(L && L.sessions.box)} seg=${on(L && L.sessions.seg)}`,
    `gpuF16=${gpuF16}`, `threads=${threads}`, `cam=${lastRes.w}x${lastRes.h}`,
    `load_ms=${fmt(L && L.loadMs, 0)} warmup_ms=${fmt(L && L.warmMs, 0)}`,
    `med${WINDOW}(n=${s.n},seg=${s.nSeg}): pre=${fmt(s.pre)} box=${fmt(s.box)} boxNMS=${fmt(s.boxNms)} seg=${fmt(s.seg)} segNMS=${fmt(s.segNms)} ` +
      `draw=${fmt(s.draw)} total=${fmt(s.total)} totalSeg=${fmt(s.totalSeg)} totalTanpaSeg=${fmt(s.totalNoSeg)} ms`,
    `fps=${fmt(s.fps, 2)}`, `nBox=${lastNBox} nSeg=${lastNSeg}`,
    ...(L && L.precNote ? [`catatan=${L.precNote}`] : []),
    `UA=${navigator.userAgent}`,
  ].join(" | ");
}
function render() {
  const s = snapshot(), L = loaded;
  el.fps.textContent = `${fmt(s.fps, 2)} fps`;
  el.stats.textContent =
`model        : ${el.mdl.value}   file ${L ? L.files.join(", ") : "-"}
backend      : ${L ? L.backend : "-"}   presisi diminta ${el.prec.value}, JALAN ${L ? L.precRun : "-"}   (gpu shader-f16: ${gpuF16})
imgsz        : ${el.sz.value}   kamera ${lastRes.w}x${lastRes.h}   seg tiap ${el.segN.value} frame   preprocess ${preRun}
load model   : ${fmt(L && L.loadMs, 0)} ms (+ warm-up ${fmt(L && L.warmMs, 0)} ms), sekali
--- median ${WINDOW} frame terakhir (n=${s.n}, seg jalan di ${s.nSeg}) ---
preprocess   : ${fmt(s.pre)} ms
box model    : ${fmt(s.box)} ms    box NMS : ${fmt(s.boxNms)} ms    (${lastNBox} deteksi)
seg model    : ${fmt(s.seg)} ms    seg NMS : ${fmt(s.segNms)} ms    (${lastNSeg} deteksi, tanpa mask; hanya frame yang seg jalan)
gambar       : ${fmt(s.draw)} ms
TOTAL/frame  : ${fmt(s.total)} ms   (frame dengan seg ${fmt(s.totalSeg)}, tanpa seg ${fmt(s.totalNoSeg)})`;
}
setInterval(() => { if (running) render(); }, 1000);

// ---------- wake lock ----------
async function takeWake() {
  try { if (navigator.wakeLock) wakeLock = await navigator.wakeLock.request("screen"); } catch (e) { console.warn("wakeLock", e); }
}
document.addEventListener("visibilitychange", () => {
  if (recOn && document.visibilityState === "hidden") hiddenCount++; // tes tidak sah kalau layar mati / pindah aplikasi
  if (running && document.visibilityState === "visible") takeWake();
});

// ---------- start / stop ----------
const CONTROLS = ["sz", "be", "prec", "segN", "pre", "mdl", "useBox", "useSeg"];
function lockControls(b) { for (const k of CONTROLS) el[k].disabled = b; }
async function start() {
  if (!el.useBox.checked && !el.useSeg.checked) { setMsg("pilih minimal satu model (box/seg)"); return; }
  lockControls(true); el.go.disabled = true;
  try {
    const sz = +el.sz.value;
    await ensureLoaded(sz, el.useBox.checked, el.useSeg.checked, el.be.value, el.prec.value, el.mdl.value);
    preFn = pickPre(params.get("pre") === "lama" ? "lama" : el.pre.value);
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
    el.vid.srcObject = stream;
    await el.vid.play();
    await takeWake();
    sample = []; running = true;
    el.go.textContent = "Stop"; el.go.classList.add("on");
    loop(sz, +el.segN.value);
  } catch (e) {
    console.error(e); setMsg("gagal: " + errText(e)); lockControls(false);
  }
  el.go.disabled = false;
}
async function stop() {
  running = false; recOn = false;
  await sleep(50);
  render();
  el.out.value = resultLine();
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
  el.vid.srcObject = null;
  if (wakeLock) { try { await wakeLock.release(); } catch (e) {} wakeLock = null; }
  el.go.textContent = "Start"; el.go.classList.remove("on");
  lockControls(false);
}
el.go.addEventListener("click", () => (testRunning ? finishTest(true) : running ? stop() : start()));
el.copy.addEventListener("click", async () => {
  const line = running || !el.out.value ? resultLine() : el.out.value;
  el.out.value = line;
  try { await navigator.clipboard.writeText(line); setMsg("tersalin ke clipboard"); }
  catch (e) { el.out.select(); document.execCommand("copy"); setMsg("tersalin (cara lama); kalau gagal, salin teks di kotak bawah"); }
});

// ---------- tes ketahanan 5 menit (5b) ----------
// FPS per menit = median dari nilai fps blok 30 frame berurutan (tiap blok: 29 selang / waktu, sama dengan fps 30 frame di 5a),
// blok masuk menit tempat frame terakhirnya berakhir. "menit 3-5" = 120 s sampai 300 s sejak frame pertama.
// Dengan ?dur=DETIK tes diperpendek (untuk uji di laptop); satu "menit" = dur/5.
const testMs = params.get("dur") ? +params.get("dur") * 1000 : TEST_MS;
const minMs = testMs / 5;
async function batInfo() {
  try { if (!navigator.getBattery) return "n/a"; const b = await navigator.getBattery(); return `${Math.round(b.level * 100)}%${b.charging ? "+cas" : ""}`; }
  catch (e) { return "n/a"; }
}
function blocks(frames) {
  const out = [];
  for (let i = 0; i + WINDOW <= frames.length; i += WINDOW) {
    const a = frames[i], b = frames[i + WINDOW - 1];
    out.push({ fps: ((WINDOW - 1) * 1000) / (b.end - a.end), t: b.end - recT0 });
  }
  return out;
}
function enduranceLine(batEnd) {
  const L = loaded;
  const frames = rec.filter((r) => r.end - recT0 < testMs);
  const bl = blocks(frames);
  const perMin = [0, 1, 2, 3, 4].map((k) => median(bl.filter((b) => b.t >= k * minMs && b.t < (k + 1) * minMs).map((b) => b.fps)));
  const late = frames.filter((r) => r.end - recT0 >= 2 * minMs);
  const m35 = median(bl.filter((b) => b.t >= 2 * minMs).map((b) => b.fps));
  const mean35 = late.length > 1 ? ((late.length - 1) * 1000) / (late[late.length - 1].end - late[0].end) : NaN;
  const col = (k) => median(late.map((r) => r[k]).filter(Number.isFinite));
  const fallback = L && L.precNote ? "ya" : "tidak";
  const on = (x) => (x ? "on" : "off");
  return [
    `JalanKu5b-TAHAN ort=${ORT_VERSION}`,
    `durasi=${(testMs / 1000).toFixed(0)}s`,
    `model=${el.mdl.value} file=${L ? L.files.join(",") : "-"}`,
    `imgsz=${el.sz.value}`, `presisi=${el.prec.value}->${L ? L.precRun : "-"}`, `backend=${L ? L.backend : "-"}`,
    `segN=${el.segN.value}`, `pre=${preRun}`, `box=${on(L && L.sessions.box)} seg=${on(L && L.sessions.seg)}`,
    `cam=${lastRes.w}x${lastRes.h}`, `gpuF16=${gpuF16}`,
    `fps_menit(median blok30) m1=${fmt(perMin[0], 2)} m2=${fmt(perMin[1], 2)} m3=${fmt(perMin[2], 2)} m4=${fmt(perMin[3], 2)} m5=${fmt(perMin[4], 2)}`,
    `FPS_m3-5=${fmt(m35, 2)}`, `(rata2 m3-5=${fmt(mean35, 2)})`, `fps_30awal=${fmt(bl.length ? bl[0].fps : NaN, 2)}`,
    `med_m3-5 ms: pre=${fmt(col("pre"))} box=${fmt(col("box"))} seg=${fmt(col("seg"))}`,
    `frame=${frames.length} blok=${bl.length}`,
    `fallback=${fallback}`, `galat=${errCount}${lastErr ? " (" + lastErr + ")" : ""}`, `layar_tersembunyi=${hiddenCount}`,
    `baterai=${batStart}->${batEnd}`,
    ...(L && L.precNote ? [`catatan=${L.precNote}`] : []),
    `UA=${navigator.userAgent}`,
  ].join(" | ");
}
let testTimer = null, testDone = null;
function currentMinuteFps() {
  if (recT0 === null || !rec.length) return NaN;
  const k = Math.min(4, Math.floor((rec[rec.length - 1].end - recT0) / minMs));
  const f = rec.filter((r) => { const t = r.end - recT0; return t >= k * minMs && t < (k + 1) * minMs; });
  return f.length > 1 ? ((f.length - 1) * 1000) / (f[f.length - 1].end - f[0].end) : NaN;
}
async function finishTest(aborted) {
  clearInterval(testTimer); testTimer = null; testRunning = false;
  if (running) await stop(); else recOn = false;
  el.tes.disabled = false;
  if (aborted) { el.cd.textContent = "tes dibatalkan (Stop ditekan). Tidak ada hasil."; if (testDone) testDone(null); return; }
  const line = enduranceLine(await batInfo());
  el.out5.value = line;
  el.cd.textContent = "SELESAI. Baris hasil ada di kotak bawah.";
  try { await navigator.clipboard.writeText(line); setMsg("baris 5 menit tersalin ke clipboard"); }
  catch (e) { setMsg("belum tersalin otomatis: tekan 'Salin baris 5 menit' atau salin teks di kotak bawah"); }
  if (testDone) testDone(line);
}
async function startTest() {
  if (running || testRunning) return;
  rec = []; recOn = true; recT0 = null; errCount = 0; lastErr = ""; hiddenCount = 0; el.out5.value = "";
  el.tes.disabled = true; el.cd.textContent = "memuat model dan kamera ...";
  batStart = await batInfo();
  await start();
  if (!running) { recOn = false; el.tes.disabled = false; el.cd.textContent = "gagal mulai: " + el.msg.textContent; if (testDone) testDone(null); return; }
  testRunning = true;
  testTimer = setInterval(() => {
    if (recT0 === null) { el.cd.textContent = "menunggu frame pertama ..."; return; }
    const t = performance.now() - recT0;
    if (t >= testMs) { finishTest(false); return; }
    const k = Math.min(4, Math.floor(t / minMs));
    el.cd.textContent = `TES BERJALAN: sisa ${Math.ceil((testMs - t) / 1000)} s | menit ${k + 1}/5 | fps menit ini ${fmt(currentMinuteFps(), 2)} | frame ${rec.length}`;
  }, 500);
}
el.tes.addEventListener("click", startTest);
el.copy5.addEventListener("click", async () => {
  if (!el.out5.value) { setMsg("belum ada hasil tes 5 menit"); return; }
  try { await navigator.clipboard.writeText(el.out5.value); setMsg("baris 5 menit tersalin ke clipboard"); }
  catch (e) { el.out5.select(); document.execCommand("copy"); setMsg("tersalin (cara lama); kalau gagal, salin teks di kotak"); }
});

// model baru (hp-*) hanya ada 320 dan 416
function syncMdl() {
  const baru = el.mdl.value === "baru";
  for (const o of el.sz.options) o.disabled = baru && o.value === "640";
  if (baru && el.sz.value === "640") el.sz.value = "416";
}
el.mdl.addEventListener("change", syncMdl);

// ---------- mode otomatis untuk tes di laptop ----------
// ?tes5=1 (+ sz, be, prec, segN, pre, mdl, dur=DETIK) -> jalankan tes ketahanan lalu POST /report
// ?auto=DETIK&sz=320&be=webgpu&prec=fp32&segN=2&pre=webgl|2d|lama&box=1&seg=1  -> POST /report satu baris hasil
(async function auto() {
  for (const k of ["mdl", "sz", "be", "prec", "segN", "pre"]) if (params.get(k) && !(k === "pre" && params.get(k) === "lama")) el[k].value = params.get(k);
  syncMdl();
  if (params.get("tes5")) {
    el.useBox.checked = params.get("box") !== "0";
    el.useSeg.checked = params.get("seg") !== "0";
    const fin = new Promise((r) => { testDone = r; });
    startTest();
    const line = await fin;
    await fetch("/report", { method: "POST", body: line || "TES5 GAGAL: " + el.msg.textContent + " " + el.cd.textContent });
    document.title = "DONE";
    return;
  }
  if (!params.get("auto")) return;
  el.useBox.checked = params.get("box") !== "0";
  el.useSeg.checked = params.get("seg") !== "0";
  await start();
  if (!running) { await fetch("/report", { method: "POST", body: "AUTO GAGAL: " + el.msg.textContent }); return; }
  if (params.get("cekpre")) { // banding isi buffer webgl vs 2d pada frame yang sama (salah balik/geser akan terlihat besar)
    const v = el.vid, sz = +el.sz.value;
    const a = pre2d(v, sz).tensor.data.slice(), b = preWebgl(v, sz).tensor.data;
    let mx = 0, sum = 0;
    for (let i = 0; i < a.length; i++) { const d = Math.abs(a[i] - b[i]); sum += d; if (d > mx) mx = d; }
    const shift = []; // rata-rata beda bila webgl digeser dx,dy piksel (kanal R, area dalam): minimum harus di 0,0
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      let s = 0, n = 0;
      for (let y = 8; y < sz - 8; y++) for (let x = 8; x < sz - 8; x++) { s += Math.abs(a[y * sz + x] - b[(y + dy) * sz + x + dx]); n++; }
      shift.push(`${dx},${dy}:${(s / n * 255).toFixed(2)}`);
    }
    await fetch("/report", { method: "POST", body: `CEKPRE sz=${sz} cam=${v.videoWidth}x${v.videoHeight} maxdiff=${(mx * 255).toFixed(1)}/255 meandiff=${(sum / a.length * 255).toFixed(3)}/255 geser=[${shift.join(" ")}]` });
    P.g = null;
  }
  await sleep(+params.get("auto") * 1000);
  await stop();
  await fetch("/report", { method: "POST", body: resultLine() });
  document.title = "DONE";
})();
