// ---------- AD (under the clock): satellite tracking of the active VFO ----------
// While the Doppler correction tunes this VFO (st.trsp_sat), the AD shows a small polar plot of the pass (north up, the
// satellite now as a yellow dot, the antenna as a red cross) and beside it the satellite, the frequency received now and
// the state of the rotor tracking (as on the TRACK page).
// Loaded after app.js and uses its globals ($, st, satFetch, satShort, satPolarXY, adRotInfo, rotorBase, renderAd, escHtml).

var satAd = { dop: null, rot: null, pass: null, passFor: null, passAt: 0, busy: false };

/** renderAd: the satellite comes after the error messages and before the rotor. */
function satAdOn() {
  return !!(st && st.trsp_sat && satAd.dop && satAd.dop.on);
}

/** The pass of the tracked satellite that is on now (or the next one): its samples for the track. */
async function satAdPass(norad) {
  const now = Date.now() / 1000, p = satAd.pass;
  if (satAd.passFor === norad && p && p.samples[p.samples.length - 1].t > now) return;
  if (satAd.passFor === norad && Date.now() - satAd.passAt < 300000) return;   // none found: try again after 5 min
  satAd.passFor = norad;
  satAd.passAt = Date.now();
  satAd.pass = null;
  const all = await satFetch("/api/sat/passes?hours=24");
  const next = all.passes.find((x) => x.norad === norad && x.los > now);
  if (next) satAd.pass = await satFetch(`/api/sat/pass?norad=${norad}&aos=${next.aos}&los=${next.los}`);
}

async function satAdPoll() {
  if (satAd.busy) return;
  const want = !!(st && st.trsp_sat);
  if (!want) {
    if (satAd.dop) { satAd.dop = null; renderAd(); }
    return;
  }
  satAd.busy = true;
  try {
    satAd.dop = await satFetch("/api/sat/doppler");
    satAd.rot = await satFetch("/api/sat/rotor", undefined, rotorBase()).catch(() => null);
    if (satAd.dop.on) await satAdPass(satAd.dop.norad).catch(() => {});
  } catch { satAd.dop = null; }
  satAd.busy = false;
  renderAd();
}
setInterval(() => { if (!document.hidden) satAdPoll(); }, 1000);

function satAdRender() {
  const d = satAd.dop, p = satAd.pass, R = 100;
  const xy = (az, el) => satPolarXY(((az % 360) + 360) % 360, el, R).map((v) => v.toFixed(1));
  let track = "";
  if (p && p.norad === d.norad) {
    const s = p.samples, [ax, ay] = xy(s[0].az, s[0].el), [lx, ly] = xy(s[s.length - 1].az, s[s.length - 1].el);
    track = `<polyline class="pg-track" points="${s.map((q) => xy(q.az, q.el).join(",")).join(" ")}"/>`
      + `<circle class="pg-end" cx="${ax}" cy="${ay}" r="9"/><circle class="pg-end" cx="${lx}" cy="${ly}" r="9"/>`;
  }
  let now = "";
  if (d.az != null && d.el != null && d.el >= 0) {
    const [x, y] = xy(d.az, d.el);
    now = `<circle class="pg-now" cx="${x}" cy="${y}" r="12"/>`;
  }
  let rot = "";
  const r = typeof adRotInfo !== "undefined" ? adRotInfo : null;
  if (r && r.on && r.connected && r.azShow != null && r.elShow != null) {
    const back = r.elShow > 90, [x, y] = xy(back ? r.azShow + 180 : r.azShow, back ? 180 - r.elShow : r.elShow);
    rot = `<g class="pg-rot" transform="translate(${x},${y})"><line x1="-13" y1="-13" x2="13" y2="13"/><line x1="-13" y1="13" x2="13" y2="-13"/></g>`;
  }
  const svg = `<svg class="ad-sat-polar" viewBox="-108 -108 216 216" aria-hidden="true">`
    + `<circle class="pg-ring" r="${R}"/><circle class="pg-ring" r="${(R * 2) / 3}"/><circle class="pg-ring" r="${R / 3}"/>`
    + `<line class="pg-ring" x1="${-R}" x2="${R}"/><line class="pg-ring" y1="${-R}" y2="${R}"/>${track}${rot}${now}</svg>`;
  const f = d.f_rx != null ? d.f_rx : d.last_set, r2 = satAd.rot;
  // the rotor tracking, as the flag on the TRACK page: follows this satellite / only calculates / off
  const mine = !!(r2 && r2.on && r2.norad === d.norad);
  const [flag, cls, tip] = mine && r2.linked !== false && r2.rotor_on && r2.control ? ["TRACKING", "", "The rotor follows this satellite"]
    : mine ? ["CALC ONLY", "warn", "TRACK only calculates: the rotor link is off, disconnected or the rotor was stopped"]
    : ["NOT TRACKING", "dim", r2 && r2.on ? "The rotor follows another satellite" : "Rotor tracking (TRACK) is off"];
  const box = $("adSat");
  box.title = `${d.name}${d.label ? ` · ${d.label}` : ""} · Doppler correction on this VFO`;
  box.innerHTML = svg + `<div class="ad-sat-txt"><div class="ad-sat-name">${escHtml(satShort(d.name))}</div>`
    + `<div class="ad-sat-f">${f != null ? (f / 1e6).toFixed(6) : "–"}<small>MHz</small></div>`
    + `<div><span class="flag ad-sat-flag ${cls}" title="${tip}">${flag}</span></div>${satAdCount(p)}</div>`;
}

/** "AOS in 12:05" before the pass, "LOS in 3:12" during it (satCountdown of app.js), "" without a pass. */
function satAdCount(p) {
  if (!p) return "";
  const s = p.samples, now = Date.now() / 1000, aos = s[0].t, los = s[s.length - 1].t;
  if (now > los) return "";
  const on = now >= aos;
  return `<div class="ad-sat-count${on ? " live" : ""}">${on ? "LOS" : "AOS"} in <b>${satCountdown(on ? los : aos)}</b></div>`;
}
