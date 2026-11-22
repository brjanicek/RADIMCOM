// SATELLITES › SUN NOISE › SUN SCAN: the antenna sweeps across the Sun without stopping, there and back a few
// times. Each S-meter reading is put at the rotor position of its moment (the rotor is read 10 times a second and
// interpolated), the readings are averaged in 1° bins per direction and the beam is fitted in each direction. A lag of
// the S-meter or of the position reading shifts the peak in the direction of the sweep, so the mean of the two
// directions cancels it, and half their difference shows it.
// Loaded after app.js: uses its SUN NOISE globals (snRun, snScan, snCollect, snCfg, snSaveCfg, snGoto, snRotor,
// snBodyNow, snScanFit, snSay, snSleep, snGainProblem, snRenderButtons, snRenderRotor, snRenderScan, ...).

var SN_FAST_BIN = 1.0;          // degrees: the bins the readings are averaged in
var SN_FAST_OVER = 7;           // the rotor is sent this far past each end: it stops within its 5° tolerance, past the end
var SN_FAST_POLL_MS = 100;      // the rotor position is read this often during a sweep
var SN_FAST_MAX_LAG_S = 3;      // a larger lag (either sign) found: something is wrong (the result is not offered for APPLY)

function snFastWrap(d) { return ((d + 540) % 360) - 180; }

/** One sweep along the axis to `end` (the other axis held at `hold`). -> {rot: [[ms, pos]], met: [[ms, dB]]} */
async function snFastSweep(axis, end, hold, hasEl, run) {
  const tgt = axis === "az" ? [Math.round((((end % 360) + 360) % 360) * 10) / 10, hasEl ? Math.max(0, hold) : 0]
    : [Math.round((((hold % 360) + 360) % 360) * 10) / 10, Math.max(0, end)];
  const r = await snFetch(rotorBase() + "/api/rotor", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goto: tgt, source: "sat" }) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
  const rot = [], met = [], t0 = performance.now();
  let last = null, still = 0, moved = false, n = 0;
  snCollect = (db) => { if (Number.isFinite(db)) met.push([performance.now(), db]); };
  try {
    for (;;) {
      await snSleep(SN_FAST_POLL_MS, run);
      if (snFreq() !== run.f || active !== run.vfo) throw new Error("the frequency or the VFO changed");
      const a = performance.now(), i = await snRotor(), b = performance.now();
      if (!i || i.az == null) continue;
      if (i.fault) throw new Error(`rotor: ${i.fault}`);
      const pos = axis === "az" ? i.az : i.el;
      if (pos == null) throw new Error("the rotor gives no elevation");
      rot.push([(a + b) / 2, pos]);
      if (++n % 5 === 0) { rotorInfo = snRot = i; snRenderRotor(); }
      const step = last == null ? 0 : Math.abs(axis === "az" ? snFastWrap(pos - last) : pos - last);
      if (step > 0.3) moved = true;
      still = last != null && step < 0.2 ? still + 1 : 0;
      last = pos;
      const left = Math.abs(axis === "az" ? snFastWrap(pos - tgt[0]) : pos - tgt[1]);
      if (left <= SN_ROT_TOL && still >= 5) break;                  // at the end and standing for 0.5 s
      if (still >= 60) {                                            // 6 s without a move: an end stop, 0° elevation
        if (!moved) throw new Error("the rotor does not move");
        break;
      }
      if (performance.now() - t0 > 90000) throw new Error("a sweep took over 90 s");
    }
  } finally { snCollect = null; }
  return { rot, met };
}

/** The readings of one sweep -> offsets from the Sun: [[x °, linear power]] (the Sun interpolated between s0 and s1). */
function snFastPlace(axis, sw, s0, s1) {
  const sunAt = (t) => {
    const f = s1.t === s0.t ? 0 : Math.min(1, Math.max(0, (t - s0.t) / (s1.t - s0.t)));
    return axis === "az" ? s0.az + snFastWrap(s1.az - s0.az) * f : s0.el + (s1.el - s0.el) * f;
  };
  const rx = sw.rot.map(([t, p]) => [t, axis === "az" ? snFastWrap(p - sunAt(t)) : p - sunAt(t)]);
  const out = [];
  let j = 0;
  for (const [t, db] of sw.met) {
    if (rx.length < 2 || t < rx[0][0] || t > rx[rx.length - 1][0]) continue;
    while (j < rx.length - 2 && rx[j + 1][0] < t) j++;
    const [ta, xa] = rx[j], [tb, xb] = rx[j + 1];
    out.push([xa + (xb - xa) * (tb === ta ? 0 : (t - ta) / (tb - ta)), 10 ** (db / 10)]);
  }
  return out;
}

/** The speed of the sweep in °/s (the median of the moving parts), for the lag in seconds. */
function snFastSpeed(rot) {
  const v = [];
  for (let k = 1; k < rot.length; k++) {
    const dt = (rot[k][0] - rot[k - 1][0]) / 1000, d = Math.abs(snFastWrap(rot[k][1] - rot[k - 1][1]));
    if (dt > 0 && d > 0.2) v.push(d / dt);
  }
  v.sort((a, b) => a - b);
  return v.length ? v[v.length >> 1] : null;
}

/** The bins of both directions -> chart points {x, db, dir}. bins: Map "dir:bin" -> {sx, sp, n, dir} */
function snFastPoints(bins) {
  const pts = [];
  for (const b of bins.values()) if (b.n >= 2) pts.push({ x: b.sx / b.n, db: 10 * Math.log10(b.sp / b.n), dir: b.dir });
  return pts.sort((a, b) => a.x - b.x);
}

async function snFastStart() {
  if (snRun) return;
  const c = { ...snSaveCfg(), scan_el: snCfg().scan_el };
  const g = snGainProblem();
  if (g) { snSay(g, true); return; }
  const run = { why: "", cycles: [], f: snFreq(), vfo: active, scan: true };
  run.abort = (why) => { run.why = why; if (run.onAbort) run.onAbort(); };
  snRun = run;
  snRenderButtons();
  const trips = c.fast_trips, span = c.scan_span;
  snScan = { f: run.f, t: Date.now() / 1000, az: null, el: null, fast: trips };
  const box = document.getElementById("snScanR");
  if (box) box.innerHTML = `<span class="v">fast scan…</span><small>the charts show after the first sweep</small>`;
  try {
    for (const axis of c.scan_el ? ["az", "el"] : ["az"]) {
      if (axis === "el") { const why = snElTooLow((await snBodyNow(c)).el); if (why) { snScan.elSkip = why; snSay(why, true); continue; } }
      const sun = await snBodyNow(c), info = await snRotor() || {}, hasEl = info.el != null;
      if (axis === "el" && !hasEl) throw new Error("the rotor gives no elevation");
      const at = axis === "az" ? sun.az : sun.el, hold = axis === "az" ? sun.el : sun.az;
      const lo = axis === "az" ? at - span - SN_FAST_OVER : Math.max(0, at - span - SN_FAST_OVER), hi = at + span + SN_FAST_OVER;
      snScan[axis] = { pts: [], fit: null, fast: true, sun: at };
      snSay(`FAST ${axis.toUpperCase()}: ±${span}° around the Sun, ${trips}× there and back`);
      // to the start, then the sweeps: up, down, up, down…
      await snGoto(axis === "az" ? lo : hold, axis === "az" ? hold : lo, run);
      await snSleep(1000, run);
      const bins = new Map(), speeds = [];
      for (let k = 0; k < 2 * trips; k++) {
        const dir = k % 2 === 0 ? 1 : -1;
        const s0 = { ...(await snBodyNow(c)), t: performance.now() };
        const sw = await snFastSweep(axis, dir > 0 ? hi : lo, hold, hasEl, run);
        const s1 = { ...(await snBodyNow(c)), t: performance.now() };
        if (snGainProblem()) throw new Error(snGainProblem());
        const sp = snFastSpeed(sw.rot);
        if (sp) speeds.push(sp);
        let used = 0;
        for (const [x, p] of snFastPlace(axis, sw, s0, s1)) {
          if (x < -span || x > span) continue;
          const key = `${dir}:${Math.round(x / SN_FAST_BIN)}`, b = bins.get(key) || { sx: 0, sp: 0, n: 0, dir };
          b.sx += x; b.sp += p; b.n++; used++;
          bins.set(key, b);
        }
        snSay(`FAST ${axis.toUpperCase()} ${dir > 0 ? "→" : "←"} sweep ${k + 1}/${2 * trips}: ${used} readings${sp ? `, ${sp.toFixed(1)}°/s` : ""}`);
        if (used < 10) throw new Error("too few noise readings in a sweep: is the active VFO running (its server restarted since 1.1rc2)?");
        snScan[axis].pts = snFastPoints(bins);
        snRenderScan();
      }
      // the beam in each direction: their mean cancels the lag, half their difference is the lag
      const pts = snScan[axis].pts;
      const [fA, fF, fB] = await Promise.all([snScanFit(pts, axis === "el"), snScanFit(pts.filter((q) => q.dir > 0), axis === "el"),
        snScanFit(pts.filter((q) => q.dir < 0), axis === "el")]);
      let fit = fA;
      if (fA.ok && fF.ok && fB.ok) {
        const lagDeg = (fF.x0 - fB.x0) / 2, speed = speeds.length ? speeds.reduce((s, v) => s + v, 0) / speeds.length : null;
        const lagS = speed ? lagDeg / speed : null;
        fit = { ...fA, x0: Math.round(((fF.x0 + fB.x0) / 2) * 100) / 100, sigma: Math.round((Math.hypot(fF.sigma, fB.sigma) / 2) * 100) / 100 };
        // either sign: + the S-meter lags, − the position reading lags (the median filter of rotor.py, ~0.3 s)
        const bad = lagS != null && Math.abs(lagS) > SN_FAST_MAX_LAG_S;
        snScan[axis].dirs = { there: fF.x0, back: fB.x0, d: fF.x0 - fB.x0, bad, lag_s: lagS };
        snSay(`FAST ${axis.toUpperCase()}: → ${fF.x0.toFixed(1)}°, ← ${fB.x0.toFixed(1)}°, lag ${lagDeg.toFixed(1)}°` +
          (lagS != null ? ` = ${lagS.toFixed(2)} s at ${speed.toFixed(1)}°/s` : "") + (bad ? ": not consistent, not applied" : ": cancelled"), bad);
      } else if (fA.ok) {
        const why = [fF.ok ? "" : `→: ${fF.why || "no fit"}`, fB.ok ? "" : `←: ${fB.why || "no fit"}`].filter(Boolean).join("; ");
        snScan[axis].dirs = { why };
        snSay(`FAST ${axis.toUpperCase()}: the two directions could not be fitted apart (${why})`, true);
      }
      snScan[axis].fit = fit;
      snRenderScan();
      snSay(fit && fit.ok ? `FAST ${axis.toUpperCase()}: error ${fit.x0 >= 0 ? "+" : ""}${fit.x0.toFixed(1)}° ± ${fit.sigma.toFixed(1)}°, beam ${fit.width.toFixed(0)}°, peak ${fit.peak_db.toFixed(2)} dB`
        : `FAST ${axis.toUpperCase()}: ${(fit && fit.why) || "no fit"}`, !(fit && fit.ok));
    }
    const ri = await snRotor() || {};
    snScan.cal = ri.az_cal || null;
    snScan.elOff = ri.el_off != null ? ri.el_off : null;
  } catch (e) {
    snSay(`fast scan ended: ${e.message}`, true);
    if (run.why === "stopped") rotorPost({ stop: true });
  } finally {
    snRun = null;
    snCollect = null;
    snRenderButtons();
    snRenderScan();
  }
}
