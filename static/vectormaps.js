// ---------- Vector maps (vectormaps.py): airspaces, airports, navaids, reporting points, obstacles ----------
// The data is kept on the server (data/vectormaps/, one file per source and country, downloaded with Update), so it
// works offline. Drawn on every decoder map in its own pane under the tracks, one canvas for all. What is shown is in
// the map settings (mapOpts.vm: shared by the tab, the window and the full screen; defaults in com_defaults.js).
// Loaded before app.js (vmOptsNorm is used when app.js reads the settings); the rest runs later and uses app.js.

const VM_KINDS = [
  ["airspace", "Airspaces", ["CTR", "TMA", "CTA", "ATZ", "MCTR", "R", "D", "P", "TRA", "TSA", "RMZ", "TMZ", "GLIDING", "SPORT", "MTA",
    "FIS", "FIR", "UIR", "ACC", "AWY", "ADIZ", "MATZ", "HTZ", "TIZ", "TIA", "LTA", "UTA", "LOWFLY", "VFR", "TRP", "MTR", "MRT", "TFR",
    "ALERT", "WARNING", "PROTECTED", "OTHER"]],
  ["airport", "Airports", ["intl", "ifr", "airport", "civil", "military", "glider", "ul", "heli", "heli_mil", "water", "strip", "agri", "altiport", "closed"]],
  ["navaid", "Navaids", ["VOR", "VOR-DME", "DVOR", "DVOR-DME", "VORTAC", "DVORTAC", "TACAN", "DME", "NDB"]],
  ["point", "Reporting points", ["RP", "RP_OPT"]],
  ["obstacle", "Obstacles", ["tower", "chimney", "wind", "building", "obstacle"]],
];
const VM_CAT_NAME = {
  R: "R (restricted)", D: "D (danger)", P: "P (prohibited)", GLIDING: "Gliding sectors", SPORT: "Para / sport", FIS: "FIS sectors",
  OTHER: "Other", AWY: "Airways", LOWFLY: "Low flying", ALERT: "Alert areas", WARNING: "Warning areas", PROTECTED: "Protected areas",
  intl: "International", ifr: "IFR", airport: "Airports", civil: "Civil airfields", military: "Military", glider: "Glider sites",
  ul: "Ultralight", heli: "Heliports", heli_mil: "Military heliports", water: "Water", strip: "Landing strips", agri: "Agricultural",
  altiport: "Altiports", closed: "Closed", RP: "Compulsory", RP_OPT: "On request", tower: "Towers / masts", chimney: "Chimneys",
  wind: "Wind turbines", building: "Buildings", obstacle: "Other",
};
// shown at first (later: as the person set it)
const VM_OFF = new Set(["airspace.FIR", "airspace.UIR", "airspace.ACC", "airspace.FIS", "airspace.OTHER", "airport.closed", "obstacle"]);
const VM_MAX_FL = [0, 50, 65, 95, 100, 125, 145, 195, 245, 660];   // airspaces starting below this FL (0 = all)

/** The vector map part of the map settings, checked. */
function vmOptsNorm(v) {
  const o = v && typeof v === "object" ? v : {};
  const bool = (x) => (x && typeof x === "object" ? Object.fromEntries(Object.entries(x).filter(([k, b]) => /^[\w.-]{1,80}$/.test(k) && typeof b === "boolean")) : {});
  return {
    on: o.on != null ? !!o.on : true,
    countries: typeof o.countries === "string" ? o.countries.toUpperCase().replace(/[^A-Z ,]/g, "").slice(0, 120) : "SK CZ AT HU PL UA",
    maps: bool(o.maps), cats: bool(o.cats),
    maxFL: VM_MAX_FL.includes(+o.maxFL) ? +o.maxFL : 0,
    rev: +o.rev || 0,
  };
}
const vmOpt = () => mapOpts.vm || vmOptsNorm(null);
const vmCatOn = (kind, cat) => {
  const c = vmOpt().cats, k = c[kind] != null ? c[kind] : !VM_OFF.has(kind);
  return k && (cat == null || (c[`${kind}.${cat}`] != null ? c[`${kind}.${cat}`] : !VM_OFF.has(`${kind}.${cat}`)));
};
const vmMapOn = (id) => vmOpt().maps[id] !== false;

// default look per kind / part (stage 2 makes these settable)
const VM_AS_STYLE = {
  CTR: ["#ff5a5a", 2, "", 0.08], MCTR: ["#ff5a5a", 2, "6 4", 0.06], TMA: ["#4f9dff", 1.5, "", 0.04], CTA: ["#4f9dff", 1.5, "8 4", 0.03],
  ATZ: ["#d97aff", 1.5, "", 0.06], R: ["#ff3b3b", 1.5, "", 0.12], P: ["#ff2020", 2, "", 0.18], D: ["#ff8c1a", 1.5, "", 0.1],
  TRA: ["#ffb020", 1.5, "6 4", 0.06], TSA: ["#ffb020", 1.5, "6 4", 0.06], RMZ: ["#b48cff", 1.5, "2 4", 0.04], TMZ: ["#b48cff", 1.5, "2 4", 0.04],
  GLIDING: ["#4cd97a", 1.2, "4 4", 0.04], SPORT: ["#4cd97a", 1.2, "", 0.06], MTA: ["#ff8c1a", 1.2, "4 4", 0.05],
  FIR: ["#8fa3bd", 2, "10 6", 0], UIR: ["#8fa3bd", 2, "10 6", 0], FIS: ["#8fa3bd", 1.2, "10 6", 0],
};
const VM_AS_DEF = ["#9fb3c8", 1, "4 4", 0.03];
const VM_PT_STYLE = {   // colour, radius
  airport: ["#4fd2ff", 5], navaid: ["#7cff9a", 4], point: ["#ffd84a", 3], obstacle: ["#ff6cd2", 3],
};
function vmStyle(p) {
  if (p.kind === "airspace") {
    const [c, w, dash, fo] = VM_AS_STYLE[p.cat] || VM_AS_DEF;
    return { color: c, weight: w, dashArray: dash || null, opacity: 0.9, fillColor: c, fillOpacity: fo };
  }
  const [c, r] = VM_PT_STYLE[p.kind] || ["#ffffff", 3];
  const big = p.kind === "airport" && (p.cat === "intl" || p.cat === "ifr" || p.cat === "military");
  return { color: "#000", weight: 1, opacity: 0.8, fillColor: c, fillOpacity: p.cat === "closed" ? 0.3 : 0.95, radius: big ? r + 2 : r };
}

// the list of the stored maps and their GeoJSON (asked from the VFO of the page or any VFO, like the own layers)
let vmList = null, vmListP = null, vmListRev = -1;
const vmGj = new Map();   // id -> Promise of the GeoJSON
function vmListGet(force) {
  const rev = vmOpt().rev;
  if (force || rev !== vmListRev) { vmList = null; vmListP = null; vmGj.clear(); vmListRev = rev; }
  if (vmList) return Promise.resolve(vmList);
  return (vmListP = vmListP || mapLayApi("/api/vectormaps").then((j) => (vmList = j.maps || [])).catch(() => (vmList = [])));
}
function vmGet(id) {
  if (!vmGj.has(id)) vmGj.set(id, mapLayApi(`/api/vectormaps/${encodeURIComponent(id)}`).catch(() => { vmGj.delete(id); return null; }));
  return vmGj.get(id);
}

/** The lower limit of an airspace in hundreds of feet (FL), for the altitude filter. */
function vmLowerFL(l) {
  if (!l) return 0;
  return l.u === "FL" ? l.v : l.u === "m" ? l.v * 3.2808 / 100 : l.v / 100;
}
const vmLim = (l) => (!l ? "" : l.u === "FL" ? `FL${l.v}` : l.v === 0 && l.ref === "GND" ? "GND" : `${l.v} ${l.u} ${l.ref === "STD" ? "" : l.ref}`.trim());
const vmFreq = (f) => `${f.type ? `${escHtml(f.type)} ` : ""}${f.f < 1 ? `${Math.round(f.f * 1e6) / 1000} kHz` : `${f.f.toFixed(3)}`}${f.name ? ` <span class="muted">${escHtml(f.name)}</span>` : ""}`;
function vmTip(p) {
  const head = `<b>${escHtml(p.name || p.ident || "")}</b>${p.ident && p.name ? ` ${escHtml(p.ident)}` : ""}`;
  const cat = VM_CAT_NAME[p.cat] || p.cat;
  const rows = [];
  if (p.kind === "airspace") rows.push(`${escHtml(cat)}${p.cls && p.cls !== "SUA" ? ` · class ${escHtml(p.cls)}` : ""}`, `${vmLim(p.lower) || "?"} – ${vmLim(p.upper) || "?"}`);
  else rows.push(escHtml(cat) + (p.elev != null ? ` · ${p.elev} m` : "") + (p.height != null ? ` · ${p.height} m AGL` : "") + (p.channel ? ` · ch ${escHtml(p.channel)}` : ""));
  if (p.rwy && p.rwy.length) rows.push(`RWY ${p.rwy.map(escHtml).join(" ")}`);
  for (const f of (p.freq || []).slice(0, 6)) rows.push(vmFreq(f));
  if (p.remarks) rows.push(`<span class="muted">${escHtml(String(p.remarks).slice(0, 120))}</span>`);
  return `${head}<br>${rows.join("<br>")}`;
}

/** Draws the vector maps on one map as the settings say (called from the map's apply()). */
async function vmApply(map) {
  const st = map._vm || (map._vm = { layers: new Map(), renderer: null, attr: false });
  if (!st.renderer) {
    if (!map.getPane("vmaps")) map.createPane("vmaps").style.zIndex = 380;   // over the tiles and clouds, under the tracks
    st.renderer = L.canvas({ pane: "vmaps", padding: 0.3 });
  }
  const o = vmOpt(), list = o.on ? await vmListGet() : [];
  const want = new Set(list.filter((m) => vmMapOn(m.id)).map((m) => m.id));
  const sig = JSON.stringify([o.cats, o.maxFL, o.rev]);
  for (const [id, x] of st.layers) if (!want.has(id) || x.sig !== sig) { map.removeLayer(x.layer); st.layers.delete(id); }
  for (const m of list) {
    if (!want.has(m.id) || st.layers.has(m.id)) continue;
    const gj = await vmGet(m.id);
    if (!gj || !vmOpt().on || !vmMapOn(m.id) || st.layers.has(m.id)) continue;
    const feats = (gj.features || []).filter((f) => {
      const p = f.properties || {};
      if (!vmCatOn(p.kind, p.cat)) return false;
      return !(p.kind === "airspace" && o.maxFL && vmLowerFL(p.lower) >= o.maxFL);
    });
    // the big airspaces first: the small ones over them get the mouse
    const ext = (f) => { const c = f.geometry.type === "Polygon" ? f.geometry.coordinates[0] : null; if (!c) return 0;
      let a = 180, b = -180, d = 90, e = -90; for (const [x, y] of c) { a = Math.min(a, x); b = Math.max(b, x); d = Math.min(d, y); e = Math.max(e, y); } return (b - a) * (e - d); };
    feats.sort((p, q) => ext(q) - ext(p));
    const layer = L.geoJSON({ type: "FeatureCollection", features: feats }, {
      pane: "vmaps",
      style: (f) => ({ ...vmStyle(f.properties || {}), renderer: st.renderer }),
      pointToLayer: (f, ll) => L.circleMarker(ll, { ...vmStyle(f.properties || {}), renderer: st.renderer, pane: "vmaps" }),
      onEachFeature: (f, l) => l.bindTooltip(vmTip(f.properties || {}), { className: "ais-label vm-tip", sticky: true }),
    }).addTo(map);
    st.layers.set(m.id, { sig, layer });
  }
  const attr = [...new Set(list.filter((m) => st.layers.has(m.id)).map((m) => m.attribution).filter(Boolean))].join(" | ");
  if (map.attributionControl && attr !== st.attr) {
    if (st.attr) map.attributionControl.removeAttribution(st.attr);
    if (attr) map.attributionControl.addAttribution(attr);
    st.attr = attr;
  }
}

/** The Vector maps section of the map settings window. */
function vmSettingsHtml() {
  const o = vmOpt(), list = vmList || [], n = (x) => x.toLocaleString("en-US").replace(/,/g, " ");
  const day = (t) => new Date(t * 1000).toISOString().slice(0, 10);
  const chk = (attr, on) => `<input type="checkbox" ${attr}${on ? " checked" : ""}>`;
  let h = `<label>${chk('data-vm="on"', o.on)} Show the vector maps</label>` +
    `<div class="map-opts-sub2">openAIP <small>airspaces, airports, navaids, reporting points, obstacles (CC BY-NC)</small></div>` +
    `<label>API key <input type="text" class="map-opts-url" data-key="openaip" value="${escHtml((mapKeys && mapKeys.openaip) || "")}" placeholder="from openaip.net (free account)" spellcheck="false"></label>` +
    `<label>Countries <input type="text" class="vm-countries" data-vm="countries" value="${escHtml(o.countries)}" placeholder="SK CZ AT" spellcheck="false">` +
    `<button type="button" class="vm-btn" data-vmupd>Update</button></label><p class="map-opts-note vm-msg"></p>`;
  if (!vmList) { vmListGet().then(() => { const b = document.querySelector(".map-opts-panel:not([hidden]) details[data-sec=vmaps] .map-opts-body"); if (b && !b.contains(document.activeElement)) b.innerHTML = vmSettingsHtml(); }); }
  h += list.length ? `<table class="map-opts-t vm-maps">` + list.map((m) => `<tr><th><label title="${n(m.n)} objects, ${Math.max(1, Math.round(m.size / 1024))} kB">` +
    `${chk(`data-vmmap="${escHtml(m.id)}"`, vmMapOn(m.id))} ${escHtml(m.name)}</label></th>` +
    `<td class="${m.stale ? "vm-stale" : "muted"}" title="${m.stale ? "Older than an AIRAC cycle (28 days): Update" : "Downloaded"}">${day(m.fetched)}${m.stale ? " ⚠" : ""}</td>` +
    `<td><button type="button" class="map-opts-del" data-vmdel="${escHtml(m.id)}" title="Delete the downloaded data">✕</button></td></tr>`).join("") + `</table>`
    : `<p class="map-opts-note">${vmList ? "Nothing downloaded yet: enter the API key and the countries, then Update." : "Loading…"}</p>`;
  // the tree: kind › part, the counts of all shown maps together
  const cnt = {};
  for (const m of list) if (vmMapOn(m.id)) for (const [k, cs] of Object.entries(m.cats || {})) for (const [c, x] of Object.entries(cs)) { cnt[k] = cnt[k] || {}; cnt[k][c] = (cnt[k][c] || 0) + x; }
  for (const [k, name, order] of VM_KINDS) {
    const cs = cnt[k];
    if (!cs) continue;
    const cats = [...order.filter((c) => cs[c]), ...Object.keys(cs).filter((c) => !order.includes(c))];
    const tot = Object.values(cs).reduce((a, b) => a + b, 0);
    const sw = (c) => { const s = vmStyle({ kind: k, cat: c }); return `<i class="vm-sw${k === "airspace" ? "" : " pt"}" style="--c:${s.fillColor}"></i>`; };
    h += `<details class="vm-kind" data-vmkind="${k}"${vmKindOpen().includes(k) ? " open" : ""}><summary>${chk(`data-vmcat="${k}"`, vmCatOn(k))} ${name} <small class="muted">${n(tot)}</small></summary>` +
      `<div class="vm-cats">${cats.map((c) => `<label>${chk(`data-vmcat="${k}.${escHtml(c)}"`, vmCatOn(k, c))}${sw(c)} ${escHtml(VM_CAT_NAME[c] || c)} <small class="muted">${cs[c]}</small></label>`).join("")}</div>` +
      (k === "airspace" ? `<label>Only starting below <select data-vm="maxFL">${VM_MAX_FL.map((v) => `<option value="${v}"${v === o.maxFL ? " selected" : ""}>${v ? `FL${v}` : "any altitude"}</option>`).join("")}</select></label>` : "") +
      `</details>`;
  }
  return h;
}
function vmKindOpen() {   // the kinds open in the tree (this browser; the first time all closed)
  try { const v = JSON.parse(localStorage.getItem("vmKindOpen") || "[]"); return Array.isArray(v) ? v : []; } catch { return []; }
}

function vmSet(patch) { mapOptsSet({ vm: { ...vmOpt(), ...patch } }); }

/** Inputs of the Vector maps section (true = handled). */
function vmOnInput(e, panel) {
  const t = e.target;
  if (!t.closest || !t.closest("details[data-sec=vmaps]")) return false;
  if (t.dataset.key) return false;   // the API key: the settings window stores it
  if (e.type !== "change") return true;
  const o = vmOpt();
  if (t.dataset.vm === "on") vmSet({ on: t.checked });
  else if (t.dataset.vm === "countries") vmSet({ countries: t.value.toUpperCase().replace(/[^A-Z ,]/g, "") });
  else if (t.dataset.vm === "maxFL") vmSet({ maxFL: +t.value });
  else if (t.dataset.vmmap) vmSet({ maps: { ...o.maps, [t.dataset.vmmap]: t.checked } });
  else if (t.dataset.vmcat) vmSet({ cats: { ...o.cats, [t.dataset.vmcat]: t.checked } });
  else return true;
  vmRefill(panel);
  return true;
}
function vmRefill(panel) {
  const b = panel.querySelector("details[data-sec=vmaps] .map-opts-body");
  if (b) b.innerHTML = vmSettingsHtml();
}

/** Clicks of the Vector maps section: Update, delete, the tree opened / closed (true = handled). */
function vmOnClick(e, panel) {
  const upd = e.target.closest("button[data-vmupd]"), del = e.target.closest("button[data-vmdel]");
  const msg = () => panel.querySelector(".vm-msg");
  if (upd) {
    const cs = [...new Set(vmOpt().countries.split(/[\s,]+/).filter((c) => /^[A-Z]{2}$/.test(c)))];
    if (!cs.length) { msg().textContent = "Enter the countries (two letters each, e.g. SK CZ AT)."; return true; }
    upd.disabled = true;
    (async () => {
      const bad = [];
      for (const [i, c] of cs.entries()) {
        if (msg()) msg().textContent = `Downloading ${c} (${i + 1} / ${cs.length})…`;
        try {
          await mapLayApi("/api/vectormaps/openaip", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ country: c }) });
        } catch (err) { bad.push(`${c}: ${err.message}`); }
      }
      vmSet({ rev: Date.now() });
      await vmListGet(true);
      vmRefill(panel);
      if (msg()) msg().textContent = bad.length ? `Not downloaded: ${bad.join("; ")}` : `Downloaded: ${cs.join(" ")}`;
    })();
    return true;
  }
  if (del) {
    const id = del.dataset.vmdel, m = (vmList || []).find((x) => x.id === id);
    if (!confirm(`Delete the downloaded "${m ? m.name : id}"? Update downloads it again.`)) return true;
    mapLayApi(`/api/vectormaps/${encodeURIComponent(id)}`, { method: "DELETE" })
      .then(() => { vmSet({ rev: Date.now() }); return vmListGet(true); }).then(() => vmRefill(panel))
      .catch((err) => { msg().textContent = `Not deleted: ${err.message}`; });
    return true;
  }
  return false;
}
document.addEventListener("toggle", (e) => {   // a kind of the tree opened / closed: remembered in this browser
  if (!e.target.matches || !e.target.matches("details[data-vmkind]")) return;
  const open = new Set(vmKindOpen());
  if (e.target.open) open.add(e.target.dataset.vmkind); else open.delete(e.target.dataset.vmkind);
  try { localStorage.setItem("vmKindOpen", JSON.stringify([...open])); } catch { /* this page only */ }
}, true);
