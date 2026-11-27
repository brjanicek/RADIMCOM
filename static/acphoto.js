// ---------- COMPOSITE map: a small photo of the selected aircraft (Planespotters.net) ----------
// Loaded after app.js. comAirPopup (the detail on the right) calls acPhotoHtml(hex, reg): the photo when known, else ""
// and it is asked for once (by the ICAO hex, then by the registration); when it comes, the detail is drawn again.
// Asked from the browser (the API allows it; a server would need a contact URL in its User-Agent). The photo is shown
// as Planespotters.net wants it: linked to its page there, with the photographer's name.
// Remembered in this browser (localStorage "acPhotos": hex -> result, a week; "no photo" a day).

var AC_PHOTO_API = "https://api.planespotters.net/pub/photos/";
var AC_PHOTO_KEEP_MS = 7 * 86400e3, AC_PHOTO_NONE_MS = 86400e3, AC_PHOTO_MAX = 400;
var acPhotos = (() => {        // hex -> {t, p: {src, w, h, link, by} | null}; "busy" while asked
  try {
    const o = JSON.parse(localStorage.getItem("acPhotos") || "{}");
    return new Map(Object.entries(o && typeof o === "object" ? o : {}));
  } catch { return new Map(); }
})();

function acPhotoSave() {
  try {
    const now = Date.now(), list = [...acPhotos.entries()]
      .filter(([, e]) => e && e !== "busy" && now - e.t < (e.p ? AC_PHOTO_KEEP_MS : AC_PHOTO_NONE_MS))
      .sort((a, b) => b[1].t - a[1].t).slice(0, AC_PHOTO_MAX);
    localStorage.setItem("acPhotos", JSON.stringify(Object.fromEntries(list)));
  } catch { /* no storage: this page only */ }
}

/** The first photo of an answer of the API, or null. */
function acPhotoPick(j) {
  const ph = j && Array.isArray(j.photos) && j.photos[0];
  const th = ph && (ph.thumbnail_large || ph.thumbnail);
  if (!th || !/^https:\/\//.test(th.src || "")) return null;
  return { src: th.src, w: (th.size && th.size.width) || 0, h: (th.size && th.size.height) || 0,
           link: /^https:\/\//.test(ph.link || "") ? ph.link : "https://www.planespotters.net/", by: String(ph.photographer || "").slice(0, 80) };
}

async function acPhotoFetch(hex, reg) {
  acPhotos.set(hex, "busy");
  let p = null;
  const ask = async (path) => {
    const r = await fetch(AC_PHOTO_API + path, { headers: { Accept: "application/json" } });
    return r.ok ? acPhotoPick(await r.json()) : null;
  };
  try {
    p = await ask(`hex/${encodeURIComponent(hex)}`);
    if (!p && reg) p = await ask(`reg/${encodeURIComponent(reg)}`);
  } catch { p = null; }      // offline, blocked: "no photo" for a day
  acPhotos.set(hex, { t: Date.now(), p });
  acPhotoSave();
  if (p && typeof comSel !== "undefined" && comSel === `air:${hex}` && typeof renderComSide === "function") renderComSide();
}

/** The photo block for the detail (the width of the block), "" while unknown or when there is none. */
function acPhotoHtml(hex, reg) {
  if (!/^[0-9A-F]{6}$/.test(hex || "")) return "";
  const e = acPhotos.get(hex);
  if (e === "busy") return "";
  if (!e || Date.now() - e.t > (e.p ? AC_PHOTO_KEEP_MS : AC_PHOTO_NONE_MS)) { acPhotoFetch(hex, reg); return ""; }
  if (!e.p) return "";
  const esc = escHtml, p = e.p, by = p.by ? `© ${p.by}` : "Planespotters.net";
  return `<a class="cs-photo" href="${esc(p.link)}" target="_blank" rel="noopener" title="Photo ${esc(by)} · Planespotters.net (click: the photo there)">` +
    `<img src="${esc(p.src)}" alt=""${p.w && p.h ? ` width="${p.w}" height="${p.h}"` : ""} onerror="this.parentElement.hidden=true">` +
    `<span>${esc(by)}</span></a>`;
}
