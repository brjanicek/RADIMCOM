// ---------- FR24 RECEIVER (fr24.py): the local Flightradar24 receiver of the station, its BaseStation stream ----------
// Loaded after app.js and uses its globals ($, vbase, bodyTab, escHtml, renderAdsbInfo, renderAdsbView, onAdsb).
// app.js calls fr24SetStart when SETTINGS › FR24 RECEIVER opens, fr24ComFeed from the COMPOSITE poll (a feed of its
// own, "~fr24", source "fr24") and fr24AdsbTag in the ADS-B aircraft table. The server holds the connection to the
// receiver only while these ask (fr24.py IDLE_S) or the ADS-B decoder has FR24 ticked.

var FR24_TRAIL_S = 1800;           // trail kept on the COMPOSITE map (the server keeps 30 min of points too)
var fr24Timer = null;              // SETTINGS page poll
var fr24Filled = false;            // the inputs were filled from the server (not again while the page is open)
var fr24Tr = new Map();            // hex -> [[lat, lon, t, (emergency squawk)]…] joined over the COMPOSITE polls
var fr24Since = 0;                 // server time of the last COMPOSITE answer: only newer trail points are asked
var fr24Radar = "";                // FR24 radar code of the receiver (F-LZPP1…), read by the server from its status page

/** "FR24 F-LZPP1": the name of the source everywhere (COMPOSITE keys, popups, details; ADS-B map and list). */
function fr24Name() { return fr24Radar ? `FR24 ${fr24Radar}` : "FR24"; }
function fr24TakeRadar(d) {
  fr24Radar = (d && d.radar) || "";
  if (typeof COM_SRC !== "undefined" && COM_SRC.fr24) COM_SRC.fr24[0] = fr24Name();
}

async function fr24Api(path, body) {
  const r = await fetch(vbase + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}

// ----- SETTINGS › FR24 RECEIVER -----

function fr24PanelOpen() {
  const p = document.querySelector('[data-set-panel="fr24"]');
  return bodyTab === "set" && p && !p.hidden && !document.hidden;
}

function fr24SetStart() {
  fr24Filled = false;
  fr24SetLoad();
  if (!fr24Timer) fr24Timer = setInterval(() => { if (fr24PanelOpen()) fr24SetLoad(); else { clearInterval(fr24Timer); fr24Timer = null; } }, 2000);
}

async function fr24SetLoad() {
  try {
    fr24SetRender(await fr24Api("/api/fr24"));
  } catch (e) { $("fr24Info").textContent = e.message; }
}

function fr24SetRender(d) {
  fr24TakeRadar(d);
  if (!fr24Filled) {
    fr24Filled = true;
    $("fr24Host").value = d.host || "";
    $("fr24Port").value = d.port || 30003;
    $("fr24On").checked = d.on !== false;
  }
  const web = $("fr24Web");
  web.hidden = !d.host;
  if (d.host) web.href = `http://${d.host}/`;
  const st = !d.host ? "no address set" : !d.on ? "not used" : d.status === "connected" ? "connected" : d.status === "error" ? "error" : d.status;
  $("fr24Info").textContent = st;
  $("fr24Info").classList.toggle("err", d.status === "error");
  const age = d.since ? Math.round(Date.now() / 1000 - d.since) : null;
  const w = d.web || {}, e = escHtml;
  const rows = [
    ["Radar code", w.radar ? `<b class="fr24-c">${e(w.radar)}</b>${w.feeding ? ` · feeding FR24: ${e(w.feeding)}` : ""}` : ""],
    ["Connection", d.host ? `${e(d.host)}:${d.port} · ${e(st)}${age != null ? ` for ${age < 120 ? `${age} s` : `${Math.round(age / 60)} min`}` : ""}` : "—"],
    ["Error", d.error ? `<span class="err">${e(d.error)}</span>` : ""],
    ["Messages", d.host && d.on ? `${d.rate || 0}/s · ${(d.count || 0).toLocaleString("en-US")} since the server start` : ""],
    ["Aircraft", d.host && d.on ? `${d.aircraft || 0} (${d.with_pos || 0} with a position)${w.ac ? ` · the receiver itself counts ${e(w.ac)}` : ""}` : ""],
    ["Receiver", [w.status && `status ${w.status}`, w.gps && `GPS antenna ${w.gps}`, w.sats && `${w.sats} satellites`, w.temp, w.uptime && `up ${w.uptime}`].filter(Boolean).map(e).join(" · ")],
  ].filter((r) => r[1]);
  $("fr24Stat").innerHTML = rows.map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join("");
}

$("fr24Save").addEventListener("click", async () => {
  const msg = $("fr24Msg");
  try {
    const d = await fr24Api("/api/fr24", { host: $("fr24Host").value, port: Number($("fr24Port").value) || 30003, on: $("fr24On").checked });
    fr24Filled = false;            // show the address as the server keeps it (http:// and the path dropped)
    fr24SetRender(d);
    fr24Tr.clear();
    fr24Since = 0;
    msg.textContent = "Saved";
  } catch (e) { msg.textContent = `Not saved: ${e.message}`; }
  setTimeout(() => { msg.textContent = ""; }, 3000);
});

// ----- COMPOSITE: the aircraft of the receiver as a feed of their own -----

/** The aircraft of the receiver with their trails joined over the polls: s = {tr: Map, since} of one user (the
 *  COMPOSITE, the ADS-B map). [] with s.off when no receiver is set up, null when the server does not answer. */
async function fr24Pull(s) {
  let d;
  try { d = await fr24Api(`/api/fr24?ac=1&since=${s.since ? s.since - 2 : 0}`); } catch { return null; }
  fr24TakeRadar(d);
  s.off = !d.host || !d.on;
  s.err = d.status === "error" ? d.error : "";
  if (s.off) { s.tr.clear(); s.since = 0; return []; }
  s.since = d.t;
  const seen = new Set();
  for (const a of d.aircraft || []) {
    seen.add(a.icao);
    const tr = s.tr.get(a.icao) || [];
    for (const p of a.trail || []) if (!tr.length || p[2] > tr[tr.length - 1][2]) tr.push(p);
    while (tr.length && d.t - tr[0][2] > FR24_TRAIL_S) tr.shift();
    s.tr.set(a.icao, tr);
    a.trail = tr;
  }
  for (const k of [...s.tr.keys()]) if (!seen.has(k)) s.tr.delete(k);
  return d.aircraft || [];
}

/** {sources, hist_sources, items, gs} in the shape of /api/positions, or null when no receiver is set up. */
async function fr24ComFeed() {
  const s = { tr: fr24Tr, since: fr24Since };
  const list = await fr24Pull(s);
  fr24Since = s.since;
  if (!list || s.off) return null;
  const items = [];
  for (const a of list) {
    const tr = a.trail;
    if (a.lat == null) continue;
    items.push({ src: "fr24", id: a.icao, label: a.flight || a.icao, lat: a.lat, lon: a.lon, alt_m: a.alt == null ? null : Math.round(a.alt * 0.3048),
      t: a.pos_time || a.last, trail: tr, track: a.track,
      air: { hex: a.icao, reg: "", flight: a.flight || "", type: "", desc: "", alt_ft: a.alt, gs_kt: a.gs, squawk: a.squawk || "",
        ground: !!a.ground, track: a.track, vs_fpm: a.vrate ?? null, gs: "", n: a.n || 0 } });
  }
  return { sources: ["fr24"], hist_sources: [], items, gs: [] };
}

// ----- DECODERS › ADS-B: FR24 ticked = the aircraft of the receiver join those decoded here -----

/** The F after the ICAO address: also (white) or only (cyan) heard by the FR24 receiver. */
function fr24AdsbTag(a) {
  if (!a.fr24) return "";
  return a.n ? `<span class="fr24-tag" title="Also heard by the local ${fr24Name()} receiver">F</span>`
    : `<span class="fr24-tag only" title="Only the local ${fr24Name()} receiver hears it (not decoded here)">F</span>`;
}

$("adsbFr24").addEventListener("change", async () => {
  const on = $("adsbFr24").checked;
  try {
    const d = await fr24Api("/api/adsb", { action: "fr24", on });
    renderAdsbInfo(d);
    if (on && d.fr24_rx && !d.fr24_rx.host) $("adsbStatus").textContent = "FR24: set the address of the receiver in SETTINGS › FR24 RECEIVER";
    if (!on) renderAdsbView();
  } catch (e) { $("adsbStatus").textContent = `FR24: ${e.message}`; }
});

// ----- DECODERS › ADS-B › MAP: FR24 RECEIVER = the aircraft of the receiver as a layer of their own (cyan) -----
// Independent of FR24 above (that one joins them into the decoder on the server): this one only draws, also while
// the decoder has nothing; an aircraft the decoder already shows is not drawn twice.

var fr24MapOn = recall("adsbFr24Map") === "1";
var fr24MapS = { tr: new Map(), since: 0, off: false, err: "" };
var fr24MapAc = [], fr24MapAt = 0;

async function fr24MapLoad() {
  if (!fr24MapOn || Date.now() - fr24MapAt < 4000) return;
  fr24MapAt = Date.now();
  const list = await fr24Pull(fr24MapS);
  if (list) fr24MapAc = list;
}

function fr24MapPopup(a) {
  const esc = escHtml, c = icaoCountry(a.icao);
  const lines = [`<b>${esc(a.flight || a.icao)}</b> ICAO ${a.icao}${c ? ` · ${esc(c.name)}` : ""}`];
  const nav = [a.squawk ? `squawk ${a.squawk}` : "", adsbAlt(a) ? `${adsbAlt(a)} ft` : "", a.vrate != null ? `${a.vrate > 0 ? "+" : ""}${a.vrate} ft/min` : "",
    adsbSpd(a) ? `${adsbSpd(a)} kt` : "", adsbTrk(a)].filter(Boolean).join(" · ");
  if (nav) lines.push(esc(nav));
  if (a.emergency) lines.push(`<span class="sq-emerg">${esc(a.emergency.toUpperCase())}</span>`);
  lines.push(`position ${a.lat.toFixed(4)}, ${a.lon.toFixed(4)} (${adsbAge(a.pos_time)} ago)${a.dist_km != null ? ` · ${Math.round(a.dist_km)} km, ${a.az}°` : ""}`);
  lines.push(`<span class="fr24-c">local ${fr24Name()} receiver</span> · ${a.n} msgs · <a href="${adsbGlobe(a.icao)}" target="_blank" rel="noopener">globe.adsb.fi</a>`);
  return lines.join("<br>");
}

/** Called by renderAdsbMap: draws the layer (or empties it when off). Returns the number drawn. The marks stay and
 *  are only moved (like those of the decoder): a new mark on each redraw would close the open bubble at once.
 *  The selection is the one of the decoder map (adsbSel): red, its bubble open; a click on the map drops it. */
async function fr24MapDraw() {
  if (!adsbMapLayers) return 0;
  if (!adsbMapLayers.fr24) {
    adsbMapLayers.fr24 = { tracks: L.layerGroup(), planes: L.layerGroup().addTo(adsbMap), marks: new Map() };
  }
  const lay = adsbMapLayers.fr24;
  if (fr24MapOn) await fr24MapLoad();
  lay.tracks.clearLayers();
  // the trails inside those of the decoder: the Trails switch of the map (mapPrecip) hides them all; renderAdsbMap
  // empties that group on each redraw, so this one goes back in every time
  if (!adsbMapLayers.tracks.hasLayer(lay.tracks)) lay.tracks.addTo(adsbMapLayers.tracks);
  const keep = new Set(), now = Date.now() / 1000;
  if (fr24MapOn) {
    for (const a of fr24MapAc) {
      const own = adsbAc.get(a.icao);
      if (a.lat == null || (own && adsbPos(own))) continue;   // the decoder shows it already
      keep.add(a.icao);
      const sel = a.icao === adsbSel;
      if (a.trail.length > 1) L.polyline(a.trail.map((p) => [p[0], p[1]]), { color: sel ? "#ff4b3c" : "#5ee6e6", weight: sel ? 2.5 : 1.5, opacity: sel ? 0.9 : 0.45, interactive: false }).addTo(lay.tracks);
      const old = now - a.last > ADSB_OLD_S;
      const cls = `hfdl-plane adsb-plane fr24${sel ? " sel" : ""}${old ? " old" : ""}${adsbEmerg(a) ? " emerg" : ""}${a.ground ? " ground" : ""}`;
      const svg = `<svg viewBox="0 0 24 24" style="transform: rotate(${Math.round(a.track ?? 0)}deg)"><path d="M12 2c.6 0 1 .9 1 2v5.2l8 4.6v2l-8-2.5v4.9l2.2 1.6V21L12 20.2 8.8 21v-1.2L11 18.2v-4.9l-8 2.5v-2l8-4.6V4c0-1.1.4-2 1-2z"/></svg>`;
      const alt = adsbAlt(a);
      let mk = lay.marks.get(a.icao);
      if (!mk) {
        mk = L.marker([a.lat, a.lon]).bindPopup("").bindTooltip("", { permanent: true, direction: "bottom", offset: [0, 8], className: "ais-label" }).addTo(lay.planes);
        mk.on("click", () => { adsbSel = a.icao; renderAdsbMap().then(() => { const m = lay.marks.get(a.icao); if (m && !m.isPopupOpen()) m.openPopup(); }); });
        lay.marks.set(a.icao, mk);
      }
      mk.setLatLng([a.lat, a.lon]);
      const key = cls + Math.round(a.track ?? 0);   // a new icon only when it changes (it is a new element)
      if (mk._fr24Key !== key) { mk._fr24Key = key; mk.setIcon(L.divIcon({ className: cls, html: svg, iconSize: [22, 22], iconAnchor: [11, 11] })); }
      mk.setTooltipContent(`${escHtml(a.flight || a.icao)}${alt ? `<br>${alt}` : ""}`);
      mk.setPopupContent(fr24MapPopup(a));
    }
  }
  for (const [k, mk] of lay.marks) if (!keep.has(k)) { mk.remove(); lay.marks.delete(k); }
  fr24MapShown = fr24MapAc.filter((a) => keep.has(a.icao)).sort((x, y) => (adsbEmerg(y) - adsbEmerg(x)) || (y.last - x.last));
  return keep.size;
}
var fr24MapShown = [];   // the aircraft drawn by the layer now (for the list beside the map)

/** Rows of the list right of the map: the aircraft of the layer, after those of the decoder (cyan). */
function fr24MapListHtml() {
  if (!fr24MapOn || !fr24MapShown.length) return "";
  const now = Date.now() / 1000;
  return `<div class="ais-ml-head fr24-c">${fr24MapShown.length} more from the ${fr24Name()} receiver</div>` +
    fr24MapShown.map((a) => {
      const c = icaoCountry(a.icao);
      return `<div class="ais-ml adsb-ml fr24-ml${a.icao === adsbSel ? " sel" : ""}${now - a.last > ADSB_OLD_S ? " old" : ""}${adsbEmerg(a) ? " emerg" : ""}" data-fr24="${a.icao}">` +
        `${c && c.cc ? `<img src="${flagUrl(c.cc)}" alt="" title="${escHtml(c.name)}">` : "<span></span>"}` +
        `<b>${escHtml(a.flight || a.icao)}</b><span class="mmsi">${a.icao}</span><span class="stype">${adsbAlt(a)}</span>` +
        `<span>${a.dist_km == null ? "" : `${Math.round(a.dist_km)} km`}</span><span class="age">${adsbAge(a.last)}</span></div>`;
    }).join("");
}

$("adsbMapList").addEventListener("click", (e) => {
  const r = e.target.closest("[data-fr24]");
  if (!r) return;
  const icao = r.dataset.fr24;
  adsbSel = icao;
  renderAdsbMap().then(() => {
    const mk = adsbMapLayers && adsbMapLayers.fr24 && adsbMapLayers.fr24.marks.get(icao);
    if (!mk) return;
    adsbMap.setView(mk.getLatLng(), Math.max(adsbMap.getZoom(), 8));
    mk.openPopup();
  });
});

/** The part of the map note about the layer. */
function fr24MapNote(n) {
  if (!fr24MapOn) return "";
  if (fr24MapS.off) return " · FR24 RECEIVER: no receiver set up (SETTINGS › FR24 RECEIVER)";
  return ` · cyan = ${fr24Name()} receiver (${n} more aircraft${fr24MapS.err ? `, ${fr24MapS.err}` : ""})`;
}

$("adsbFr24Map").checked = fr24MapOn;
$("adsbFr24Map").addEventListener("change", () => {
  fr24MapOn = $("adsbFr24Map").checked;
  store("adsbFr24Map", fr24MapOn ? "1" : "0");
  fr24MapAt = 0;
  const lay = adsbMapLayers && adsbMapLayers.fr24;
  if (!fr24MapOn && lay && lay.marks) {   // off: away at once, not only at the next redraw
    lay.tracks.clearLayers();
    for (const mk of lay.marks.values()) mk.remove();
    lay.marks.clear();
    fr24MapAc = [];
  }
  renderAdsbMap();
});
// the decoder's own 5 s redraw runs only while it has aircraft: the layer keeps moving without them too
setInterval(() => { if (fr24MapOn && !adsbAc.size && adsbView === "map" && !$("adsbCard").hidden) renderAdsbMap(); }, 5000);

// the radar code at once (from data/fr24.json, without connecting): the names are right before the first poll
fr24Api("/api/fr24?peek=1").then(fr24TakeRadar).catch(() => { /* an older server */ });
