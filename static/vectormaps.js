// ---------- Vector maps (vectormaps.py): airspaces, airports, navaids, reporting points, obstacles ----------
// The data is kept on the server (data/vectormaps/, one file per source and country, downloaded with Update), so it
// works offline. Drawn on every decoder map in its own pane under the tracks, one canvas for all. What is shown is in
// the map settings (mapOpts.vm: shared by the tab, the window and the full screen; defaults in com_defaults.js).
// Loaded before app.js (vmOptsNorm is used when app.js reads the settings); the rest runs later and uses app.js.

const VM_KINDS = [
  ["airspace", "Airspaces", ["CTR", "TMA", "CTA", "ATZ", "MCTR", "R", "D", "P", "TRA", "TSA", "RMZ", "TMZ", "GLIDING", "SPORT", "MTA",
    "FIS", "FIR", "UIR", "ACC", "AWY", "ADIZ", "MATZ", "HTZ", "TIZ", "TIA", "LTA", "UTA", "LOWFLY", "VFR", "TRP", "MTR", "MRT", "TFR",
    "ALERT", "WARNING", "PROTECTED", "OTHER"]],
  ["fua", "FUA", ["active", "planned"]],
  ["airport", "Airports", ["intl", "large", "medium", "ifr", "airport", "small", "civil", "military", "glider", "ul", "heli", "heli_mil", "water", "strip", "agri", "altiport", "balloon", "closed"]],
  ["aero", "AD layout", ["aerodrome", "runway", "apron", "taxiway", "helipad"]],
  ["navaid", "Navaids", ["VOR", "VOR-DME", "DVOR", "DVOR-DME", "VORTAC", "DVORTAC", "TACAN", "DME", "NDB", "NDB-DME"]],
  ["point", "Rep. points", ["RP", "RP_OPT"]],
  ["wpt", "IFR waypoints", ["enroute", "terminal"]],
  ["obstacle", "Obstacles", ["tower", "chimney", "wind", "building", "obstacle"]],
  ["tx", "Transmitters", ["bcast", "radar", "ham", "comm", "mobile"]],
  ["chan", "MEMORIES", ["nogroup"]],   // one part per group (names from the map file)
  ["own", "Own files", ["area", "line", "point"]],
];
const vmIsArea = (kind, cat) => kind === "airspace" || kind === "aero" || kind === "fua" || (kind === "own" && cat !== "point");   // drawn with line and fill
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
  altiport: "Altiports", closed: "Closed", large: "Large airports", medium: "Medium airports", small: "Small airfields", balloon: "Balloon ports", RP: "Compulsory", RP_OPT: "On request", enroute: "En-route", terminal: "Terminal (RNAV)", tower: "Towers / masts", chimney: "Chimneys",
  wind: "Wind turbines", building: "Buildings", obstacle: "Other",
  area: "Areas", line: "Lines", point: "Points", aerodrome: "Aerodrome boundary", runway: "Runways", apron: "Aprons",
  taxiway: "Taxiways", helipad: "Helipads", active: "Active now", planned: "Planned (later today)", bcast: "Broadcasting (radio, TV)", radar: "Radar", ham: "Amateur radio", comm: "Other radio", mobile: "Mobile phone",
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
  const c = vmOpt().cats, d = VM_VIEW_DEF.cats, on = (x) => c[x] != null ? c[x] : d[x] != null ? d[x] : !VM_OFF.has(x);
  return on(kind) && (cat == null || on(`${kind}.${cat}`));
};
const vmMapOn = (id) => vmOpt().maps[id] !== false;
const vmSrcOn = (src) => (vmOpt().srcs || {})[src || "openaip"] !== false;
const vmShown = (m) => vmSrcOn(m.source) && vmMapOn(m.id);   // drawn: its source used and the map on
const VM_LBL_DEF = { fua: true, airspace: true, airport: true, navaid: true, point: false, wpt: true, obstacle: false, tx: true, chan: true, own: true, aero: true };
const vmLblOn = (kind) => { const l = vmOpt().lbl, d = VM_VIEW_DEF.lbl; return l[kind] != null ? l[kind] : d[kind] != null ? d[kind] : !!VM_LBL_DEF[kind]; };
const vmKey = (p) => `${p.src || "x"}:${p.srcId || p.name}`;   // an object, for hiding it
// names on the map from this zoom on (per kind; big airports earlier); at most VM_LBL_MAX in the view
const VM_LBL_ZOOM = { fua: 7, airspace: 8, airport: 9, navaid: 7, point: 9, wpt: 9, obstacle: 11, tx: 10, chan: 9, own: 9, aero: 13 };
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
const VM_FUA_STYLE = { active: ["#ff2a2a", 2.5, "", 0.2], planned: ["#ffb020", 1.5, "8 4", 0.05] };   // FUA: active now / later today
const VM_AERO_STYLE = {   // the layout of aerodromes: colour, width, dash, fill
  aerodrome: ["#4fd2ff", 1.5, "4 4", 0.04], runway: ["#e6e6e6", 1, "", 0.75], apron: ["#9aa5b1", 1, "", 0.35],
  taxiway: ["#e0c050", 1.5, "", 0], helipad: ["#e6e6e6", 1, "", 0.5],
};
const VM_PT_STYLE = {   // colour, radius
  airport: ["#4fd2ff", 5], navaid: ["#7cff9a", 4], point: ["#ffd84a", 3], wpt: ["#8fc8ff", 4], obstacle: ["#ff6cd2", 3], tx: ["#ff9f40", 4], chan: ["#ffe14a", 4], own: ["#c8a0ff", 4],
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
  wpt: { enroute: "triangle", terminal: "triangle" },
  obstacle: { wind: "wind", tower: "obst", chimney: "obst", building: "obst", obstacle: "obst" },
  tx: { bcast: "mast", radar: "mast", ham: "mast", comm: "mast", mobile: "mast" },
};
// the zooms at first (Zoom levels): the airport symbol up to 11 and its layout (runways, …) from 12, the points first
// without and closer with their names; per kind or kind.part (s: symbol / outline from–to, l: name from–to)
const VM_ZOOM_DEF = {
  airport: { s: [1, 11], l: [8, 11] }, aero: { s: [12, 18], l: [12, 18] }, navaid: { s: [1, 18], l: [9, 18] },
  "wpt.enroute": { s: [7, 18], l: [9, 18] }, "wpt.terminal": { s: [9, 18], l: [11, 18] }, point: { s: [9, 18], l: [11, 18] },
  airspace: { s: [1, 18], l: [8, 18] }, fua: { s: [1, 18], l: [7, 18] }, obstacle: { s: [11, 18], l: [13, 18] },
  tx: { s: [9, 18], l: [12, 18] }, chan: { s: [1, 18], l: [9, 18] }, own: { s: [1, 18], l: [9, 18] },
};
const vmZoomDef = (kind, cat) => VM_ZOOM_DEF[`${kind}.${cat}`] || VM_ZOOM_DEF[kind] || { s: [1, 18], l: [VM_LBL_ZOOM[kind] || 9, 18] };
const vmStyDef = (kind, cat) => ({ ...vmStyBase(kind, cat), ...(VM_VIEW_DEF.style[`${kind}.${cat}`] || {}) });
function vmStyBase(kind, cat) {
  const zd = vmZoomDef(kind, cat);
  if (vmIsArea(kind, cat)) {
    const [c, w, dash, fo] = kind === "own" ? ["#c8a0ff", 2, "", cat === "line" ? 0 : 0.06] : kind === "aero" ? VM_AERO_STYLE[cat] || VM_AS_DEF
      : kind === "fua" ? VM_FUA_STYLE[cat] || VM_AS_DEF : VM_AS_STYLE[cat] || VM_AS_DEF;
    return { c, w, d: VM_DASH_OF[dash] || "solid", o: 0.9, fc: c, fo, lc: c, ls: 10, lz: zd.l[0], lx: zd.l[1], cz: zd.s[0], cx: zd.s[1], fz: zd.s[0], fx: zd.s[1] };   // cz-cx / fz-fx / lz-lx: the line / fill / name from / to these zooms
  }
  const [c, r] = VM_PT_STYLE[kind] || ["#ffffff", 3];
  const major = kind === "airport" && ["intl", "ifr", "large", "medium"].includes(cat);
  const big = major || (kind === "airport" && cat === "military");
  const aero = (VM_AERO_SYM[kind] || {})[cat] || (kind === "navaid" ? "vor" : kind === "obstacle" ? "obst" : kind === "airport" ? "ad_civil" : "");
  const term = kind === "wpt" && cat === "terminal";   // the terminal fixes (many near the aerodromes): later and smaller
  return { fc: c, r: big ? r + 2 : term ? r - 1 : r, sym: aero || (kind === "chan" ? "square" : "circle"), fo: cat === "closed" ? 0.6 : 0.95,
    lc: c, ls: 10, lz: Math.max(1, zd.l[0] - (major ? 1 : 0)), lx: zd.l[1], sz: zd.s[0], sx: zd.s[1] };   // sz-sx: the symbol from / to these zooms
}
// what is shown at first, until something is stored (the parts on / off, the names and the looks set up on the author's
// station); under VM_OFF / VM_LBL_DEF / the looks above, and what ↺ brings back
const VM_VIEW_DEF = {
  cats: {
    aero: true, "aero.aerodrome": true, airport: true, "airport.civil": false, "airport.closed": false,
    "airport.glider": false, "airport.heli": true, "airport.intl": true, "airport.large": true, "airport.small": false,
    "airport.ul": false, airspace: true, "airspace.ATZ": false, "airspace.CTA": true, "airspace.CTR": true,
    "airspace.D": false, "airspace.FIR": true, "airspace.FIS": true, "airspace.GLIDING": false,
    "airspace.LOWFLY": true, "airspace.MCTR": true, "airspace.MTA": false, "airspace.OTHER": true, "airspace.P": false,
    "airspace.R": false, "airspace.SPORT": false, "airspace.TMA": true, "airspace.TRA": false, "airspace.TSA": false,
    chan: false, "fua.active": true, navaid: true, "navaid.DME": false, "navaid.NDB": false, "navaid.TACAN": false,
    "navaid.VOR-DME": true, "navaid.VORTAC": false, obstacle: false, "obstacle.building": false,
    "obstacle.chimney": false, "obstacle.obstacle": false, "obstacle.tower": false, "obstacle.wind": false,
    point: true, "point.RP": true, "point.RP_OPT": true, tx: false, "tx.bcast": false, "tx.comm": false,
    "tx.ham": false, "tx.mobile": false, "tx.radar": false, wpt: true, "wpt.terminal": false
  },
  lbl: { airport: true, airspace: false, point: true },
  style: {
    "aero.aerodrome": { lz: 9, cz: 9, fz: 9 }, "aero.apron": { lz: 9, cz: 9, fz: 9 },
    "aero.helipad": { lz: 9, cz: 9, fz: 9 }, "aero.runway": { lz: 9, cz: 9, fz: 9 },
    "aero.taxiway": { lz: 9, cz: 9, fz: 9 }, "airport.agri": { lz: 1, lx: 8, sx: 8 },
    "airport.airport": { lz: 1, lx: 8, sx: 8 }, "airport.altiport": { lz: 1, lx: 8, sx: 8 },
    "airport.balloon": { lz: 1, lx: 8, sx: 8 }, "airport.civil": { ls: 8, r: 3, lz: 1, lx: 8, sx: 8 },
    "airport.closed": { lz: 1, lx: 8, sx: 8 }, "airport.glider": { lz: 1, lx: 8, sx: 8 },
    "airport.heli": { lz: 1, lx: 8, sx: 8 }, "airport.heli_mil": { r: 3, lz: 1, lx: 8, sx: 8 },
    "airport.ifr": { lz: 1, lx: 8, sx: 8 }, "airport.intl": { lz: 1, lx: 8, sx: 8 },
    "airport.large": { lz: 1, lx: 8, sx: 8 }, "airport.medium": { lz: 1, lx: 8, sx: 8 },
    "airport.military": { lz: 1, lx: 8, sx: 8 }, "airport.small": { lz: 1, lx: 8, sx: 8 },
    "airport.strip": { lz: 1, lx: 8, sx: 8 }, "airport.ul": { lz: 1, lx: 8, sx: 8 },
    "airport.water": { lz: 1, lx: 8, sx: 8 }, "airspace.ACC": { lz: 13 }, "airspace.ADIZ": { lz: 13 },
    "airspace.ALERT": { lz: 13 }, "airspace.ATZ": { c: "#008000", fc: "#008000", lc: "#008000", lz: 13 },
    "airspace.AWY": { lz: 13 }, "airspace.CTA": { fo: 0, lz: 13 },
    "airspace.CTR": { c: "#0000ff", fc: "#0000ff", lc: "#0000ff", w: 1, lz: 13 }, "airspace.D": { lz: 13 },
    "airspace.FIR": { lz: 13 }, "airspace.FIS": { lz: 13 }, "airspace.GLIDING": { lz: 13 }, "airspace.HTZ": { lz: 13 },
    "airspace.LOWFLY": { lz: 13 }, "airspace.LTA": { lz: 13 }, "airspace.MATZ": { lz: 13 },
    "airspace.MCTR": { c: "#0000ff", d: "solid", fc: "#0000ff", fo: 0.08, lc: "#0000ff", w: 1, lz: 13 },
    "airspace.MRT": { lz: 13 },
    "airspace.MTA": { c: "#008000", d: "dashdot", fc: "#008000", lc: "#008000", w: 1.5, lz: 13 },
    "airspace.MTR": { lz: 13 }, "airspace.OTHER": { lz: 13 }, "airspace.P": { lz: 13 },
    "airspace.PROTECTED": { lz: 13 }, "airspace.R": { lz: 13 }, "airspace.RMZ": { lz: 13 },
    "airspace.SPORT": { lz: 13 }, "airspace.TFR": { lz: 13 }, "airspace.TIA": { lz: 13 }, "airspace.TIZ": { lz: 13 },
    "airspace.TMA": { c: "#008000", d: "dashdot", fc: "#008000", fo: 0.05, lc: "#008000", lz: 13 },
    "airspace.TMZ": { lz: 13 }, "airspace.TRA": { lz: 13 }, "airspace.TRP": { lz: 13 }, "airspace.TSA": { lz: 13 },
    "airspace.UIR": { lz: 13 }, "airspace.UTA": { lz: 13 }, "airspace.VFR": { lz: 13 }, "airspace.WARNING": { lz: 13 },
    "chan.nogroup": { lx: 15, lz: 5, sx: 12, sz: 8 }, "fua.active": { cz: 5, fo: 0.05, fz: 5, o: 0.4, lz: 9 },
    "fua.planned": { cz: 5, fz: 5, lz: 9 }, "navaid.DME": { sz: 7 }, "navaid.DVOR": { sz: 7 },
    "navaid.DVOR-DME": { sz: 7 }, "navaid.DVORTAC": { sz: 7 }, "navaid.NDB": { sz: 7 }, "navaid.NDB-DME": { sz: 7 },
    "navaid.TACAN": { sz: 7 }, "navaid.VOR": { sz: 7 }, "navaid.VOR-DME": { sz: 7 }, "navaid.VORTAC": { sz: 7 },
    "point.RP": { sz: 11 }, "point.RP_OPT": { sz: 11 }, "tx.bcast": { sz: 8 }, "tx.comm": { sz: 8 },
    "tx.ham": { sz: 8 }, "tx.mobile": { sz: 8 }, "tx.radar": { sz: 8 }, "wpt.enroute": { sz: 8 },
    "wpt.terminal": { sz: 8 }
  },
};
const vmSty = (kind, cat) => ({ ...vmStyDef(kind, cat), ...(((vmOpt().style || {})[`${kind}.${cat}`]) || {}) });
/** The Leaflet style of an object; z: the zoom of the map (the line and the fill of an area each from their own zoom on). */
function vmStyle(p, z = 99) {
  const y = vmSty(p.kind, p.cat);
  if (vmIsArea(p.kind, p.cat)) return { color: y.c, weight: y.w, dashArray: VM_DASH[y.d] || null, opacity: z >= (y.cz || 1) && z <= (y.cx || 18) ? y.o : 0,
    fillColor: y.fc, fillOpacity: z >= (y.fz || 1) && z <= (y.fx || 18) ? y.fo : 0 };
  return { color: "#000", weight: 1, opacity: 0.8, fillColor: y.fc, fillOpacity: y.fo, radius: y.r, sym: y.sym, sz: y.sz || 1, sx: y.sx || 18 };
}
/** Which line / fill zooms of the styles the zoom z has reached (the areas are styled again when it changes). */
const vmZoomSig = (z) => Object.values(vmOpt().style || {}).map((y) => `${z >= (y.cz || 1) && z <= (y.cx || 18) ? 1 : 0}${z >= (y.fz || 1) && z <= (y.fx || 18) ? 1 : 0}`).join("");
const vmKindName = (k) => (VM_KINDS.find((x) => x[0] === k) || [k, k])[1];
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
function vmBasicPath(ctx, sym, x, y, r) {   // circle, square, diamond, triangle, cross
  if (sym === "square") ctx.rect(x - r, y - r, 2 * r, 2 * r);
  else if (sym === "diamond") { ctx.moveTo(x, y - r * 1.3); ctx.lineTo(x + r * 1.3, y); ctx.lineTo(x, y + r * 1.3); ctx.lineTo(x - r * 1.3, y); ctx.closePath(); }
  else if (sym === "triangle") { ctx.moveTo(x, y - r * 1.3); ctx.lineTo(x + r * 1.15, y + r * 0.8); ctx.lineTo(x - r * 1.15, y + r * 0.8); ctx.closePath(); }
  else if (sym === "cross") { const t = Math.max(1, r / 2.5); ctx.rect(x - r, y - t, 2 * r, 2 * t); ctx.rect(x - t, y - r, 2 * t, 2 * r); }
  else ctx.arc(x, y, r, 0, 2 * Math.PI);
}
// a symbol as a small picture (the tree and the style editor): drawn as on the map, cached
const vmIcons = new Map();
function vmSymIcon(sym, color, size = 20) {
  const id = `${sym}|${color}|${size}`;
  if (vmIcons.has(id)) return vmIcons.get(id);
  let url = "";
  try {
    const k = 2, cv = document.createElement("canvas");
    cv.width = cv.height = size * k;
    const ctx = cv.getContext("2d");
    ctx.scale(k, k);
    const x = size / 2, y = size / 2, r = size / 4.2;
    if (VM_AERO_DRAW[sym]) vmAeroDraw(ctx, sym, x, y, r, color, 1);
    else { ctx.beginPath(); vmBasicPath(ctx, sym, x, y, r); ctx.fillStyle = color; ctx.fill(); ctx.strokeStyle = "rgba(0,0,0,.8)"; ctx.lineWidth = 1; ctx.stroke(); }
    url = cv.toDataURL();
  } catch { /* no canvas */ }
  vmIcons.set(id, url);
  return url;
}
// a point drawn as a symbol on the canvas (one canvas for thousands of points); made when first needed, since
// Leaflet is loaded after this file
let VmSymCls = null;
const vmSymMarker = (ll, opt) => new (VmSymCls = VmSymCls || L.CircleMarker.extend({
  _updatePath() {
    const rd = this._renderer, sym = this.options.sym || "circle";
    const mz = this._map && this._map.getZoom();
    if (this._map && (mz < (this.options.sz || 1) || mz > (this.options.sx || 18))) return;   // not drawn outside the zooms of its symbol
    if (sym === "circle" || !rd._ctx) { L.CircleMarker.prototype._updatePath.call(this); return; }
    if (!rd._drawing || this._empty()) return;
    const ctx = rd._ctx, { x, y } = this._point, r = Math.max(this._radius, 1);
    if (VM_AERO_DRAW[sym]) { vmAeroDraw(ctx, sym, x, y, r, this.options.fillColor, this.options.fillOpacity); return; }
    ctx.beginPath();
    vmBasicPath(ctx, sym, x, y, r);
    rd._fillStroke(ctx, this);
  },
}))(ll, opt);

// the list of the stored maps and their GeoJSON (asked from the VFO of the page or any VFO, like the own layers)
let vmList = null, vmListP = null, vmListRev = -1, vmViewRev = -1;
let vmNotes = {};   // own names and notes of objects {key: {name, note}} (server: data/vectormaps_notes.json)
const vmNote = (p) => vmNotes[vmKey(p)] || {};
const vmGj = new Map();   // id -> Promise of the GeoJSON
function vmListGet(force) {
  const b = mapOpts.vm || vmOptsNorm(null);
  if (force || b.rev !== vmListRev) { vmList = null; vmListP = null; vmGj.clear(); vmListRev = b.rev; }
  else if (b.viewRev !== vmViewRev) { vmList = null; vmListP = null; }   // only the view: the GeoJSON stays
  vmViewRev = b.viewRev;
  if (vmList) return Promise.resolve(vmList);
  return (vmListP = vmListP || mapLayApi("/api/vectormaps").then((j) => {
    const v = j.view || {};
    vmNotes = j.notes || {};
    if (vmViewBusy) return (vmList = j.maps || []);   // a change of this page not yet stored: it stays (the server would bring back the older view)
    vmView = { cats: v.cats || {}, lbl: v.lbl || {}, maxFL: +v.maxFL || 0, maps: v.maps || {}, hidden: v.hidden || [], style: v.style || {}, srcs: v.srcs || {} };
    if (!v.stored && (j.maps || []).length && VM_VIEW_KEYS.some((k) => { const x = b[k]; return Array.isArray(x) ? x.length : x && typeof x === "object" ? Object.keys(x).length : x; })) {
      vmView = Object.fromEntries(VM_VIEW_KEYS.map((k) => [k, b[k]]));   // once: what this browser had before goes to the server
      vmViewSave();
    }
    return (vmList = j.maps || []);
  }).catch(() => (vmList = [])));
}
let vmViewT = null, vmViewBusy = 0;   // busy: changes of this page on their way to the server
function vmViewSave() {   // to the server (a moment later: several clicks one write), then the other windows ask again
  clearTimeout(vmViewT);
  if (!vmViewT) vmViewBusy++;
  vmViewT = setTimeout(() => {
    vmViewT = null;
    mapLayApi("/api/vectormaps/view", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(vmView) })
      .then(() => { vmViewRev = Date.now(); mapOptsSet({ vm: { ...(mapOpts.vm || vmOptsNorm(null)), viewRev: vmViewRev } }); })
      .catch((err) => { const m = document.querySelector(".vm-msg"); if (m) m.textContent = `Not stored on the server: ${err.message}`; })
      .finally(() => { vmViewBusy = Math.max(0, vmViewBusy - 1); });
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
/** The tooltip / card of an object; src: the name of its map. */
function vmTip(p, src) {
  const nt = vmNote(p);
  const head = `<b>${escHtml(vmName(p) || p.ident || vmCatName(p.cat))}</b>${p.ident && p.name ? ` ${escHtml(p.ident)}` : ""}` +
    (nt.name && p.name && nt.name !== p.name ? ` <span class="muted">(${escHtml(p.name)})</span>` : "");
  const cat = vmCatName(p.cat);
  const rows = [];
  if (p.kind === "airspace") rows.push(`${escHtml(cat)}${p.cls && p.cls !== "SUA" ? ` · class ${escHtml(p.cls)}` : ""}`, `${vmLim(p.lower) || "?"} – ${vmLim(p.upper) || "?"}`);
  else if (p.kind === "fua") rows.push(`<b class="vm-fua-${p.cat === "active" ? "on" : "plan"}">${escHtml(cat)}</b>${[p.type, p.activity, p.mil, p.origin].filter(Boolean).map((x) => ` · ${escHtml(x)}`).join("")}`,
    `${vmLim(p.lower) || "?"} – ${vmLim(p.upper) || "?"}`, vmFuaTime(p), ...(p.place ? [escHtml(p.place)] : []));
  else if (p.kind === "wpt") {
    const role = { E: "entry", X: "exit", I: "intermediate", A: "arrival", D: "departure" };
    rows.push(`IFR waypoint · ${escHtml(cat)}${p.fra ? " · FRA" : ""}${p.fir ? " · FIR boundary" : ""}`);
    if (p.fraRole || p.fraAD) rows.push(`FRA ${[...(p.fraRole || ""), ...(p.fraAD || "")].map((c) => role[c] || c).join(", ")}`);
    if (p.arr) rows.push(`Arrival ${escHtml(p.arr)}`);
    if (p.dep) rows.push(`Departure ${escHtml(p.dep)}`);
    if (p.fl) rows.push(escHtml(p.fl));
    if (p.fraArea) rows.push(`<span class="muted">${escHtml(p.fraArea)}</span>`);
    if (p.valid || p.airac) rows.push(`<span class="muted">${[p.valid ? `Valid from ${escHtml(p.valid)}` : "", p.airac ? `AIRAC ${escHtml(p.airac)}` : ""].filter(Boolean).join(" · ")}</span>`);
  }
  else rows.push(escHtml(cat) + (p.elev != null ? ` · ${p.elev} m` : "") + (p.height != null ? ` · ${p.height} m AGL` : "") + (p.channel ? ` · ch ${escHtml(p.channel)}` : ""));
  if (p.operator) rows.push(escHtml(String(p.operator).slice(0, 80)));
  if (p.rwy && p.rwy.length) rows.push(`RWY ${p.rwy.map(escHtml).join(" ")}`);
  for (const f of (p.freq || []).slice(0, 6)) rows.push(vmFreq(f));
  if (p.remarks) rows.push(`<span class="muted">${escHtml(String(p.remarks).slice(0, 120))}</span>`);
  if (nt.note) rows.push(`<span class="vm-note">${escHtml(nt.note.slice(0, 300)).replace(/\n/g, "<br>")}</span>`);
  if (src) rows.push(`<span class="muted">Source: ${escHtml(src)}</span>`);
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
const vmName = (p) => vmNote(p).name || p.name || (p.kind === "tx" ? p.operator || p.ident || "" : p.kind === "aero" ? p.ident || "" : "");
/** The window of a FUA activation: "21.11. 06:00 – 22.11. 06:00 UTC". */
function vmFuaTime(p) {
  const f = (t) => (t ? `${t.slice(8, 10)}.${t.slice(5, 7)}. ${t.slice(11, 16)}` : "?");
  return `${f(p.start)} – ${f(p.end)} UTC`;
}
function vmLabel(p) {
  const own = vmNote(p).name;
  if (own) return `${escHtml(own)}${p.kind === "airspace" ? `<small>${escHtml(vmLim(p.lower))} – ${escHtml(vmLim(p.upper))}</small>` : ""}`;
  if (p.kind === "fua") return `${escHtml(p.name)}<small>${escHtml(vmLim(p.lower))} – ${escHtml(vmLim(p.upper))}${p.cat === "planned" ? ` · from ${escHtml((p.start || "").slice(11, 16))}Z` : ""}</small>`;
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
  const fetchedOf = new Map(list.map((m) => [m.id, m.fetched]));
  for (const [id, x] of st.layers) if (!want.has(id) || x.sig !== sig || x.fetched !== fetchedOf.get(id)) { map.removeLayer(x.layer); st.layers.delete(id); changed = true; }
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
      if (g.type === "Point") return { p, m: m.name, ll: [g.coordinates[1], g.coordinates[0]], sz: vmSty(p.kind, p.cat).sz || 1, sx: vmSty(p.kind, p.cat).sx || 18 };
      const ring = g.type === "Polygon" ? g.coordinates[0] : g.type === "MultiPolygon" ? g.coordinates[0][0] : null;
      const y = vmSty(p.kind, p.cat);
      return ring ? { p, m: m.name, ring, vz: Math.min(y.cz || 1, y.fz || 1), vx: Math.max(y.cx || 18, y.fx || 18), ...vmRingInfo(ring) } : null;
    }).filter(Boolean);
    const area = (f) => { const g = f.geometry; return g.type === "Polygon" ? vmRingInfo(g.coordinates[0]).area : g.type === "MultiPolygon" ? vmRingInfo(g.coordinates[0][0]).area : 0; };
    feats.sort((a, b) => area(b) - area(a));
    const layer = L.geoJSON({ type: "FeatureCollection", features: feats }, {
      pane: "vmaps", interactive: false,
      style: (f) => ({ ...vmStyle(f.properties || {}, map.getZoom()), renderer: st.renderer, interactive: false }),
      pointToLayer: (f, ll) => vmSymMarker(ll, { ...vmStyle(f.properties || {}), renderer: st.renderer, pane: "vmaps", interactive: false }),
    }).addTo(map);
    st.layers.set(m.id, { sig, layer, objs, fetched: m.fetched });
    changed = true;
  }
  st.zsig = vmZoomSig(map.getZoom());
  if (changed) { st.pts = []; st.polys = []; for (const x of st.layers.values()) for (const ob of x.objs) (ob.ring ? st.polys : st.pts).push(ob); st.polys.sort((a, b) => a.area - b.area); }
  st.labels();
  const attr = [...new Set(list.filter((m) => st.layers.has(m.id)).flatMap((m) => String(m.attribution || "").split(" · ")).filter(Boolean))].join(" | ");   // each source once
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
  map.on("zoomend", () => {   // the taller mark of the zoom bars in its settings window
    const z = Math.round(map.getZoom());
    map.getContainer().querySelectorAll(".vm-zb").forEach((b) => b.querySelectorAll("i").forEach((x, n) => x.classList.toggle("cur", n + 1 === z)));
  });
  // the sources line of the map folded into a small © (a click opens / closes it): the long list covered the map
  if (map.attributionControl && map.attributionControl.getPosition() !== "topright") map.attributionControl.setPosition("topright");   // up under the map buttons: the bars of the COMPOSITE map cover the bottom (a new container)
  const ac = map.attributionControl && map.attributionControl.getContainer();
  if (ac && !ac.classList.contains("vm-attr")) {
    ac.classList.add("vm-attr");
    ac.title = "Map sources";
    L.DomEvent.disableClickPropagation(ac);
    ac.addEventListener("click", (e) => { if (!e.target.closest("a")) ac.classList.toggle("open"); });
  }
  const st = { layers: new Map(), renderer: L.canvas({ pane: "vmaps", padding: 0.3 }), attr: "", pts: [], polys: [] };
  const lblLayer = L.layerGroup().addTo(map);
  const tip = L.tooltip({ className: "ais-label vm-tip", direction: "top", offset: [0, -6], opacity: 1 });
  /** The object under a container point: a point within 7 px first, else the smallest airspace around it. */
  function hit(cp) {
    if (!st.layers.size) return null;
    const ll = map.containerPointToLatLng(cp), tol = 7;
    const d = map.containerPointToLatLng([cp.x + tol, cp.y + tol]), dLat = Math.abs(d.lat - ll.lat), dLon = Math.abs(d.lng - ll.lng);
    let best = null, bd = tol * tol + 1;
    const z = map.getZoom();
    for (const ob of st.pts) {
      if (z < ob.sz || z > ob.sx) continue;   // its symbol is not drawn at this zoom
      if (Math.abs(ob.ll[0] - ll.lat) > dLat || Math.abs(ob.ll[1] - ll.lng) > dLon) continue;
      const q = map.latLngToContainerPoint(ob.ll), dd = (q.x - cp.x) ** 2 + (q.y - cp.y) ** 2;
      if (dd < bd) { bd = dd; best = ob; }
    }
    if (best) return best;
    for (const ob of st.polys) {
      if (z < ob.vz || z > ob.vx) continue;   // neither its line nor its fill is drawn at this zoom
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
      const ob = vmOpt().on && vmInfoOn() ? hit(last.containerPoint) : null;   // the info under the mouse only with Map info on
      if (!ob) { if (shown) { map.closeTooltip(tip); shown = null; } return; }
      if (ob !== shown) { tip.setContent(vmTip(ob.p, ob.m)); shown = ob; }
      tip.setLatLng(ob.ll || last.latlng);
      if (!map.hasLayer(tip)) map.openTooltip(tip);
    });
  });
  map.on("mouseout", () => { if (shown) { map.closeTooltip(tip); shown = null; } });
  /** A right click on an object: its card with its own name and note to fill in and "Hide this object"
   *  (the right click on a track stays its Track menu: the tracks stop it before the map; a left click selects as before). */
  const card = (e, edit = true) => {
    const ob = vmOpt().on ? hit(e.containerPoint) : null;
    if (!ob) return;
    const box = document.createElement("div");
    box.className = "vm-card";
    // the own name and note: kept on the server apart from the map, so an update keeps them
    const nt = vmNote(ob.p);
    box.innerHTML = !edit ? `${vmTip(ob.p, ob.m)}<div class="vm-card-act"><button type="button" class="vm-btn" data-a="hide">Hide this object</button></div>` :
      `${vmTip(ob.p, ob.m)}<div class="vm-note-f"><label>Name <input type="text" data-f="name" maxlength="120" value="${escHtml(nt.name || "")}" placeholder="${escHtml(ob.p.name || ob.p.ident || "")}" title="Empty: the name of the map"></label>` +
      `<label>Note <textarea data-f="note" rows="2" maxlength="2000">${escHtml(nt.note || "")}</textarea></label>` +
      `<div class="vm-card-act"><button type="button" class="vm-btn" data-a="save">Save</button><button type="button" class="vm-btn" data-a="hide">Hide this object</button></div>` +
      `<p class="map-opts-note vm-note-msg"></p></div>`;
    L.DomEvent.disableClickPropagation(box);
    if (edit) box.querySelector('[data-f="name"]').addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); box.querySelector('button[data-a="save"]').click(); } });
    box.addEventListener("click", (ev) => {
      ev.stopPropagation();   // the button is replaced below: Leaflet would no longer see it inside the card and take the click for the map
      const a = ev.target.closest("button[data-a]");
      if (!a) return;
      if (a.dataset.a === "hide") { vmSet({ hidden: [...new Set([...vmOpt().hidden, vmKey(ob.p)])] }); map.closePopup(); }
      else if (a.dataset.a === "save") {
        a.disabled = true;
        mapLayApi("/api/vectormaps/note", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: vmKey(ob.p), name: box.querySelector('[data-f="name"]').value, note: box.querySelector('[data-f="note"]').value }) })
          .then((j) => {   // the names on every map and window again (the other windows ask the server as after a view change)
            vmNotes = j.notes || {};
            vmViewRev = Date.now();
            mapOptsSet({ vm: { ...(mapOpts.vm || vmOptsNorm(null)), viewRev: vmViewRev } });
            map.closePopup();
          })
          .catch((err) => { a.disabled = false; box.querySelector(".vm-note-msg").textContent = `Not saved: ${err.message}`; });
      }
    });
    L.popup({ className: "vm-pop", maxWidth: 320 }).setLatLng(ob.ll || e.latlng).setContent(box).openOn(map);
    if (edit) box.querySelector('[data-f="name"]').focus();
  };
  map.on("contextmenu", (e) => { if (vmEditOn()) card(e); });   // the card only with Map edit on (the Maps bar)
  /** The names of the objects in the view (from a zoom on per kind, at most VM_LBL_MAX). */
  st.labels = () => {
    lblLayer.clearLayers();
    if (!vmOpt().on || !st.layers.size) return;
    const z = map.getZoom(), b = map.getBounds().pad(0.1), out = [];
    const ok = (p) => vmLblOn(p.kind) && z >= vmSty(p.kind, p.cat).lz && z <= (vmSty(p.kind, p.cat).lx || 18);
    for (const ob of st.pts) if (ok(ob.p) && b.contains(ob.ll)) out.push(ob);
    for (const ob of st.polys) if (ok(ob.p) && b.contains(ob.c) && ob.area > 0) out.push(ob);
    const rank = { chan: 0, navaid: 1, airport: 2, tx: 3, aero: 4, fua: 5, airspace: 5, own: 6, point: 7, wpt: 7, obstacle: 8 };
    out.sort((a, c) => (rank[a.p.kind] ?? 8) - (rank[c.p.kind] ?? 8));
    const placed = [];   // boxes of the names already placed: a name that would overlap one is left out
    for (const ob of out) {
      if (placed.length >= VM_LBL_MAX) break;
      const pt = !ob.ring, y = vmSty(ob.p.kind, ob.p.cat), col = y.lc;
      const q = map.latLngToContainerPoint(ob.ll || ob.c), txt = String(vmNote(ob.p).name || (ob.p.ident && !["airspace", "tx", "aero"].includes(ob.p.kind) ? ob.p.ident : vmName(ob.p)));
      if (!txt) continue;   // nothing to write
      const w = Math.max(20, txt.length * 6), hh = ob.p.kind === "airspace" || ob.p.kind === "navaid" ? 24 : 12;
      const dy = pt ? Math.round((y.r || 4) * 1.5) + 1 : 0;   // a point: the name right under its symbol (its half height + 1 px)
      const r = [q.x - w / 2, pt ? q.y + dy : q.y - hh / 2, q.x + w / 2, (pt ? q.y + dy : q.y - hh / 2) + hh];
      if (placed.some((o) => r[0] < o[2] && r[2] > o[0] && r[1] < o[3] && r[3] > o[1])) continue;
      placed.push(r);
      L.marker(ob.ll || ob.c, { pane: "vmlabels", interactive: false, keyboard: false,
        icon: L.divIcon({ className: `vm-lbl${pt ? " pt" : ""}`, html: `<span style="--c:${col};font-size:${y.ls}px${pt ? `;--dy:${dy}px` : ""}">${vmLabel(ob.p)}</span>`, iconSize: null }) }).addTo(lblLayer);
    }
  };
  map.on("moveend zoomend", () => st.labels());
  map.on("zoomend", () => {   // an area whose line or fill starts at another zoom: the areas styled again
    const z = map.getZoom(), sig = vmZoomSig(z);
    if (sig === st.zsig) return;
    st.zsig = sig;
    for (const x of st.layers.values()) x.layer.eachLayer((l) => { const p = l.feature && l.feature.properties; if (p && l.setStyle && vmIsArea(p.kind, p.cat)) l.setStyle(vmStyle(p, z)); });
  });
  return st;
}

/** The Vector maps section of the map settings window. */
// the sources of the vector maps, one tab each (openAIP now; more sources come as more tabs)
const VM_SOURCES = [["openaip", "openAIP"], ["ourairports", "OurAirports"], ["osm", "OpenStreetMap"], ["ifr", "IFR waypoints"], ["fua", "FUA"], ["memories", "MEMORIES"], ["file", "Own files"]];
const VM_SRC_NOTE = {
  openaip: "Airspaces, airports, navaids, reporting points, obstacles per country (CC BY-NC).",
  ourairports: "Airports with frequencies and runways (drawn where both ends are known), navaids, per country (public domain, no key; the whole world is downloaded once a day, about 20 MB).",
  fua: "The airspaces activated today in Slovakia (TRA, TSA, R, D, … from the AUP / UUP of AMC Zvolen and the national areas), from the map of LPS SR (gis.lps.sk/vfrm). Kept up to date every 2 minutes while shown; Active now and Planned (later today) are drawn differently. Information only: check the airspace with the ATS unit before flying.",
  ifr: "IFR waypoints, no key: the free route airspace (FRA) points of the EUROCONTROL list (all of Europe, the AIRAC cycle in force, with their FRA role, levels and aerodromes; the list, about 1.6 MB, is downloaded at most once a day) together with the en-route points and terminal RNAV fixes of the national INSPIRE services of Slovakia (LPS SR), Germany (DFS, CC BY 4.0), Austria (Austro Control) and Finland (Traficom, CC BY 4.0). Not for operational use.",
  osm: "Transmitter sites (broadcasting, mobile phone, radar, amateur and other radio) and the layout of aerodromes (boundary, runways, taxiways, aprons, helipads) per country (ODbL, no key; a big country takes a minute or two).",
};
// the countries openAIP can be downloaded for (ISO 3166 and Kosovo); their names come from the browser
const VM_COUNTRIES = ("AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF " +
  "CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP " +
  "GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT " +
  "LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL " +
  "PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR " +
  "TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS XK YE YT ZA ZM ZW").split(" ");
const VM_SRC_COUNTRIES = { ifr: "AL AM AT AZ BA BE BG CH CY CZ DE DK DZ EE ES FI FR GB GE GI GR HR HU IE IL IS IT LT LU LV MA MC MD MK MT NL NO PL PT RO RS SE SI SK TN TR UA".split(" ") };   // a source for a few countries only (ifr: vectormaps.ifr_countries())
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
  } else if (tab === "fua") {   // one map (Slovakia), downloaded again by the server every 2 minutes while it exists
    const m = list[0], hm = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    h += `<p class="map-opts-note">${VM_SRC_NOTE.fua}</p><p class="map-opts-note vm-msg"></p>` + (m ? `<div class="vm-ctry"><table class="map-opts-t vm-maps"><tr class="vm-have"><th><label title="${n(m.n)} activations">` +
      `${chk(`data-vmmap="${escHtml(m.id)}"`, vmMapOn(m.id))} FUA Slovakia <small class="muted">${n(m.n)}</small></label></th><td class="muted" title="Last downloaded">${hm(m.fetched)}</td>` +
      `<td><button type="button" class="vm-get" data-vmfua title="Download now">↻</button>` +
      `<button type="button" class="map-opts-del" data-vmdel="${escHtml(m.id)}" title="Remove (no more downloads)">✕</button></td></tr></table></div>`
      : `<button type="button" class="vm-btn" data-vmfua>Download the FUA of Slovakia</button>`);
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
      `<p class="map-opts-note">${vmList ? `${list.length} of ${(VM_SRC_COUNTRIES[tab] || VM_COUNTRIES).length} downloaded (on top, highlighted): the download button downloads a country, ↻ updates it, ✕ deletes it.` : "Loading…"}</p>` +
      `<p class="map-opts-note vm-msg"></p><div class="vm-ctry"><table class="map-opts-t vm-maps">` +
      [...new Set([...(VM_SRC_COUNTRIES[tab] || VM_COUNTRIES), ...have.keys()])].map((c) => [c, vmCountryName(c)]).sort((a, b) => (have.has(b[0]) - have.has(a[0])) || a[1].localeCompare(b[1])).map(([c, name]) => {
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
  const cur = vmPanelZoom();   // the zoom of the map now: the taller mark of the zoom bars
  if (Object.keys(cnt).length) h += `<p class="map-opts-note">The bars: from – to which zoom the symbol (or line) and the name are drawn; drag an end. The taller mark: the zoom of the map now.</p>`;
  for (const [k, name, order] of VM_KINDS) {
    const cs = cnt[k];
    if (!cs) continue;
    const cats = [...order.filter((c) => cs[c]), ...Object.keys(cs).filter((c) => !order.includes(c))];
    const tot = Object.values(cs).reduce((a, b) => a + b, 0);
    const sw = (c) => { const y = vmSty(k, c); return `${vmIsArea(k, c) ? `<i class="vm-sw" data-vmswatch="${escHtml(`${k}.${c}`)}" title="Style (click)" style="--c:${y.c}"></i>`
      : `<img class="vm-sw pt" data-vmswatch="${escHtml(`${k}.${c}`)}" title="Style (click)" alt="" src="${vmSymIcon(y.sym, y.fc)}">`}`; };
    h += `<details class="vm-kind" data-vmkind="${k}"${vmKindOpen().includes(k) ? " open" : ""}><summary title="${escHtml(`Sources: ${list.filter((m) => vmShown(m) && m.cats && m.cats[k]).map((m) => m.name || m.id).join(", ")}`)}">${chk(`data-vmcat="${k}"`, vmCatOn(k))} <span class="vm-kn">${name} <small class="muted">${n(tot)}</small></span>${vmZoomKind(k, cnt, cur)}</summary>` +
      `<div class="vm-cats">${cats.map((c) => { const id = escHtml(`${k}.${c}`);   // a part: its objects one by one when opened
        const srcs = list.filter((m) => vmShown(m) && m.cats && m.cats[k] && m.cats[k][c]).map((m) => m.name || m.id);
        return `<details class="vm-cat" data-vmcatd="${id}"${vmCatOpen().includes(`${k}.${c}`) ? " open" : ""}><summary title="${escHtml(`Source${srcs.length > 1 ? "s" : ""}: ${srcs.join(", ")}`)}">${chk(`data-vmcat="${id}"`, vmCatOn(k, c))}${sw(c)} ` +
          `${escHtml(vmCatName(c))} <small class="muted">${cs[c]}</small></summary><div class="vm-objs" data-vmobjs="${id}"><p class="map-opts-note">Loading…</p></div></details>` +
          (vmStyOpen === `${k}.${c}` ? vmStyEditor(k, c) : ""); }).join("")}</div>` +
      `<label>${chk(`data-vmlbl="${k}"`, vmLblOn(k))} Names on the map</label>` +
      (k === "airspace" ? `<label>Only starting below <select data-vm="maxFL">${VM_MAX_FL.map((v) => `<option value="${v}"${v === o.maxFL ? " selected" : ""}>${v ? `FL${v}` : "any altitude"}</option>`).join("")}</select></label>` : "") +
      `</details>`;
  }
  if (Object.keys(cnt).length) h += `<button type="button" class="vm-btn" data-vmzdef="*" title="The default zooms of all kinds (colours and shapes stay)">All default zooms</button>`;
  if (o.hidden.length) h += `<div class="map-opts-sub2">Hidden objects <small>a click on an object on the map hides it</small></div>` +
    `<label>${o.hidden.length} hidden <button type="button" class="vm-btn" data-vmshow="*">Show all</button></label>`;
  return h;
}
// Zoom levels: one row per kind (IFR waypoints per part), from–to zoom of the symbol / outline and of the name, for all its parts
const VM_ZOOM_ROWS = [["airport", "", "Airports"], ["aero", "", "Aerodrome layout"], ["navaid", "", "Navaids"],
  ["wpt", "", "IFR waypoints"], ["point", "", "Reporting points"],
  ["airspace", "", "Airspaces"], ["fua", "", "FUA"], ["obstacle", "", "Obstacles"], ["tx", "", "Transmitters"], ["chan", "", "MEMORIES"], ["own", "", "Own files"]];
function vmZoomCats(kind, cat, cnt) {   // the parts a row sets
  if (cat) return [cat];
  const order = (VM_KINDS.find(([k]) => k === kind) || [])[2] || [];
  return [...new Set([...order, ...Object.keys((cnt && cnt[kind]) || {})])];
}
/** The zoom of the map whose settings window is open (the COMPOSITE map when none). */
function vmPanelZoom() {
  const pn = document.querySelector(".map-opts-panel"), c = pn && pn.closest(".leaflet-container");
  const m = (c && c._vmMap) || (typeof comMap !== "undefined" && comMap) || null;
  return m && m.getZoom ? Math.round(m.getZoom()) : 0;
}
/** A bargraph of the zooms 1-18 like the meters of the display: from-to lit in the colour of the layer, the rest grey,
 *  the zoom the map has now taller; its ends are dragged with the mouse (data: row, which part s / l, from, to). */
function vmZoomBar(i, w, from, to, col, cur) {
  return `<div class="vm-zb" data-vmzb="${i}" data-w="${w}" data-from="${from}" data-to="${to}" style="--c:${col}" title="Drag an end: from ${from} to ${to}">` +
    Array.from({ length: 18 }, (_, n) => `<i class="${n + 1 >= from && n + 1 <= to ? "on" : ""}${n + 1 === cur ? " cur" : ""}"></i>`).join("") + `</div>`;
}
const vmZoomTxt = (a, b) => (a <= 1 && b >= 18 ? "all" : `${a}–${b}`);
/** The zoom bars of a kind in its row of the tree: the symbol / outline over the name, ↺ beside them. */
function vmZoomKind(k, cnt, cur) {
  const i = VM_ZOOM_ROWS.findIndex((r) => r[0] === k && !r[1]);
  if (i < 0) return "";
  const cats = vmZoomCats(k, "", cnt).filter((x) => !cnt[k] || cnt[k][x]);
  const y = vmSty(k, cats[0] || ""), area = vmIsArea(k, cats[0] || "");
  const own = cats.some((x) => ["sz", "sx", "cz", "cx", "fz", "fx", "lz", "lx"].some((q) => q in (((vmOpt().style || {})[`${k}.${x}`]) || {})));
  const s0 = area ? y.cz : y.sz, s1 = area ? y.cx : y.sx;
  return `<span class="vm-kz"><span class="vm-zbw"><b>${area ? "Line" : "Sym"}</b>${vmZoomBar(i, "s", s0, s1, area ? y.c : y.fc, cur)}<span class="vm-zv">${vmZoomTxt(s0, s1)}</span></span>` +
    `<span class="vm-zbw"><b>Name</b>${vmZoomBar(i, "l", y.lz, y.lx, y.lc, cur)}<span class="vm-zv">${vmZoomTxt(y.lz, y.lx)}</span></span></span>` +
    `<button type="button" class="vm-get vm-kzdef" data-vmzdef="${i}"${own ? "" : " disabled"} title="The default zooms of this kind">↺</button>`;
}
document.addEventListener("click", (e) => { if (e.target.closest && e.target.closest(".vm-kz")) e.preventDefault(); }, true);   // the bars in a row of the tree: no open / close
// dragging an end of a zoom bar: the nearer end follows the mouse, stored on release
document.addEventListener("pointerdown", (e) => {
  const bar = e.target.closest && e.target.closest(".vm-zb");
  if (!bar || e.button !== 0) return;
  e.preventDefault();
  const at = (ev) => { const r = bar.getBoundingClientRect(); return Math.min(18, Math.max(1, Math.floor(((ev.clientX - r.left) / r.width) * 18) + 1)); };
  let from = +bar.dataset.from, to = +bar.dataset.to;
  const z0 = at(e), end = z0 < from ? "from" : z0 > to ? "to" : z0 - from <= to - z0 ? "from" : "to";
  const show = (z) => {
    if (end === "from") from = Math.min(z, to); else to = Math.max(z, from);
    bar.querySelectorAll("i").forEach((x, n) => x.classList.toggle("on", n + 1 >= from && n + 1 <= to));
    const v = bar.parentElement.querySelector(".vm-zv");
    if (v) v.textContent = vmZoomTxt(from, to);
  };
  show(z0);
  try { bar.setPointerCapture(e.pointerId); } catch { /* old browser */ }
  const move = (ev) => show(at(ev));
  const up = () => {
    bar.removeEventListener("pointermove", move);
    bar.removeEventListener("pointerup", up);
    bar.removeEventListener("pointercancel", up);
    const w = bar.dataset.w, i = +bar.dataset.vmzb;
    if (from !== +bar.dataset.from) vmZoomSet(i, `${w}0`, from);
    if (to !== +bar.dataset.to) vmZoomSet(i, `${w}1`, to);
    vmRefillAll();
  };
  bar.addEventListener("pointermove", move);
  bar.addEventListener("pointerup", up);
  bar.addEventListener("pointercancel", up);
});
/** ↺ of a row (or All default): the own zooms of its parts removed (the colours and shapes stay). */
function vmZoomDefault(i) {
  const zk = ["sz", "sx", "cz", "cx", "fz", "fx", "lz", "lx"], style = { ...(vmOpt().style || {}) };
  const rows = i === "*" ? VM_ZOOM_ROWS : [VM_ZOOM_ROWS[+i]].filter(Boolean);
  for (const [kind, cat] of rows) for (const c of vmZoomCats(kind, cat)) {
    const key = `${kind}.${c}`;
    if (!style[key]) continue;
    const cur = { ...style[key] };
    for (const k of zk) delete cur[k];
    if (Object.keys(cur).length) style[key] = cur; else delete style[key];
  }
  vmSet({ style });
}
/** A zoom of Zoom levels changed: written into the style of every part of that row (the default left out). */
function vmZoomSet(i, w, v) {
  const [kind, cat] = VM_ZOOM_ROWS[i] || [];
  if (!kind) return;
  const style = { ...(vmOpt().style || {}) };
  for (const c of vmZoomCats(kind, cat)) {
    const keys = w[0] === "l" ? [w === "l0" ? "lz" : "lx"] : vmIsArea(kind, c) ? (w === "s0" ? ["cz", "fz"] : ["cx", "fx"]) : [w === "s0" ? "sz" : "sx"];
    const cur = { ...(style[`${kind}.${c}`] || {}) }, def = vmStyDef(kind, c);
    for (const k of keys) { if (v === def[k]) delete cur[k]; else cur[k] = v; }
    if (Object.keys(cur).length) style[`${kind}.${c}`] = cur; else delete style[`${kind}.${c}`];
  }
  vmSet({ style });
}
let vmStyOpen = "";
/** The copied style ({name, st}) or null. */
function vmStyClip() { try { const v = JSON.parse(localStorage.getItem("vmStyClip") || "null"); return v && v.st ? v : null; } catch { return null; } }   // the part whose style editor is open (one at a time)
/** The style editor of a part, under its row in the tree. */
function vmStyEditor(kind, cat) {
  const y = vmSty(kind, cat), key = escHtml(`${kind}.${cat}`), pc = (v) => `${Math.round(v * 100)} %`;
  const sel = (k, list, name) => `<select data-vmsty="${key}" data-k="${k}">${list.map((v) => `<option value="${v}"${String(v) === String(y[k]) ? " selected" : ""}>${name ? name(v) : v}</option>`).join("")}</select>`;
  const col = (k) => `<input type="color" class="map-opts-cp" data-vmsty="${key}" data-k="${k}" value="${y[k]}">`;
  const own = !!((vmOpt().style || {})[`${kind}.${cat}`]), clip = vmStyClip();
  // a zoom: its list and This zoom under it; from (k) "all" = 1, to (x) "all" = 18
  const zoomSel = (k, first) => sel(k, [...new Set([first, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, y[k] || first])].sort((a, b) => a - b),
    (v) => (v <= 1 ? "all" : String(v)));
  const toSel = (k) => sel(k, [...new Set([3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, y[k] || 18])].sort((a, b) => a - b),
    (v) => (v >= 18 ? "all" : String(v)));
  const thisZoom = (k, to) => `<button type="button" class="vm-btn" data-vmthiszoom="${key}" data-k="${k}" title="${to ? "Up to" : "From"} the zoom the map has now">This zoom</button>`;
  const zf = (k, first) => `<div class="vm-sty-wd">${zoomSel(k, first)}${thisZoom(k)}</div>`, zt = (k) => `<div class="vm-sty-wd">${toSel(k)}${thisZoom(k, true)}</div>`;
  const cp = (k, ok) => `<div class="vm-sty-cp">${col(k)}${ok || ""}</div>`;   // a colour with its opacity under it
  // one table: name | colour (opacity under it) | size | from zoom | to zoom (each with This zoom under it)
  const rows = vmIsArea(kind, cat) ? [
    ["Line", cp("c", sel("o", [0.2, 0.4, 0.6, 0.8, 0.9, 1], pc)), `<div class="vm-sty-wd">${sel("w", [0.5, 1, 1.5, 2, 3, 4, 5], (v) => `${v} px`)}${sel("d", Object.keys(VM_DASH))}</div>`,
    ],
    ["Fill", cp("fc", sel("fo", [0, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5], pc)), ""],
  ] : [
    ["Symbol", cp("fc", sel("fo", [0.3, 0.5, 0.7, 0.95, 1], pc)), sel("r", [2, 3, 4, 5, 6, 7, 8, 10], (v) => `${v} px`)],
  ];
  rows.push(["Name", cp("lc"), sel("ls", [8, 9, 10, 11, 12, 14, 16], (v) => `${v} px`)]);   // the zooms: in Zoom levels
  const grid = vmIsArea(kind, cat) ? "" : `<tr><th>Shape</th><td colspan="2"><div class="vm-syms">${VM_SYMS.map(([v, name]) => `<label class="vm-symopt${v === y.sym ? " on" : ""}" title="${escHtml(name)}">` +
    `<input type="radio" name="vmsym-${key}" data-vmsty="${key}" data-k="sym" value="${v}"${v === y.sym ? " checked" : ""}><img alt="${escHtml(name)}" src="${vmSymIcon(v, y.fc, 22)}"></label>`).join("")}</div></td></tr>`;
  const head = `<tr class="vm-sty-h"><th></th><td>Colour</td><td>Size</td></tr>`;
  return `<div class="vm-sty"><button type="button" class="vm-sty-x" data-vmstyclose title="Close">✕</button><table class="vm-sty-t">${head}` +
    rows.map((r) => `<tr><th>${r[0]}</th>${r.slice(1).map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") + grid +
    `<tr><th></th><td colspan="2"><div class="vm-sty-act"><button type="button" class="vm-btn" data-vmstydef="${key}"${own ? "" : " disabled"}>Default</button>` +
    `<button type="button" class="vm-btn" data-vmstycopy="${key}" title="Remember this style to paste it to other parts">Copy</button>` +
    `<button type="button" class="vm-btn" data-vmstypaste="${key}"${clip ? "" : " disabled"} title="${clip ? `The style copied from ${escHtml(clip.name)}` : "Copy a style first"}">Paste</button>` +
    `</div></td></tr></table></div>`;
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
  const groups = new Map(), srcOf = new Map();   // name -> rows; object key -> the name of its map
  gjs.forEach((gj, i) => {
    const m = list[i], g = m.country ? `${vmCountryName(m.country)} (${m.country})` : m.name || m.id;
    for (const f of (gj && gj.features) || []) {
      const p = f.properties || {};
      if (p.kind === kind && p.cat === cat) { if (!groups.has(g)) groups.set(g, new Map()); groups.get(g).set(vmKey(p), p); srcOf.set(vmKey(p), m.name || m.id); }   // one object once per group
    }
  });
  const hidden = new Set(vmOpt().hidden), open = vmGrpOpen();
  const tipOf = (p) => [p.name || p.ident || "", vmNote(p).name ? `Own name: ${vmNote(p).name}` : "", vmNote(p).note || "", `Source: ${srcOf.get(vmKey(p)) || "?"}`].filter(Boolean).join("\n");
  const item = (p) => `<label title="${escHtml(tipOf(p))}"><input type="checkbox" data-vmobj="${escHtml(vmKey(p))}"${hidden.has(vmKey(p)) ? "" : " checked"}> ` +
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
  else if (t.dataset.vmz) { vmZoomSet(+t.dataset.vmz, t.dataset.w, +t.value); }   // a zoom of Zoom levels
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
  const mem = e.target.closest("button[data-vmmem]"), fua = e.target.closest("button[data-vmfua]");
  if (fua) {   // the FUA activations downloaded now
    fua.disabled = true;
    mapLayApi("/api/vectormaps/fua", { method: "POST" })
      .then((j) => { vmSet({ rev: Date.now() }); return vmListGet(true).then(() => { vmRefill(panel); if (msg()) msg().textContent = `${(j.map && j.map.n) || 0} activations today.`; }); })
      .catch((err) => { fua.disabled = false; if (msg()) msg().textContent = `Not downloaded: ${err.message}`; });
    return true;
  }
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
  const zd = e.target.closest("button[data-vmzdef]");
  if (zd) { e.preventDefault(); vmZoomDefault(zd.dataset.vmzdef); vmRefill(panel); return true; }
  const tz = e.target.closest("button[data-vmthiszoom]");
  if (tz) {   // the names (lz) or the symbols (sz) of the part from the zoom the map has now
    const box = panel.closest(".leaflet-container"), map = box && box._vmMap;
    if (!map) return true;
    const key = tz.dataset.vmthiszoom, k = ["sz", "cz", "fz", "sx", "cx", "fx", "lx"].includes(tz.dataset.k) ? tz.dataset.k : "lz", [kind, cat] = key.split("."), style = { ...(vmOpt().style || {}) };
    const cur = { ...(style[key] || {}), [k]: Math.round(map.getZoom()) };
    if (cur[k] === vmStyDef(kind, cat)[k]) delete cur[k];
    if (Object.keys(cur).length) style[key] = cur; else delete style[key];
    vmSet({ style });
    vmRefill(panel);
    return true;
  }
  const tb = e.target.closest("button[data-vmtab]");
  if (tb) { try { localStorage.setItem("vmSrcTab", tb.dataset.vmtab); } catch { /* this page only */ } vmRefill(panel); return true; }
  const scp = e.target.closest("button[data-vmstycopy]"), spa = e.target.closest("button[data-vmstypaste]");
  if (scp) {   // Copy: the whole look of the part (also its defaults), kept in this browser
    const [kind, cat] = scp.dataset.vmstycopy.split(".");
    try { localStorage.setItem("vmStyClip", JSON.stringify({ name: `${vmKindName(kind)} › ${vmCatName(cat)}`, st: vmSty(kind, cat) })); } catch { /* this page only */ }
    vmRefill(panel);
    return true;
  }
  if (spa) {   // Paste: to this part; only the keys the part has (an area takes no symbol)
    const clip = vmStyClip();
    if (!clip) return true;
    const key = spa.dataset.vmstypaste, [kind, cat] = key.split("."), def = vmStyDef(kind, cat), cur = {};
    for (const [k, v] of Object.entries(clip.st)) if (k in def && v !== def[k]) cur[k] = v;
    const style = { ...(vmOpt().style || {}) };
    if (Object.keys(cur).length) style[key] = cur; else delete style[key];
    vmSet({ style });
    vmRefill(panel);
    return true;
  }
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

// FUA: while its map is shown, the list is asked every minute (the server downloads the activations every 2 minutes);
// a newer FUA map is loaded again and drawn on all maps of this page
setInterval(() => {
  if (!vmList || !vmOpt().on || document.hidden) return;
  const old = vmList.find((m) => m.source === "fua");
  if (!old || !vmShown(old)) return;
  mapLayApi("/api/vectormaps").then((j) => {
    const now = (j.maps || []).find((m) => m.id === old.id);
    if (!now || now.fetched === old.fetched || !vmList) return;
    vmList = vmList.map((m) => (m.id === old.id ? now : m));
    vmGj.delete(old.id);
    mapOptsSet({});   // the maps draw again (vmApply replaces the FUA layer)
  }).catch(() => { /* the server is away: the next minute */ });
}, 60000);

// Map info (the key on the Maps bar, mapmemo.js): the info of a point / area under the mouse; off at first, per browser
let vmInfo = null;
function vmInfoOn() {
  if (vmInfo === null) { try { vmInfo = localStorage.getItem("vmMapInfo") === "1"; } catch { vmInfo = false; } }
  return vmInfo;
}
function vmInfoSet(on) {
  vmInfo = !!on;
  try { localStorage.setItem("vmMapInfo", vmInfo ? "1" : "0"); } catch { /* this page only */ }
}
// Map edit (the key on the Maps bar): the right click card of a point / area (own name, note, hide); off at first, per browser
let vmEdit = null;
function vmEditOn() {
  if (vmEdit === null) { try { vmEdit = localStorage.getItem("vmMapEdit") === "1"; } catch { vmEdit = false; } }
  return vmEdit;
}
function vmEditSet(on) {
  vmEdit = !!on;
  try { localStorage.setItem("vmMapEdit", vmEdit ? "1" : "0"); } catch { /* this page only */ }
}
window.addEventListener("storage", (e) => {
  if (e.key === "vmMapInfo") vmInfo = e.newValue === "1";
  else if (e.key === "vmMapEdit") vmEdit = e.newValue === "1";
});
