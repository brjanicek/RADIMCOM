// ---------- Vector maps (vectormaps.py): airspaces, airports, navaids, reporting points, obstacles ----------
// The data is kept on the server (data/vectormaps/, one file per source and country, downloaded with Update), so it
// works offline. Drawn on every decoder map in its own pane under the tracks, one canvas for all. What is shown is in
// the map settings (mapOpts.vm: shared by the tab, the window and the full screen; defaults in com_defaults.js).
// Loaded before app.js (vmOptsNorm is used when app.js reads the settings); the rest runs later and uses app.js.

const VM_KINDS = [
  ["airspace", "Airspaces", ["CTR", "TMA", "CTA", "ATZ", "MCTR", "R", "D", "P", "TRA", "TSA", "RMZ", "TMZ", "GLIDING", "SPORT", "MTA",
    "FIS", "FIR", "UIR", "ACC", "AWY", "ADIZ", "MATZ", "HTZ", "TIZ", "TIA", "LTA", "UTA", "LOWFLY", "VFR", "TRP", "MTR", "MRT", "TFR",
    "ALERT", "WARNING", "PROTECTED", "OTHER"]],
  ["airport", "Airports", ["intl", "large", "medium", "ifr", "airport", "small", "civil", "military", "glider", "ul", "heli", "heli_mil", "water", "strip", "agri", "altiport", "balloon", "closed"]],
  ["navaid", "Navaids", ["VOR", "VOR-DME", "DVOR", "DVOR-DME", "VORTAC", "DVORTAC", "TACAN", "DME", "NDB", "NDB-DME"]],
  ["point", "Reporting points", ["RP", "RP_OPT"]],
  ["obstacle", "Obstacles", ["tower", "chimney", "wind", "building", "obstacle"]],
  ["tx", "Transmitters", ["bcast", "radar", "ham", "comm", "mobile"]],
  ["chan", "MEMORIES channels", ["nogroup"]],   // one part per group (names from the map file)
  ["own", "Own files", ["area", "line", "point"]],
];
const vmIsArea = (kind, cat) => kind === "airspace" || (kind === "own" && cat !== "point");   // drawn with line and fill
function vmCatName(c) {   // the name of a part; the groups of the MEMORIES channels come with their map
  if (VM_CAT_NAME[c]) return VM_CAT_NAME[c];
  for (const m of vmList || []) if (m.catNames && m.catNames[c]) return m.catNames[c];
  return c;
}
const VM_CAT_NAME = {
  R: "R (restricted)", D: "D (danger)", P: "P (prohibited)", GLIDING: "Gliding sectors", SPORT: "Para / sport", FIS: "FIS sectors",
  OTHER: "Other", AWY: "Airways", LOWFLY: "Low flying", ALERT: "Alert areas", WARNING: "Warning areas", PROTECTED: "Protected areas",
  intl: "International", ifr: "IFR", airport: "Airports", civil: "Civil airfields", military: "Military", glider: "Glider sites",
  ul: "Ultralight", heli: "Heliports", heli_mil: "Military heliports", water: "Water", strip: "Landing strips", agri: "Agricultural",
  altiport: "Altiports", closed: "Closed", large: "Large airports", medium: "Medium airports", small: "Small airfields", balloon: "Balloon ports", RP: "Compulsory", RP_OPT: "On request", tower: "Towers / masts", chimney: "Chimneys",
  wind: "Wind turbines", building: "Buildings", obstacle: "Other",
  area: "Areas", line: "Lines", point: "Points", bcast: "Broadcasting (radio, TV)", radar: "Radar", ham: "Amateur radio", comm: "Other radio", mobile: "Mobile phone",
};
// shown at first (later: as the person set it)
const VM_OFF = new Set(["airspace.FIR", "airspace.UIR", "airspace.ACC", "airspace.FIS", "airspace.OTHER", "airport.closed", "obstacle", "tx.mobile"]);
const VM_MAX_FL = [0, 50, 65, 95, 100, 125, 145, 195, 245, 660];   // airspaces starting below this FL (0 = all)

/** The vector map part of the map settings, checked. */
function vmOptsNorm(v) {
  const o = v && typeof v === "object" ? v : {};
  const bool = (x) => (x && typeof x === "object" ? Object.fromEntries(Object.entries(x).filter(([k, b]) => /^[\w.-]{1,80}$/.test(k) && typeof b === "boolean")) : {});
  return {
    on: o.on != null ? !!o.on : true,
    maps: bool(o.maps), cats: bool(o.cats), srcs: bool(o.srcs),   // srcs: a source used in the maps or not
    maxFL: VM_MAX_FL.includes(+o.maxFL) ? +o.maxFL : 0,
    lbl: bool(o.lbl),   // names on the map per kind (missing: VM_LBL_DEF)
    style: o.style && typeof o.style === "object" ? o.style : {},
    hidden: Array.isArray(o.hidden) ? o.hidden.filter((x) => typeof x === "string" && /^[\w:-]{1,80}$/.test(x)).slice(0, 5000) : [],
    rev: +o.rev || 0,   // the data changed (Update, delete): all windows load it again
    viewRev: +o.viewRev || 0,   // what is shown changed: all windows ask the server again
  };
}
// What is shown (cats, lbl, maxFL, maps, hidden) is stored on the server in the map files (the same in every browser
// and computer); the browser keeps only on and the revisions. vmOpt() gives both together.
const VM_VIEW_KEYS = ["cats", "lbl", "maxFL", "maps", "hidden", "style", "srcs"];
let vmView = null;   // from the server (GET /api/vectormaps → view)
const vmOpt = () => { const b = mapOpts.vm || vmOptsNorm(null); return vmView ? { ...b, ...vmView } : b; };
const vmCatOn = (kind, cat) => {
  const c = vmOpt().cats, k = c[kind] != null ? c[kind] : !VM_OFF.has(kind);
  return k && (cat == null || (c[`${kind}.${cat}`] != null ? c[`${kind}.${cat}`] : !VM_OFF.has(`${kind}.${cat}`)));
};
const vmMapOn = (id) => vmOpt().maps[id] !== false;
const vmSrcOn = (src) => (vmOpt().srcs || {})[src || "openaip"] !== false;
const vmShown = (m) => vmSrcOn(m.source) && vmMapOn(m.id);   // drawn: its source used and the map on
const VM_LBL_DEF = { airspace: true, airport: true, navaid: true, point: false, obstacle: false, tx: true, chan: true, own: true };
const vmLblOn = (kind) => { const l = vmOpt().lbl; return l[kind] != null ? l[kind] : !!VM_LBL_DEF[kind]; };
const vmKey = (p) => `${p.src || "x"}:${p.srcId || p.name}`;   // an object, for hiding it
// names on the map from this zoom on (per kind; big airports earlier); at most VM_LBL_MAX in the view
const VM_LBL_ZOOM = { airspace: 8, airport: 9, navaid: 7, point: 9, obstacle: 11, tx: 10, chan: 9, own: 9 };
const VM_LBL_MAX = 300;

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
  airport: ["#4fd2ff", 5], navaid: ["#7cff9a", 4], point: ["#ffd84a", 3], obstacle: ["#ff6cd2", 3], tx: ["#ff9f40", 4], chan: ["#ffe14a", 4], own: ["#c8a0ff", 4],
};
// the style of a part (kind.cat): line c / w / d (type) / o, fill fc / fo, point r / sym, name lc / ls / lz (from zoom);
// the defaults above, what the person changed in view.style (stored on the server with the maps)
const VM_DASH = { solid: null, dash: "8 5", long: "14 6", dot: "2 4", dashdot: "8 4 2 4" };
const VM_DASH_OF = { "6 4": "dash", "8 4": "dash", "4 4": "dash", "2 4": "dot", "10 6": "long" };
const VM_SYMS = [["circle", "Circle"], ["square", "Square"], ["diamond", "Diamond"], ["triangle", "Triangle"], ["cross", "Cross"],
  // the symbols of the aeronautical (ICAO VFR) charts
  ["ad", "Aerodrome, paved runway"], ["ad_civil", "Aerodrome, grass"], ["ad_mil", "Military aerodrome"], ["heli", "Heliport"],
  ["glider", "Glider site"], ["ul", "Ultralight site"], ["closed", "Closed aerodrome"], ["vor", "VOR"], ["vordme", "VOR-DME"],
  ["vortac", "VORTAC"], ["tacan", "TACAN"], ["dme", "DME"], ["ndb", "NDB"], ["ndbdme", "NDB-DME"], ["rp", "Reporting point, compulsory"],
  ["rp_opt", "Reporting point, on request"], ["obst", "Obstacle"], ["wind", "Wind turbine"], ["mast", "Transmitter mast"]];
// the aeronautical symbol of a part at first (as on the ICAO VFR charts)
const VM_AERO_SYM = {
  airport: { intl: "ad", large: "ad", medium: "ad", ifr: "ad", airport: "ad", civil: "ad_civil", small: "ad_civil", strip: "ad_civil",
    agri: "ad_civil", water: "ad_civil", altiport: "ad_civil", balloon: "ad_civil", military: "ad_mil", heli: "heli", heli_mil: "heli",
    glider: "glider", ul: "ul", closed: "closed" },
  navaid: { VOR: "vor", DVOR: "vor", "VOR-DME": "vordme", "DVOR-DME": "vordme", VORTAC: "vortac", DVORTAC: "vortac", TACAN: "tacan",
    DME: "dme", NDB: "ndb", "NDB-DME": "ndbdme" },
  point: { RP: "rp", RP_OPT: "rp_opt" },
  obstacle: { wind: "wind", tower: "obst", chimney: "obst", building: "obst", obstacle: "obst" },
  tx: { bcast: "mast", radar: "mast", ham: "mast", comm: "mast", mobile: "mast" },
};
function vmStyDef(kind, cat) {
  if (vmIsArea(kind, cat)) {
    const [c, w, dash, fo] = kind === "own" ? ["#c8a0ff", 2, "", cat === "line" ? 0 : 0.06] : VM_AS_STYLE[cat] || VM_AS_DEF;
    return { c, w, d: VM_DASH_OF[dash] || "solid", o: 0.9, fc: c, fo, lc: c, ls: 10, lz: VM_LBL_ZOOM[kind] };
  }
  const [c, r] = VM_PT_STYLE[kind] || ["#ffffff", 3];
  const major = kind === "airport" && ["intl", "ifr", "large", "medium"].includes(cat);
  const big = major || (kind === "airport" && cat === "military");
  const aero = (VM_AERO_SYM[kind] || {})[cat] || (kind === "navaid" ? "vor" : kind === "obstacle" ? "obst" : kind === "airport" ? "ad_civil" : "");
  return { fc: c, r: big ? r + 2 : r, sym: aero || (kind === "chan" ? "square" : "circle"), fo: cat === "closed" ? 0.6 : 0.95,
    lc: c, ls: 10, lz: (VM_LBL_ZOOM[kind] || 9) - (major ? 2 : 0) };
}
const vmSty = (kind, cat) => ({ ...vmStyDef(kind, cat), ...(((vmOpt().style || {})[`${kind}.${cat}`]) || {}) });
function vmStyle(p) {
  const y = vmSty(p.kind, p.cat);
  if (vmIsArea(p.kind, p.cat)) return { color: y.c, weight: y.w, dashArray: VM_DASH[y.d] || null, opacity: y.o, fillColor: y.fc, fillOpacity: y.fo };
  return { color: "#000", weight: 1, opacity: 0.8, fillColor: y.fc, fillOpacity: y.fo, radius: y.r, sym: y.sym };
}
// the aeronautical symbols: drawn as lines in the colour of the part, with a dark edge so they stand out on any map
function vmHex(ctx, x, y, R) { ctx.moveTo(x + R, y); for (let i = 1; i < 6; i++) ctx.lineTo(x + R * Math.cos(i * Math.PI / 3), y + R * Math.sin(i * Math.PI / 3)); ctx.closePath(); }
const VM_AERO_DRAW = {
  ad: (c, x, y, R) => { c.arc(x, y, R, 0, 2 * Math.PI); c.moveTo(x - R * 1.45, y); c.lineTo(x + R * 1.45, y); },
  ad_civil: (c, x, y, R) => { c.arc(x, y, R, 0, 2 * Math.PI); for (const [a, b] of [[0, -1], [1, 0], [0, 1], [-1, 0]]) { c.moveTo(x + a * R, y + b * R); c.lineTo(x + a * R * 1.5, y + b * R * 1.5); } },
  ad_mil: (c, x, y, R) => { c.arc(x, y, R, 0, 2 * Math.PI); c.moveTo(x + R * 0.55, y); c.arc(x, y, R * 0.55, 0, 2 * Math.PI); c.moveTo(x - R * 1.45, y); c.lineTo(x + R * 1.45, y); },
  heli: (c, x, y, R) => { c.arc(x, y, R, 0, 2 * Math.PI); const h = R * 0.5; c.moveTo(x - h, y - h); c.lineTo(x - h, y + h); c.moveTo(x + h, y - h); c.lineTo(x + h, y + h); c.moveTo(x - h, y); c.lineTo(x + h, y); },
  glider: (c, x, y, R) => { c.arc(x, y, R, 0, 2 * Math.PI); c.moveTo(x - R * 0.8, y - R * 0.1); c.quadraticCurveTo(x, y + R * 0.45, x + R * 0.8, y - R * 0.1); c.moveTo(x, y + R * 0.2); c.lineTo(x, y - R * 0.4); },
  ul: (c, x, y, R) => { c.arc(x, y, R, 0, 2 * Math.PI); c.moveTo(x - R * 0.5, y - R * 0.4); c.lineTo(x, y + R * 0.45); c.lineTo(x + R * 0.5, y - R * 0.4); },
  closed: (c, x, y, R) => { c.arc(x, y, R, 0, 2 * Math.PI); const d = R * 0.72; c.moveTo(x - d, y - d); c.lineTo(x + d, y + d); c.moveTo(x + d, y - d); c.lineTo(x - d, y + d); },
  vor: (c, x, y, R) => { vmHex(c, x, y, R); },
  vordme: (c, x, y, R) => { vmHex(c, x, y, R); c.rect(x - R * 1.1, y - R * 0.95, R * 2.2, R * 1.9); },
  vortac: (c, x, y, R) => { vmHex(c, x, y, R); },
  tacan: (c, x, y, R) => { vmHex(c, x, y, R); },
  dme: (c, x, y, R) => { c.rect(x - R, y - R * 0.8, 2 * R, 1.6 * R); },
  ndb: (c, x, y, R) => { for (let i = 0; i < 12; i++) { const a = i * Math.PI / 6, px = x + R * Math.cos(a), py = y + R * Math.sin(a); c.moveTo(px + 0.9, py); c.arc(px, py, 0.9, 0, 2 * Math.PI); } },
  ndbdme: (c, x, y, R) => { VM_AERO_DRAW.ndb(c, x, y, R * 0.85); c.moveTo(x - R * 1.1, y - R * 1.1); c.rect(x - R * 1.1, y - R * 1.1, R * 2.2, R * 2.2); },
  rp: (c, x, y, R) => { c.moveTo(x, y - R); c.lineTo(x + R * 0.9, y + R * 0.6); c.lineTo(x - R * 0.9, y + R * 0.6); c.closePath(); },
  rp_opt: (c, x, y, R) => { c.moveTo(x, y - R); c.lineTo(x + R * 0.9, y + R * 0.6); c.lineTo(x - R * 0.9, y + R * 0.6); c.closePath(); },
  obst: (c, x, y, R) => { c.moveTo(x - R * 0.55, y + R * 0.7); c.lineTo(x, y - R * 1.1); c.lineTo(x + R * 0.55, y + R * 0.7); },
  wind: (c, x, y, R) => { c.moveTo(x, y + R); c.lineTo(x, y - R * 0.3); for (let i = 0; i < 3; i++) { const a = -Math.PI / 2 + i * 2 * Math.PI / 3; c.moveTo(x, y - R * 0.3); c.lineTo(x + R * 0.8 * Math.cos(a), y - R * 0.3 + R * 0.8 * Math.sin(a)); } },
  mast: (c, x, y, R) => { c.moveTo(x - R * 0.5, y + R * 0.8); c.lineTo(x, y - R * 0.6); c.lineTo(x + R * 0.5, y + R * 0.8); c.moveTo(x - R * 0.25, y + R * 0.1); c.lineTo(x + R * 0.25, y + R * 0.1);
    c.moveTo(x - R * 0.45, y - R * 1.05); c.arc(x, y - R * 0.6, R * 0.45, Math.PI * 1.25, Math.PI * 1.75); },
};
function vmAeroDraw(ctx, sym, x, y, r, color, alpha) {
  const R = r * 1.5;
  ctx.save();
  ctx.globalAlpha = alpha == null ? 1 : alpha;
  ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.beginPath();
  VM_AERO_DRAW[sym](ctx, x, y, R);
  ctx.strokeStyle = "rgba(0,0,0,.75)"; ctx.lineWidth = 3.4; ctx.stroke();   // the dark edge
  ctx.strokeStyle = color; ctx.lineWidth = 1.6; ctx.stroke();
  ctx.fillStyle = color;
  if (sym === "rp") ctx.fill();
  if (sym === "vortac" || sym === "tacan") {   // three filled lobes on every other side of the hexagon
    for (let i = 0; i < 3; i++) {
      const a = (2 * i + 0.5) * Math.PI / 3, nx = Math.cos(a), ny = Math.sin(a), tx = -ny, ty = nx, m = R * Math.cos(Math.PI / 6), h = R / 2;
      ctx.beginPath();
      ctx.moveTo(x + nx * m + tx * h, y + ny * m + ty * h); ctx.lineTo(x + nx * m - tx * h, y + ny * m - ty * h);
      ctx.lineTo(x + nx * (m + R * 0.45) - tx * h, y + ny * (m + R * 0.45) - ty * h); ctx.lineTo(x + nx * (m + R * 0.45) + tx * h, y + ny * (m + R * 0.45) + ty * h);
      ctx.closePath(); ctx.fill();
    }
  }
  if (["vor", "vordme", "vortac", "dme", "ndb", "ndbdme", "obst", "mast"].includes(sym)) {   // the centre dot
    ctx.beginPath(); ctx.arc(x, sym === "obst" ? y + R * 0.7 : sym === "mast" ? y - R * 0.6 : y, 1.6, 0, 2 * Math.PI); ctx.fill();
  }
  ctx.restore();
}
// a point drawn as a symbol on the canvas (one canvas for thousands of points); made when first needed, since
// Leaflet is loaded after this file
let VmSymCls = null;
const vmSymMarker = (ll, opt) => new (VmSymCls = VmSymCls || L.CircleMarker.extend({
  _updatePath() {
    const rd = this._renderer, sym = this.options.sym || "circle";
    if (sym === "circle" || !rd._ctx) { L.CircleMarker.prototype._updatePath.call(this); return; }
    if (!rd._drawing || this._empty()) return;
    const ctx = rd._ctx, { x, y } = this._point, r = Math.max(this._radius, 1);
    if (VM_AERO_DRAW[sym]) { vmAeroDraw(ctx, sym, x, y, r, this.options.fillColor, this.options.fillOpacity); return; }
    ctx.beginPath();
    if (sym === "square") ctx.rect(x - r, y - r, 2 * r, 2 * r);
    else if (sym === "diamond") { ctx.moveTo(x, y - r * 1.3); ctx.lineTo(x + r * 1.3, y); ctx.lineTo(x, y + r * 1.3); ctx.lineTo(x - r * 1.3, y); ctx.closePath(); }
    else if (sym === "triangle") { ctx.moveTo(x, y - r * 1.3); ctx.lineTo(x + r * 1.15, y + r * 0.8); ctx.lineTo(x - r * 1.15, y + r * 0.8); ctx.closePath(); }
    else if (sym === "cross") { const t = Math.max(1, r / 2.5); ctx.rect(x - r, y - t, 2 * r, 2 * t); ctx.rect(x - t, y - r, 2 * t, 2 * r); }
    rd._fillStroke(ctx, this);
  },
}))(ll, opt);

// the list of the stored maps and their GeoJSON (asked from the VFO of the page or any VFO, like the own layers)
let vmList = null, vmListP = null, vmListRev = -1, vmViewRev = -1;
const vmGj = new Map();   // id -> Promise of the GeoJSON
function vmListGet(force) {
  const b = mapOpts.vm || vmOptsNorm(null);
  if (force || b.rev !== vmListRev) { vmList = null; vmListP = null; vmGj.clear(); vmListRev = b.rev; }
  else if (b.viewRev !== vmViewRev) { vmList = null; vmListP = null; }   // only the view: the GeoJSON stays
  vmViewRev = b.viewRev;
  if (vmList) return Promise.resolve(vmList);
  return (vmListP = vmListP || mapLayApi("/api/vectormaps").then((j) => {
    const v = j.view || {};
    vmView = { cats: v.cats || {}, lbl: v.lbl || {}, maxFL: +v.maxFL || 0, maps: v.maps || {}, hidden: v.hidden || [], style: v.style || {}, srcs: v.srcs || {} };
    if (!v.stored && (j.maps || []).length && VM_VIEW_KEYS.some((k) => { const x = b[k]; return Array.isArray(x) ? x.length : x && typeof x === "object" ? Object.keys(x).length : x; })) {
      vmView = Object.fromEntries(VM_VIEW_KEYS.map((k) => [k, b[k]]));   // once: what this browser had before goes to the server
      vmViewSave();
    }
    return (vmList = j.maps || []);
  }).catch(() => (vmList = [])));
}
let vmViewT = null;
function vmViewSave() {   // to the server (a moment later: several clicks one write), then the other windows ask again
  clearTimeout(vmViewT);
  vmViewT = setTimeout(() => {
    mapLayApi("/api/vectormaps/view", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(vmView) })
      .then(() => { vmViewRev = Date.now(); mapOptsSet({ vm: { ...(mapOpts.vm || vmOptsNorm(null)), viewRev: vmViewRev } }); })
      .catch((err) => { const m = document.querySelector(".vm-msg"); if (m) m.textContent = `Not stored on the server: ${err.message}`; });
  }, 400);
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
  const head = `<b>${escHtml(vmName(p) || p.ident || vmCatName(p.cat))}</b>${p.ident && p.name ? ` ${escHtml(p.ident)}` : ""}`;
  const cat = vmCatName(p.cat);
  const rows = [];
  if (p.kind === "airspace") rows.push(`${escHtml(cat)}${p.cls && p.cls !== "SUA" ? ` · class ${escHtml(p.cls)}` : ""}`, `${vmLim(p.lower) || "?"} – ${vmLim(p.upper) || "?"}`);
  else rows.push(escHtml(cat) + (p.elev != null ? ` · ${p.elev} m` : "") + (p.height != null ? ` · ${p.height} m AGL` : "") + (p.channel ? ` · ch ${escHtml(p.channel)}` : ""));
  if (p.operator) rows.push(escHtml(String(p.operator).slice(0, 80)));
  if (p.rwy && p.rwy.length) rows.push(`RWY ${p.rwy.map(escHtml).join(" ")}`);
  for (const f of (p.freq || []).slice(0, 6)) rows.push(vmFreq(f));
  if (p.remarks) rows.push(`<span class="muted">${escHtml(String(p.remarks).slice(0, 120))}</span>`);
  return `${head}<br>${rows.join("<br>")}`;
}

/** The point where the name of an airspace stands (the mean of its outline) and its box [w, s, e, n]. */
function vmRingInfo(ring) {
  let a = 180, b = -180, d = 90, e = -90, x = 0, y = 0;
  for (const [lo, la] of ring) { a = Math.min(a, lo); b = Math.max(b, lo); d = Math.min(d, la); e = Math.max(e, la); x += lo; y += la; }
  return { box: [a, d, b, e], c: [y / ring.length, x / ring.length], area: (b - a) * (e - d) };
}
function vmInRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
// the name of an object; transmitter sites in OpenStreetMap are often unnamed: their operator or ref then
const vmName = (p) => p.name || (p.kind === "tx" ? p.operator || p.ident || "" : "");
function vmLabel(p) {
  if (p.kind === "airspace") return `${escHtml(p.name)}<small>${escHtml(vmLim(p.lower))} – ${escHtml(vmLim(p.upper))}</small>`;
  if (p.kind === "navaid") return `${escHtml(p.ident || p.name)}<small>${p.freq && p.freq[0] ? (p.freq[0].f < 1 ? Math.round(p.freq[0].f * 1e6) / 1000 : p.freq[0].f.toFixed(2)) : ""}</small>`;
  if (p.kind === "airport") return escHtml(p.ident || p.name);
  if (p.kind === "obstacle") return `${escHtml(p.name || "")}${p.height != null ? `<small>${p.height} m</small>` : ""}`;
  if (p.kind === "tx") return `${escHtml(vmName(p))}${p.name && p.operator ? `<small>${escHtml(p.operator)}</small>` : ""}`;
  return escHtml(p.name || "");
}

/** Draws the vector maps on one map as the settings say (called from the map's apply()). The shapes are not
 *  interactive (the trails' canvas lies over them): the mouse is tested here against the objects drawn. */
async function vmApply(map) {
  const st = map._vm || (map._vm = vmInit(map));
  const o = vmOpt(), list = o.on ? await vmListGet() : [];
  const want = new Set(list.filter(vmShown).map((m) => m.id));
  const sig = JSON.stringify([o.cats, o.maxFL, o.rev, o.hidden, o.style]);
  let changed = false;
  for (const [id, x] of st.layers) if (!want.has(id) || x.sig !== sig) { map.removeLayer(x.layer); st.layers.delete(id); changed = true; }
  const hidden = new Set(o.hidden);
  for (const m of list) {
    if (!want.has(m.id) || st.layers.has(m.id)) continue;
    const gj = await vmGet(m.id);
    if (!gj || !vmOpt().on || !vmShown(m) || st.layers.has(m.id)) continue;
    const feats = (gj.features || []).filter((f) => {
      const p = f.properties || {};
      if (!vmCatOn(p.kind, p.cat) || hidden.has(vmKey(p))) return false;
      return !(p.kind === "airspace" && o.maxFL && vmLowerFL(p.lower) >= o.maxFL);
    });
    const objs = feats.map((f) => {   // what the mouse and the names need
      const g = f.geometry, p = f.properties || {};
      if (g.type === "Point") return { p, ll: [g.coordinates[1], g.coordinates[0]] };
      const ring = g.type === "Polygon" ? g.coordinates[0] : g.type === "MultiPolygon" ? g.coordinates[0][0] : null;
      return ring ? { p, ring, ...vmRingInfo(ring) } : null;
    }).filter(Boolean);
    const area = (f) => { const g = f.geometry; return g.type === "Polygon" ? vmRingInfo(g.coordinates[0]).area : g.type === "MultiPolygon" ? vmRingInfo(g.coordinates[0][0]).area : 0; };
    feats.sort((a, b) => area(b) - area(a));
    const layer = L.geoJSON({ type: "FeatureCollection", features: feats }, {
      pane: "vmaps", interactive: false,
      style: (f) => ({ ...vmStyle(f.properties || {}), renderer: st.renderer, interactive: false }),
      pointToLayer: (f, ll) => vmSymMarker(ll, { ...vmStyle(f.properties || {}), renderer: st.renderer, pane: "vmaps", interactive: false }),
    }).addTo(map);
    st.layers.set(m.id, { sig, layer, objs });
    changed = true;
  }
  if (changed) { st.pts = []; st.polys = []; for (const x of st.layers.values()) for (const ob of x.objs) (ob.ring ? st.polys : st.pts).push(ob); st.polys.sort((a, b) => a.area - b.area); }
  st.labels();
  const attr = [...new Set(list.filter((m) => st.layers.has(m.id)).map((m) => m.attribution).filter(Boolean))].join(" | ");
  if (map.attributionControl && attr !== st.attr) {
    if (st.attr) map.attributionControl.removeAttribution(st.attr);
    if (attr) map.attributionControl.addAttribution(attr);
    st.attr = attr;
  }
}

function vmInit(map) {
  if (!map.getPane("vmaps")) map.createPane("vmaps").style.zIndex = 380;   // over the tiles and clouds, under the tracks
  if (!map.getPane("vmlabels")) { const lp = map.createPane("vmlabels"); lp.style.zIndex = 385; lp.style.pointerEvents = "none"; }
  map.getContainer()._vmMap = map;   // for "This zoom" of the settings window inside it
  const st = { layers: new Map(), renderer: L.canvas({ pane: "vmaps", padding: 0.3 }), attr: "", pts: [], polys: [] };
  const lblLayer = L.layerGroup().addTo(map);
  const tip = L.tooltip({ className: "ais-label vm-tip", direction: "top", offset: [0, -6], opacity: 1 });
  /** The object under a container point: a point within 7 px first, else the smallest airspace around it. */
  function hit(cp) {
    if (!st.layers.size) return null;
    const ll = map.containerPointToLatLng(cp), tol = 7;
    const d = map.containerPointToLatLng([cp.x + tol, cp.y + tol]), dLat = Math.abs(d.lat - ll.lat), dLon = Math.abs(d.lng - ll.lng);
    let best = null, bd = tol * tol + 1;
    for (const ob of st.pts) {
      if (Math.abs(ob.ll[0] - ll.lat) > dLat || Math.abs(ob.ll[1] - ll.lng) > dLon) continue;
      const q = map.latLngToContainerPoint(ob.ll), dd = (q.x - cp.x) ** 2 + (q.y - cp.y) ** 2;
      if (dd < bd) { bd = dd; best = ob; }
    }
    if (best) return best;
    for (const ob of st.polys) {
      const [w, s, e, n] = ob.box;
      if (ll.lng >= w && ll.lng <= e && ll.lat >= s && ll.lat <= n && vmInRing(ll.lng, ll.lat, ob.ring)) return ob;
    }
    return null;
  }
  let raf = 0, last = null, shown = null;
  map.on("mousemove", (e) => {
    last = e;
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      const ob = vmOpt().on ? hit(last.containerPoint) : null;
      if (!ob) { if (shown) { map.closeTooltip(tip); shown = null; } return; }
      if (ob !== shown) { tip.setContent(vmTip(ob.p)); shown = ob; }
      tip.setLatLng(ob.ll || last.latlng);
      if (!map.hasLayer(tip)) map.openTooltip(tip);
    });
  });
  map.on("mouseout", () => { if (shown) { map.closeTooltip(tip); shown = null; } });
  map.on("click", (e) => {   // a click on an object: its card with "Hide this object"
    const ob = vmOpt().on ? hit(e.containerPoint) : null;
    if (!ob) return;
    const box = document.createElement("div");
    box.className = "vm-card";
    box.innerHTML = `${vmTip(ob.p)}<div class="vm-card-act"><button type="button" class="vm-btn">Hide this object</button></div>`;
    box.querySelector("button").addEventListener("click", () => {
      vmSet({ hidden: [...new Set([...vmOpt().hidden, vmKey(ob.p)])] });
      map.closePopup();
    });
    L.popup({ className: "vm-pop", maxWidth: 320 }).setLatLng(ob.ll || e.latlng).setContent(box).openOn(map);
  });
  /** The names of the objects in the view (from a zoom on per kind, at most VM_LBL_MAX). */
  st.labels = () => {
    lblLayer.clearLayers();
    if (!vmOpt().on || !st.layers.size) return;
    const z = map.getZoom(), b = map.getBounds().pad(0.1), out = [];
    const ok = (p) => vmLblOn(p.kind) && z >= vmSty(p.kind, p.cat).lz;
    for (const ob of st.pts) if (ok(ob.p) && b.contains(ob.ll)) out.push(ob);
    for (const ob of st.polys) if (ok(ob.p) && b.contains(ob.c) && ob.area > 0) out.push(ob);
    const rank = { chan: 0, navaid: 1, airport: 2, tx: 3, airspace: 4, own: 5, point: 6, obstacle: 7 };
    out.sort((a, c) => (rank[a.p.kind] ?? 8) - (rank[c.p.kind] ?? 8));
    const placed = [];   // boxes of the names already placed: a name that would overlap one is left out
    for (const ob of out) {
      if (placed.length >= VM_LBL_MAX) break;
      const pt = !ob.ring, y = vmSty(ob.p.kind, ob.p.cat), col = y.lc;
      const q = map.latLngToContainerPoint(ob.ll || ob.c), txt = String(ob.p.ident && ob.p.kind !== "airspace" && ob.p.kind !== "tx" ? ob.p.ident : vmName(ob.p));
      if (!txt) continue;   // nothing to write
      const w = Math.max(20, txt.length * 6), hh = ob.p.kind === "airspace" || ob.p.kind === "navaid" ? 24 : 12;
      const r = [q.x - w / 2, pt ? q.y + 10 : q.y - hh / 2, q.x + w / 2, (pt ? q.y + 10 : q.y - hh / 2) + hh];
      if (placed.some((o) => r[0] < o[2] && r[2] > o[0] && r[1] < o[3] && r[3] > o[1])) continue;
      placed.push(r);
      L.marker(ob.ll || ob.c, { pane: "vmlabels", interactive: false, keyboard: false,
        icon: L.divIcon({ className: `vm-lbl${pt ? " pt" : ""}`, html: `<span style="--c:${col};font-size:${y.ls}px">${vmLabel(ob.p)}</span>`, iconSize: null }) }).addTo(lblLayer);
    }
  };
  map.on("moveend zoomend", () => st.labels());
  return st;
}

/** The Vector maps section of the map settings window. */
// the sources of the vector maps, one tab each (openAIP now; more sources come as more tabs)
const VM_SOURCES = [["openaip", "openAIP"], ["ourairports", "OurAirports"], ["osm", "OpenStreetMap"], ["memories", "MEMORIES"], ["file", "Own files"]];
const VM_SRC_NOTE = {
  openaip: "Airspaces, airports, navaids, reporting points, obstacles per country (CC BY-NC).",
  ourairports: "Airports with frequencies and runways, navaids, per country (public domain, no key; the whole world is downloaded once a day, about 20 MB).",
  osm: "Transmitter sites (broadcasting, mobile phone, radar, amateur and other radio) per country (ODbL, no key; a big country takes a minute or two).",
};
// the countries openAIP can be downloaded for (ISO 3166 and Kosovo); their names come from the browser
const VM_COUNTRIES = ("AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF " +
  "CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP " +
  "GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT " +
  "LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL " +
  "PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR " +
  "TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS XK YE YT ZA ZM ZW").split(" ");
let vmCtryNames = null;
function vmCountryName(c) {
  if (!vmCtryNames) { try { const d = new Intl.DisplayNames(["en"], { type: "region" }); vmCtryNames = (x) => d.of(x); } catch { vmCtryNames = (x) => x; } }
  try { return c === "XK" ? "Kosovo" : vmCtryNames(c) || c; } catch { return c; }
}
let vmFind = "", vmBusy = false;
// the download icon: an arrow into a tray
const VM_DL_ICON = `<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M8 2v8M4.5 6.5 8 10l3.5-3.5M2.5 11v2.5h11V11" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;   // the filter of the country list (this page)
function vmFindApply(box) {   // the rows of the country list that match the filter
  const q = vmFind.trim().toLowerCase();
  box.querySelectorAll("tr[data-vmfind]").forEach((tr) => { tr.hidden = !!q && !tr.dataset.vmfind.includes(q); });
}
function vmSrcTab() { try { const v = localStorage.getItem("vmSrcTab"); return VM_SOURCES.some(([k]) => k === v) ? v : VM_SOURCES[0][0]; } catch { return VM_SOURCES[0][0]; } }
/** The Map sources section: a tab per source with its key, what to download and the downloaded maps. */
function vmSourcesHtml() {
  const o = vmOpt(), tab = vmSrcTab(), n = (x) => x.toLocaleString("en-US").replace(/,/g, " ");
  const day = (t) => new Date(t * 1000).toISOString().slice(0, 10);
  const chk = (attr, on) => `<input type="checkbox" ${attr}${on ? " checked" : ""}>`;
  const list = (vmList || []).filter((m) => (m.source || "openaip") === tab);
  if (!vmList) vmListGet().then(() => vmRefillAll());
  let h = `<div class="vm-tabs">${VM_SOURCES.map(([k, name]) => `<button type="button" class="vm-tab${k === tab ? " on" : ""}${vmSrcOn(k) ? "" : " off"}" data-vmtab="${k}">${name}</button>`).join("")}</div>`;
  const geo = { point: 0, line: 0, area: 0 };   // all the maps of this source together
  for (const m of list) for (const k of Object.keys(geo)) geo[k] += (m.geo && m.geo[k]) || 0;
  h += `<div class="vm-srcbar"><label>${chk(`data-vmsrc="${tab}"`, vmSrcOn(tab))} Use in maps</label>` +
    `<small class="muted">${list.length ? [["point", "point"], ["line", "line"], ["area", "area"]].map(([k, w]) => `${n(geo[k])} ${w}${geo[k] === 1 ? "" : "s"}`).join(" · ") : "nothing yet"}</small></div>`;
  if (tab === "file") {   // own files: GeoJSON, KML, GPX
    h += `<p class="map-opts-note">Own GeoJSON, KML or GPX files as vector maps: areas, lines and points under Own files in the tree (a file in this format keeps its airspaces, airports, …). The same name again replaces it.</p>` +
      `<label class="map-opts-up">Add <input type="file" data-vmfile accept=".geojson,.json,.kml,.gpx"></label><p class="map-opts-note vm-msg"></p>` +
      (list.length ? `<div class="vm-ctry"><table class="map-opts-t vm-maps">` + list.map((m) => `<tr class="vm-have"><th><label title="${n(m.n)} objects, ${Math.max(1, Math.round(m.size / 1024))} kB">` +
        `${chk(`data-vmmap="${escHtml(m.id)}"`, vmMapOn(m.id))} ${escHtml(m.name)} <small class="muted">${n(m.n)}</small></label></th><td class="muted">${day(m.fetched)}</td>` +
        `<td><button type="button" class="map-opts-del" data-vmdel="${escHtml(m.id)}" title="Remove the file">✕</button></td></tr>`).join("") + `</table></div>`
        : `<p class="map-opts-note">${vmList ? "No own file yet." : "Loading…"}</p>`);
  } else if (tab === "memories") {   // no countries: one map, made again whenever MEMORIES change
    const m = list[0];
    h += `<p class="map-opts-note">The MEMORIES channels that have a location (LAT / LON), one part per group; kept up to date when the channels change.</p>` +
      `<p class="map-opts-note vm-msg"></p>` + (m ? `<div class="vm-ctry"><table class="map-opts-t vm-maps"><tr class="vm-have"><th><label title="${n(m.n)} channels">` +
        `${chk(`data-vmmap="${escHtml(m.id)}"`, vmMapOn(m.id))} MEMORIES channels <small class="muted">${n(m.n)}</small></label></th><td class="muted">${day(m.fetched)}</td>` +
        `<td><button type="button" class="vm-get" data-vmmem title="Make it again">↻</button>` +
        `<button type="button" class="map-opts-del" data-vmdel="${escHtml(m.id)}" title="Remove the map (the channels stay)">✕</button></td></tr></table></div>`
        : `<button type="button" class="vm-btn" data-vmmem>Show the channels on the map</button>`);
  } else {
    const have = new Map(list.map((m) => [m.country, m]));
    h += `<p class="map-opts-note">${VM_SRC_NOTE[tab] || ""}</p>` + (tab !== "openaip" ? "" :
      `<label>API key <input type="text" class="map-opts-url" data-key="openaip" value="${escHtml((mapKeys && mapKeys.openaip) || "")}" placeholder="from openaip.net (free account)" spellcheck="false"></label>`) +
      `<label>Find <input type="search" class="vm-find" data-vmfind value="${escHtml(vmFind)}" placeholder="country or code" spellcheck="false">` +
      `<button type="button" class="vm-btn" data-vmupd${list.length ? "" : " disabled"} title="Download all the downloaded countries again">Update all</button></label>` +
      `<p class="map-opts-note">${vmList ? `${list.length} of ${VM_COUNTRIES.length} downloaded (on top, highlighted): the download button downloads a country, ↻ updates it, ✕ deletes it.` : "Loading…"}</p>` +
      `<p class="map-opts-note vm-msg"></p><div class="vm-ctry"><table class="map-opts-t vm-maps">` +
      [...new Set([...VM_COUNTRIES, ...have.keys()])].map((c) => [c, vmCountryName(c)]).sort((a, b) => (have.has(b[0]) - have.has(a[0])) || a[1].localeCompare(b[1])).map(([c, name]) => {
        const m = have.get(c), q = escHtml(`${name} ${c}`.toLowerCase());
        if (!m) return `<tr data-vmfind="${q}"><th><span class="vm-cn">${escHtml(name)} <small class="muted">${c}</small></span></th><td></td>` +
          `<td><button type="button" class="vm-get vm-dl" data-vmget="${c}" title="Download ${escHtml(name)}">${VM_DL_ICON}</button></td></tr>`;
        return `<tr class="vm-have" data-vmfind="${q}"><th><label title="${n(m.n)} objects, ${Math.max(1, Math.round(m.size / 1024))} kB · shown on the map">` +
          `${chk(`data-vmmap="${escHtml(m.id)}"`, vmMapOn(m.id))} ${escHtml(name)} <small class="muted">${c}</small></label></th>` +
          `<td class="${m.stale ? "vm-stale" : "muted"}" title="${m.stale ? "Older than an AIRAC cycle (28 days): update it" : "Downloaded"}">${day(m.fetched)}${m.stale ? " ⚠" : ""}</td>` +
          `<td><button type="button" class="vm-get" data-vmget="${c}" title="Update ${escHtml(name)}">↻</button>` +
          `<button type="button" class="map-opts-del" data-vmdel="${escHtml(m.id)}" title="Delete the downloaded data">✕</button></td></tr>`;
      }).join("") + `</table></div>`;
  }
  return h;
}
function vmRefillAll() {   // both sections in every open settings window of this page
  document.querySelectorAll(".map-opts-panel").forEach((p) => {
    const b = p.querySelector("details[data-sec=vsrc] > .map-opts-body"), v = p.querySelector("details[data-sec=vlist] > .map-opts-body");
    if (b && !b.contains(document.activeElement)) { b.innerHTML = vmSourcesHtml(); const box = b.querySelector(".vm-ctry"); if (box) vmFindApply(box); }
    if (v && !v.contains(document.activeElement)) v.innerHTML = vmSettingsHtml();
  });
}

/** The Vector maps section of the map settings window: what is shown (the maps come from Map sources). */
function vmSettingsHtml() {
  const o = vmOpt(), list = vmList || [], n = (x) => x.toLocaleString("en-US").replace(/,/g, " ");
  const chk = (attr, on) => `<input type="checkbox" ${attr}${on ? " checked" : ""}>`;
  if (!vmList) vmListGet().then(() => vmRefillAll());
  let h = `<label>${chk('data-vm="on"', o.on)} Show the vector maps</label>` +
    (vmList && !list.length ? `<p class="map-opts-note">No map downloaded yet: see Map sources above.</p>` : "");
  // the tree: kind › part, the counts of all shown maps together
  const cnt = {};
  for (const m of list) if (vmShown(m)) for (const [k, cs] of Object.entries(m.cats || {})) for (const [c, x] of Object.entries(cs)) { cnt[k] = cnt[k] || {}; cnt[k][c] = (cnt[k][c] || 0) + x; }
  for (const [k, name, order] of VM_KINDS) {
    const cs = cnt[k];
    if (!cs) continue;
    const cats = [...order.filter((c) => cs[c]), ...Object.keys(cs).filter((c) => !order.includes(c))];
    const tot = Object.values(cs).reduce((a, b) => a + b, 0);
    const sw = (c) => { const y = vmSty(k, c); return `<i class="vm-sw${vmIsArea(k, c) ? "" : " pt"}" data-vmswatch="${escHtml(`${k}.${c}`)}" title="Style (click)" style="--c:${vmIsArea(k, c) ? y.c : y.fc}"></i>`; };
    h += `<details class="vm-kind" data-vmkind="${k}"${vmKindOpen().includes(k) ? " open" : ""}><summary>${chk(`data-vmcat="${k}"`, vmCatOn(k))} ${name} <small class="muted">${n(tot)}</small></summary>` +
      `<div class="vm-cats">${cats.map((c) => { const id = escHtml(`${k}.${c}`);   // a part: its objects one by one when opened
        return `<details class="vm-cat" data-vmcatd="${id}"${vmCatOpen().includes(`${k}.${c}`) ? " open" : ""}><summary>${chk(`data-vmcat="${id}"`, vmCatOn(k, c))}${sw(c)} ` +
          `${escHtml(vmCatName(c))} <small class="muted">${cs[c]}</small></summary><div class="vm-objs" data-vmobjs="${id}"><p class="map-opts-note">Loading…</p></div></details>` +
          (vmStyOpen === `${k}.${c}` ? vmStyEditor(k, c) : ""); }).join("")}</div>` +
      `<label>${chk(`data-vmlbl="${k}"`, vmLblOn(k))} Names on the map <small class="muted">from zoom ${VM_LBL_ZOOM[k]}</small></label>` +
      (k === "airspace" ? `<label>Only starting below <select data-vm="maxFL">${VM_MAX_FL.map((v) => `<option value="${v}"${v === o.maxFL ? " selected" : ""}>${v ? `FL${v}` : "any altitude"}</option>`).join("")}</select></label>` : "") +
      `</details>`;
  }
  if (o.hidden.length) h += `<div class="map-opts-sub2">Hidden objects <small>a click on an object on the map hides it</small></div>` +
    `<label>${o.hidden.length} hidden <button type="button" class="vm-btn" data-vmshow="*">Show all</button></label>`;
  return h;
}
let vmStyOpen = "";   // the part whose style editor is open (one at a time)
/** The style editor of a part, under its row in the tree. */
function vmStyEditor(kind, cat) {
  const y = vmSty(kind, cat), key = escHtml(`${kind}.${cat}`), pc = (v) => `${Math.round(v * 100)} %`;
  const sel = (k, list, name) => `<select data-vmsty="${key}" data-k="${k}">${list.map((v) => `<option value="${v}"${String(v) === String(y[k]) ? " selected" : ""}>${name ? name(v) : v}</option>`).join("")}</select>`;
  const col = (k) => `<input type="color" class="map-opts-cp" data-vmsty="${key}" data-k="${k}" value="${y[k]}">`;
  const own = !!((vmOpt().style || {})[`${kind}.${cat}`]);
  const rows = vmIsArea(kind, cat) ? [
    ["Line", col("c") + sel("w", [0.5, 1, 1.5, 2, 3, 4, 5], (v) => `${v} px`) + sel("d", Object.keys(VM_DASH)) + sel("o", [0.2, 0.4, 0.6, 0.8, 0.9, 1], pc)],
    ["Fill", col("fc") + sel("fo", [0, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5], pc)],
  ] : [
    ["Symbol", col("fc") + sel("sym", VM_SYMS.map(([v]) => v), (v) => VM_SYMS.find(([x]) => x === v)[1]) + sel("r", [2, 3, 4, 5, 6, 7, 8, 10], (v) => `${v} px`) + sel("fo", [0.3, 0.5, 0.7, 0.95, 1], pc)],
  ];
  const zs = [...new Set([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, y.lz])].sort((a, b) => a - b);
  rows.push(["Name", col("lc") + sel("ls", [8, 9, 10, 11, 12, 14, 16], (v) => `${v} px`) + sel("lz", zs, (v) => `from zoom ${v}`) +
    `<button type="button" class="vm-btn" data-vmthiszoom="${key}" title="From the zoom the map has now">This zoom</button>`]);
  return `<div class="vm-sty"><button type="button" class="vm-sty-x" data-vmstyclose title="Close">✕</button>${rows.map(([n, c]) => `<div class="vm-sty-row"><span>${n}</span>${c}</div>`).join("")}` +
    `<div class="vm-sty-row"><span></span><button type="button" class="vm-btn" data-vmstydef="${key}"${own ? "" : " disabled"}>Default</button></div></div>`;
}
function vmCatOpen() {   // the parts open in the tree (this browser)
  try { const v = JSON.parse(localStorage.getItem("vmCatOpen") || "[]"); return Array.isArray(v) ? v : []; } catch { return []; }
}
/** The objects of one part (kind.cat) in all shown maps, by name, as checkboxes (checked = shown). */
// the objects of a part in groups by country (by map where a map has no country); a group opened / closed is remembered
const vmGrpKeys = new Map();   // group id -> the keys of its objects (its checkbox shows / hides them all)
function vmGrpOpen() { try { const v = JSON.parse(localStorage.getItem("vmGrpOpen") || "[]"); return Array.isArray(v) ? v : []; } catch { return []; } }
async function vmFillObjs(box) {
  const [kind, cat] = box.dataset.vmobjs.split(".");
  const list = (await vmListGet()).filter(vmShown);
  const gjs = await Promise.all(list.map((m) => vmGet(m.id)));
  const groups = new Map();   // name -> rows
  gjs.forEach((gj, i) => {
    const m = list[i], g = m.country ? `${vmCountryName(m.country)} (${m.country})` : m.name || m.id;
    for (const f of (gj && gj.features) || []) {
      const p = f.properties || {};
      if (p.kind === kind && p.cat === cat) { if (!groups.has(g)) groups.set(g, new Map()); groups.get(g).set(vmKey(p), p); }   // one object once per group
    }
  });
  const hidden = new Set(vmOpt().hidden), open = vmGrpOpen();
  const item = (p) => `<label title="${escHtml(p.name || "")}"><input type="checkbox" data-vmobj="${escHtml(vmKey(p))}"${hidden.has(vmKey(p)) ? "" : " checked"}> ` +
    `${escHtml(vmName(p) || p.ident || "?")}${p.ident && p.kind !== "airspace" ? ` <small class="muted">${escHtml(p.ident)}</small>` : ""}</label>`;
  let left = 3000;
  box.innerHTML = groups.size ? [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([g, rowsMap]) => {
    const rows = [...rowsMap.values()].sort((a, b) => String(vmName(a) || a.ident || "").localeCompare(String(vmName(b) || b.ident || "")));
    const id = `${kind}.${cat}.${g}`, keys = rows.map(vmKey), on = keys.filter((k) => !hidden.has(k)).length;
    vmGrpKeys.set(id, keys);
    const body = rows.slice(0, Math.max(0, left)).map(item).join("");
    left -= rows.length;
    return `<details class="vm-cat vm-grp" data-vmgrpd="${escHtml(id)}"${open.includes(id) ? " open" : ""}><summary>` +
      `<input type="checkbox" data-vmgrp="${escHtml(id)}"${on ? " checked" : ""}${on && on < keys.length ? ' data-mixed="1"' : ""}> ${escHtml(g)} <small class="muted">${on < keys.length ? `${on} / ` : ""}${keys.length}</small></summary>` +
      `<div class="vm-grp-objs">${body}</div></details>`;
  }).join("") : `<p class="map-opts-note">None in the shown maps.</p>`;
  box.querySelectorAll("input[data-mixed]").forEach((x) => { x.indeterminate = true; });
}
function vmKindOpen() {   // the kinds open in the tree (this browser; the first time all closed)
  try { const v = JSON.parse(localStorage.getItem("vmKindOpen") || "[]"); return Array.isArray(v) ? v : []; } catch { return []; }
}

function vmSet(patch) {
  const view = Object.fromEntries(Object.entries(patch).filter(([k]) => VM_VIEW_KEYS.includes(k)));
  const rest = Object.fromEntries(Object.entries(patch).filter(([k]) => !VM_VIEW_KEYS.includes(k)));
  if (Object.keys(view).length) {
    vmView = { ...(vmView || Object.fromEntries(VM_VIEW_KEYS.map((k) => [k, vmOpt()[k]]))), ...view };
    vmViewSave();
  }
  mapOptsSet({ vm: { ...(mapOpts.vm || vmOptsNorm(null)), ...rest } });   // this page draws again at once
}

/** Inputs of the Vector maps section (true = handled). */
function vmOnInput(e, panel) {
  const t = e.target;
  if (!t.closest || !t.closest("details[data-sec=vmaps], details[data-sec=vsrc]")) return false;
  if (t.dataset.key) return false;   // the API key: the settings window stores it
  if (t.matches("input[data-vmfile]")) {   // an own file: turned into GeoJSON here, stored on the server
    if (e.type !== "change" || !t.files || !t.files[0]) return true;
    const file = t.files[0], msg = t.closest(".map-opts-body").querySelector(".vm-msg");
    if (msg) msg.textContent = `Reading ${file.name}…`;
    (async () => {
      const ext = (file.name.split(".").pop() || "").toLowerCase(), text = await file.text();
      let gj;
      if (ext === "kml" || ext === "gpx") gj = mapToGeoJson(text, ext);
      else if (ext === "geojson" || ext === "json") {
        try { gj = JSON.parse(text); } catch { throw new Error("the file is not valid JSON"); }
        if (gj && /^(Point|MultiPoint|LineString|MultiLineString|Polygon|MultiPolygon|GeometryCollection)$/.test(gj.type)) gj = { type: "Feature", properties: {}, geometry: gj };
      } else throw new Error("only GeoJSON, KML and GPX files (KMZ: unpack the KML from it)");
      const j = await mapLayApi("/api/vectormaps/file", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: file.name.replace(/\.[^.]+$/, ""), geojson: gj }) });
      vmSet({ rev: Date.now() });
      await vmListGet(true);
      vmRefill(panel);
      const m2 = panel.querySelector(".vm-msg");
      if (m2) m2.textContent = `${file.name}: ${(j.map && j.map.n) || 0} objects.`;
    })().catch((err) => { const m2 = panel.querySelector(".vm-msg"); if (m2) m2.textContent = `Not added: ${err.message}`; });
    return true;
  }
  if (t.matches("[data-vmfind]")) { vmFind = t.value; const box = t.closest(".map-opts-body").querySelector(".vm-ctry"); if (box) vmFindApply(box); return true; }
  if (e.type !== "change") return true;
  const o = vmOpt();
  if (t.dataset.vm === "on") vmSet({ on: t.checked });
  else if (t.dataset.vmsrc) { vmSet({ srcs: { ...(o.srcs || {}), [t.dataset.vmsrc]: t.checked } }); vmRefill(panel); }
  else if (t.dataset.vm === "maxFL") vmSet({ maxFL: +t.value });
  else if (t.dataset.vmmap) vmSet({ maps: { ...o.maps, [t.dataset.vmmap]: t.checked } });
  else if (t.dataset.vmcat) vmSet({ cats: { ...o.cats, [t.dataset.vmcat]: t.checked } });
  else if (t.dataset.vmlbl) vmSet({ lbl: { ...o.lbl, [t.dataset.vmlbl]: t.checked } });
  else if (t.dataset.vmsty) {   // one style value of a part
    const key = t.dataset.vmsty, k = t.dataset.k, [kind, cat] = key.split(".");
    const v = ["c", "fc", "lc", "d", "sym"].includes(k) ? t.value : +t.value;
    const cur = { ...((o.style || {})[key] || {}) }, def = vmStyDef(kind, cat);
    if (v === def[k]) delete cur[k]; else cur[k] = v;
    const style = { ...(o.style || {}) };
    if (Object.keys(cur).length) style[key] = cur; else delete style[key];
    vmSet({ style });
  }
  else if (t.dataset.vmgrp) {   // all objects of a country group shown / hidden
    const h = new Set(o.hidden), keys = vmGrpKeys.get(t.dataset.vmgrp) || [];
    for (const k of keys) if (t.checked) h.delete(k); else h.add(k);
    vmSet({ hidden: [...h] });
    const d = t.closest("details");
    if (d) d.querySelectorAll("input[data-vmobj]").forEach((x) => { x.checked = t.checked; });
    t.indeterminate = false;
    return true;
  }
  else if (t.dataset.vmobj) {   // one object shown / hidden: the list keeps its place (no new section)
    const h = new Set(o.hidden);
    if (t.checked) h.delete(t.dataset.vmobj); else h.add(t.dataset.vmobj);
    vmSet({ hidden: [...h] });
    return true;
  }
  else return true;
  vmRefill(panel);
  return true;
}
function vmRefill(panel) {
  const b = panel.querySelector("details[data-sec=vlist] > .map-opts-body"), c = panel.querySelector("details[data-sec=vsrc] > .map-opts-body");
  if (b) b.innerHTML = vmSettingsHtml();
  if (c) { c.innerHTML = vmSourcesHtml(); const box = c.querySelector(".vm-ctry"); if (box) vmFindApply(box); }
}

/** Clicks of the Vector maps section: Update, delete, the tree opened / closed (true = handled). */
function vmOnClick(e, panel) {
  const upd = e.target.closest("button[data-vmupd], button[data-vmget]"), del = e.target.closest("button[data-vmdel]");
  const msg = () => panel.querySelector(".vm-msg");
  const mem = e.target.closest("button[data-vmmem]");
  if (mem) {   // the map of the MEMORIES channels made (again)
    mem.disabled = true;
    mapLayApi("/api/vectormaps/memories", { method: "POST" })
      .then((j) => { vmSet({ rev: Date.now() }); return vmListGet(true).then(() => { vmRefill(panel); if (msg()) msg().textContent = `${(j.map && j.map.n) || 0} channels with a location.`; }); })
      .catch((err) => { mem.disabled = false; if (msg()) msg().textContent = `Not made: ${err.message}`; });
    return true;
  }
  if (upd) {   // ⬇ / ↻ one country, or Update all the downloaded ones
    const src = vmSrcTab();
    const cs = upd.dataset.vmget ? [upd.dataset.vmget] : (vmList || []).filter((m) => (m.source || "openaip") === src && m.country).map((m) => m.country);
    if (!cs.length) return true;
    if (vmBusy) { msg().textContent = "Wait, a download is running."; return true; }
    vmBusy = true;
    upd.disabled = true;
    (async () => {
      const bad = [];
      for (const [i, c] of cs.entries()) {
        if (msg()) msg().textContent = `Downloading ${c} (${i + 1} / ${cs.length})…`;
        try {
          await mapLayApi(`/api/vectormaps/${src}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ country: c }) });
        } catch (err) { bad.push(`${c}: ${err.message}`); }
      }
      vmBusy = false;
      vmSet({ rev: Date.now() });
      await vmListGet(true);
      vmRefill(panel);
      if (msg()) msg().textContent = bad.length ? `Not downloaded: ${bad.join("; ")}` : `Downloaded: ${cs.join(" ")}`;
    })();
    return true;
  }
  const swb = e.target.closest("[data-vmswatch]"), sdef = e.target.closest("button[data-vmstydef]");
  if (swb) {   // the swatch of a part: its style editor opens / closes (the row itself stays as it was)
    e.preventDefault();
    vmStyOpen = vmStyOpen === swb.dataset.vmswatch ? "" : swb.dataset.vmswatch;
    vmRefill(panel);
    return true;
  }
  if (e.target.closest("button[data-vmstyclose]")) { vmStyOpen = ""; vmRefill(panel); return true; }
  const tz = e.target.closest("button[data-vmthiszoom]");
  if (tz) {   // the names of the part from the zoom the map has now
    const box = panel.closest(".leaflet-container"), map = box && box._vmMap;
    if (!map) return true;
    const key = tz.dataset.vmthiszoom, [kind, cat] = key.split("."), style = { ...(vmOpt().style || {}) };
    const cur = { ...(style[key] || {}), lz: Math.round(map.getZoom()) };
    if (cur.lz === vmStyDef(kind, cat).lz) delete cur.lz;
    if (Object.keys(cur).length) style[key] = cur; else delete style[key];
    vmSet({ style });
    vmRefill(panel);
    return true;
  }
  const tb = e.target.closest("button[data-vmtab]");
  if (tb) { try { localStorage.setItem("vmSrcTab", tb.dataset.vmtab); } catch { /* this page only */ } vmRefill(panel); return true; }
  if (sdef) {
    const style = { ...(vmOpt().style || {}) };
    delete style[sdef.dataset.vmstydef];
    vmSet({ style });
    vmRefill(panel);
    return true;
  }
  if (e.target.closest("button[data-vmshow]")) { vmSet({ hidden: [] }); vmRefill(panel); return true; }
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
document.addEventListener("toggle", (e) => {   // a kind / part of the tree opened / closed: remembered in this browser
  if (e.target.matches && e.target.open && e.target.matches("details[data-sec=vsrc], details[data-sec=vlist]")) {   // Map sources or Maps: one open at a time
    const other = e.target.parentElement.querySelector(`:scope > details[data-sec=${e.target.dataset.sec === "vsrc" ? "vlist" : "vsrc"}]`);
    if (other) other.open = false;
    return;
  }
  if (e.target.matches && e.target.matches("details[data-vmcatd]")) {
    const d = e.target, open = new Set(vmCatOpen());
    if (d.open) { open.add(d.dataset.vmcatd); vmFillObjs(d.querySelector("[data-vmobjs]")); } else open.delete(d.dataset.vmcatd);
    try { localStorage.setItem("vmCatOpen", JSON.stringify([...open])); } catch { /* this page only */ }
    return;
  }
  if (e.target.matches && e.target.matches("details[data-vmgrpd]")) {
    const open = new Set(vmGrpOpen());
    if (e.target.open) open.add(e.target.dataset.vmgrpd); else open.delete(e.target.dataset.vmgrpd);
    try { localStorage.setItem("vmGrpOpen", JSON.stringify([...open].slice(-300))); } catch { /* this page only */ }
    return;
  }
  if (!e.target.matches || !e.target.matches("details[data-vmkind]")) return;
  const open = new Set(vmKindOpen());
  if (e.target.open) open.add(e.target.dataset.vmkind); else open.delete(e.target.dataset.vmkind);
  try { localStorage.setItem("vmKindOpen", JSON.stringify([...open])); } catch { /* this page only */ }
}, true);
