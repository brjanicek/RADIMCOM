// ---------- DECODE › ATC (atc.py): speech to text of the airband voice; the aircraft whose callsign is heard is
// selected on the COMPOSITE map. The key blinks while a transmission is transcribed (loading the model: slowly). ----------
// Loaded after app.js and uses its globals ($, st, vbase, escHtml, renderAd). app.js calls atcStatus from each state
// of the VFO, atcText from the "atc" event (one transcribed transmission) and atcAdOn / atcAdRender from renderAd
// (nothing in the AD now). The transcripts: GET /api/atc (history).

var atcLast = null;                // the last transmission of the active VFO: {t, hz, text, calls}

/** Airband AM: the only place where the key is shown. */
function atcHere(s) {
  return !!s && s.mode === "AM" && s.tune_hz >= 117975000 && s.tune_hz <= 137000000 && !s.dab;
}

function atcStatus(s) {
  const k = $("atcKey"), here = atcHere(s);
  k.hidden = false;
  // only in AM on the airband; elsewhere shown, but inactive (greyed, not disabled: a disabled key shows no tooltip)
  k.classList.toggle("atc-off", !here);
  k.setAttribute("aria-disabled", here ? "false" : "true");
  k.classList.toggle("on", here && !!s.atc);
  k.classList.toggle("atc-load", !!s.atc && s.atc_state === "loading");
  k.classList.toggle("atc-err", !!s.atc && s.atc_state === "error");
  k.classList.toggle("atc-busy", here && !!s.atc && s.atc_state === "busy");   // transcribing: blinks
  // the tooltip: its own text kept apart (tooltip.js takes title off while the mouse is over), written only on a change
  if (k.dataset.tip0 == null) k.dataset.tip0 = k.getAttribute("title") || "";
  const tip = k.dataset.tip0 + (s.atc && s.atc_state === "error" ? `\n\nNow: ${s.atc_error || "error"}` : "");
  if (k._tip !== tip) { k._tip = tip; k.title = tip; }
}

$("atcKey").addEventListener("click", async () => {
  if (!st || !atcHere(st)) return;
  const on = !st.atc;
  st.atc = on;
  $("atcKey").classList.toggle("on", on);
  if (!on) atcLast = null;
  try {
    await fetch(vbase + "/api/atc", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on }) });
  } catch { /* the state from the server corrects the key */ }
});

// ----- COMPOSITE: the aircraft of the callsign heard is selected (red, its details on the right) -----

/** "RYR028KK" / "RYR 28KK" -> "RYR28KK" (leading zeros of the number dropped, as they are not spoken). */
function atcNorm(f) {
  const s = String(f || "").toUpperCase().replace(/\s+/g, "");
  const m = /^([A-Z]{3})0*([0-9A-Z]+)$/.exec(s);
  return m ? m[1] + m[2] : s;
}

/** The COMPOSITE object of an ICAO callsign (its flight as ADS-B / FR24 / adsb.fi / VDL2 give it), or null. */
function atcComFind(cs) {
  if (typeof comMerged === "undefined" || !comMerged.length) return null;
  const want = atcNorm(cs);
  return comMerged.find((m) => m.air && [m.air.flight, m.label].some((f) => f && (atcNorm(f) === want ||
    (typeof comFlight === "function" && atcNorm(comFlight(f)) === want)))) || null;
}

/** Selects the aircraft on the COMPOSITE map; the map moves only when it is out of the view (pan = always). */
function atcComSelect(cs, pan) {
  const m = atcComFind(cs);
  if (!m) return false;
  comSel = m.id;
  if (comMap && (pan || !comMap.getBounds().contains([m.lat, m.lon]))) comMap.panTo([m.lat, m.lon]);
  renderComMap();
  return true;
}

/** The ICAO callsigns of the aircraft on the COMPOSITE map (normalised by atcNorm). */
function atcMapCalls() {
  const out = new Set();
  if (typeof comMerged === "undefined") return out;
  for (const m of comMerged) {
    if (!m.air) continue;
    for (const f of [m.air.flight, m.label]) {
      const n = atcNorm(f && typeof comFlight === "function" ? comFlight(f) || f : f);
      if (/^[A-Z]{3}/.test(n)) out.add(n);
    }
  }
  return out;
}

/** Letters and digits the speech recognition mixes up ("zulu zulu" heard as "zero zero"). */
function atcSound(s) {
  return s.replace(/Z/g, "0");
}

/** The letters a in this order in b ("FL" in "FTL"): a designator spelled with a letter swallowed. */
function atcLettersIn(a, b) {
  let i = 0;
  for (const ch of b) if (ch === a[i]) i++;
  return i === a.length;
}

function atcLev(a, b) {
  let p = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const c = [i];
    for (let j = 1; j <= b.length; j++) c.push(Math.min(p[j] + 1, c[j - 1] + 1, p[j - 1] + (a[i - 1] !== b[j - 1])));
    p = c;
  }
  return p[b.length];
}

/** How well the heard flight number h fits the number m of an aircraft on the map (0 = not at all). */
function atcSufScore(h, m) {
  if (!h || !m) return 0;
  if (h === m) return 10;
  if (atcSound(h) === atcSound(m)) return 9;                    // RYR900 heard for RYR9ZZ
  if (h.length < 2) return 0;
  if (m.endsWith(h)) return 4 + Math.min(h.length, 4);          // the start lost: "234" of 1234
  if (m.startsWith(h)) return 3 + Math.min(h.length, 4);       // the end lost: "123" of 1234, "5K" of 5KE
  if (h.length >= 3 && m.length >= 3 && atcLev(atcSound(h), atcSound(m)) === 1) return 6;   // one character wrong
  if (h.length >= 3 && m.includes(h)) return 5;
  return 0;
}

/** How well the heard airline letters p (3 from the telephony or spelled, 2 spelled with one swallowed) fit d. */
function atcPreScore(p, d) {
  if (!p) return 0;
  if (p === d) return 6;
  let same = 0;
  for (let i = 0; i < 3; i++) if (p[i] && p[i] === d[i]) same++;
  return Math.max(2 * same, p.length === 2 && atcLettersIn(p, d) ? 4 : 0);
}

var ATC_MATCH_MIN = 9;             // the score of a partial match to be taken (a whole number alone is 10)

/** The aircraft on the map that fits a heard callsign best, even partly (AC.234 for AB1234: the number is heard
 *  better than the airline, and an aircraft that is there is far more likely than one that is not):
 *  [{cs, score, alt}]: the best one, or the two that fit alike (alt), or [] when none is good enough. */
function atcBestMatch(c) {
  const heard = c.cs ? atcNorm(c.cs) : "";
  const pre = heard ? heard.slice(0, 3) : c.pre || "";
  const suf = heard ? heard.slice(3) : String(c.suf || "").replace(/^0+(?=.)/, "");
  const scores = [];
  for (const n of atcMapCalls()) {
    const s = atcSufScore(suf, n.slice(3));
    if (!s) continue;
    if (suf.length < 2 && n.slice(0, 3) !== pre) continue;      // one digit ("ups three"): the airline must be the same
    scores.push([n, s + atcPreScore(pre, n.slice(0, 3))]);
  }
  scores.sort((a, b) => b[1] - a[1]);
  if (!scores.length || scores[0][1] < ATC_MATCH_MIN) return [];
  // two alike: both (one of them is very likely it); more than two alike: none
  const close = scores.filter((s) => s[1] >= ATC_MATCH_MIN && scores[0][1] - s[1] < 2);
  return close.length <= 2 ? close.map(([cs, score]) => ({ cs, score, alt: close.length > 1 })) : [];
}

/** A callsign not on the map, or a number said alone ("four one seven eight"), joined to the aircraft on the map it
 *  fits best, even partly (atcBestMatch): no "Scandinavian 4178" guessed when Ryanair 4178 is there.
 *  c.heard keeps what was recognised; a number without such an aircraft is dropped. */
function atcResolve(d) {
  const out = [];
  for (const c of d.calls || []) {
    if (c.cs && atcComFind(c.cs)) { out.push(c); continue; }
    const bs = atcBestMatch(c);
    for (const b of bs) out.push({ ...c, heard: c.cs || (c.pre || "") + c.suf, cs: b.cs, exact: false, bynum: true, alt: b.alt });
    if (!bs.length && !c.num && !c.short) out.push(c);   // one digit only ("ups three"): only an aircraft on the map
  }
  d.calls = out;
}

/** One transmission from the server. */
function atcText(d) {
  atcResolve(d);
  // the first callsign found on the map (an exact one first) is selected there
  const calls = [...(d.calls || [])].sort((a, b) => b.exact - a.exact);
  d.onMap = calls.map((c) => c.cs).filter((cs) => atcComFind(cs));
  if (d.onMap.length) atcComSelect(d.onMap[0], false);
  atcLast = d;
  atcFixHeard(d);                  // a navpoint said ("direct ERGOM"): its icon blinks yellow on the map
}

/** The AD shows nothing of ATC (the key blinks while transcribing; the texts: GET /api/atc). */
function atcAdOn() {
  return false;
}
function atcAdRender() { /* nothing in the AD */ }

// ----- Navpoints: a name of a waypoint / reporting point of the vector maps heard in a transmission ("ryanair 123
// direct ERGOM") blinks yellow on the COMPOSITE map; while the aircraft of that transmission is selected, it stays yellow.
// The names around the station are given to Whisper as its prompt (it writes them right more often). -----

var ATC_FIX_KM = 350;              // navpoints this far from the station (or the map centre) are looked for
var ATC_FIX_BLINK_MS = 6000;       // the blinking after it was heard
var ATC_FIX_KEEP_S = 1800;         // a navpoint stays tied to its aircraft this long
var ATC_HINT_KM = 200, ATC_HINT_MAX = 60;   // the names for the prompt: the nearest, within this distance
var atcFixes = [];                 // [{name, ll, t (ms), ids: [aircraft ids of the transmission]}]
var atcFixLay = null;
// words a navpoint name must not be taken for (the phraseology, numbers, the spelling alphabet, units)
var ATC_FIX_STOP = new Set(("radar radio tower approach ground contact climb climbing descend descending maintain level flight " +
  "heading direct proceed cleared cross crossing report squawk runway turn right left hello good morning evening day night " +
  "thank thanks bye roger wilco affirm negative correct confirm request standby information speed knots feet altitude " +
  "decimal point hundred thousand ready continue expect traffic when able inbound outbound via after before until then " +
  "zero one two three four five six seven eight nine niner alfa alpha bravo charlie delta echo foxtrot golf hotel india " +
  "juliett juliet kilo lima mike november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu " +
  "bratislava praha prague wien vienna budapest krakow warsaw ruzyne").split(" "));

/** The navpoints of the vector maps on the COMPOSITE map near the station: [{name, ll, km}], nearest first. */
function atcFixPoints(maxKm) {
  const st = typeof comMap !== "undefined" && comMap && comMap._vm;
  if (!st || !st.pts) return [];
  const mc = comMap.getCenter(), c = typeof mapQthV !== "undefined" && mapQthV ? mapQthV : { lat: mc.lat, lon: mc.lng };
  const out = new Map();
  for (const ob of st.pts) {
    const p = ob.p || {};
    if (p.kind !== "wpt" && p.kind !== "point") continue;
    const name = String(p.name || "").trim().toUpperCase();
    if (!/^[A-Z]{3,6}$/.test(name)) continue;
    const km = mapAzDist(c, { lat: ob.ll[0], lon: ob.ll[1] })[1];
    if (km <= maxKm && (!out.has(name) || km < out.get(name).km)) out.set(name, { name, ll: ob.ll, km });
  }
  return [...out.values()].sort((a, b) => a.km - b.km);
}

/** The navpoints said in a transcript (not inside a callsign): exact, or one letter off for 5+ letters; after
 *  "direct / proceed / to / via / cross" also two off or a cut end ("pepi" of PEPIK). */
function atcFixFind(d) {
  const pts = atcFixPoints(ATC_FIX_KM);
  if (!pts.length || !d.text) return [];
  const taken = (d.calls || []).map((c) => [c.start, c.end]);
  const words = [...d.text.matchAll(/[A-Za-z]+/g)].map((m) => ({ w: m[0].toLowerCase(), s: m.index, e: m.index + m[0].length }))
    .filter((x) => !taken.some(([a, b]) => x.s >= a && x.s < b));
  const found = new Map();
  words.forEach((x, i) => {
    const prev = i ? words[i - 1].w : "", after = ["direct", "proceed", "to", "via", "cross", "crossing", "over", "after"].includes(prev);
    // the word alone, and joined with the next one ("ar nix" = ARNIX)
    for (const cand of [x.w, i + 1 < words.length ? x.w + words[i + 1].w : ""]) {
      if (cand.length < 3 || cand.length > 7 || ATC_FIX_STOP.has(cand)) continue;
      let best = null;
      for (const p of pts) {
        const n = p.name.toLowerCase();
        let d0 = n === cand ? 0 : cand.length >= 5 || n.length >= 5 ? atcLev(cand, n) : 9;
        if (after && cand.length >= 4 && n.startsWith(cand)) d0 = Math.min(d0, 1);
        const lim = n === cand ? 0 : after ? 2 : 1;
        if (d0 <= lim && n.length >= 4 && (!best || d0 < best.d)) best = { p, d: d0 };
      }
      if (best) { found.set(best.p.name, best.p); break; }
    }
  });
  return [...found.values()];
}

var ATC_FIX_AHEAD = 30;            // a navpoint more than this off the track of its aircraft is not shown (not where it flies)
/** Is the navpoint ahead of the aircraft (within ATC_FIX_AHEAD° of its track)? Unknown track: yes. */
function atcFixAhead(m, ll) {
  const a = m && m.air;
  const trk = m && (m.track ?? (typeof comHeading === "function" ? comHeading(m) : null) ?? (a && a.track));
  if (!m || trk == null || (a && a.ground)) return true;
  const brg = mapAzDist({ lat: m.lat, lon: m.lon }, { lat: ll[0], lon: ll[1] })[0];
  return Math.abs(((brg - trk + 540) % 360) - 180) <= ATC_FIX_AHEAD;
}
const atcMapById = (id) => (typeof comMerged !== "undefined" && comMerged.find((y) => y.id === id)) || null;

/** A transmission: its navpoints blink and are tied to its aircraft (the one selected stays yellow); a navpoint
 *  off the track of all its aircraft (more than ATC_FIX_AHEAD°) is not taken. */
function atcFixHeard(d) {
  const fx = atcFixFind(d);
  if (!fx.length) return;
  const all = (d.onMap || []).map((cs) => { const m = atcComFind(cs); return m && m.id; }).filter(Boolean);
  const now = Date.now();
  for (const f of fx) {
    const ids = all.filter((id) => atcFixAhead(atcMapById(id), f.ll));
    if (all.length && !ids.length) continue;   // behind the aircraft: not where it flies
    atcFixes = atcFixes.filter((x) => !(x.name === f.name && x.ids.join() === ids.join()));
    atcFixes.push({ name: f.name, ll: f.ll, t: now, ids });
  }
  d.fixes = fx.map((f) => f.name);
  atcFixDraw();
}

/** The yellow marks: blinking while fresh, steady for the selected aircraft's navpoints. */
function atcFixDraw() {
  if (typeof comMap === "undefined" || !comMap) return;
  if (!atcFixLay) {
    if (!comMap.getPane("atcFix")) comMap.createPane("atcFix").style.zIndex = 590;   // over the vector maps, under the aircraft
    atcFixLay = L.layerGroup().addTo(comMap);
  }
  const now = Date.now(), sel = typeof comSel !== "undefined" ? comSel : null;
  atcFixes = atcFixes.filter((x) => now - x.t < ATC_FIX_KEEP_S * 1000);
  const show = new Map();
  for (const x of atcFixes) {
    // steady only while the selected aircraft flies towards it (more than ATC_FIX_AHEAD° off its track: not shown)
    const blink = now - x.t < ATC_FIX_BLINK_MS, on = !!sel && x.ids.includes(sel) && atcFixAhead(atcMapById(sel), x.ll);
    if (!blink && !on) continue;
    const k = x.name, had = show.get(k);
    show.set(k, { ...x, blink: (had && had.blink) || blink });
  }
  atcRouteDraw(now, sel);
  const sig = [...show.values()].map((x) => `${x.name}${x.blink ? "*" : ""}`).sort().join(",");
  if (sig === atcFixLay._sig) return;
  atcFixLay._sig = sig;
  atcFixLay.clearLayers();
  for (const x of show.values()) {
    L.marker(x.ll, { pane: "atcFix", interactive: false, keyboard: false,
      icon: L.divIcon({ className: `atc-fix${x.blink ? " blink" : ""}`, html: `<i></i><b>${escHtml(x.name)}</b>`, iconSize: [22, 22], iconAnchor: [11, 11] }) }).addTo(atcFixLay);
  }
}
setInterval(atcFixDraw, 500);      // the blinking ends, the selection changes

var atcRouteLay = null;
/** Where the aircraft was told to fly: a red dashed line from the aircraft (where it is now) to the navpoint heard
 *  with it; blinking while fresh, steady while that aircraft is selected. */
function atcRouteDraw(now, sel) {
  if (!atcRouteLay) atcRouteLay = L.layerGroup().addTo(comMap);
  const lines = [];
  for (const x of atcFixes) {
    const blink = now - x.t < ATC_FIX_BLINK_MS;
    for (const id of x.ids) {
      if (!blink && id !== sel) continue;
      const m = atcMapById(id);
      if (m && atcFixAhead(m, x.ll)) lines.push({ a: [m.lat, m.lon], b: x.ll, blink });
    }
  }
  const sig = lines.map((l) => `${l.a[0].toFixed(4)},${l.a[1].toFixed(4)}>${l.b}${l.blink ? "*" : ""}`).join("|");
  if (sig === atcRouteLay._sig) return;
  atcRouteLay._sig = sig;
  atcRouteLay.clearLayers();
  for (const l of lines) {
    L.polyline([l.a, l.b], { pane: "atcFix", color: "#ff3b3b", weight: 2, opacity: 0.9, dashArray: "8 6", interactive: false,
      className: l.blink ? "atc-route blink" : "atc-route" }).addTo(atcRouteLay);
  }
}

/** The names around for Whisper's prompt: sent to the VFO when ATC is on there and the list changed. */
var atcHintSig = "", atcHintTo = "", atcHintAt = 0;
function atcHintSend() {
  if (!st || !st.atc || !atcHere(st)) return;
  const names = atcFixPoints(ATC_HINT_KM).slice(0, ATC_HINT_MAX).map((p) => p.name);
  const sig = names.join(" ");
  // again when the list or the VFO changed, and every 5 min (a restarted server has none)
  if (!names.length || (sig === atcHintSig && vbase === atcHintTo && Date.now() - atcHintAt < 300000)) return;
  atcHintSig = sig;
  atcHintTo = vbase;
  atcHintAt = Date.now();
  fetch(vbase + "/api/atc", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ hints: names }) })
    .catch(() => { atcHintSig = ""; });
}
setInterval(atcHintSend, 10000);   // (the vector maps load with the COMPOSITE map; a new VFO / restart gets them again)

