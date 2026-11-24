// ---------- DECODERS › BPSK (bpsk.py + funcube.py: satellite telemetry, AO-40 FEC and AX.25), newest on top ----------
// Loaded after app.js and uses its globals ($, st, active, send, tune, …); app.js calls bpskStatus / bpskAdd / bpskStat /
// bpskReset / bpskLoad from its state, events and VFO switch.

var bpskOpts = { bauds: [1200, 2400, 4800, 9600], spans: [3000, 6000, 12000], sats: [] };
var bpskSatsHtml = "";
var BPSK_MAX_ROWS = 300;
var BPSK_USB_OFFSET = 1500;       // a satellite key tunes this far below the downlink (USB: the carrier at 1.5 kHz)

function bpskSelect(sel, values, cur, label) {
  const h = values.map((v) => `<option value="${v}">${label(v)}</option>`).join("");
  if (sel._h !== h) { sel.innerHTML = h; sel._h = h; }
  sel.value = String(cur);
}

function bpskStatus(s) {
  if (!s) return;
  $("bpskOn").checked = !!s.bpsk;
  bpskSelect($("bpskBaud"), bpskOpts.bauds, s.bpsk_baud || 1200, (v) => `${v} Bd`);
  bpskSelect($("bpskSpan"), bpskOpts.spans, s.bpsk_span || 6000, (v) => `±${v / 1000} kHz`);
  const h = bpskOpts.sats.map((b) => `<button data-f="${b.f}" data-baud="${b.baud}" ` +
    `title="${escHtml(b.name)} · ${fmtMHz(b.f, 3)} MHz · ${b.baud} Bd ${escHtml(b.framing)} · tunes ${fmtMHz(b.f - BPSK_USB_OFFSET, 4)} USB">` +
    `${escHtml(b.name.replace(/ \(.*\)$/, ""))}</button>`).join("");
  if (h !== bpskSatsHtml) { $("bpskSats").innerHTML = h; bpskSatsHtml = h; }
  for (const b of $("bpskSats").querySelectorAll("button[data-f]")) {
    b.classList.toggle("on", Math.abs(s.tune_hz - (Number(b.dataset.f) - BPSK_USB_OFFSET)) <= 4000 && Number(b.dataset.baud) === s.bpsk_baud);
  }
  bpskInfo(s, s.bpsk_info);
}

function bpskInfo(s, text) {
  if (!s) return;
  const err = s.bpsk_error ? ` · ${s.bpsk_error}` : "";
  $("bpskInfo").textContent = !s.bpsk ? "off" : (text || "searching for a BPSK carrier…") + err;
  $("bpskInfo").classList.toggle("bpsk-lock", !!(s.bpsk && s.bpsk_stat && s.bpsk_stat.lock));
}

function bpskStat(d) {
  if (!st) return;
  st.bpsk_stat = d;
  st.bpsk_info = d.info;
  bpskInfo(st, d.info);
}

// the newest FUNcube realtime telemetry above the table
function bpskTelemetry(d) {
  const t = d.telemetry;
  if (!t || !t.eps) return;
  const e = t.eps, sw = t.sw, rf = t.rf, pa = t.pa, bob = e;
  const flags = [sw.eclipse ? "ECLIPSE" : "SUN", sw.safe_mode ? "SAFE MODE" : "", sw.deploy_wait ? "DEPLOY WAIT" : ""].filter(Boolean).join(" · ");
  const cell = (k, v, tip) => `<div class="bt-c"${tip ? ` title="${tip}"` : ""}><span>${k}</span><b>${v}</b></div>`;
  const pnl = Object.entries(bob.panel_C || {}).map(([k, v]) => `${k} ${v.toFixed(0)}`).join(" ");
  $("bpskTlm").innerHTML = `<div class="bt-head"><b>${escHtml(t.sat)}</b> · ${escHtml(t.type)} · seq ${sw.seq} · ${d.time} UTC · ${flags}</div>` +
    `<div class="bt-grid">` +
    cell("BATTERY", `${(e.batt_mV / 1000).toFixed(2)} V`) + cell("BATT TEMP", `${e.batt_C} °C`) +
    cell("SYSTEM", `${e.sys_mA} mA`) + cell("SOLAR", `${e.photo_mA} mA`, `Panel voltages ${e.photo_mV.join(" / ")} mV`) +
    cell("PANELS °C", pnl || "–") + cell("RF TEMP", `${rf.temp_C} °C`) +
    cell("PA FWD / REV", `${pa.fwd_mW} / ${pa.rev_mW} mW`) + cell("PA", `${pa.board_mA} mA`) +
    cell("REBOOTS", e.reboots) + cell("3V3 / 5V", `${(e.v3v3_mV / 1000).toFixed(2)} / ${(e.v5_mV / 1000).toFixed(2)} V`) +
    `</div>`;
  $("bpskTlm").hidden = false;
}

function bpskRow(d, fresh) {
  const tr = document.createElement("tr");
  if (fresh) tr.classList.add("new");
  const fec = d.fec ? ` title="sync errors ${d.fec.sync_err} · channel bit errors ${d.fec.ch_err} · RS corrected ${d.fec.rs.join(" + ")} bytes"` : "";
  tr.innerHTML = `<td class="utc">${d.time}</td><td class="num fq">${(d.freq_hz / 1e6).toFixed(6)}</td><td class="num">${d.baud}</td>` +
    `<td class="bpsk-fr"${fec}>${escHtml(d.framing)}</td><td class="bpsk-sat">${escHtml(d.sat || "")}</td><td class="msg">${escHtml(d.text)}</td>`;
  tr.addEventListener("click", () => {
    const nx = tr.nextElementSibling;
    if (nx && nx.classList.contains("bpsk-hex")) { nx.remove(); return; }
    const x = document.createElement("tr");
    x.className = "bpsk-hex";
    const td = document.createElement("td");
    td.colSpan = 6;
    let txt = d.hex.match(/.{1,48}/g).map((l, i) => `${(i * 16).toString(16).padStart(4, "0")}  ${l}`).join("\n");
    if (d.telemetry && d.telemetry.message) txt = `Fitter message: ${d.telemetry.message}\n\n` + txt;
    td.innerHTML = `<pre>${escHtml(txt)}</pre>`;
    x.appendChild(td);
    tr.after(x);
  });
  return tr;
}

function bpskAdd(d, fresh) {
  const tb = $("bpskRows");
  $("bpskEmpty").hidden = true;
  tb.prepend(bpskRow(d, fresh));
  while (tb.rows.length > BPSK_MAX_ROWS) tb.lastChild.remove();
  bpskTelemetry(d);
}

function bpskReset() {
  $("bpskRows").innerHTML = "";
  $("bpskEmpty").hidden = false;
  $("bpskTlm").hidden = true;
}

async function bpskLoad(v) {
  try {
    const r = await fetch(v.base + "/api/bpsk").then((x) => x.json());
    if (v !== active) return;
    bpskOpts = { bauds: r.bauds || bpskOpts.bauds, spans: r.spans || bpskOpts.spans, sats: r.sats || [] };
    bpskSatsHtml = "";
    bpskReset();
    for (const d of r.decodes || []) bpskAdd(d, false);
    bpskStatus(st);
  } catch { /* server unreachable */ }
}

$("bpskOn").addEventListener("change", () => {
  if (!st) return;
  st.bpsk = $("bpskOn").checked;
  send({ bpsk: st.bpsk });
  bpskStatus(st);
});
for (const id of ["bpskBaud", "bpskSpan"]) {
  $(id).addEventListener("change", () => {
    if (!st) return;
    const ch = { bpsk_baud: Number($("bpskBaud").value), bpsk_span: Number($("bpskSpan").value) };
    Object.assign(st, ch);
    send(ch);
    bpskStatus(st);
  });
}
$("bpskSats").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-f]");
  if (!b || !st) return;
  const f = Number(b.dataset.f) - BPSK_USB_OFFSET;
  await ensureVfoFor(f);
  if (!st) return;
  st.mode = "USB";
  renderControls();
  tune(f);
  const changes = { mode: "USB", bpsk_baud: Number(b.dataset.baud) };
  if (!st.bpsk) { st.bpsk = true; $("bpskOn").checked = true; changes.bpsk = true; decOnlyThis("bpsk"); }
  Object.assign(st, changes);
  send(changes);
  bpskStatus(st);
  renderDecTab();
});
$("bpskClear").addEventListener("click", () => {
  bpskReset();
  if (active) fetch(active.base + "/api/bpsk", { method: "DELETE" }).catch(() => {});
});
