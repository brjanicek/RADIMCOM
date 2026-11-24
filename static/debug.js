// SETTINGS › DEBUG: where RADIMCOM spends its time, to find the slow places.
// Loaded before app.js: it wraps the event listeners, timers and fetch of every script, which only measure while
// START is on (otherwise a listener costs one extra check, timeouts and frames are not touched at all).
// START also wraps every global function (each call measured: own time without the functions it calls, and all).
// The servers of the VFOs: CPU of each thread and where it works (dbgstats.py, /api/debug/threads).
// The text is meant to be copied (COPY) and pasted to whoever looks for the slow place.
"use strict";

var dbg = {
  on: false, t0: 0, stats: new Map(), stack: [], top: 0, gaps: [], lastFrame: 0, raf: 0, long: { n: 0, sum: 0, max: 0 },
  loaf: new Map(), fetches: new Map(), wrapped: [], srv: new Map(), srvReset: true, poll: 0, shown: 0, text: "",
};

function dbgEl(id) { return document.getElementById(id); }      // app.js (with its $) comes after this file

/** Where in our scripts something was set up (file:line), from an Error made at that moment. */
function dbgWhere(err) {
  if (!err) return "?";
  if (err._where) return err._where;
  // the first place in our scripts and the one that called it (a helper like listen() in connectEvents is not enough)
  const at = [];
  for (const line of String(err.stack || "").split("\n").slice(1)) {
    if (line.includes("debug.js")) continue;
    const m = line.match(/\/static\/([\w.-]+\.js)(?:\?[^:]*)?:(\d+)/);
    if (m) at.push(at.length && m[1] === at[0][0] ? m[2] : `${m[1]}:${m[2]}`);
    if (at.length === 2) break;
  }
  return (err._where = at.length ? at.join(" ← ") : "?");
}
function dbgErr() {
  const l = Error.stackTraceLimit;
  Error.stackTraceLimit = 5;
  const e = new Error();
  Error.stackTraceLimit = l;
  return e;
}
function dbgAdd(label, all, own) {
  let s = dbg.stats.get(label);
  if (!s) dbg.stats.set(label, (s = { n: 0, own: 0, all: 0, max: 0 }));
  s.n++; s.own += own; s.all += all;
  if (all > s.max) s.max = all;
}
/** Runs f and measures it under the label; nested measured calls are taken out of its own time. */
function dbgRun(label, f, self, args, nt) {
  const S = dbg.stack;
  S.push(0);
  const t0 = performance.now();
  try {
    return nt ? Reflect.construct(f, args, nt) : f.apply(self, args);
  } finally {
    const dt = performance.now() - t0, child = S.pop();
    dbgAdd(typeof label === "function" ? label() : label, dt, dt - child);
    if (S.length) S[S.length - 1] += dt; else dbg.top += dt;
  }
}

// ---- event listeners (DOM, the event streams of the VFOs, the buses): one wrapper per listener function ----
(() => {
  const add = EventTarget.prototype.addEventListener, rem = EventTarget.prototype.removeEventListener;
  const wraps = new WeakMap();
  EventTarget.prototype.addEventListener = function (type, fn, opt) {
    if (typeof fn !== "function") return add.call(this, type, fn, opt);
    let w = wraps.get(fn);
    if (!w) {
      const err = dbgErr();
      w = function (e) {
        if (!dbg.on) return fn.call(this, e);
        const kind = typeof EventSource !== "undefined" && this instanceof EventSource ? "event"
          : this instanceof Node || this === window ? "dom" : "bus";
        // an event of a server: by kind only (one per VFO); the others also by the place they were set up
        const label = kind === "event" ? `event ${e.type}` : `${kind} ${e.type} ${fn.name || dbgWhere(err)}`;
        return dbgRun(label, fn, this, [e]);
      };
      wraps.set(fn, w);
    }
    return add.call(this, type, w, opt);
  };
  EventTarget.prototype.removeEventListener = function (type, fn, opt) {
    const w = typeof fn === "function" && wraps.get(fn);
    if (w) rem.call(this, type, w, opt);
    return rem.call(this, type, fn, opt);
  };
})();

// ---- timers and animation frames ----
(() => {
  const st = window.setTimeout, si = window.setInterval, raf = window.requestAnimationFrame;
  const wrap = (kind, fn, err) => function (...a) {
    if (!dbg.on) return fn.apply(this, a);
    return dbgRun(() => `${kind} ${fn.name || dbgWhere(err)}`, fn, this, a);
  };
  // a timeout or a frame set up while START is off runs as it is (nothing to measure then)
  window.setTimeout = function (fn, ms, ...a) {
    return st.call(window, dbg.on && typeof fn === "function" ? wrap("timeout", fn, dbgErr()) : fn, ms, ...a);
  };
  window.requestAnimationFrame = function (fn) {
    return raf.call(window, dbg.on && typeof fn === "function" ? wrap("frame", fn, dbgErr()) : fn);
  };
  // an interval is set up once and runs for ever: always wrapped
  window.setInterval = function (fn, ms, ...a) {
    return si.call(window, typeof fn === "function" ? wrap("interval", fn, dbgErr()) : fn, ms, ...a);
  };
  dbg.raf0 = raf.bind(window);
})();

// ---- fetch: requests by server port and path (time until the answer's headers) ----
(() => {
  const f0 = window.fetch.bind(window);
  dbg.fetch0 = f0;
  window.fetch = function (input, init) {
    if (!dbg.on) return f0(input, init);
    let key = "?";
    try {
      const u = new URL(typeof input === "string" ? input : input.url, location.href);
      key = `${u.port || "-"} ${u.pathname}`;
    } catch (e) { /* key stays ? */ }
    const t0 = performance.now();
    return f0(input, init).finally(() => {
      const ms = performance.now() - t0;
      let s = dbg.fetches.get(key);
      if (!s) dbg.fetches.set(key, (s = { n: 0, sum: 0, max: 0 }));
      s.n++; s.sum += ms;
      if (ms > s.max) s.max = ms;
    });
  };
})();

// ---- what the browser itself reports: tasks over 50 ms, slow frames with the scripts in them ----
try {
  new PerformanceObserver((l) => {
    if (!dbg.on) return;
    for (const e of l.getEntries()) { dbg.long.n++; dbg.long.sum += e.duration; dbg.long.max = Math.max(dbg.long.max, e.duration); }
  }).observe({ type: "longtask" });
} catch (e) { /* not in this browser */ }
try {
  new PerformanceObserver((l) => {
    if (!dbg.on) return;
    for (const e of l.getEntries()) {
      for (const s of e.scripts || []) {
        const file = String(s.sourceURL || "").split("/").pop().split("?")[0];
        const key = `${s.invokerType || ""} ${s.invoker || "?"} → ${s.sourceFunctionName || "?"}${file ? ` (${file})` : ""}`;
        let x = dbg.loaf.get(key);
        if (!x) dbg.loaf.set(key, (x = { n: 0, sum: 0, max: 0, layout: 0 }));
        x.n++; x.sum += s.duration; x.max = Math.max(x.max, s.duration); x.layout += s.forcedStyleAndLayoutDuration || 0;
      }
    }
  }).observe({ type: "long-animation-frame" });
} catch (e) { /* not in this browser */ }

// ---- global functions: wrapped while START is on ----
const DBG_SKIP = new Set(["$", "dbgWhere", "dbgErr", "dbgAdd", "dbgRun", "dbgStart", "dbgStop", "dbgReset", "dbgFrame",
  "dbgReport", "dbgPoll", "dbgShow", "dbgCopy", "dbgEl", "dbgFrame", "dbgWrapAll", "dbgUnwrapAll",
  "setTimeout", "setInterval", "requestAnimationFrame", "fetch"]);    // the patched ones above: measured there already
const DBG_PROXIES = new WeakSet();
function dbgWrapAll() {
  for (const n of Object.keys(window)) {
    if (DBG_SKIP.has(n)) continue;
    let d;
    try { d = Object.getOwnPropertyDescriptor(window, n); } catch (e) { continue; }
    if (!d || !d.writable || typeof d.value !== "function" || DBG_PROXIES.has(d.value)) continue;
    // a Proxy: properties kept on the function (foo.cache, foo.prototype) stay where the code looks for them
    const f = d.value, label = `${n}()`;
    const w = new Proxy(f, {
      apply: (t, self, a) => (dbg.on ? dbgRun(label, t, self, a) : Reflect.apply(t, self, a)),
      construct: (t, a, nt) => (dbg.on ? dbgRun(label, t, null, a, nt) : Reflect.construct(t, a, nt)),
    });
    DBG_PROXIES.add(w);
    try { window[n] = w; } catch (e) { continue; }
    if (window[n] === w) dbg.wrapped.push([n, f, w]);
  }
}
function dbgUnwrapAll() {
  for (const [n, f, w] of dbg.wrapped) if (window[n] === w) window[n] = f;
  dbg.wrapped = [];
}

function dbgFrame(now) {
  if (!dbg.on) { dbg.raf = 0; return; }
  dbg.raf = dbg.raf0(dbgFrame);
  if (dbg.lastFrame && now - dbg.lastFrame < 2000 && dbg.gaps.length < 200000) dbg.gaps.push(now - dbg.lastFrame);
  dbg.lastFrame = now;
}
function dbgReset() {
  dbg.t0 = performance.now(); dbg.stats.clear(); dbg.top = 0; dbg.gaps = []; dbg.lastFrame = 0;
  dbg.long = { n: 0, sum: 0, max: 0 }; dbg.loaf.clear(); dbg.fetches.clear(); dbg.srv.clear(); dbg.srvReset = true;
}
function dbgStart() {
  if (dbg.on) return;
  dbgReset();
  if (dbgEl("dbgFns").checked) dbgWrapAll();
  dbg.on = true;
  dbg.raf = dbg.raf0(dbgFrame);
  dbgPoll();
  dbg.poll = setInterval(dbgPoll, 2000);
  dbgShow(true);
}
function dbgStop() {
  if (!dbg.on) return;
  dbgReport();
  dbg.on = false;
  clearInterval(dbg.poll);
  dbgUnwrapAll();
  dbgShow(true);
}

// ---- the servers: RADIMCOM's processes (/api/sysload) and the threads of each VFO (/api/debug/threads) ----
async function dbgPoll() {
  if (!dbg.on) return;
  const f = dbg.fetch0, reset = dbg.srvReset, sample = dbgEl("dbgPy").checked;
  dbg.srvReset = false;
  f("/api/sysload").then((r) => (r.ok ? r.json() : null)).then((d) => { dbg.sys = d; }).catch(() => {});
  const list = (typeof vfos !== "undefined" ? vfos : []).filter((v) => v.base !== undefined);
  await Promise.all(list.map(async (v) => {
    try {
      const r = await f(`${v.base}/api/debug/threads?sample=${sample ? 1 : 0}${reset ? "&reset=1" : ""}`);
      if (r.status === 404) throw new Error("no /api/debug/threads: restart the server (dbgstats.py is new)");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      const s = dbg.srv.get(v) || {};
      dbg.srv.set(v, { first: s.first || d, prev: s.last || d, last: d, err: "" });
    } catch (e) {
      const s = dbg.srv.get(v) || {};
      dbg.srv.set(v, { ...s, err: String(e.message || e) });
    }
  }));
}

// ---- the report (plain text, to copy) ----
function dbgReport() {
  const now = performance.now(), el = Math.max(0.001, (now - dbg.t0) / 1000);
  const p = (v, n) => String(v).padStart(n), l = (v, n) => { v = String(v); return v.length > n ? v.slice(0, n - 1) + "…" : v.padEnd(n); };
  const pct = (ms) => ((ms / (el * 1000)) * 100).toFixed(1);
  const out = [];
  const tab = typeof bodyTab !== "undefined" ? bodyTab : "?";
  out.push(`RADIMCOM DEBUG · ${el.toFixed(0)} s since RESET · tab ${tab} · ${new Date().toLocaleTimeString()}` +
    ` · ${dbgEl("dbgFns").checked ? "functions measured" : "functions NOT measured"}`);
  // frames
  const g = dbg.gaps.slice().sort((a, b) => a - b);
  if (g.length) {
    const med = g[Math.floor(g.length / 2)], late = g.filter((x) => x > med * 1.6).length;
    const p99 = g[Math.floor(g.length * 0.99)];
    out.push(`FRAMES ${(1000 / med).toFixed(0)} fps · late ${late} of ${g.length} (${((100 * late) / g.length).toFixed(1)} %)` +
      ` · 99 % under ${p99.toFixed(0)} ms · worst ${g[g.length - 1].toFixed(0)} ms`);
  }
  out.push(`MAIN THREAD measured busy ${pct(dbg.top)} % · long tasks (>50 ms) ${dbg.long.n}, max ${dbg.long.max.toFixed(0)} ms,` +
    ` ${pct(dbg.long.sum)} % of the time`);
  const heap = performance.memory ? `${(performance.memory.usedJSHeapSize / 2 ** 20).toFixed(0)} MB` : "?";
  out.push(`PAGE JS heap ${heap} · ${document.getElementsByTagName("*").length} elements · ` +
    `${document.getElementsByTagName("canvas").length} canvases · ${dbg.wrapped.length} functions wrapped`);
  // what ran
  const rows = [...dbg.stats.entries()].sort((a, b) => b[1].own - a[1].own).slice(0, 40);
  out.push("", `WHAT RAN IN THE PAGE (top 40 by own time; own = without the measured calls inside; % of the main thread)`);
  out.push(`${l("what", 58)} ${p("calls/s", 8)} ${p("own %", 7)} ${p("all %", 7)} ${p("avg ms", 7)} ${p("max ms", 7)}`);
  for (const [k, s] of rows) {
    out.push(`${l(k, 58)} ${p((s.n / el).toFixed(1), 8)} ${p(pct(s.own), 7)} ${p(pct(s.all), 7)} ${p((s.all / s.n).toFixed(2), 7)} ${p(s.max.toFixed(1), 7)}`);
  }
  if (dbg.loaf.size) {
    out.push("", "SLOW FRAMES (>50 ms) BY SCRIPT, as the browser reports them (layout = forced style and layout inside)");
    out.push(`${l("invoker → function (file)", 70)} ${p("n", 5)} ${p("sum ms", 8)} ${p("max ms", 7)} ${p("layout", 7)}`);
    for (const [k, x] of [...dbg.loaf.entries()].sort((a, b) => b[1].sum - a[1].sum).slice(0, 15)) {
      out.push(`${l(k, 70)} ${p(x.n, 5)} ${p(x.sum.toFixed(0), 8)} ${p(x.max.toFixed(0), 7)} ${p(x.layout.toFixed(0), 7)}`);
    }
  }
  // requests
  const vname = (port) => {
    const v = (typeof vfos !== "undefined" ? vfos : []).find((x) => x.base && x.base.includes(`:${port}`));
    return v ? `VFO ${v.name}` : port === "-" ? "page" : `:${port}`;
  };
  if (dbg.fetches.size) {
    out.push("", "REQUESTS (fetch; time until the answer arrives)");
    out.push(`${l("server path", 58)} ${p("n/s", 7)} ${p("avg ms", 7)} ${p("max ms", 7)}`);
    for (const [k, s] of [...dbg.fetches.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 25)) {
      const [port, path] = k.split(" ");
      out.push(`${l(`${vname(port)} ${path}`, 58)} ${p((s.n / el).toFixed(2), 7)} ${p((s.sum / s.n).toFixed(0), 7)} ${p(s.max.toFixed(0), 7)}`);
    }
  }
  // processes
  const sys = dbg.sys && dbg.sys.procs;
  if (sys && sys.server) {
    out.push("", `PROCESSES (CPU = share of all ${sys.cpus || "?"} cores, as Task Manager) · whole PC ${dbg.sys.cpu ?? "?"} %`);
    const row = (n, x) => `${l(n, 14)} CPU ${p(x.cpu, 5)} %  MEM ${p(Math.round(x.mem / 2 ** 20), 5)} MB  ${x.procs.join(", ")}`;
    out.push(row("server", sys.server));
    for (const x of sys.server.parts || []) out.push(row("  " + x.name, x));
    if (sys.client) out.push(row("window", sys.client));
  }
  // threads of each VFO
  for (const [v, s] of dbg.srv) {
    if (!s.last) { out.push("", `VFO ${v.name}: ${s.err || "no answer"}`); continue; }
    const a = s.first, b = s.last, c = s.prev, dtA = b.t - a.t, dtC = b.t - c.t;
    const cpuA = dtA > 0 ? (100 * (b.proc - a.proc)) / dtA : 0, cpuC = dtC > 0 ? (100 * (b.proc - c.proc)) / dtC : 0;
    out.push("", `VFO ${v.name} server (pid ${b.pid}): ${cpuA.toFixed(0)} % of one core on average, ${cpuC.toFixed(0)} % now` +
      `${s.err ? ` · last poll: ${s.err}` : ""}${b.sampled ? ` · ${b.sampled} samples` : ""}`);
    out.push(`  ${l("thread", 34)} ${p("avg %", 6)} ${p("now %", 6)}  where (share of the samples of the thread)`);
    const byId = (r) => new Map(r.threads.map((t) => [t.id, t]));
    const ta = byId(a), tc = byId(c);
    const th = b.threads.map((t) => {
      const t0 = ta.get(t.id), t1 = tc.get(t.id);
      const avg = dtA > 0 && t.cpu != null ? (100 * (t.cpu - (t0 && t0.cpu != null ? t0.cpu : 0))) / dtA : 0;
      const nw = dtC > 0 && t.cpu != null && t1 && t1.cpu != null ? (100 * (t.cpu - t1.cpu)) / dtC : 0;
      return { t, avg, nw };
    }).sort((x, y) => y.avg - x.avg);
    let rest = 0, restN = 0;
    for (const { t, avg, nw } of th) {
      if (avg < 0.5 && nw < 0.5) { rest += avg; restN++; continue; }
      const sm = (b.samples || {})[String(t.id)] || [], tot = sm.reduce((x, y) => x + y[1], 0) || 1;
      const where = sm.slice(0, 3).map(([w, n]) => `${w} ${Math.round((100 * n) / tot)}%`).join(" · ");
      out.push(`  ${l(t.name, 34)} ${p(avg.toFixed(1), 6)} ${p(nw.toFixed(1), 6)}  ${where}`);
    }
    if (restN) out.push(`  ${l(`${restN} other threads`, 34)} ${p(rest.toFixed(1), 6)}`);
    const sumT = th.reduce((x, y) => x + y.avg, 0);
    if (cpuA - sumT > 2) out.push(`  ${l("outside Python threads", 34)} ${p((cpuA - sumT).toFixed(1), 6)}  (numpy / native threads, GC …)`);
  }
  dbg.text = out.join("\n");
  return dbg.text;
}
function dbgShow(force) {
  const o = dbgEl("dbgOut");
  dbgEl("dbgRun").textContent = dbg.on ? "STOP" : "START";
  dbgEl("dbgRun").classList.toggle("on", dbg.on);
  dbgEl("dbgInfo").textContent = dbg.on ? "measuring" : dbg.text ? "stopped" : "";
  if (!o || o.closest("[hidden]")) return;
  const sel = window.getSelection && window.getSelection();
  if (!force && sel && !sel.isCollapsed && o.contains(sel.anchorNode)) return;      // being selected: keep it
  if (dbg.on || force) o.textContent = dbg.on ? dbgReport() : dbg.text || "Press START, use RADIMCOM for a while (the tab, the decoder, the VFO that are slow), then COPY.";
}
async function dbgCopy() {
  const t = dbg.on ? dbgReport() : dbg.text;
  try { await navigator.clipboard.writeText(t); dbgEl("dbgInfo").textContent = "copied"; return; } catch (e) { /* below */ }
  const r = document.createRange();
  r.selectNodeContents(dbgEl("dbgOut"));
  const sel = window.getSelection();
  sel.removeAllRanges(); sel.addRange(r);
  try { document.execCommand("copy"); dbgEl("dbgInfo").textContent = "copied"; } catch (e) { dbgEl("dbgInfo").textContent = "Ctrl+C to copy"; }
}
dbgEl("dbgRun").addEventListener("click", () => (dbg.on ? dbgStop() : dbgStart()));
dbgEl("dbgReset").addEventListener("click", () => { dbgReset(); dbgShow(true); });
dbgEl("dbgCopy").addEventListener("click", dbgCopy);
document.querySelector('[data-set-tab="dbg"]').addEventListener("click", () => setTimeout(() => dbgShow(true)));
setInterval(() => { if (dbg.on) dbgShow(false); }, 1000);
