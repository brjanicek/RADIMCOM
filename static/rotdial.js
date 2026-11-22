// ---------- Rotor dial: one block for RCTRL › SETTINGS, SATELLITES › SUN NOISE and DECODERS › METEORS ----------
// The polar plot (azimuth, elevation 0–90, north up) and the elevation column 0–180 with ACTUAL / REQUESTED, STOP, RESET,
// MONITOR and an optional body drawn on the plots (the Sun, GRAVES). A click in a plot turns the rotor (source manual).
// Loaded after app.js and uses its globals (rotorInfo, rotorPost, satPolarAt, satPolarXY, satDialRefusal, rotorMoving,
// rotorMonOn, rotorMonToggle). app.js calls rotDialDrawAll(info) from renderRotor on every rotor state.
//   rotDialHtml(p, o) -> HTML, all ids start with p;  rotDialWire(p, o) once it is in the page;  rotDialDraw(p, info)
//   o.mark  = {cap, cls, ico, title, at: () => {az, el} | null}   the body on the plots and its own row of numbers
//   o.extra = HTML under the numbers (link chips, warnings);  o.note = the hint under the keys
//   o.say   = (text) where a refused click is told;  o.onStop = also on STOP;  o.stopTitle, o.offText

const ROT_EL = { top: 8, h: 216 };      // the column in the SVG: y of 180°, height of 0–180°
const rotElY = (el) => ROT_EL.top + (1 - Math.min(Math.max(el, 0), 180) / 180) * ROT_EL.h;
const ROT_EL_GRID = (() => {
  let g = "";
  for (let el = 0; el <= 180; el += 15) {
    const y = rotElY(el).toFixed(1), major = el % 30 === 0;
    g += `<line class="${major ? "rot-elgrid major" : "rot-elgrid"}" x1="${major ? 26 : 30}" x2="46" y1="${y}" y2="${y}"/>`;
    if (major) g += `<text class="rot-ellbl" x="22" y="${(+y + 3.5).toFixed(1)}">${el}</text>`;
  }
  return g;
})();
// the bodies drawn on the plots (centred on 0,0, about 18 units)
const ROT_MK_SUN = '<circle r="5.5"/><path d="M0-9v2.2M0 7v2.2M-9 0h2.2M7 0h2.2M-6.4-6.4l1.6 1.6M4.8 4.8l1.6 1.6M-6.4 6.4l1.6-1.6M4.8-4.8l1.6-1.6"/>';
const ROT_MK_RADAR = '<path d="M0-8L7 4H-7z"/><path d="M-3.5 7.5h7"/>';
var rotDials = {};      // p -> o: the dials built so far (a page rebuilt by innerHTML wires its dial again)

function rotDialHtml(p, o = {}) {
  const m = o.mark;
  const cross = '<line x1="-6" y1="-6" x2="6" y2="6"/><line x1="-6" y1="6" x2="6" y2="-6"/>';
  return `<div class="rot-dial rd">
    <div class="rot-plots">
      <svg class="rot-polar" id="${p}Polar" viewBox="-118 -118 236 236" role="img" aria-label="Antenna azimuth and elevation, north up">
        <circle class="pg-ring" r="100"/><circle class="pg-ring" r="66.7"/><circle class="pg-ring" r="33.3"/>
        <line class="pg-ring" x1="-100" x2="100"/><line class="pg-ring" y1="-100" y2="100"/>
        <text class="pg-lbl" y="-106">N</text><text class="pg-lbl" x="108" y="4">E</text><text class="pg-lbl" y="114">S</text><text class="pg-lbl" x="-108" y="4">W</text>
        <text class="pg-el" x="3" y="-56.7">30°</text><text class="pg-el" x="3" y="-23.3">60°</text>
        ${m ? `<g class="rd-mk ${m.cls || ""}" id="${p}PolarMk" visibility="hidden"><title>${m.title}</title>${m.ico}</g>` : ""}
        <g class="pg-tgt" id="${p}PolarTgt" visibility="hidden"><circle r="6"/></g>
        <g class="pg-rot" id="${p}PolarX" visibility="hidden">${cross}</g>
        <g class="pg-aim" id="${p}PolarAim" visibility="hidden">${cross}</g>
        <circle class="pg-hit" id="${p}PolarHit" r="100"/>
      </svg>
      <svg class="rot-elcol" id="${p}ElCol" viewBox="0 0 64 236" role="img" aria-label="Antenna elevation 0 to 180 degrees">
        <rect class="rot-elbar" x="30" y="8" width="16" height="216"/>
        <g>${ROT_EL_GRID}</g>
        ${m ? `<g class="rd-mk ${m.cls || ""}" id="${p}ElMk" visibility="hidden"><title>${m.title}</title><g transform="translate(54,0) scale(.8)">${m.ico}</g></g>` : ""}
        <g class="pg-tgt" id="${p}ElTgt" visibility="hidden"><circle cx="38" r="5"/></g>
        <g class="rot-elnow" id="${p}ElNow" visibility="hidden"><path d="M26 0 L18 -5 L18 5 Z"/><line x1="30" x2="46"/></g>
        <line class="rot-elaim" id="${p}ElAim" x1="30" x2="46" visibility="hidden"/>
        <rect class="pg-hit" id="${p}ElHit" x="18" y="2" width="40" height="228"/>
      </svg>
    </div>
    <div class="rot-side">
      <div class="rot-pos">
        <i class="rot-cap">ACTUAL</i><span>AZ</span><b id="${p}AzNow">–</b><span>EL</span><b id="${p}ElNowT">–</b>
        <i class="rot-cap req">REQUESTED</i><span>AZ</span><b class="req" id="${p}AzReq">–</b><span>EL</span><b class="req" id="${p}ElReq">–</b>
        ${m ? `<i class="rot-cap mk ${m.cls || ""}">${m.cap}</i><span>AZ</span><b class="mk ${m.cls || ""}" id="${p}AzMk">–</b><span>EL</span><b class="mk ${m.cls || ""}" id="${p}ElMkT">–</b>` : ""}
      </div>
      ${o.extra || ""}
      <small id="${p}Target"></small>
      <div class="rot-keys">
        <button id="${p}Stop" class="key" title="${o.stopTitle || "Stop both motors"}">STOP</button>
        <button id="${p}Reset" class="key" title="Clear a fault after checking the rotor">RESET</button>
        <button id="${p}Mon" class="key" title="MONITOR: show the antenna AZ / EL in the additional display (AD) above">MONITOR</button>
      </div>
      <small id="${p}Note">${rotDialNote(o)}</small>
    </div>
  </div>`;
}

function rotDialNote(o) {
  return o.note || `Orange ✕ antenna · green ring requested${o.mark ? ` · ${o.mark.cap.toLowerCase()} now` : ""}. Click a plot to turn the rotor.`;
}

function rotDialWire(p, o = {}) {
  rotDials[p] = o;
  const note = (t) => { $(`${p}Note`).textContent = t; };
  const say = (t) => (o.say ? o.say(t) : rotorShowError(t, true));
  const elAt = (e) => {
    const svg = e.target.ownerSVGElement, q = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse());
    return Math.round(Math.min(Math.max((1 - (q.y - ROT_EL.top) / ROT_EL.h) * 180, 0), 180));
  };
  $(`${p}PolarHit`).addEventListener("pointermove", (e) => {
    const at = satPolarAt(e), x = $(`${p}PolarAim`), refusal = satDialRefusal(rotorInfo);
    if (!at || refusal) { x.setAttribute("visibility", "hidden"); e.target.style.cursor = refusal ? "not-allowed" : ""; note(refusal || rotDialNote(o)); return; }
    const [px, py] = satPolarXY(at[0], at[1], 100);
    x.setAttribute("transform", `translate(${px.toFixed(1)},${py.toFixed(1)})`);
    x.setAttribute("visibility", "visible");
    e.target.style.cursor = "crosshair";
    note(`Click: turn the antenna to AZ ${at[0]}° EL ${at[1]}°.`);
  });
  $(`${p}PolarHit`).addEventListener("pointerleave", () => { $(`${p}PolarAim`).setAttribute("visibility", "hidden"); note(rotDialNote(o)); });
  $(`${p}PolarHit`).addEventListener("click", (e) => {
    const at = satPolarAt(e), refusal = satDialRefusal(rotorInfo);
    if (!at) return;
    if (refusal) { say(refusal); return; }
    rotorPost({ goto: at });
  });
  $(`${p}ElHit`).addEventListener("pointermove", (e) => {
    const el = elAt(e), aim = $(`${p}ElAim`), refusal = satDialRefusal(rotorInfo);
    aim.setAttribute("visibility", refusal ? "hidden" : "visible");
    aim.setAttribute("y1", rotElY(el).toFixed(1)); aim.setAttribute("y2", rotElY(el).toFixed(1));
    e.target.style.cursor = refusal ? "not-allowed" : "crosshair";
    note(refusal || `Click: antenna EL ${el}°${el > 90 ? " (over the top, looking back)" : ""}, the azimuth stays.`);
  });
  $(`${p}ElHit`).addEventListener("pointerleave", () => { $(`${p}ElAim`).setAttribute("visibility", "hidden"); note(rotDialNote(o)); });
  $(`${p}ElHit`).addEventListener("click", (e) => {
    const el = elAt(e), info = rotorInfo, refusal = satDialRefusal(info);
    if (refusal) { say(refusal); return; }
    const az = info.target ? info.target[0] : info.az;     // the azimuth stays
    rotorPost({ goto: [Math.round(az), el] });
  });
  $(`${p}Stop`).addEventListener("click", () => { if (o.onStop) o.onStop(); rotorPost({ stop: true }); });
  $(`${p}Reset`).addEventListener("click", () => rotorPost({ reset: true }));
  $(`${p}Mon`).addEventListener("click", rotorMonToggle);
  rotDialDraw(p, rotorInfo);
}

/** Draws the antenna, the requested direction and the body (if any) on the dial p; info = the last /api/rotor state. */
function rotDialDraw(p, info) {
  const o = rotDials[p];
  if (!o || !document.getElementById(`${p}Polar`)) return;
  const place = (g, az, el) => {
    const back = el > 90, [px, py] = satPolarXY(back ? (az + 180) % 360 : az, back ? 180 - el : el, 100);
    g.setAttribute("transform", `translate(${px.toFixed(1)},${py.toFixed(1)})`);
  };
  const vis = (id, on) => $(id).setAttribute("visibility", on ? "visible" : "hidden");
  const colY = (id, el) => $(id).setAttribute("transform", `translate(0,${rotElY(el).toFixed(1)})`);
  const ok = !!(info && info.connected && info.azShow != null && info.elShow != null);
  vis(`${p}PolarX`, ok); vis(`${p}ElNow`, ok);
  if (ok) { place($(`${p}PolarX`), info.azShow, info.elShow); colY(`${p}ElNow`, info.elShow); }
  const t = ok && rotorMoving(info) && info.target;      // the green ring only while the rotor is on its way
  vis(`${p}PolarTgt`, !!t); vis(`${p}ElTgt`, !!t);
  if (t) { place($(`${p}PolarTgt`), t[0], t[1]); colY(`${p}ElTgt`, t[1]); }
  const deg = (v) => (v != null ? `${Math.round(v)}°` : "–");
  if (o.mark) {
    const m = o.mark.at(), up = !!(m && m.el >= 0);
    vis(`${p}PolarMk`, up); vis(`${p}ElMk`, up);
    if (up) { place($(`${p}PolarMk`), m.az, m.el); colY(`${p}ElMk`, m.el); }
    $(`${p}AzMk`).textContent = m ? deg(m.az) : "–";
    $(`${p}ElMkT`).textContent = m ? deg(m.el) : "–";
  }
  $(`${p}AzNow`).textContent = ok ? deg(info.azShow) : "–";
  $(`${p}ElNowT`).textContent = ok ? deg(info.elShow) : "–";
  $(`${p}AzReq`).textContent = ok && info.target ? deg(info.target[0]) : "–";
  $(`${p}ElReq`).textContent = ok && info.target ? deg(info.target[1]) : "–";
  const tg = $(`${p}Target`);
  tg.textContent = !info ? "Rotor state not known yet" : !info.on ? (o.offText || "The rotor link is off (RCTRL › SETTINGS).")
    : !info.connected ? "Connecting to the rotor controller…"
    : info.fault ? `Fault: ${info.fault}`
    : info.target ? `Moving to AZ ${Math.round(info.target[0])}° EL ${Math.round(info.target[1])}° (${info.source})` : "No target";
  tg.classList.toggle("error", !!(info && info.fault));
  $(`${p}Reset`).classList.toggle("warn", !!(info && info.fault));
  $(`${p}Mon`).classList.toggle("on", rotorMonOn());
  const refusal = satDialRefusal(info);
  $(`${p}Polar`).classList.toggle("locked", !!refusal);
  $(`${p}ElCol`).classList.toggle("locked", !!refusal);
}

function rotDialDrawAll(info) { for (const p of Object.keys(rotDials)) rotDialDraw(p, info); }

// RCTRL › SETTINGS: its dial is built once at the start (the other two are built with their pages)
{
  const o = {
    offText: "Choose the serial port of the rotor controller.",
    stopTitle: "Stop both motors; the rotor no longer follows the satellite tracking (TRACK on the TRACK page moves it again)",
  };
  $("rdBox").innerHTML = rotDialHtml("rd", o);
  rotDialWire("rd", o);
}

// DECODERS › METEORS: its dial with GRAVES (the meteor zone over the middle of the path); the link chip, POINT, RCTRL and
// the message (static in index.html, wired by app.js) move under the numbers
{
  const o = {
    mark: { cap: "GRAVES", cls: "radar", ico: ROT_MK_RADAR, title: "GRAVES: the meteor zone over the middle of the path",
      at: () => (mtData && mtData.path ? mtData.path : null) },
  };
  $("mtDialBox").innerHTML = rotDialHtml("mt", o);
  $("mtTarget").before($("mtRotExtra"));
  rotDialWire("mt", o);
}
