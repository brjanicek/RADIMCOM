// ---------- PROPAGATION › AURORA: the aurora map of NOAA SWPC (OVATION, northern hemisphere) as NOAA draws it, through
// our server (spacewx.aurora_image, cached in data/spacewx), and from the OVATION grid (spacewx.py, feed "aur") the
// nearest part of the oval with its distance and beam heading (aurora scatter on 6 m / 2 m: beam towards the oval).
Object.assign(SDG_ICO, {
  aur: '<path d="M1.5 12.5c2-6 4-8 6.5-8s4.5 2 6.5 8"/><path d="M4 12.5c1.2-3.5 2.5-5 4-5s2.8 1.5 4 5" opacity=".6"/>',
});
const AUR_IMG_MS = 10 * 60e3;   // the map is asked for again after this (the server downloads it as often)

function aurBearing(la1, lo1, la2, lo2) {
  const r = Math.PI / 180, y = Math.sin((lo2 - lo1) * r) * Math.cos(la2 * r);
  const x = Math.cos(la1 * r) * Math.sin(la2 * r) - Math.sin(la1 * r) * Math.cos(la2 * r) * Math.cos((lo2 - lo1) * r);
  return (Math.atan2(y, x) / r + 360) % 360;
}

function propAuroraRender(d) {
  const el = $("propAur");
  if (!el) return;
  const a = d.aur, q = d.qth, n = a?.near, has = q && q.lat != null && !(q.lat === 0 && q.lon === 0);
  const az = n && has ? Math.round(aurBearing(q.lat, q.lon, n.lat, n.lon)) : null;
  const lvl = !a ? "off" : n && n.km <= 1000 ? "lit bad" : n && n.km <= 1600 ? "lit warn" : "lit";
  const head = !a ? "–" : !has ? `max ${a.max ?? 0} %` : n ? `oval ${n.km} km · az ${az}°` : "no oval (≥ 10 %)";
  const src = `/api/spacewx/aurora.jpg?t=${Math.floor(Date.now() / AUR_IMG_MS)}`;
  const old = el.querySelector(".aur-map img");      // kept, so the map does not blink on each refresh
  el.innerHTML = sdgBlk("AURORA · OVATION · NORTH", `<span class="v">${head}</span>` +
    `<span class="prop-sub">${has ? `station ${a?.here ?? 0} % · ` : ""}max ${a?.max ?? "–"} %${a?.fc ? ` · for ${a.fc.slice(11, 16)} UTC` : ""}</span>` +
    `<div class="aur-map"></div>`, `${lvl} k-aur`,
    "Aurora forecast of NOAA SWPC (OVATION model, about 30–90 min ahead), northern hemisphere, the map as NOAA draws it. " +
    "oval = the nearest place with 10 %+ probability of aurora and its heading from the station: aurora scatter (Au) on 6 m / 2 m " +
    "works with the antenna towards it, usually when the oval is under about 1000–1500 km away. Red block = up to 1000 km, amber = up to 1600 km.");
  const img = old || Object.assign(document.createElement("img"), { alt: "NOAA aurora forecast, northern hemisphere" });
  if (img.getAttribute("src") !== src) img.src = src;
  img.onerror = () => { img.hidden = true; };
  img.onload = () => { img.hidden = false; };
  img.onclick = () => window.open(img.src, "_blank", "noopener");   // full size in a new window
  el.querySelector(".aur-map").append(img);
}
