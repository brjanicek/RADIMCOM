// ---------- COMPOSITE map: multiselect and STCA (Short Term Conflict Alert) ----------
// Multiselect: Alt + click (or Ctrl + click) on an aircraft, ship or sonde, on the map or in the list, adds it to the
// selection (the one selected before joins it), again removes it; a plain click selects one track as before, a click on
// the empty map drops the selection. The selected aircraft are listed right of the map with the separation of every pair
// (now and at the closest point of approach) and joined on the map by dashed lines.
// STCA: every pair of airborne aircraft with a fresh position is predicted linearly (ground speed, track, vertical rate)
// over the look-ahead time; a pair that is, or will be, closer than both minima (horizontal NM and vertical ft) is an
// alert: a line between them, rings, its row in the STCA list. Only a help for watching, not an ATC tool.
// The settings are mapOpts.stca (the map settings window, section STCA; the STCA bar over the map steps the main ones).
// Hooks in app.js: mapOptsRead0 (stcaOptsNorm), the settings window (stcaSecHtml, stcaOnInput), renderComMap (selected
// marks, clicks, stcaDraw, stcaInfo), renderComSide (stcaSideHtml), renderComList (selected rows), the list click,
// COM_BARS (the STCA bar: stcaBarHtml, stcaBarClick).

const comMulti = new Set();   // the tracks selected with Alt / Ctrl + click (this window only)
const comMultiHas = (id) => comMulti.has(id);

/** A click on a track (map or list): Alt / Ctrl = into / out of the selection (-> true); a plain click drops the
 *  selection of several (-> false, the caller selects the one track). */
function comMultiClick(id, ev) {
  if (!ev || !(ev.altKey || ev.ctrlKey)) { comMulti.clear(); return false; }
  if (!comMulti.size && comSel && comSel !== id) comMulti.add(comSel);   // the one selected before joins
  if (comMulti.has(id)) comMulti.delete(id); else comMulti.add(id);
  comSel = comMulti.has(id) ? id : [...comMulti].pop() || null;   // the details: the one clicked last
  if (comMulti.size < 2) comMulti.clear();   // one left: an ordinary selection
  return true;
}

// ----- settings: mapOpts.stca (remembered in the browser, the same in all windows) -----
const STCA_STEPS = {
  h: [1, 2, 3, 5, 8, 10], v: [500, 1000, 1500, 2000], look: [30, 60, 90, 120, 180, 300],
  floor: [0, 500, 1000, 1500, 3000, 6000, 10000], age: [10, 20, 30, 60],
};
const STCA_DEF = { on: true, h: 5, v: 1000, look: 120, floor: 1500, age: 30, scope: "all", vr: true, shr: true, sel: true,
  blink: true, sound: false, c: "#ff2a2a", cSel: "#ff8c1a" };
const STCA_STEP_S = 5, STCA_SEL_MAX = 6;
try { localStorage.removeItem("stcaOpt"); } catch { /* the first version kept its own key */ }
/** The stored STCA settings checked (unknown / missing -> the defaults). */
function stcaOptsNorm(v) {
  const o = v && typeof v === "object" ? v : {};
  const pick = (k) => (STCA_STEPS[k].includes(+o[k]) ? +o[k] : STCA_DEF[k]);
  const b = (k) => (o[k] != null ? !!o[k] : STCA_DEF[k]);
  const hex = (k) => (/^#[0-9a-f]{6}$/i.test(o[k] || "") ? o[k] : STCA_DEF[k]);
  return { on: b("on"), h: pick("h"), v: pick("v"), look: pick("look"), floor: pick("floor"), age: pick("age"),
    scope: o.scope === "sel" ? "sel" : "all", vr: b("vr"), shr: b("shr"), sel: b("sel"), blink: b("blink"), sound: b("sound"),
    c: hex("c"), cSel: hex("cSel") };
}
const stcaO = () => (typeof mapOpts !== "undefined" && mapOpts.stca) || STCA_DEF;
function stcaSet(patch) {
  mapOptsSet({ stca: stcaOptsNorm({ ...stcaO(), ...patch }) });
  renderComMap();
}
let stcaAlerts = [], stcaSelPairs = [], stcaSeen = new Set();   // the last render: the alerts, the selected pairs, the alert keys

/** Kinematics of an airborne aircraft with a fresh position, moved to now: lat, lon, alt (ft), ve / vn (NM/s), vz (ft/s). */
function stcaKin(m, now, o) {
  const a = m.air;
  if (!a || a.ground || typeof a.alt_ft !== "number") return null;
  const age = Math.max(0, now - m.t);
  if (age > o.age) return null;
  const r = Math.PI / 180, trk = m.track ?? comHeading(m) ?? a.track, gs = a.gs_kt;
  const moving = trk != null && gs != null;
  const ve = moving ? (gs * Math.sin(trk * r)) / 3600 : 0, vn = moving ? (gs * Math.cos(trk * r)) / 3600 : 0;
  const vz = o.vr && typeof a.vs_fpm === "number" ? a.vs_fpm / 60 : 0;
  const lat = m.lat + (vn * age) / 60;
  return { m, lat, lon: m.lon + (ve * age) / (60 * Math.cos(lat * r) || 1e-9), alt: a.alt_ft + vz * age, ve, vn, vz };
}

/** A pair now and over the look-ahead: h0 / z0 (NM / ft) now, tc / hc / zc at the closest point of approach (horizontal),
 *  hit = seconds to the first infringement of both minima (0 = now, null = none) with hh / hz then. Without full a
 *  pair that cannot come near in the look-ahead -> null at once. */
function stcaPair(A, B, o, full) {
  const r = Math.PI / 180, k = 60 * Math.cos(((A.lat + B.lat) / 2) * r);
  const dx = (B.lon - A.lon) * k, dy = (B.lat - A.lat) * 60, dz = B.alt - A.alt;
  const vx = B.ve - A.ve, vy = B.vn - A.vn, vz = B.vz - A.vz, T = o.look;
  const h0 = Math.hypot(dx, dy);
  if (!full && (h0 - Math.hypot(vx, vy) * T > o.h || Math.abs(dz) - Math.abs(vz) * T > o.v)) return null;
  const v2 = vx * vx + vy * vy, tc = v2 > 1e-12 ? Math.max(0, Math.min(T, -(dx * vx + dy * vy) / v2)) : 0;
  const at = (t) => [Math.hypot(dx + vx * t, dy + vy * t), dz + vz * t];
  const inf = ([h, z]) => h < o.h && Math.abs(z) < o.v;
  let hit = null, hh = 0, hz = 0;
  for (let t = 0; t <= T; t += STCA_STEP_S) {
    const p = at(t);
    if (inf(p)) { hit = t; [hh, hz] = p; break; }
  }
  const [hc, zc] = at(tc);
  if (hit == null && inf([hc, zc])) { hit = Math.round(tc); hh = hc; hz = zc; }   // a short crossing between the steps
  return { h0, z0: dz, tc, hc, zc, hit, hh, hz };
}

const stcaTxt = (h, z) => `${h.toFixed(1)} NM · ${Math.round(Math.abs(z) / 100) * 100} ft`;
const stcaWhen = (s) => (!s ? "NOW" : s < 60 ? `in ${Math.round(s)} s` : `in ${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`);
const stcaKey = (p) => [p.a.m.id, p.b.m.id].sort().join("|");

/** A text label on the map at a point (centred, not clickable), in colour c; in its own pane over everything (also
 *  over the labels of the aircraft). Gives the marker. */
function stcaLabel(layer, ll, html, cls, c) {
  const map = typeof comMap !== "undefined" ? comMap : null;
  if (map && !map.getPane("stcaTop")) map.createPane("stcaTop").style.zIndex = 700;   // tooltips are 650
  return L.marker(ll, { icon: L.divIcon({ className: `stca-lbl ${cls || ""}`, html: `<span style="--stc:${c}">${html}</span>`, iconSize: null }),
    interactive: false, keyboard: false, zIndexOffset: 1500, ...(map ? { pane: "stcaTop" } : {}) }).addTo(layer);
}

const STCA_PRED_MIN = 2;   // the prediction of an aircraft in conflict: minutes ahead (a tick each minute)
/** The straight-ahead line of an aircraft for STCA_PRED_MIN minutes (track and ground speed now), in the alert colour. */
function stcaPred(layer, m, color) {
  const a = m.air;
  const brg = m.track ?? (typeof comHeading === "function" ? comHeading(m) : null) ?? (a && a.track), kt = a && a.gs_kt;
  if (!a || a.ground || brg == null || !(kt >= 30)) return;
  const R = 6371, b = (brg * Math.PI) / 180, la = (m.lat * Math.PI) / 180, lo = (m.lon * Math.PI) / 180;
  const dest = (d) => {   // great circle: the point d km ahead
    const r = d / R, la2 = Math.asin(Math.sin(la) * Math.cos(r) + Math.cos(la) * Math.sin(r) * Math.cos(b));
    const lo2 = lo + Math.atan2(Math.sin(b) * Math.sin(r) * Math.cos(la), Math.cos(r) - Math.sin(la) * Math.sin(la2));
    return [(la2 * 180) / Math.PI, (lo2 * 180) / Math.PI];
  };
  const km = (kt * 1.852) / 60, pts = [[m.lat, m.lon]];
  for (let i = 1; i <= STCA_PRED_MIN; i++) pts.push(dest(km * i));
  L.polyline(pts, { color, weight: 2, opacity: 0.95, dashArray: "2 4", interactive: false }).addTo(layer);
  const tick = L.divIcon({ className: "map-tick", html: `<i style="transform: rotate(${Math.round(brg)}deg); border-color: ${color}"></i>`, iconSize: [9, 9], iconAnchor: [4.5, 4.5] });
  for (let i = 1; i <= STCA_PRED_MIN; i++) L.marker(pts[i], { icon: tick, interactive: false, keyboard: false }).addTo(layer);
}

let stcaMovedLbl = new Set();   // tooltips moved out of the way of a warning (put back when no longer needed)
/** The labels of the aircraft of an alert moved so that they do not cover its warning (the shortest way out). */
function stcaClearLabels(warns) {
  const map = typeof comMap !== "undefined" ? comMap : null, moved = new Set();
  if (!map || typeof comMarks === "undefined") return;
  const c = map.getContainer(), box = c.getBoundingClientRect();
  const sx = box.width / (c.offsetWidth || box.width) || 1, sy = box.height / (c.offsetHeight || box.height) || 1;   // a scaled page
  const rect = (el) => { const r = el.getBoundingClientRect(); return [(r.left - box.left) / sx, (r.top - box.top) / sy, (r.right - box.left) / sx, (r.bottom - box.top) / sy]; };
  for (const [mk, ids] of warns) {
    const wEl = mk.getElement() && mk.getElement().firstElementChild;
    if (!wEl) continue;
    const w = rect(wEl), pad = 4;
    for (const id of ids) {
      const am = comMarks.get(id), tt = am && am.getTooltip(), el = tt && tt.getElement();
      if (!el || !tt._lbl || !tt._lbl.on) continue;
      const au = tt._auto || [0, 0], r = rect(el);
      const l = [r[0] - au[0], r[1] - au[1], r[2] - au[0], r[3] - au[1]];   // where it is without the old move
      if (!(l[0] < w[2] + pad && l[2] > w[0] - pad && l[1] < w[3] + pad && l[3] > w[1] - pad)) continue;
      const opts = [[0, w[1] - pad - l[3]], [0, w[3] + pad - l[1]], [w[0] - pad - l[2], 0], [w[2] + pad - l[0], 0]];
      const best = opts.reduce((b, o) => (Math.hypot(...o) < Math.hypot(...b) ? o : b));
      tt._auto = best;
      moved.add(tt);
    }
  }
  for (const tt of new Set([...stcaMovedLbl, ...moved])) {
    if (!moved.has(tt)) tt._auto = null;
    if (!tt._source || !tt._source._map) continue;
    mapLblPlace(tt, tt._source._map);
    tt.update();
    mapLeaderLater(tt);
  }
  stcaMovedLbl = moved;
}

/** A short two-tone beep (a new alert, when Sound is on). */
let stcaAc = null;
function stcaBeep() {
  try {
    stcaAc = stcaAc || new (window.AudioContext || window.webkitAudioContext)();
    const t0 = stcaAc.currentTime;
    for (const [f, dt] of [[880, 0], [660, 0.18], [880, 0.36]]) {
      const os = stcaAc.createOscillator(), g = stcaAc.createGain();
      os.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t0 + dt);
      g.gain.exponentialRampToValueAtTime(0.15, t0 + dt + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.15);
      os.connect(g).connect(stcaAc.destination);
      os.start(t0 + dt);
      os.stop(t0 + dt + 0.16);
    }
  } catch { /* no audio */ }
}

/** After the marks of renderComMap: the selection kept to the tracks on the map, the alerts and the pairs of the
 *  selected aircraft computed and drawn into layer (cleared by each render). */
function stcaDraw(layer, drawn, now) {
  const ids = new Set(drawn.map((m) => m.id));
  for (const id of comMulti) if (!ids.has(id)) comMulti.delete(id);
  if (comMulti.size < 2) comMulti.clear();
  const o = stcaO(), kin = [];
  for (const m of drawn) { const k = stcaKin(m, now, o); if (k) kin.push(k); }
  stcaAlerts = [];
  if (o.on) {
    const isSel = (id) => id === comSel || comMulti.has(id), shrOnly = (m) => m.srcs.every((x) => COM_SHARED.has(x));
    const pool = o.shr ? kin : kin.filter((k) => !shrOnly(k.m));
    for (let i = 0; i < pool.length; i++) {
      for (let j = i + 1; j < pool.length; j++) {
        const A = pool[i], B = pool[j];
        if (Math.min(A.alt, B.alt) < o.floor) continue;   // below the floor: approaches, parallel runways
        if (o.scope === "sel" && !isSel(A.m.id) && !isSel(B.m.id)) continue;
        const p = stcaPair(A, B, o, false);
        if (p && p.hit != null) stcaAlerts.push({ a: A, b: B, ...p });
      }
    }
    stcaAlerts.sort((x, y) => x.hit - y.hit || x.hh - y.hh);
  }
  const keys = new Set(stcaAlerts.map(stcaKey));
  if (o.sound && [...keys].some((k) => !stcaSeen.has(k))) stcaBeep();   // a new alert
  stcaSeen = keys;
  const sel = o.sel ? kin.filter((k) => comMulti.has(k.m.id)) : [];
  stcaSelPairs = [];
  if (sel.length <= STCA_SEL_MAX) {
    for (let i = 0; i < sel.length; i++) for (let j = i + 1; j < sel.length; j++) stcaSelPairs.push({ a: sel[i], b: sel[j], ...stcaPair(sel[i], sel[j], o, true) });
  }
  const mid = (p) => [(p.a.m.lat + p.b.m.lat) / 2, (p.a.m.lon + p.b.m.lon) / 2];
  for (const p of stcaSelPairs) {   // the selected pairs: a dashed line with the separation now
    if (keys.has(stcaKey(p))) continue;
    L.polyline([[p.a.m.lat, p.a.m.lon], [p.b.m.lat, p.b.m.lon]], { color: o.cSel, weight: 1.2, opacity: 0.85, dashArray: "4 5", interactive: false }).addTo(layer);
    stcaLabel(layer, mid(p), escHtml(stcaTxt(p.h0, p.z0)), "sel", o.cSel);
  }
  const ring = new Map(), warns = [];
  for (const p of stcaAlerts) {   // the alerts: a line (dashed = predicted), rings around the aircraft (blinking = now)
    L.polyline([[p.a.m.lat, p.a.m.lon], [p.b.m.lat, p.b.m.lon]], { color: o.c, weight: 2.2, opacity: 0.95, dashArray: p.hit ? "7 5" : null, interactive: false }).addTo(layer);
    warns.push([stcaLabel(layer, mid(p), `STCA ${stcaWhen(p.hit)} · ${escHtml(stcaTxt(p.hh, p.hz))}`, !p.hit && o.blink ? "now" : "", o.c), [p.a.m.id, p.b.m.id]]);
    for (const k of [p.a, p.b]) ring.set(k.m.id, [k.m, ring.has(k.m.id) && ring.get(k.m.id)[1] ? true : !p.hit]);
  }
  for (const [m] of ring.values()) stcaPred(layer, m, o.c);   // the aircraft in conflict: where they are in 2 min
  stcaClearLabels(warns);   // the labels of the pair out of the way of its warning
  for (const [m, now0] of ring.values()) {
    L.circleMarker([m.lat, m.lon], { radius: 16, color: o.c, weight: 2, fill: false, interactive: false, className: `stca-ring${now0 && o.blink ? " blink" : ""}` }).addTo(layer);
  }
}

/** The part of the status row under the map. */
const stcaInfo = () => (stcaO().on && stcaAlerts.length ? ` · STCA ${stcaAlerts.length}` : "");

/** Above the details right of the map: the STCA alerts and the selection of several tracks with its pairs. */
function stcaSideHtml() {
  const esc = escHtml, o = stcaO(), nm = (m) => esc(String(comName(m) || m.id)), out = [];
  if (stcaAlerts.length) {
    out.push(`<div class="cs-blk stca-blk" style="--stc:${o.c}"><div class="com-kind stca-head" style="--stc:${o.c}">STCA · ${stcaAlerts.length} ALERT${stcaAlerts.length > 1 ? "S" : ""}</div><table class="stca-t" style="--stc:${o.c}">` +
      `<colgroup><col><col class="w-when"><col class="w-n"><col class="w-n"></colgroup><tr><th>Pair</th><th>When</th><th>H NM</th><th>V ft</th></tr>` +
      stcaAlerts.map((p) => `<tr class="stca-row${p.hit ? "" : " now"}" data-stca="pair" data-a="${esc(p.a.m.id)}" data-b="${esc(p.b.m.id)}" title="Select the pair and show it on the map">` +
        `<td>${nm(p.a.m)} – ${nm(p.b.m)}</td><td>${stcaWhen(p.hit)}</td><td>${p.hh.toFixed(1)}</td><td>${Math.round(Math.abs(p.hz) / 100) * 100}</td></tr>`).join("") +
      `</table><span class="muted cs-note">minima ${o.h} NM / ${o.v} ft, look-ahead ${o.look} s, above ${o.floor} ft${o.scope === "sel" ? ", selected only" : ""}</span></div>`);
  }
  if (comMulti.size >= 2) {
    const list = [...comMulti].map((id) => comMerged.find((x) => x.id === id)).filter(Boolean);
    const row = (m) => {   // only what is needed: the name, FL with ↑↓, speed, track (the rest in the title)
      const a = m.air, fl = !a ? (m.ship ? "ship" : m.sonde ? "sonde" : "") : a.ground ? "GND" : a.alt_ft != null ? String(Math.round(a.alt_ft / 100)).padStart(3, "0") : "";
      const trk = m.track ?? (a && a.track);
      const tip = a && typeof a.vs_fpm === "number" ? `${a.vs_fpm > 0 ? "+" : ""}${Math.round(a.vs_fpm)} fpm` : "";
      return `<tr${m.id === comSel ? ' class="sel"' : ""}${tip ? ` title="${tip}"` : ""}><td><a href="#" data-stca="focus" data-id="${esc(m.id)}" title="Its details below">${nm(m)}</a></td>` +
        `<td>${fl}${typeof comTrend === "function" ? comTrend(a) : ""}</td>` +
        `<td>${a && a.gs_kt != null && !a.ground ? Math.round(a.gs_kt) : ""}</td><td>${trk != null ? `${String(Math.round(trk) % 360).padStart(3, "0")}°` : ""}</td>` +
        `<td><button type="button" class="stca-x" data-stca="unsel" data-id="${esc(m.id)}" title="Out of the selection">✕</button></td></tr>`;
    };
    out.push(`<div class="cs-blk stca-blk sel" style="--stc:${o.cSel}"><div class="com-kind stca-head sel" style="--stc:${o.cSel}">SELECTED (${list.length}) <button type="button" class="key small" data-stca="clear" title="Drop the selection (or a click on the empty map)">CLEAR</button></div>` +
      `<table class="stca-t" style="--stc:${o.cSel}"><colgroup><col><col class="w-n"><col class="w-n"><col class="w-n"><col class="w-x"></colgroup>` +
      `<tr><th>Flight</th><th>FL</th><th>kt</th><th>Trk</th><th></th></tr>${list.map(row).join("")}</table>`);
    if (stcaSelPairs.length) {
      out.push(`<table class="stca-t" style="--stc:${o.c}"><colgroup><col><col class="w-sep"><col class="w-when"><col class="w-sep"></colgroup><tr><th>Pair</th><th title="Horizontal / vertical separation now">Now</th><th title="Closest point of approach (horizontal) within the look-ahead">CPA</th><th>at CPA</th></tr>` +
        stcaSelPairs.map((p) => `<tr${p.hit != null ? ' class="stca-row"' : ""}><td>${nm(p.a.m)} – ${nm(p.b.m)}</td><td>${stcaTxt(p.h0, p.z0)}</td>` +
          `<td>${p.tc > 0 && p.tc < o.look ? stcaWhen(p.tc) : p.tc ? `> ${o.look} s` : "diverging"}</td><td>${p.tc ? stcaTxt(p.hc, p.zc) : ""}</td></tr>`).join("") + "</table>");
    } else if (o.sel && list.filter((m) => m.air).length >= 2) {
      out.push(`<span class="muted cs-note">separation: only airborne aircraft with a position younger than ${o.age} s${list.length > STCA_SEL_MAX ? `, at most ${STCA_SEL_MAX} selected` : ""}</span>`);
    }
    out.push("</div>");   // the block SELECTED
  }
  return out.join("");
}
document.addEventListener("click", (e) => {   // the STCA list and the selection right of the map
  const t = e.target.closest && e.target.closest("#comSide [data-stca]");
  if (!t) return;
  e.preventDefault();
  const a = t.dataset.stca;
  if (a === "pair") {   // an alert: both selected, the map on them
    comMulti.clear();
    comMulti.add(t.dataset.a).add(t.dataset.b);
    comSel = t.dataset.a;
    const pts = comMerged.filter((m) => comMulti.has(m.id)).map((m) => [m.lat, m.lon]);
    if (comMap && pts.length) comMap.fitBounds(pts, { padding: [60, 60], maxZoom: Math.max(comMap.getZoom(), 9) });
  } else if (a === "focus") comSel = t.dataset.id;
  else if (a === "unsel") {
    comMulti.delete(t.dataset.id);
    if (comSel === t.dataset.id) comSel = [...comMulti].pop() || null;
    if (comMulti.size < 2) comMulti.clear();
  } else if (a === "clear") { comMulti.clear(); comSel = null; }
  renderComMap();
});

// ----- the map settings window (COMPOSITE): section STCA -----
function stcaSecHtml() {
  const o = stcaO();
  const sel = (k, name) => `<select data-stca-o="${k}">${STCA_STEPS[k].map((v) => `<option value="${v}"${v === o[k] ? " selected" : ""}>${name(v)}</option>`).join("")}</select>`;
  const cb = (k, txt, tip) => `<label${tip ? ` title="${tip}"` : ""}><input type="checkbox" data-stca-o="${k}"${o[k] ? " checked" : ""}> ${txt}</label>`;
  const sub = (t) => `<div class="map-opts-sub2">${t}</div>`;
  const ft = (v) => `${v.toLocaleString("en-US")} ft`;
  return cb("on", "Short Term Conflict Alert on", "Pairs of airborne aircraft closer than both minima now or within the look-ahead") +
    sub("Minima") +
    `<label>Horizontal ${sel("h", (v) => `${v} NM`)}</label>` +
    `<label>Vertical ${sel("v", ft)}</label>` +
    sub("Prediction") +
    `<label title="How far ahead the straight-line prediction looks">Look-ahead ${sel("look", (v) => `${v} s`)}</label>` +
    cb("vr", "use the vertical rate (else level flight)", "The vertical rate of ADS-B, FR24 and adsb.fi; a climb or descent that levels off can give a false alert") +
    `<label title="An older position is not predicted (the aircraft may have turned)">Position not older than ${sel("age", (v) => `${v} s`)}</label>` +
    sub("Aircraft") +
    `<label title="Pairs with an aircraft below this altitude are left out (approaches, parallel runways)">Ignore below ${sel("floor", (v) => (v ? ft(v) : "nothing"))}</label>` +
    `<label>Pairs <select data-stca-o="scope"><option value="all"${o.scope === "all" ? " selected" : ""}>all aircraft</option>` +
    `<option value="sel"${o.scope === "sel" ? " selected" : ""}>with a selected aircraft</option></select></label>` +
    cb("shr", "also aircraft only from Sharing (adsb.fi)") +
    sub("Show") +
    cb("blink", "blink a conflict now") +
    cb("sound", "a tone on a new alert", "Three short beeps in this window when a new pair is in conflict") +
    cb("sel", "the separation of the selected aircraft (Alt / Ctrl + click)") +
    `<label>Colour of an alert <input type="color" class="map-opts-cp" data-stca-o="c" value="${o.c}"></label>` +
    `<label>Colour of the selected pairs <input type="color" class="map-opts-cp" data-stca-o="cSel" value="${o.cSel}"></label>` +
    `<p class="map-opts-note">A help for watching, not an ATC tool: a straight-line prediction without the cleared levels of the aircraft.</p>`;
}
/** An input of the section: -> true when it was one (stored on change). */
function stcaOnInput(e) {
  const t = e.target, k = t.dataset && t.dataset.stcaO;
  if (!k) return false;
  if (e.type === "change") stcaSet({ [k]: t.type === "checkbox" ? t.checked : t.type === "color" || k === "scope" ? t.value : +t.value });
  return true;
}

// ----- the STCA bar over the bottom of the map (COM_BARS in app.js): each key steps to the next value -----
function stcaBarHtml() {
  const o = stcaO();
  return `<button type="button" data-tb="stcaOn" class="${o.on ? "stca-on" : ""}" title="Short Term Conflict Alert: pairs of airborne aircraft closer than both minima now or within the look-ahead (all settings: ⚙ › STCA)">STCA ${o.on ? "on" : "off"}</button>` +
    `<button type="button" data-tb="stcaH" title="Horizontal minimum (click: the next value)">H ${o.h} NM</button>` +
    `<button type="button" data-tb="stcaV" title="Vertical minimum (click: the next value)">V ${o.v} ft</button>` +
    `<button type="button" data-tb="stcaLook" title="Look-ahead of the linear prediction (click: the next value)">Look-ahead ${o.look} s</button>` +
    `<button type="button" data-tb="stcaFloor" title="Pairs with an aircraft below this altitude are left out (approaches, parallel runways)">Above ${o.floor} ft</button>` +
    `<button type="button" data-tb="stcaScope" title="All pairs, or only the pairs with a selected aircraft">${o.scope === "sel" ? "Selected only" : "All aircraft"}</button>` +
    `<button type="button" data-tb="stcaSound" class="${o.sound ? "stca-on" : ""}" title="A tone on a new alert">Sound ${o.sound ? "on" : "off"}</button>` +
    (o.on ? `<span class="stca-n${stcaAlerts.length ? " on" : ""}">${stcaAlerts.length ? `${stcaAlerts.length} alert${stcaAlerts.length > 1 ? "s" : ""}` : "no alert"}</span>` : "");
}
function stcaBarClick(b) {
  const k = { stcaOn: "on", stcaH: "h", stcaV: "v", stcaLook: "look", stcaFloor: "floor", stcaScope: "scope", stcaSound: "sound" }[b.dataset.tb];
  if (!k) return;
  const o = stcaO();
  if (k === "on" || k === "sound") stcaSet({ [k]: !o[k] });
  else if (k === "scope") stcaSet({ scope: o.scope === "sel" ? "all" : "sel" });
  else { const s = STCA_STEPS[k], i = s.indexOf(o[k]); stcaSet({ [k]: s[(i + 1) % s.length] }); }
}
