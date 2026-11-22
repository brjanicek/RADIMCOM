// ---------- DECODERS › Q65 / JT65 (q65.py: jt9 of WSJT-X on the T/R periods), newest on top ----------
// Loaded after app.js and uses its globals ($, st, active, send, tune, …); app.js calls q65Status / q65Add / q65Reset /
// q65Load / q65Cycle from its state, events and VFO switch.

var q65Freqs = null;        // the band keys: [{f, mode, period, sub}] from GET /api/q65
var q65Modes = { Q65: { periods: [15, 30, 60, 120, 300], subs: "ABCDE" }, JT65: { periods: [60], subs: "ABC" } };
var q65BandsHtml = "";
var Q65_MAX_ROWS = 400;
var q65Prog = { rec_t0: null, rec_s: 30, busy: false };
var q65LastTime = null;     // the period of the newest row: a thin line between periods

function q65Opts(sel, values, cur) {
  const h = values.map((v) => `<option value="${v}"${String(v) === String(cur) ? " selected" : ""}>${v}${sel.id === "q65Period" ? " s" : ""}</option>`).join("");
  if (sel._h !== h) { sel.innerHTML = h; sel._h = h; }
  sel.value = String(cur);
}

function q65Status(s) {
  if (!s) return;
  $("q65On").checked = !!s.q65;
  const mode = s.q65_mode || "Q65", m = q65Modes[mode] || q65Modes.Q65;
  $("q65Mode").value = mode;
  q65Opts($("q65Period"), m.periods, s.q65_period || m.periods[0]);
  $("q65Period").disabled = m.periods.length < 2;
  q65Opts($("q65Sub"), m.subs.split(""), s.q65_sub || "A");
  if (q65Freqs) {
    const h = q65Freqs.map((b) => {
      const lbl = b.mode === "JT65" ? `JT65${b.sub}` : `Q65-${b.period}${b.sub}`;
      return `<button data-f="${b.f}" data-mode="${b.mode}" data-period="${b.period}" data-sub="${b.sub}" ` +
        `title="${fmtKHz(b.f, 1)} kHz USB · ${lbl}">${fmtMHz(b.f, 3)}<i class="q65-bm">${b.mode === "JT65" ? "JT65" : "Q65"}</i></button>`;
    }).join("");
    if (h !== q65BandsHtml) { $("q65Bands").innerHTML = h; q65BandsHtml = h; }
    q65MarkBands(s);
  }
  q65Info(s, s.q65_info);
  if (s.q65_prog) q65Prog = s.q65_prog;
  q65RenderProg();
}

function q65MarkBands(s) {
  for (const b of $("q65Bands").querySelectorAll("button[data-f]")) {
    b.classList.toggle("on", !!s && s.mode === "USB" && Math.abs(s.tune_hz - Number(b.dataset.f)) <= 100 && s.q65_mode === b.dataset.mode);
  }
}

function q65Info(s, text) {
  if (!s) return;
  const lbl = s.q65_label ? `${s.q65_label} · ` : "";
  $("q65Info").textContent = !s.q65 ? (s.q65_error ? `off · ${s.q65_error}` : "off")
    : s.q65_error && !text ? `error: ${s.q65_error}` : lbl + (text || "waiting for the next period…");
}

function q65Cycle(d) {
  q65Prog = { ...q65Prog, ...d };
  q65Info(st, d.info);
  q65RenderProg();
}

// the recording of the period: rec_t0 = its start, rec_s = its length; drawn twice a second
function q65RenderProg() {
  const box = $("q65Prog"), on = !!(st && st.q65);
  box.hidden = !on;
  if (!on || bodyTab !== "dec" || decPage !== "q65") return;
  const now = Date.now() / 1000, p = q65Prog, dec = p.busy ? " · jt9 decodes the previous period…" : "";
  const per = (st && st.q65_period) || p.rec_s || 60;
  let pct = 0, txt;
  if (p.rec_t0) {
    const t = Math.max(0, now - p.rec_t0);
    pct = Math.min(100, (100 * t) / p.rec_s);
    const hms = new Date(p.rec_t0 * 1000).toISOString().slice(11, p.rec_s < 60 ? 19 : 16);
    txt = `<span class="wp-r">● RX</span> period ${hms} · ${Math.min(p.rec_s, Math.round(t))} / ${p.rec_s} s${dec}`;
  } else {
    txt = `waiting for the next period · it starts in ${Math.round(Math.ceil(now / per) * per - now)} s${dec}`;
  }
  box.classList.toggle("wp-rec", !!p.rec_t0);
  box.classList.toggle("wp-busy", !!p.busy);
  box.querySelector(".wp-fill").style.width = pct.toFixed(1) + "%";
  const el = box.querySelector(".wp-txt");
  if (el.innerHTML !== txt) el.innerHTML = txt;
}
setInterval(q65RenderProg, 500);

function q65Row(d, fresh) {
  const tr = document.createElement("tr");
  if (fresh) tr.classList.add("new");
  const lvl = Math.max(0, Math.min(1, (d.snr + 30) / 30));
  const snrCls = d.snr >= -10 ? "s-hi" : d.snr >= -20 ? "s-mid" : "s-lo";
  const call = d.call ? escHtml(d.call) : "";
  let msg = escHtml(d.msg);
  if (call) msg = msg.replace(call, `<span class="t-call">${call}</span>`);
  const ap = d.flags && /^q[1-9]/.test(d.flags) ? ` <i class="q65-ap" title="decoded with a priori information (${escHtml(d.flags)})">AP</i>` : "";
  tr.innerHTML = `<td class="utc">${d.time}</td>` +
    `<td class="snr ${snrCls}"><div class="cf"><span class="snr-v">${d.snr > 0 ? "+" : ""}${d.snr}</span><span class="snr-b"><i style="width:${(lvl * 100).toFixed(0)}%"></i></span></div></td>` +
    `<td class="num">${d.dt.toFixed(1)}</td><td class="num">${d.df}</td><td class="q65-mode">${escHtml(d.mode)}${ap}</td>` +
    `<td class="num fq">${(d.freq_hz / 1e6).toFixed(6)}</td><td class="msg">${msg}</td>`;
  return tr;
}

function q65Add(d, fresh) {
  const tb = $("q65Rows");
  $("q65Empty").hidden = true;
  const tr = q65Row(d, fresh);
  if (q65LastTime !== null && q65LastTime !== d.time && tb.firstChild) tb.firstChild.classList.add("q65-sep");
  q65LastTime = d.time;
  tb.prepend(tr);
  while (tb.rows.length > Q65_MAX_ROWS) tb.lastChild.remove();
}

function q65Reset() {
  $("q65Rows").innerHTML = "";
  $("q65Empty").hidden = false;
  q65LastTime = null;
}

async function q65Load(v) {
  try {
    const r = await fetch(v.base + "/api/q65").then((x) => x.json());
    if (v !== active) return;
    q65Freqs = r.freqs || q65Freqs;
    if (r.modes) q65Modes = r.modes;
    q65BandsHtml = "";
    q65Reset();
    for (const d of r.decodes || []) q65Add(d, false);
    q65Status(st);
  } catch { /* server unreachable */ }
}

$("q65On").addEventListener("change", () => {
  if (!st) return;
  st.q65 = $("q65On").checked;
  send({ q65: st.q65 });
  q65Status(st);
});
for (const id of ["q65Mode", "q65Period", "q65Sub"]) {
  $(id).addEventListener("change", () => {
    if (!st) return;
    const ch = { q65_mode: $("q65Mode").value, q65_period: Number($("q65Period").value), q65_sub: $("q65Sub").value };
    if (id === "q65Mode") {          // another mode: its own periods and submodes (the server corrects the rest)
      const m = q65Modes[ch.q65_mode];
      if (!m.periods.includes(ch.q65_period)) ch.q65_period = ch.q65_mode === "JT65" ? 60 : 30;
      if (!m.subs.includes(ch.q65_sub)) ch.q65_sub = "A";
    }
    Object.assign(st, ch);
    send(ch);
    q65Status(st);
  });
}
$("q65Bands").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-f]");
  if (!b || !st) return;
  await ensureVfoFor(Number(b.dataset.f));
  if (!st) return;
  st.mode = "USB";
  renderControls();
  tune(Number(b.dataset.f));
  const changes = { mode: "USB", q65_mode: b.dataset.mode, q65_period: Number(b.dataset.period), q65_sub: b.dataset.sub };
  if (!st.q65) { st.q65 = true; $("q65On").checked = true; changes.q65 = true; decOnlyThis("q65"); }
  Object.assign(st, changes);
  send(changes);
  q65Status(st);
  renderDecTab();
});
$("q65Clear").addEventListener("click", () => {
  q65Reset();
  if (active) fetch(active.base + "/api/q65", { method: "DELETE" }).catch(() => {});
});
