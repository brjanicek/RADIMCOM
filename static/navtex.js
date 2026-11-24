// ---------- DECODERS › NAVTEX (navtex.py: SITOR-B maritime safety information), newest message on top ----------
// Loaded after app.js and uses its globals ($, st, active, send, tune, …); app.js calls navtexStatus / navtexAdd /
// navtexText / navtexState / navtexReset / navtexLoad from its state, events and VFO switch.

var navtexFreqList = [];
var NAVTEX_AUDIO_HZ = 1700;       // a key tunes USB this far below the frequency (the tones at 1615 / 1785 Hz)
var NAVTEX_MAX_ROWS = 300;
var NAVTEX_LIVE_MAX = 6000;       // characters of the live text shown

function navtexUtc(t) {
  return new Date(t * 1000).toISOString().slice(11, 19);
}

function navtexStatus(s) {
  if (!s) return;
  $("navtexOn").checked = !!s.navtex;
  for (const b of $("navtexFreqs").querySelectorAll("button[data-f]")) {
    b.classList.toggle("on", Math.abs(s.tune_hz - (Number(b.dataset.f) - NAVTEX_AUDIO_HZ)) <= 600);
  }
}

function navtexFreqs() {
  $("navtexFreqs").innerHTML = navtexFreqList.map((f) =>
    `<button data-f="${f.hz}" title="${escHtml(f.note)} · ${(f.hz / 1e3).toFixed(1)} kHz · tunes ${((f.hz - NAVTEX_AUDIO_HZ) / 1e3).toFixed(1)} kHz USB">` +
    `${escHtml(f.label)}</button>`).join("");
  navtexStatus(st);
}

function navtexState(i) {
  if (!i) return;
  const el = $("navtexInfo");
  if (!i.enabled) { el.textContent = "off"; el.classList.remove("navtex-sync"); return; }
  const parts = [];
  if (!i.locked) parts.push("searching for the tone pair…");
  else {
    parts.push(`tones ${(i.tone_hz / 1e3).toFixed(2)} kHz (${i.offset_hz > 0 ? "+" : ""}${i.offset_hz} Hz) · ${i.snr_db} dB`);
    parts.push(i.sync ? (i.in_msg ? "receiving a message" : "in sync") : "no sync");
  }
  if (i.chars) parts.push(`${i.chars} chars, ${i.lost} lost`);
  el.textContent = parts.join(" · ");
  el.classList.toggle("navtex-sync", !!(i.locked && i.sync));
}

function navtexMatch(tr) {
  const f = $("navtexFilter").value.trim().toUpperCase();
  return !f || tr.dataset.search.includes(f);
}

function navtexRow(m, fresh) {
  const tr = document.createElement("tr");
  if (fresh) tr.classList.add("new");
  const first = m.text.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 3).join(" · ");
  const lost = m.lost ? ` <span class="lost">${m.lost} lost</span>` : "";
  const end = m.end ? ` <span class="muted">[${escHtml(m.end)}]</span>` : "";
  tr.dataset.search = `${m.header} ${m.station} ${m.subject} ${m.subject_name} ${m.text}`.toUpperCase();
  tr.innerHTML = `<td class="utc">${navtexUtc(m.time)}</td><td class="num fq">${(m.freq_hz / 1e3).toFixed(1)}</td>` +
    `<td class="navtex-id" title="station ${escHtml(m.station)} · subject ${escHtml(m.subject)} · number ${escHtml(m.number)}">${escHtml(m.header)}</td>` +
    `<td class="navtex-subj">${escHtml(m.subject_name || m.subject)}</td><td class="msg">${escHtml(first)}${lost}${end}</td>`;
  tr.addEventListener("click", () => {
    const nx = tr.nextElementSibling;
    if (nx && nx.classList.contains("navtex-full")) { nx.remove(); return; }
    const x = document.createElement("tr");
    x.className = "navtex-full";
    const td = document.createElement("td");
    td.colSpan = 5;
    td.innerHTML = `<pre>ZCZC ${escHtml(m.header)}\n${escHtml(m.text)}${m.end ? "" : "\nNNNN"}</pre>`;
    x.appendChild(td);
    tr.after(x);
  });
  tr.hidden = !navtexMatch(tr);
  return tr;
}

function navtexAdd(m, fresh) {
  const tb = $("navtexRows");
  $("navtexEmpty").hidden = true;
  tb.prepend(navtexRow(m, fresh));
  while (tb.querySelectorAll("tr:not(.navtex-full)").length > NAVTEX_MAX_ROWS) tb.lastChild.remove();
}

function navtexText(t) {
  const el = $("navtexLive");
  const stick = el.scrollTop + el.clientHeight >= el.scrollHeight - 8;
  let s = el.textContent + t;
  if (s.length > NAVTEX_LIVE_MAX) s = s.slice(-NAVTEX_LIVE_MAX);
  el.textContent = s;
  if (stick) el.scrollTop = el.scrollHeight;
}

function navtexReset() {
  $("navtexRows").innerHTML = "";
  $("navtexEmpty").hidden = false;
  $("navtexLive").textContent = "";
}

async function navtexLoad(v) {
  try {
    const r = await fetch(v.base + "/api/navtex").then((x) => x.json());
    if (v !== active) return;
    navtexFreqList = r.freqs || [];
    NAVTEX_AUDIO_HZ = r.audio_hz || NAVTEX_AUDIO_HZ;
    navtexFreqs();
    navtexReset();
    for (const m of r.messages || []) navtexAdd(m, false);
    navtexText(r.text || "");
    navtexState(r);
  } catch { /* server unreachable */ }
}

$("navtexOn").addEventListener("change", () => {
  if (!st) return;
  st.navtex = $("navtexOn").checked;
  send({ navtex: st.navtex });
  navtexStatus(st);
});
$("navtexFreqs").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-f]");
  if (!b || !st) return;
  const f = Number(b.dataset.f) - NAVTEX_AUDIO_HZ;
  await ensureVfoFor(f);
  if (!st) return;
  st.mode = "USB";
  renderControls();
  tune(f);
  const changes = { mode: "USB" };
  if (!st.navtex) { st.navtex = true; $("navtexOn").checked = true; changes.navtex = true; decOnlyThis("navtex"); }
  Object.assign(st, changes);
  send(changes);
  navtexStatus(st);
  renderDecTab();
});
$("navtexFilter").addEventListener("input", () => {
  for (const tr of $("navtexRows").querySelectorAll("tr:not(.navtex-full)")) {
    tr.hidden = !navtexMatch(tr);
    const nx = tr.nextElementSibling;
    if (nx && nx.classList.contains("navtex-full")) nx.hidden = tr.hidden;
  }
});
$("navtexClear").addEventListener("click", () => {
  navtexReset();
  if (active) fetch(active.base + "/api/navtex", { method: "DELETE" }).catch(() => {});
});
